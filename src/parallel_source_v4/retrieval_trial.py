"""Freeze and measure a local retrieval experiment without graph admission.

The protocol and all results are private artifacts under an authorized data
root. A COMPLETE receipt certifies execution and integrity, not relevance or
the issue's review/ablation acceptance criteria.
"""
from __future__ import annotations

import argparse
import copy
import ctypes
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import subprocess
import sys
import time
from pathlib import Path

from trace_gc.pdf_source_parallel_v4 import digest_value
from .common import REPO, child, data_root, digest, method_hashes, within, write_once
from .fields import parse_bound_json, source_path
from .retrieval import evaluate, local_cross_encoder, normalize_queries
from .specter2_cache import produce, verify_models

VERSION = "retrieval-empirical-protocol-v1"
PACKAGES = ("torch", "transformers", "adapters", "numpy", "tokenizers",
            "safetensors", "sentence-transformers")
JSON_INPUTS = ("fields", "queries", "preparation_manifest", "dense_model_manifest",
               "reranker_manifest")
SHA = re.compile(r"[0-9a-f]{64}\Z")


class Blocked(ValueError):
    """An actionable, redacted failure code; never a private source excerpt."""


def need(condition, code):
    if not condition:
        raise Blocked(code)


def bound_json(path: Path):
    raw = path.read_bytes()
    return parse_bound_json(raw), hashlib.sha256(raw).hexdigest()


def runtime_snapshot():
    distributions = sorted([d.metadata.get("Name", ""), d.version]
                           for d in importlib.metadata.distributions())
    return {"python": platform.python_version(), "implementation": platform.python_implementation(),
            "platform": platform.platform(), "executable_sha256": digest(Path(sys.executable)),
            "base_executable_sha256": digest(Path(getattr(sys, "_base_executable", sys.executable))),
            "packages": {name: importlib.metadata.version(name) for name in PACKAGES},
            "installed_distributions": distributions}


def code_snapshot():
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, check=True,
                          capture_output=True, text=True).stdout.strip()
    return {"git_head": head, "files": method_hashes(REPO)}


def memory_receipt():
    """OS high-water mark, not a sampled or claimed system/process-tree peak."""
    if os.name == "nt":
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
                (name, ctypes.c_size_t) for name in (
                    "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                    "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage",
                    "PagefileUsage", "PeakPagefileUsage")]

        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        need(psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters),
                                       counters.cb), "memory_readback_failed")
        peak = counters.PeakWorkingSetSize
    else:
        import resource
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform != "darwin":
            peak *= 1024
    return {"peak_rss_bytes": int(peak), "scope": "current_process_lifetime_including_model_threads",
            "child_processes_included": False, "system_memory_measured": False}


def configure_cpu(threads):
    need(type(threads) is int and 1 <= threads <= 8, "invalid_cpu_thread_budget")
    for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
        os.environ[name] = str(threads)
    os.environ.update(TOKENIZERS_PARALLELISM="false", HF_HUB_OFFLINE="1",
                      TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1",
                      TORCH_FORCE_WEIGHTS_ONLY_LOAD="1")
    import torch
    torch.set_num_threads(threads)
    torch.set_num_interop_threads(1)
    need(torch.get_num_threads() == threads and torch.get_num_interop_threads() == 1,
         "cpu_thread_budget_not_applied")
    return {"device": "cpu", "torch_threads": threads, "torch_interop_threads": 1,
            "environment_thread_limit": threads, "gpu_used": False}


def permutation(queries):
    """A fixed one-position rotation, chosen before scoring, never best-of-N."""
    need(len(queries) > 1 and len({q["target_id"] for q in queries}) > 1,
         "target_permutation_requires_distinct_labels")
    targets = [q["target_id"] for q in queries]
    changed = [{**q, "target_id": targets[(i + 1) % len(targets)]} for i, q in enumerate(queries)]
    need(changed != queries, "target_permutation_did_not_change_labels")
    return changed


def _reranker_files(root, manifest):
    need(type(manifest) is dict and manifest.get("schema_version") == "local-reranker-model-v1"
         and re.fullmatch(r"[0-9a-f]{40}", manifest.get("model_revision", "")),
         "invalid_reranker_manifest")
    expected = manifest.get("files")
    need(type(expected) is dict and bool(expected), "reranker_file_hashes_required")
    need(root.is_dir() and not root.is_symlink(), "reranker_snapshot_missing_or_linked")
    observed = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    need(observed == set(expected) and not any(p.is_symlink() for p in root.rglob("*")),
         "reranker_snapshot_file_set_changed")
    need(not any(Path(name).suffix.lower() in {".py", ".bin", ".pt", ".pth", ".pkl", ".pickle", ".ckpt"}
                 for name in observed) and "config.json" in observed and
         any(name.endswith(".safetensors") for name in observed) and
         bool({"tokenizer.json", "vocab.txt", "spiece.model"} & observed),
         "reranker_local_safetensors_snapshot_required")
    for relative, sha in expected.items():
        need(type(sha) is str and SHA.fullmatch(sha), "invalid_reranker_file_hash")
        need(digest(child(root, relative)) == sha, "reranker_snapshot_bytes_changed")
    configuration, config_hash = bound_json(child(root, "config.json"))
    need(config_hash == expected["config.json"] and not configuration.get("auto_map") and
         configuration.get("num_labels", len(configuration.get("id2label", {}))) == 1,
         "reranker_no_remote_code_single_logit_required")
    return expected


def _source_readback(root, source_root, rows):
    for row in rows:
        paths = {"source": source_path(root, row, source_root),
                 **{key: child(root, row[key + "_relative"]) for key in ("page", "image", "native")}}
        for key, path in paths.items():
            need(digest(path) == row[key + "_sha256"], "source_artifact_bytes_changed:" + key)
    return {"status": "VERIFIED", "document_count": len(rows), "artifact_count": 4 * len(rows),
            "manifest_rows_sha256": digest_value(rows)}


def inspect_inputs(root, config, *, full_sources):
    """Parse each input from its hashed buffer, then verify its linked artifacts."""
    records, hashes = {}, {}
    for name in JSON_INPUTS:
        records[name], hashes[name] = bound_json(child(root, config[name]))
    fields_record, preparation = records["fields"], records["preparation_manifest"]
    fields = fields_record["fields"]
    rows = preparation["pdfs"]
    raw_queries = records["queries"]
    need(type(raw_queries) is list or (type(raw_queries) is dict and "queries" in raw_queries),
         "explicit_query_identifiers_required")
    queries = normalize_queries(raw_queries)
    need(len(fields) == len(rows) == config["document_count"] and len(queries) == config["query_count"],
         "frozen_document_or_query_count_mismatch")
    ids = [row["sample_id"] for row in rows]
    need(len(set(ids)) == len(ids) and [f["id"] for f in fields] == ids,
         "field_source_identity_or_order_mismatch")
    need(len({q["id"] for q in queries}) == len(queries) and
         all(q["target_id"] in set(ids) for q in queries), "query_identity_or_target_missing")
    code = code_snapshot()
    need(fields_record.get("field_builder_code_sha256") == code["files"],
         "fields_require_final_code_tree_rebuild")
    need(fields_record.get("fields_sha256") == digest_value(fields) and
         fields_record.get("manifest_sha256") == digest_value(preparation) and
         fields_record.get("final_input_readback_count") == len(rows) and
         fields_record.get("final_input_readback") == "all_source_page_image_native_hashes_match" and
         fields_record.get("query_independent") is True, "field_receipt_binding_invalid")
    for row, field in zip(rows, fields):
        need(row.get("physical_page") == field.get("physical_page") == 1 and
             field.get("retrieval_only") is True and field.get("eligible_for_jev") is False and
             all(row[key + "_sha256"] == field.get(key + "_sha256") for key in ("source", "page", "image", "native")),
             "field_source_binding_invalid")
        need(all(type(field.get(key)) is str for key in ("title", "abstract", "body")), "field_text_type_invalid")
    permuted = permutation(queries)
    dense_root = child(root, config["dense_model_root"])
    verify_models(dense_root, records["dense_model_manifest"])
    reranker = _reranker_files(child(root, config["reranker_directory"]), records["reranker_manifest"])
    source_readback = _source_readback(root, Path(config["source_root"]), rows) if full_sources else None
    snapshot = {"file_sha256": hashes, "code": code, "runtime": runtime_snapshot(),
                "source_manifest_rows_sha256": digest_value(rows),
                "fields_sha256": digest_value(fields), "document_ids_sha256": digest_value(ids),
                "ranking_inputs_sha256": digest_value([{"id": q["id"], "query": q["query"]} for q in queries]),
                "evaluation_labels_sha256": digest_value([{"id": q["id"], "target_id": q["target_id"]} for q in queries]),
                "permuted_queries_sha256": digest_value(permuted), "reranker_files": reranker,
                "dense_model_files": {k: v["files"] for k, v in records["dense_model_manifest"]["models"].items()}}
    return snapshot, records, queries, permuted, source_readback


def freeze(root: Path, config: dict, output: Path):
    need(not output.exists(), "protocol_output_already_exists")
    # The current dense producer explicitly uses four PyTorch threads.
    need(type(config["cpu_threads"]) is int and config["cpu_threads"] == 4 and
         config["candidate_depth"] == 50 and config["dense_batch_size"] == 16,
         "unsupported_trial_resource_policy")
    need(type(config["without_dense_ablation"]) is bool, "invalid_ablation_policy")
    snapshot, _, _, _, readback = inspect_inputs(root, config, full_sources=True)
    protocol = {"schema_version": VERSION, "configuration": config, "snapshot": snapshot,
                "source_readback_at_freeze": readback, "label_permutation": "rotate_targets_left_one",
                "metric_scope": "first_physical_page_known_item_retrieval",
                "graph_admission_enabled": False, "new_paid_api_calls": 0,
                "unsupported_ablations": ["without_page_channel", "historical_field_policy"]}
    # A freeze itself must not publish a hash of inputs that changed while read.
    after, *_ = inspect_inputs(root, config, full_sources=False)
    need(after == snapshot, "inputs_changed_during_protocol_freeze")
    return write_once(within(root, output), protocol)


def _dense_artifacts(folder):
    need(folder.is_dir(), "dense_output_missing")
    need(not any(p.is_symlink() for p in folder.rglob("*")), "dense_output_linked_artifact")
    return {p.relative_to(folder).as_posix(): digest(p)
            for p in sorted(folder.rglob("*")) if p.is_file()}


def _unchanged(root, protocol_path, expected_hash, config, expected, *, full_sources=False):
    need(digest(protocol_path) == expected_hash, "protocol_changed_during_run")
    current, _, _, _, source = inspect_inputs(root, config, full_sources=full_sources)
    need(current == expected, "frozen_input_code_or_runtime_changed")
    return source


def _metamorphic(primary, changed):
    checks = {key: primary[key] == changed[key] for key in
              ("ranking_inputs_sha256", "ranking_outputs_sha256", "candidates", "dense_cache_sha256")}
    checks["labels_changed"] = primary["evaluation_labels_sha256"] != changed["evaluation_labels_sha256"]
    return {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks}


def _timed(receipt, name, callback):
    started, cpu_started = time.perf_counter(), time.process_time()
    try:
        return callback()
    finally:
        receipt.setdefault("phase_timings", {})[name] = {
            "wall_seconds": time.perf_counter() - started,
            "process_cpu_seconds": time.process_time() - cpu_started}


def _ranking_readback(result, queries, fields, calls):
    """Retain every rank and validate it against the evaluator's full-order hash.

    Scored pairs follow the frozen candidate pool; ties retain that pool's order,
    exactly as the existing reranker does. This also binds score-call identity to
    query IDs even when two queries have identical text or an empty pool.
    """
    by_id = {row["id"]: row for row in fields}
    rankings, cursor = {}, 0
    for query in queries:
        pool = result["candidates"][query["id"]]["pool"]
        if not pool:
            rankings[query["id"]] = []
            continue
        need(cursor < len(calls), "reranker_score_call_missing")
        call = calls[cursor]
        cursor += 1
        pairs = [(query["query"], "\n".join(by_id[key].get(field, "") for field in ("title", "abstract", "body")))
                 for key in pool]
        need(call["pair_count"] == len(pool) and call["pairs_sha256"] == digest_value(pairs) and
             len(call["scores"]) == len(pool), "reranker_score_call_input_mismatch")
        call["query_id"] = query["id"]
        rankings[query["id"]] = [pool[i] for i in sorted(range(len(pool)), key=lambda i: (-call["scores"][i], i))]
    need(cursor == len(calls) and digest_value(rankings) == result["ranking_outputs_sha256"],
         "reranker_full_ranking_readback_mismatch")
    return rankings


def run(root: Path, protocol_path: Path, expected_protocol_sha256: str, output: Path):
    """A new run directory owns all measurements, including held partial work."""
    output = within(root, output)
    need(not output.exists(), "trial_output_already_exists")
    need(type(expected_protocol_sha256) is str and SHA.fullmatch(expected_protocol_sha256),
         "external_protocol_hash_required")
    protocol, protocol_sha = bound_json(within(root, protocol_path))
    need(protocol_sha == expected_protocol_sha256 and protocol.get("schema_version") == VERSION,
         "protocol_hash_or_version_mismatch")
    output.mkdir(parents=True, exist_ok=False)
    started, cpu_started = time.perf_counter(), time.process_time()
    receipt = {"schema_version": "retrieval-empirical-receipt-v1", "status": "BLOCKED",
               "protocol_sha256": protocol_sha, "new_paid_api_calls": 0, "production_graph_writes": 0,
               "graph_admission_enabled": False, "issue_acceptance_complete": False}
    try:
        config, expected = protocol["configuration"], protocol["snapshot"]
        before, records, queries, permuted, source_start = inspect_inputs(root, config, full_sources=True)
        need(before == expected, "frozen_input_code_or_runtime_changed")
        receipt["source_readback_start"] = source_start
        receipt["cpu_budget"] = configure_cpu(config["cpu_threads"])
        result_hashes = {"queries-permuted.json": write_once(output / "queries-permuted.json", {"queries": permuted})}
        dense_dir = output / "specter2"
        dense = _timed(receipt, "dense_production", lambda: produce(
            root, child(root, config["fields"]), child(root, config["queries"]),
            child(root, config["dense_model_root"]), child(root, config["dense_model_manifest"]),
            dense_dir, device="cpu", batch_size=config["dense_batch_size"], top_k=config["candidate_depth"]))
        observed_dense, dense_sha = bound_json(dense_dir / "dense_cache.json")
        need(observed_dense == dense and dense.get("binding_version") == "ranking-inputs-v2",
             "dense_producer_readback_mismatch")
        dense_files = _dense_artifacts(dense_dir)
        _unchanged(root, protocol_path, protocol_sha, config, expected)
        model_scorer = _timed(receipt, "reranker_load", lambda: local_cross_encoder(
            child(root, config["reranker_directory"]), expected["reranker_files"]))
        need(getattr(model_scorer, "offline_receipt", {}).get("local_files_only") is True,
             "local_reranker_receipt_missing")
        _unchanged(root, protocol_path, protocol_sha, config, expected)
        measured = {}
        for name, selected_queries, selected_dense in (
            ("primary", queries, dense), ("target_permutation", permuted, dense),
            *(([("without_dense", queries, None)]) if config["without_dense_ablation"] else [])):
            stage_start, stage_cpu = time.perf_counter(), time.process_time()
            scored_calls = []
            def scorer(pairs):
                input_hash = digest_value(pairs)
                scores = list(model_scorer(pairs))
                need(digest_value(pairs) == input_hash, "reranker_mutated_score_inputs")
                scored_calls.append({"pairs_sha256": input_hash, "pair_count": len(pairs),
                                     "scores": scores, "scores_sha256": digest_value(scores)})
                return scores
            scorer.offline_receipt = model_scorer.offline_receipt
            result = evaluate(copy.deepcopy(records["fields"]["fields"]), copy.deepcopy(selected_queries),
                              dense_cache=copy.deepcopy(selected_dense), scorer=scorer, k=config["candidate_depth"])
            result["stage"] = "local_cross_encoder"
            result["wall_seconds"] = time.perf_counter() - stage_start
            result["process_cpu_seconds"] = time.process_time() - stage_cpu
            result["scored_calls"] = scored_calls
            result["rankings"] = _ranking_readback(result, selected_queries, records["fields"]["fields"], scored_calls)
            result["reranker_model_manifest_sha256"] = expected["file_sha256"]["reranker_manifest"]
            _unchanged(root, protocol_path, protocol_sha, config, expected)
            need(_dense_artifacts(dense_dir) == dense_files, "dense_artifact_changed_during_run")
            measured[name] = result
            result_hashes[name + ".json"] = write_once(output / (name + ".json"),
                                                        {"status": "MEASURED_PENDING_FINAL_INTEGRITY", "result": result})
        metamorphic = _metamorphic(measured["primary"], measured["target_permutation"])
        receipt["target_permutation"] = metamorphic
        need(metamorphic["status"] == "PASS", "target_label_independence_failed")
        final_sources = _unchanged(root, protocol_path, protocol_sha, config, expected, full_sources=True)
        _unchanged(root, protocol_path, protocol_sha, config, expected)
        need(_dense_artifacts(dense_dir) == dense_files, "dense_artifact_changed_before_publication")
        need(all(digest(output / name) == sha for name, sha in result_hashes.items()),
             "measured_result_changed_before_publication")
        receipt.update(status="COMPLETE", source_readback_end=final_sources,
                       frozen_input_code_runtime_readback="MATCH", dense_cache_file_sha256=dense_sha,
                       dense_artifact_sha256=dense_files,
                       result_file_sha256=result_hashes,
                       document_count=config["document_count"], query_count=config["query_count"],
                       full_10000_by_60=config["document_count"] == 10000 and config["query_count"] == 60,
                       ablations={"without_dense": "MEASURED" if config["without_dense_ablation"] else "NOT_RUN",
                                  "without_page_channel": "UNSUPPORTED", "historical_field_policy": "NOT_RUN"},
                       relevance_judgments="NOT_PERFORMED")
    except Exception as exc:
        code = str(exc) if isinstance(exc, Blocked) else "trial_execution_error:" + type(exc).__name__
        receipt.update(status="FAIL" if code == "target_label_independence_failed" else "BLOCKED", failure_code=code)
    finally:
        receipt["wall_seconds"] = time.perf_counter() - started
        receipt["process_cpu_seconds"] = time.process_time() - cpu_started
        try:
            receipt["memory"] = memory_receipt()
        except Exception:
            receipt.update(status="BLOCKED", failure_code="memory_readback_failed")
        write_once(output / "receipt.json", receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    freeze_parser = sub.add_parser("freeze")
    for name in (*JSON_INPUTS, "source_root", "dense_model_root", "reranker_directory"):
        freeze_parser.add_argument("--" + name.replace("_", "-"), required=True)
    freeze_parser.add_argument("--cpu-threads", type=int, default=4)
    freeze_parser.add_argument("--without-dense-ablation", action="store_true")
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--protocol", required=True)
    run_parser.add_argument("--expected-protocol-sha256", required=True)
    for command in (freeze_parser, run_parser):
        command.add_argument("--data-root", required=True)
        command.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        root = data_root(args.data_root)
        if args.command == "freeze":
            config = {name: getattr(args, name) for name in (*JSON_INPUTS, "source_root", "dense_model_root", "reranker_directory")}
            config.update(source_root=str(Path(config["source_root"]).resolve()), cpu_threads=args.cpu_threads,
                          without_dense_ablation=args.without_dense_ablation, document_count=10000,
                          query_count=60, candidate_depth=50, dense_batch_size=16)
            sha = freeze(root, config, child(root, args.output))
            print(json.dumps({"status": "FROZEN_NOT_MEASURED", "protocol_sha256": sha}))
            return 0
        receipt = run(root, child(root, args.protocol), args.expected_protocol_sha256, child(root, args.output))
        print(json.dumps({"status": receipt["status"], "failure_code": receipt.get("failure_code")}))
        return 0 if receipt["status"] == "COMPLETE" else 2
    except Exception as exc:
        print(json.dumps({"status": "BLOCKED", "failure_code": str(exc) if isinstance(exc, Blocked) else type(exc).__name__}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
