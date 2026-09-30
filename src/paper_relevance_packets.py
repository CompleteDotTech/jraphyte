"""Prospective private issue #22 reviewer packet builder. No inference or ranking work.

The source material is read only after a COMPLETE, externally hash-pinned trial.
Reviewer output and private coordinator output are disjoint directories.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path

SHA = set("0123456789abcdef")
DOMAIN = b"issue22-relevance-order-v1\0"
VERSION = "paper-relevance-packet-authorization-v1"


def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def value_sha(obj):
    return hashlib.sha256(canonical(obj)).hexdigest()


def order_key(q_sha, source_sha):
    return hashlib.sha256(DOMAIN + q_sha.encode("ascii") + b"\0" +
                          source_sha.encode("ascii")).hexdigest()


def file_sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def unredirected(path):
    """Reject an output path whose existing ancestors redirect through links/junctions."""
    path = Path(path).absolute()
    for part in (path, *path.parents):
        if part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction()):
            raise ValueError("authorized_output_path_redirected")
    return path


def require_sha(value):
    if not isinstance(value, str) or len(value) != 64 or set(value) - SHA:
        raise ValueError("valid_external_sha_required")
    return value


def read_pinned(path, sha):
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != require_sha(sha):
        raise ValueError("pinned_input_changed")
    return json.loads(raw)


def child(root, relative):
    p = Path(relative)
    if p.is_absolute() or not p.parts or ".." in p.parts:
        raise ValueError("unsafe_relative_path")
    base = root.resolve(strict=True)
    current = base
    for part in p.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("source_path_symlink")
    path = (base / p).resolve(strict=True)
    if not path.is_relative_to(base):
        raise ValueError("source_path_outside_root_or_symlink")
    return path


def source_path(data_root, source_root, row):
    root_id = row["source_root_id"]
    if root_id == "external":
        return child(source_root, row["source_relative"])
    if root_id == "data_root":
        return child(data_root, row["source_relative"])
    raise ValueError("unknown_source_root")


def rank_result(payload, query_ids, target_ids, fields_ids, rank_id):
    if payload.get("status") != "MEASURED_PENDING_FINAL_INTEGRITY":
        raise ValueError("result_not_measured")
    result = payload["result"]
    ranks = result["rankings"]
    if set(ranks) != query_ids or set(result["candidates"]) != query_ids:
        raise ValueError("result_query_inventory_changed")
    if result.get("ranking_inputs_sha256") != rank_id:
        raise ValueError("ranking_inputs_changed")
    if result.get("evaluation_labels_sha256") != target_ids:
        raise ValueError("evaluation_labels_changed")
    for qid, ranked in ranks.items():
        pool = result["candidates"][qid]["pool"]
        if (not isinstance(ranked, list) or len(ranked) != len(set(ranked)) or
                set(ranked) != set(pool) or not set(ranked) <= fields_ids or
                result["candidates"][qid]["pool_sha256"] != value_sha(pool)):
            raise ValueError("rankings_or_pool_changed")
    if result.get("ranking_outputs_sha256") != value_sha(ranks):
        raise ValueError("rankings_hash_changed")
    return result


def verified_inputs(data_root, source_root, trial_dir, protocol_path, protocol_sha,
                    receipt_sha, rubric_path, rubric_sha, expected_prereg_sha256,
                    expected_queries_sha256, expected_code_head):
    rubric = read_pinned(rubric_path, rubric_sha)
    if (rubric.get("prereg_sha256") != expected_prereg_sha256 or
            rubric.get("status") != "APPROVED_PRE_RESULT_RUBRIC_ONLY" or
            rubric.get("relevance_review_performed") is not False):
        raise ValueError("approved_exact_rubric_required")
    protocol = read_pinned(protocol_path, protocol_sha)
    receipt = read_pinned(trial_dir / "receipt.json", receipt_sha)
    config, snapshot = protocol["configuration"], protocol["snapshot"]
    if (receipt.get("status") != "COMPLETE" or receipt.get("protocol_sha256") != protocol_sha or
            receipt.get("frozen_input_code_runtime_readback") != "MATCH" or
            receipt.get("full_10000_by_60") is not True or
            receipt.get("document_count") != 10000 or receipt.get("query_count") != 60 or
            config.get("document_count") != 10000 or config.get("query_count") != 60 or
            receipt.get("relevance_judgments") != "NOT_PERFORMED"):
        raise ValueError("complete_bound_trial_required")
    hashes = snapshot["file_sha256"]
    if (snapshot["code"].get("git_head") != expected_code_head or
            hashes["queries"] != expected_queries_sha256):
        raise ValueError("expected_code_and_queries_required")
    queries = read_pinned(child(data_root, config["queries"]), hashes["queries"])
    queries = queries["queries"] if isinstance(queries, dict) and "queries" in queries else queries
    if isinstance(queries, dict) and all(isinstance(v, str) for v in queries.values()):
        queries = [{"id": f"mapped-{i:04d}", "query": text, "target_id": target}
                   for i, (target, text) in enumerate(sorted(queries.items()))]
    fields = read_pinned(child(data_root, config["fields"]), hashes["fields"])
    fields = fields["fields"] if isinstance(fields, dict) and "fields" in fields else fields
    manifest = read_pinned(child(data_root, config["preparation_manifest"]), hashes["preparation_manifest"])
    if len(queries) != 60 or len(fields) != 10000 or len(manifest["pdfs"]) != 10000:
        raise ValueError("full_input_inventory_required")
    qids = [str(q["id"]) for q in queries]
    docids = [f["id"] for f in fields]
    sources = {row["sample_id"]: row for row in manifest["pdfs"]}
    if (len(set(qids)) != 60 or len(set(docids)) != 10000 or
            set(docids) != set(sources) or not {q["target_id"] for q in queries} <= set(sources)):
        raise ValueError("query_or_source_identity_changed")
    for f in fields:
        if f["source_sha256"] != sources[f["id"]]["source_sha256"]:
            raise ValueError("field_source_identity_changed")
    rank_id = value_sha([{"id":str(q["id"]),"query":q["query"]} for q in queries])
    label_id = value_sha([{"id":str(q["id"]),"target_id":q["target_id"]} for q in queries])
    arm_files = receipt["result_file_sha256"]
    if not isinstance(arm_files, dict) or not arm_files:
        raise ValueError("complete_result_file_manifest_required")
    for name, expected in arm_files.items():
        if file_sha(child(trial_dir, name)) != require_sha(expected):
            raise ValueError("listed_trial_result_artifact_changed")
    arms = {}
    for arm in ("primary", "without_dense", "without_page", "historical_fields",
                "historical_fields_without_page"):
        name = arm + ".json"
        if name in arm_files:
            arms[arm] = rank_result(read_pinned(trial_dir / name, arm_files[name]),
                                    set(qids), label_id, set(docids), rank_id)
    if "primary" not in arms:
        raise ValueError("primary_arm_missing")
    if ((config.get("without_dense_ablation") and "without_dense" not in arms) or
            (config.get("without_page_ablation") and "without_page" not in arms) or
            (config.get("historical_fields") and "historical_fields" not in arms)):
        raise ValueError("declared_measured_arm_missing")
    if not trial_dir.resolve(strict=True).is_relative_to(data_root.resolve(strict=True)):
        raise ValueError("trial_outside_data_root")
    return protocol, receipt, queries, sources, arms, rank_id


def recheck_frozen_inputs(data_root, trial_dir, protocol_path, protocol_sha,
                          receipt_sha, rubric_path, rubric_sha, protocol, receipt):
    """Recheck every approved trial input after source packet construction."""
    config = protocol["configuration"]
    hashes = protocol["snapshot"]["file_sha256"]
    pinned = ((rubric_path, rubric_sha), (protocol_path, protocol_sha),
              (trial_dir / "receipt.json", receipt_sha),
              (child(data_root, config["queries"]), hashes["queries"]),
              (child(data_root, config["fields"]), hashes["fields"]),
              (child(data_root, config["preparation_manifest"]),
               hashes["preparation_manifest"]))
    for path, expected in pinned:
        if file_sha(path) != require_sha(expected):
            raise ValueError("frozen_trial_input_changed_during_packet_construction")
    for name, expected in receipt["result_file_sha256"].items():
        if file_sha(child(trial_dir, name)) != require_sha(expected):
            raise ValueError("frozen_trial_result_changed_during_packet_construction")


def select(queries, sources, arms, focus_target_ids):
    selection, all_queries = [], []
    primary = arms["primary"]["rankings"]
    for query in queries:
        qid, target = str(query["id"]), query["target_id"]
        ranking = primary[qid]
        rank = ranking.index(target) + 1 if target in ranking else None
        all_queries.append({"query_id":qid,"target_id":target,"primary_target_rank":rank,
                            "in_primary_candidate_union":target in
                            arms["primary"]["candidates"][qid]["pool"],
                            "arm_target_rank":{
                                name:(result["rankings"][qid].index(target)+1
                                      if target in result["rankings"][qid] else None)
                                for name,result in arms.items()},
                            "arm_candidate_union_membership":{
                                name:target in result["candidates"][qid]["pool"]
                                for name,result in arms.items()}})
        reasons = []
        if rank is None or rank > 10:
            reasons.append("primary_top10_miss")
            reasons.append("candidate_union_miss" if rank is None else
                           "near_miss_11_to_50" if rank <= 50 else
                           "reranked_below_50_within_union")
        if target in focus_target_ids:
            reasons.append("prespecified_focus_target")
        if not reasons:
            continue
        ids = list(ranking[:10]) + [target]
        pairs = {}
        for arm in ("without_dense","without_page","historical_fields",
                    "historical_fields_without_page"):
            result = arms.get(arm)
            if result is None:
                pairs[arm] = {"status":"NOT_RUN","paper_id":None,"rank":None}
                continue
            if result["rankings"][qid][:10] == ranking[:10]:
                pairs[arm] = {"status":"IDENTICAL_TOP10","paper_id":None,"rank":None}
                continue
            pair = next((item for item in result["rankings"][qid][:10]
                         if item not in set(ranking[:10])), None)
            pairs[arm] = {"status":"PAIRED" if pair else "NO_DISTINCT_TOP10",
                          "paper_id":pair,"rank":result["rankings"][qid].index(pair)+1 if pair else None}
            if pair:
                ids.append(pair)
        grouped = {}
        for sid in ids:
            sha = sources[sid]["source_sha256"]
            item = grouped.setdefault(sha, [])
            if item and any(sources[other]["page_sha256"] != sources[sid]["page_sha256"] or
                            sources[other]["image_sha256"] != sources[sid]["image_sha256"] or
                            sources[other]["physical_page"] != sources[sid]["physical_page"]
                            for other in item):
                raise ValueError("same_pdf_different_page_evidence")
            if sid not in item:
                item.append(sid)
        q_sha = value_sha({"id":qid,"query":query["query"]})
        keys = {sha: order_key(q_sha, sha) for sha in grouped}
        if len(set(keys.values())) != len(keys):
            raise ValueError("ordering_key_collision")
        ordered = sorted(grouped, key=lambda sha: (keys[sha], sha))
        selection.append({"query_id":qid,"query":query["query"],"target_id":target,
                          "target_rank":rank,"primary_top10_ids":ranking[:10],
                          "reasons":reasons,"pairs":pairs,
                          "q_sha":q_sha,"ordered_keys_sha256":value_sha(
                              [[keys[sha],sha] for sha in ordered]),
                          "source_groups": [(sha,grouped[sha]) for sha in ordered]})
    return selection, all_queries


def copy_checked(source, destination, expected, authorized_output_root):
    require_sha(expected)
    unredirected(authorized_output_root)
    unredirected(destination.parent)
    if file_sha(source) != expected:
        raise ValueError("original_source_hash_changed")
    with source.open("rb") as src, destination.open("xb") as dst:
        shutil.copyfileobj(src, dst, 1024 * 1024)
        dst.flush()
        os.fsync(dst.fileno())
    unredirected(authorized_output_root)
    unredirected(destination.parent)
    if file_sha(source) != expected or file_sha(destination) != expected:
        raise ValueError("source_alias_copy_changed")


def verify_group_assets(data_root, source_root, ids, sources):
    first = sources[ids[0]]
    expected = {kind:first[kind+"_sha256"] for kind in ("source","page","image")}
    paths = []
    for sid in ids:
        row = sources[sid]
        if (row["physical_page"] != first["physical_page"] or
                any(row[kind+"_sha256"] != sha for kind,sha in expected.items())):
            raise ValueError("duplicate_source_manifest_evidence_conflict")
        items = {"source":source_path(data_root,source_root,row),
                 "page":child(data_root,row["page_relative"]),
                 "image":child(data_root,row["image_relative"])}
        if any(file_sha(path) != expected[kind] for kind,path in items.items()):
            raise ValueError("duplicate_source_asset_bytes_changed")
        paths.append(items)
    return paths


def produce(data_root, source_root, trial_dir, protocol_path, protocol_sha,
            receipt_sha, rubric_path, rubric_sha, expected_prereg_sha256,
            expected_queries_sha256, expected_code_head, focus_target_ids,
            authorized_output_root, out):
    unredirected(authorized_output_root)
    authorized = authorized_output_root.resolve(strict=True)
    if out.parent.resolve(strict=True) != authorized or out.exists() or out.is_symlink():
        raise ValueError("packet_output_must_be_new_child_of_authorized_private_root")
    protocol, receipt, queries, sources, arms, rank_id = verified_inputs(
        data_root, source_root, trial_dir, protocol_path, protocol_sha,
        receipt_sha, rubric_path, rubric_sha, expected_prereg_sha256,
        expected_queries_sha256, expected_code_head)
    if (not isinstance(focus_target_ids, list) or
            len(set(focus_target_ids)) != len(focus_target_ids) or
            not all(isinstance(s, str) and s in sources for s in focus_target_ids)):
        raise ValueError("focus_targets_must_be_unique_corpus_ids")
    picked, all_queries = select(queries, sources, arms, set(focus_target_ids))
    if out.exists():
        raise ValueError("packet_output_already_exists")
    # All identity and COMPLETE gates above run before any source bytes are opened.
    out.mkdir(parents=True, exist_ok=False)
    reviewer = out / "reviewer"
    private = out / "coordinator_private"
    private.mkdir()
    inventory = [{"query_id":row["query_id"],"q_sha":row["q_sha"],
                  "ordered_keys_sha256":row["ordered_keys_sha256"],
                  "source_groups":row["source_groups"]} for row in picked]
    preflight = {"schema_version":"issue22-private-packet-preflight-v1",
                 "protocol_sha256":protocol_sha,"receipt_sha256":receipt_sha,
                 "rubric_file_sha256":rubric_sha,"ranking_inputs_sha256":rank_id,
                 "focus_target_ids":focus_target_ids,
                 "ordering_version":"issue22-relevance-order-v1",
                 "all_60_target_ranks_and_union":all_queries,
                 "task_inventory_sha256":value_sha(inventory),"inventory":inventory}
    preflight_path = private / "selection-preflight.json"
    with preflight_path.open("xb") as handle:
        handle.write(canonical(preflight)+b"\n")
        handle.flush(); os.fsync(handle.fileno())
    reviewer.mkdir()
    packets, mapping = [], []
    for entry in picked:
        query_alias = "qry-"+uuid.uuid4().hex
        packet = {"packet_id":"pkt-"+uuid.uuid4().hex,
                  "query_id":query_alias,"query_text":entry["query"],"tasks":[]}
        private_row = {key:entry[key] for key in ("query_id","target_id","target_rank",
                                                "primary_top10_ids",
                                                "reasons","pairs","q_sha")}
        private_row["packet_id"] = packet["packet_id"]
        private_row["query_alias"] = query_alias
        private_row["ordered_keys_sha256"] = entry["ordered_keys_sha256"]
        private_row["tasks"] = []
        for sha, ids in entry["source_groups"]:
            alias = "src-"+uuid.uuid4().hex
            source = sources[ids[0]]
            group_paths = verify_group_assets(data_root,source_root,ids,sources)
            assets = {}
            for kind, path in (("pdf",group_paths[0]["source"]),
                               ("page_pdf",group_paths[0]["page"]),
                               ("page_image",group_paths[0]["image"])):
                expected = source["source_sha256" if kind == "pdf" else
                                  "page_sha256" if kind == "page_pdf" else "image_sha256"]
                filename = alias + {"pdf":"-source.pdf","page_pdf":"-page.pdf",
                                    "page_image":"-render.png"}[kind]
                copy_checked(path, reviewer / filename, expected, authorized_output_root)
                assets[kind] = filename
            verify_group_assets(data_root,source_root,ids,sources)
            packet["tasks"].append({"task_id":alias,"source_pdf":assets["pdf"],
                                    "page_pdf":assets["page_pdf"],"page_render":assets["page_image"]})
            private_row["tasks"].append({"task_id":alias,"source_sha256":sha,
                                         "document_ids":ids,"assets":assets,
                                         "source_members":[{
                                             "document_id":sid,
                                             "source_relative":sources[sid]["source_relative"],
                                             "page_relative":sources[sid]["page_relative"],
                                             "image_relative":sources[sid]["image_relative"]}
                                             for sid in ids],
                                         "source_relative":source["source_relative"],
                                         "page_relative":source["page_relative"],
                                         "image_relative":source["image_relative"],
                                         "page_sha256":source["page_sha256"],
                                         "image_sha256":source["image_sha256"],
                                         "physical_page":source["physical_page"]})
        packets.append(packet)
        mapping.append(private_row)
    reviewer_json = {"schema_version":"issue22-blinded-review-packets-v1",
                     "rubric_sha256":expected_prereg_sha256,"packets":packets}
    reviewer_path = reviewer / "packets.json"
    with reviewer_path.open("xb") as handle:
        handle.write(canonical(reviewer_json)+b"\n")
        handle.flush(); os.fsync(handle.fileno())
    private_json = {"schema_version":"issue22-private-coordinator-map-v1",
                    "protocol_sha256":protocol_sha,"receipt_sha256":receipt_sha,
                    "ranking_inputs_sha256":rank_id,"rubric_file_sha256":rubric_sha,
                    "selection_preflight_sha256":file_sha(preflight_path),
                    "task_inventory_sha256":preflight["task_inventory_sha256"],
                    "selection":mapping,"reviewer_packet_sha256":file_sha(reviewer_path)}
    with (private / "selection-map.json").open("xb") as handle:
        handle.write(canonical(private_json)+b"\n")
        handle.flush(); os.fsync(handle.fileno())
    recheck_frozen_inputs(data_root, trial_dir, protocol_path, protocol_sha,
                          receipt_sha, rubric_path, rubric_sha, protocol, receipt)
    unredirected(authorized_output_root)
    unredirected(out)
    return {"selected_queries":len(picked),"review_tasks":sum(len(p["tasks"]) for p in packets),
            "reviewer_packets_sha256":file_sha(reviewer / "packets.json"),
            "private_map_sha256":file_sha(private / "selection-map.json")}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--authorization", required=True)
    p.add_argument("--expected-authorization-sha256", required=True)
    a = p.parse_args()
    result = run_authorized(Path(a.authorization), a.expected_authorization_sha256)
    print(json.dumps(result))


def run_authorized(path, expected_sha256):
    authorization = read_pinned(path, expected_sha256)
    if authorization.get("schema_version") != VERSION:
        raise ValueError("unsupported_authorization_version")
    required = {"schema_version", "data_root", "source_root", "trial_relative",
                "protocol_relative", "protocol_sha256", "receipt_sha256", "rubric_path",
                "rubric_sha256", "expected_prereg_sha256", "expected_queries_sha256",
                "expected_code_head", "focus_target_ids", "authorized_output_root",
                "output_name", "coordinator_code_sha256"}
    if set(authorization) != required:
        raise ValueError("authorization_fields_mismatch")
    for key in ("protocol_sha256", "receipt_sha256", "rubric_sha256",
                "expected_prereg_sha256", "expected_queries_sha256",
                "coordinator_code_sha256"):
        require_sha(authorization[key])
    module_file = Path(__file__).resolve(strict=True)
    if file_sha(module_file) != authorization["coordinator_code_sha256"]:
        raise ValueError("approved_coordinator_code_changed")
    head = authorization["expected_code_head"]
    if not isinstance(head, str) or len(head) != 40 or set(head) - SHA:
        raise ValueError("expected_code_head_required")
    name = authorization["output_name"]
    if (not isinstance(name, str) or not name or name in (".", "..") or
            any(ch in name for ch in "/\\")):
        raise ValueError("single_new_output_name_required")
    data_root = Path(authorization["data_root"])
    source_root = Path(authorization["source_root"])
    output_root = Path(authorization["authorized_output_root"])
    if not (data_root.is_absolute() and source_root.is_absolute() and
            output_root.is_absolute() and data_root.is_dir() and
            source_root.is_dir() and output_root.is_dir()):
        raise ValueError("authorized_roots_required")
    result = produce(data_root, source_root,
                   child(data_root, authorization["trial_relative"]),
                   child(data_root, authorization["protocol_relative"]),
                   authorization["protocol_sha256"], authorization["receipt_sha256"],
                   Path(authorization["rubric_path"]), authorization["rubric_sha256"],
                   authorization["expected_prereg_sha256"],
                   authorization["expected_queries_sha256"], head,
                   authorization["focus_target_ids"],
                   output_root, output_root / name)
    if file_sha(module_file) != authorization["coordinator_code_sha256"]:
        raise ValueError("approved_coordinator_code_changed_after_production")
    return result


if __name__ == "__main__":
    main()
