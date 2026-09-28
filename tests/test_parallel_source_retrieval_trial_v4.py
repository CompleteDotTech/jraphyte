"""Adversarial empirical-receipt tests; authored fixtures, no model or corpus run."""
import copy
import json
import tempfile
import types
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from src.parallel_source_v4 import retrieval_trial as trial
from src.parallel_source_v4.common import digest, method_hashes, write_once
from trace_gc.pdf_source_parallel_v4 import digest_value


class EmpiricalTrialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "originals"
        self.source.mkdir()
        self.runtime = {"fixture": "authored-no-model-runtime"}
        self.calls = 0
        self.on_score = None
        self.on_load = None
        self.producer_calls = 0
        self.output = self.root / "measured"
        self.protocol = self.root / "protocol.json"
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(trial, "runtime_snapshot", side_effect=lambda: copy.deepcopy(self.runtime)))
        self.stack.enter_context(patch.object(trial, "configure_cpu", return_value={"device": "cpu", "torch_threads": 4}))
        self.stack.enter_context(patch.object(trial, "produce", side_effect=self.producer))
        self.stack.enter_context(patch.object(trial, "local_cross_encoder", side_effect=self.loader))
        rows, fields = [], []
        for sid, title in (("a", "Transport networks"), ("b", "Algebraic transport")):
            row = {"sample_id": sid, "work_id": sid, "physical_page": 1, "source_root_id": "external"}
            for kind in ("source", "page", "image", "native"):
                path = (self.source if kind == "source" else self.root) / (sid + "-" + kind)
                path.write_bytes(("authored fixture " + sid + kind).encode())
                row[kind + "_relative"] = path.name
                row[kind + "_sha256"] = digest(path)
            rows.append(row)
            fields.append({"id": sid, "title": title, "abstract": "", "body": "Transport observations",
                           "physical_page": 1, "retrieval_only": True, "eligible_for_jev": False,
                           **{k + "_sha256": row[k + "_sha256"] for k in ("source", "page", "image", "native")}})
        prep = {"pdfs": rows}
        write_once(self.root / "preparation.json", prep)
        write_once(self.root / "fields.json", {"fields": fields, "fields_sha256": digest_value(fields),
                   "field_builder_code_sha256": method_hashes(), "manifest_sha256": digest_value(prep),
                   "final_input_readback_count": 2, "final_input_readback": "all_source_page_image_native_hashes_match",
                   "query_independent": True})
        write_once(self.root / "queries.json", {"queries": [
            {"query_id": "q1", "text": "transport", "target_id": "a"},
            {"query_id": "q2", "text": "algebraic", "target_id": "b"}]})
        dense_manifest = {"schema_version": "local-specter2-model-v1", "max_tokens": 512,
                          "document_template": "title + tokenizer.sep_token + abstract", "query_template": "query_text",
                          "pooling": "last_hidden_state_cls_l2_normalized", "similarity": "cosine", "models": {}}
        for kind in ("base", "paper", "query"):
            folder = self.root / "dense-model" / kind
            folder.mkdir(parents=True)
            (folder / "config.json").write_text("{}")
            dense_manifest["models"][kind] = {"directory": kind, "model_revision": "a" * 40,
                                                 "files": {"config.json": digest(folder / "config.json")}}
        write_once(self.root / "dense-model.json", dense_manifest)
        folder = self.root / "reranker"
        folder.mkdir()
        (folder / "config.json").write_text('{"num_labels":1}')
        (folder / "tokenizer.json").write_text("{}")
        (folder / "model.safetensors").write_bytes(b"authored fixture, not model weights")
        write_once(self.root / "reranker.json", {"schema_version": "local-reranker-model-v1", "model_revision": "b" * 40,
                   "files": {p.name: digest(p) for p in folder.iterdir()}})
        self.config = {"fields": "fields.json", "queries": "queries.json", "preparation_manifest": "preparation.json",
                       "dense_model_root": "dense-model", "dense_model_manifest": "dense-model.json",
                       "reranker_directory": "reranker", "reranker_manifest": "reranker.json",
                       "source_root": str(self.source), "document_count": 2, "query_count": 2,
                       "cpu_threads": 4, "dense_batch_size": 16, "candidate_depth": 50,
                       "without_dense_ablation": False}

    def producer(self, root, fields_file, queries_file, model_root, model_manifest, output, **kwargs):
        self.producer_calls += 1
        fields = trial.bound_json(fields_file)[0]["fields"]
        queries = trial.normalize_queries(trial.bound_json(queries_file)[0])
        rankings = {q["id"]: [f["id"] for f in fields] for q in queries}
        result = {"binding_version": "ranking-inputs-v2", "channel": "specter2", "rankings": rankings,
                  "ranking_sha256": digest_value(rankings), "model_revision": "a" * 40,
                  "document_ids_sha256": digest_value([f["id"] for f in fields]),
                  "query_ids_sha256": digest_value([q["id"] for q in queries]),
                  "fields_sha256": digest_value(fields), "top_k": 50, "target_ids_used_for_ranking": False,
                  "ranking_inputs_sha256": digest_value([{"id": q["id"], "query": q["query"]} for q in queries])}
        write_once(output / "protocol.json", {"fixture": "no-real-model"})
        write_once(output / "dense_cache.json", result)
        return result

    def loader(self, folder, hashes):
        if self.on_load:
            self.on_load()
        def scorer(pairs):
            self.calls += 1
            if self.on_score:
                value = self.on_score(pairs)
                if value is not None:
                    return value
            return [float(len(text)) for _, text in pairs]
        scorer.offline_receipt = {"local_files_only": True, "model_file_hashes": hashes}
        return scorer

    def freeze(self):
        return trial.freeze(self.root, self.config, self.protocol)

    def run_trial(self, sha=None):
        return trial.run(self.root, self.protocol, sha or self.freeze(), self.output)

    def test_primary_and_real_evaluate_permutation_share_cache_and_receipts(self):
        result = self.run_trial()
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["target_permutation"]["status"], "PASS")
        self.assertFalse(result["full_10000_by_60"])
        self.assertFalse(result["issue_acceptance_complete"])
        self.assertEqual(self.producer_calls, 1)
        self.assertEqual(self.calls, 4)
        self.assertEqual(result["source_readback_start"], result["source_readback_end"])
        self.assertEqual(result["source_readback_end"]["artifact_count"], 8)
        self.assertGreater(result["memory"]["peak_rss_bytes"], 0)
        self.assertFalse(result["memory"]["child_processes_included"])
        for name, sha in result["result_file_sha256"].items():
            self.assertEqual(digest(self.output / name), sha)
        primary = trial.bound_json(self.output / "primary.json")[0]["result"]
        self.assertEqual(digest_value(primary["rankings"]), primary["ranking_outputs_sha256"])
        self.assertEqual(len(primary["scored_calls"]), 2)
        self.assertTrue(all(call["scores_sha256"] == digest_value(call["scores"]) for call in primary["scored_calls"]))

    def test_stale_protocol_hash_does_not_start_or_create_output(self):
        self.freeze()
        with self.assertRaisesRegex(trial.Blocked, "protocol_hash_or_version_mismatch"):
            self.run_trial("0" * 64)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.producer_calls, 0)

    def test_changed_source_before_run_blocks_before_model(self):
        sha = self.freeze()
        (self.source / "a-source").write_bytes(b"changed")
        result = self.run_trial(sha)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["failure_code"], "source_artifact_bytes_changed:source")
        self.assertEqual(self.producer_calls, 0)

    def test_source_change_during_scoring_blocks_final_completion(self):
        self.on_score = lambda pairs: (self.source / "a-source").write_bytes(b"changed") and None
        result = self.run_trial()
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["failure_code"], "source_artifact_bytes_changed:source")

    def test_model_change_inside_loader_cannot_publish_old_identity(self):
        self.on_load = lambda: (self.root / "reranker/model.safetensors").write_bytes(b"changed")
        result = self.run_trial()
        self.assertEqual(result["failure_code"], "reranker_snapshot_bytes_changed")
        self.assertEqual(self.calls, 0)

    def test_query_edit_during_scoring_is_blocked(self):
        def edit(_):
            q = trial.bound_json(self.root / "queries.json")[0]
            q["queries"][0]["text"] = "edited query"
            (self.root / "queries.json").write_text(json.dumps(q))
        self.on_score = edit
        result = self.run_trial()
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["failure_code"], "frozen_input_code_or_runtime_changed")

    def test_runtime_change_inside_model_load_is_blocked(self):
        self.on_load = lambda: self.runtime.update(changed=True)
        result = self.run_trial()
        self.assertEqual(result["failure_code"], "frozen_input_code_or_runtime_changed")

    def test_real_rerank_drift_on_label_permutation_has_explicit_fail_receipt(self):
        self.on_score = lambda pairs: [float(i if self.calls <= 2 else -i) for i in range(len(pairs))]
        result = self.run_trial()
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["failure_code"], "target_label_independence_failed")
        self.assertFalse(result["target_permutation"]["checks"]["ranking_outputs_sha256"])

    def test_dense_cache_change_during_scoring_is_blocked(self):
        self.on_score = lambda pairs: (self.output / "specter2/dense_cache.json").write_bytes(b"{}") and None
        result = self.run_trial()
        self.assertEqual(result["failure_code"], "dense_artifact_changed_during_run")

    def test_result_tamper_after_measurement_is_not_pinned_as_valid(self):
        def tamper(_):
            if self.calls == 3:
                (self.output / "primary.json").write_text('{"forged":true}')
        self.on_score = tamper
        result = self.run_trial()
        self.assertEqual(result["failure_code"], "measured_result_changed_before_publication")

    def test_supported_ablation_actually_omits_dense_channel(self):
        self.config["without_dense_ablation"] = True
        result = self.run_trial()
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["ablations"]["without_dense"], "MEASURED")
        ablation = trial.bound_json(self.output / "without_dense.json")[0]["result"]
        self.assertEqual(ablation["dense_stage"], "not_run")
        self.assertEqual(ablation["candidate_stage_metrics"]["specter2"]["status"], "NOT_RUN")

    def test_duplicate_json_keys_and_target_derived_query_ids_are_rejected(self):
        (self.root / "queries.json").write_text('{"queries":[],"queries":[]}')
        with self.assertRaisesRegex(ValueError, "duplicate_key"):
            self.freeze()
        (self.root / "queries.json").write_text('{"a":"transport","b":"algebraic"}')
        with self.assertRaisesRegex(trial.Blocked, "explicit_query_identifiers_required"):
            self.freeze()

    def test_field_source_mismatch_and_stale_code_fail_before_models(self):
        p = self.root / "fields.json"
        value = trial.bound_json(p)[0]
        value["fields"][0]["source_sha256"] = "0" * 64
        value["fields_sha256"] = digest_value(value["fields"])
        p.write_text(json.dumps(value))
        with self.assertRaisesRegex(trial.Blocked, "field_source_binding_invalid"):
            self.freeze()
        value["field_builder_code_sha256"] = {}
        p.write_text(json.dumps(value))
        with self.assertRaisesRegex(trial.Blocked, "fields_require_final_code_tree_rebuild"):
            self.freeze()

    def test_path_traversal_is_rejected_before_input_read(self):
        self.config["queries"] = "../outside.json"
        with self.assertRaisesRegex(ValueError, "expected_safe_relative_path"):
            self.freeze()

    def test_only_supported_four_thread_dense_policy_is_frozen(self):
        self.config["cpu_threads"] = 8
        with self.assertRaisesRegex(trial.Blocked, "unsupported_trial_resource_policy"):
            self.freeze()

    def test_memory_readback_failure_cannot_leave_complete_receipt(self):
        with patch.object(trial, "memory_receipt", side_effect=OSError("private path must not leak")):
            result = self.run_trial()
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["failure_code"], "memory_readback_failed")
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_full_ranking_readback_rejects_forged_digest(self):
        original = trial.evaluate
        def forged(*args, **kwargs):
            result = original(*args, **kwargs)
            result["ranking_outputs_sha256"] = "0" * 64
            return result
        with patch.object(trial, "evaluate", side_effect=forged):
            result = self.run_trial()
        self.assertEqual(result["failure_code"], "reranker_full_ranking_readback_mismatch")

    def test_dense_and_reranker_load_phase_timings_are_explicit(self):
        result = self.run_trial()
        self.assertEqual(set(result["phase_timings"]), {"dense_production", "reranker_load"})
        for phase in result["phase_timings"].values():
            self.assertEqual(set(phase), {"wall_seconds", "process_cpu_seconds"})
            self.assertGreaterEqual(phase["wall_seconds"], 0)
            self.assertGreaterEqual(phase["process_cpu_seconds"], 0)
            self.assertLessEqual(phase["wall_seconds"], result["wall_seconds"])
        with self.subTest("failed_load_still_records_elapsed_time"):
            self.output = self.root / "failed-load"
            self.on_load = lambda: (_ for _ in ()).throw(RuntimeError("authored load failure"))
            failure = self.run_trial(digest(self.protocol))
            self.assertEqual(failure["status"], "BLOCKED")
            self.assertIn("reranker_load", failure["phase_timings"])


class RuntimeReceiptTests(unittest.TestCase):
    def test_installed_runtime_receipt_survives_exact_json_roundtrip(self):
        distribution = types.SimpleNamespace(metadata={"Name": "fixture-package"}, version="1.0")
        with patch.object(trial.importlib.metadata, "version", return_value="1.0"), \
             patch.object(trial.importlib.metadata, "distributions", return_value=[distribution]):
            receipt = trial.runtime_snapshot()
        self.assertEqual(receipt, json.loads(json.dumps(receipt)))
        self.assertEqual(receipt["installed_distributions"], [["fixture-package", "1.0"]])


if __name__ == "__main__":
    unittest.main()
