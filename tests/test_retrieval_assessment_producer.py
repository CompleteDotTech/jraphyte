"""Corpus assessment producer guards; no model download or conversion in tests."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from src.parallel_source_v4.common import write_once
from src.parallel_source_v4 import assessment_producer as producer


class AssessmentProducerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / "run"
        self.manifest = self.root / "manifest.json"
        self.profile = self.root / "profile.json"
        self.profile.write_text("{}", encoding="utf-8")

    def manifest_rows(self, ids):
        rows = [{"sample_id": sid, "physical_page": 1,
                 **{key + "_sha256": "0" * 64 for key in ("source", "page", "image", "native")}}
                for sid in ids]
        write_once(self.manifest, {"stage": "retrieval_source_first_no_predictions",
                                   "query_independent": True, "pdfs": rows})
        return rows

    def freeze(self, selected=None):
        with patch.object(producer, "_profile"), patch.object(producer, "method_hashes", return_value={"code": "hash"}), \
                patch.object(producer, "runtime_receipt", return_value={"runtime": "pinned"}):
            return producer._freeze(self.root, self.manifest, self.profile, self.output, None,
                                    selected_ids=selected)

    def test_duplicate_and_unknown_ids_rejected_before_conversion(self):
        self.manifest_rows(["f001", "f001"])
        with self.assertRaisesRegex(ValueError, "exact_unique_manifest_ids_required"):
            self.freeze()
        self.manifest.unlink()
        self.manifest_rows(["f001", "f002"])
        with self.assertRaisesRegex(ValueError, "invalid_exposed_smoke_selection"):
            self.freeze(["f001", "missing"])

    def test_query_dependent_source_selection_rejected(self):
        rows = self.manifest_rows(["f001"])
        self.manifest.unlink()
        rows[0]["target_id"] = "f001"
        write_once(self.manifest, {"stage": "retrieval_source_first_no_predictions",
                                   "query_independent": True, "pdfs": rows})
        with self.assertRaisesRegex(ValueError, "query_or_target_dependent_source_row_forbidden"):
            self.freeze()

    def test_frozen_order_scope_and_query_free_contract(self):
        self.manifest_rows(["f002", "f001"])
        _, protocol = self.freeze(["f001"])
        self.assertEqual(protocol["ids"], ["f001"])
        self.assertEqual(protocol["scope"], "EXPOSED_SMOKE")
        self.assertNotIn("query", protocol)
        self.assertNotIn("target", protocol)
        with self.assertRaisesRegex(ValueError, "assessment_producer_protocol_changed"):
            self.freeze()

    def test_interrupted_attempt_fails_closed(self):
        rows = self.manifest_rows(["f001"])
        _, protocol = self.freeze()
        (self.output / "attempts" / "f001").mkdir(parents=True)
        with patch.object(producer, "_freeze", return_value=({"pdfs": rows}, protocol)), \
                patch.object(producer, "_check_code"), patch.object(producer, "_profile"), \
                patch.object(producer, "_verified_row", return_value=([], [100, 100], "eligible")):
            with self.assertRaisesRegex(ValueError, "unsealed_converter_attempt_requires_reconciliation"):
                producer._run(self.root, self.manifest, self.profile, self.output, None)

    def test_ineligible_row_stays_out_of_consumer_map(self):
        rows = self.manifest_rows(["f001", "f002"])
        _, protocol = self.freeze()
        receipts = []
        for row, state in zip(rows, ("native_error", "empty_native")):
            receipt = {"sample_id": row["sample_id"], "eligibility": state,
                       "state": "ineligible", "assessment_relative": None}
            write_once(self.output / "rows" / (row["sample_id"] + ".json"), receipt)
            receipts.append(receipt)
        with patch.object(producer, "_check_code"), patch.object(producer, "_verify_receipt"):
            result = producer._finalize(self.root, {"pdfs": rows}, protocol, self.output, None)
        mapping, _ = producer._read(self.output / "assessment-map.json")
        self.assertEqual(mapping["entries"], [])
        self.assertEqual(result["eligible_count"], 0)
        self.assertEqual(result["eligibility_counts"], {"empty_native": 1, "native_error": 1})

    def test_forged_or_stale_profile_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "explicit_converter_profile_required"):
            producer._profile(self.root, {"engine": {"name": "docling"}})
        self.manifest_rows(["f001"])
        self.freeze()
        self.profile.write_text('{"changed":true}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "assessment_producer_protocol_changed"):
            self.freeze()

    def test_completed_worker_error_resumes_without_duplicate_conversion(self):
        row = self.manifest_rows(["f001"])[0]
        _, protocol = self.freeze()
        folder = self.output / "attempts" / "f001"
        folder.mkdir(parents=True)
        write_once(folder / "intent.json", {"sample_id": "f001",
            "protocol_sha256": producer.digest(self.output / "protocol.json"),
            **{key + "_sha256": row[key + "_sha256"] for key in ("source", "page", "image", "native")}})
        runtime = {"python": "3.12.10", "executable_sha256": "0" * 64, "packages": {}}
        start_path = self.output / "sessions" / "one" / "start.json"
        start_sha = write_once(start_path, {"worker_pid": 123})
        partial_document_sha = write_once(folder / "document.json", {"texts": [], "body": {"children": []}})
        write_once(folder / "conversion.json", {"status": "error", "error_class": "ConversionError",
            "docling_status": "ConversionStatus.ERROR", "document_sha256": partial_document_sha,
            "worker_pid": 123, "runtime": runtime, "model_called": True,
            "session_start": {"relative": start_path.relative_to(self.root).as_posix(), "sha256": start_sha},
            "wall_seconds": 0.5, "peak_process_memory_bytes": 1000})
        source = self.root / "source.pdf"
        source.write_bytes(b"placeholder")
        session = Mock()
        with patch.object(producer, "_check_code"), \
                patch.object(producer, "_verified_row", return_value=([], [100, 100], "eligible")), \
                patch.object(producer, "source_path", return_value=source), \
                patch.object(producer.SourceGeometry, "from_pdf", return_value=Mock()), \
                patch.object(producer, "assess_document", return_value={"status": "error"}), \
                patch("trace_gc.pdf_structure_parallel_v4.seal", side_effect=lambda value: value), \
                patch.object(producer, "verify_source_bound_assessment"):
            receipt = producer._attempt(self.root, self.output, row, {"runtime": runtime}, protocol, None,
                                        [], [100, 100], session)
        session.convert.assert_not_called()
        self.assertEqual(receipt["state"], "error")
        self.assertEqual(receipt["document_sha256"], partial_document_sha)

    def test_sealed_success_reassessment_can_hold_without_reconversion(self):
        row = self.manifest_rows(["f001"])[0]
        _, protocol = self.freeze()
        folder = self.output / "attempts" / "f001"
        folder.mkdir(parents=True)
        write_once(folder / "intent.json", {"sample_id": "f001",
            "protocol_sha256": producer.digest(self.output / "protocol.json"),
            **{key + "_sha256": row[key + "_sha256"] for key in ("source", "page", "image", "native")}})
        runtime = {"python": "3.12.10", "executable_sha256": "0" * 64, "packages": {}}
        document_sha = write_once(folder / "document.json", {"texts": [], "body": {"children": []}})
        write_once(folder / "conversion.json", {"status": "success", "error_class": None,
            "docling_status": "ConversionStatus.SUCCESS", "document_sha256": document_sha,
            "worker_pid": 123, "runtime": runtime, "model_called": True,
            "session_start": {"relative": "sessions/one/start.json", "sha256": "0" * 64},
            "wall_seconds": 0.5, "peak_process_memory_bytes": 1000})
        source = self.root / "source.pdf"
        source.write_bytes(b"placeholder")
        session = Mock()
        with patch.object(producer, "_check_code"), \
                patch.object(producer, "_verified_row", return_value=([], [100, 100], "eligible")), \
                patch.object(producer, "source_path", return_value=source), \
                patch.object(producer.SourceGeometry, "from_pdf", return_value=Mock()), \
                patch.object(producer, "assess_document", return_value={"status": "uncertain", "proposal": False}), \
                patch("trace_gc.pdf_structure_parallel_v4.seal", side_effect=lambda value: value), \
                patch.object(producer, "verify_source_bound_assessment"):
            receipt = producer._attempt(self.root, self.output, row, {"runtime": runtime}, protocol, None,
                                        [], [100, 100], session)
        session.convert.assert_not_called()
        self.assertEqual(receipt["assessment_status"], "uncertain")
        self.assertEqual(receipt["state"], "complete")
        self.assertEqual(receipt["document_sha256"], document_sha)

    def test_forged_success_converter_status_rejected(self):
        row = self.manifest_rows(["f001"])[0]
        _, protocol = self.freeze()
        attempt = self.output / "attempts" / "f001"
        attempt.mkdir(parents=True)
        write_once(attempt / "intent.json", {"sample_id": "f001",
            "protocol_sha256": producer.digest(self.output / "protocol.json")})
        conversion = {"status": "success", "docling_status": "ConversionStatus.FAILURE",
                      "document_sha256": "0" * 64, "worker_pid": 123,
                      "runtime": {}, "wall_seconds": 0.1, "peak_process_memory_bytes": 10,
                      "session_start": {"relative": "missing.json", "sha256": "0" * 64},
                      "model_called": True, "error_class": None}
        conversion_sha = write_once(attempt / "conversion.json", conversion)
        receipt = {"sample_id": "f001", "protocol_sha256": producer.digest(self.output / "protocol.json"),
                   "eligibility": "eligible", "state": "complete", "conversion_relative":
                   (attempt / "conversion.json").relative_to(self.root).as_posix(),
                   "conversion_sha256": conversion_sha, "document_sha256": "0" * 64,
                   "wall_seconds": 0.1, "source_hashes":
                   {key: row[key + "_sha256"] for key in ("source", "page", "image", "native")}}
        with patch.object(producer, "_verified_row", return_value=([], [100, 100], "eligible")):
            with self.assertRaises((ValueError, FileNotFoundError)):
                producer._verify_receipt(self.root, row, receipt, self.output, None, protocol)

    def test_error_partial_document_retained_without_success_schema(self):
        row = self.manifest_rows(["f001"])[0]
        _, protocol = self.freeze()
        protocol_sha = producer.digest(self.output / "protocol.json")
        source = self.root / "source.pdf"
        source.write_bytes(b"placeholder")
        attempt = self.output / "attempts" / "f001"
        attempt.mkdir(parents=True)
        intent_sha = write_once(attempt / "intent.json", {"sample_id": "f001",
            "protocol_sha256": protocol_sha})
        runtime = {"python": "3.12.10", "executable_sha256": "0" * 64, "packages": {}}
        start_path = self.output / "sessions" / "one" / "start.json"
        start_sha = write_once(start_path, {"schema_version": "retrieval-docling-session-start-v1",
            "protocol_sha256": protocol_sha, "converter_profile_sha256": protocol["profile_sha256"],
            "worker_pid": 123, "runtime": runtime, "code_sha256": protocol["code_sha256"],
            "network_guard": "nonlocal_connect_denied"})
        start = {"relative": start_path.relative_to(self.root).as_posix(), "sha256": start_sha}
        document_sha = write_once(attempt / "document.json", {"broken_partial": ["not a Docling document"]})
        conversion_sha = write_once(attempt / "conversion.json", {"status": "error",
            "docling_status": "ConversionStatus.ERROR", "document_sha256": document_sha,
            "worker_pid": 123, "runtime": runtime, "session_start": start,
            "wall_seconds": 0.5, "peak_process_memory_bytes": 1000,
            "error_class": None, "model_called": True})
        assessment_path = self.output / "assessments" / producer.METHOD / "f001.json"
        assessment_sha = write_once(assessment_path, {"status": "error",
            "conversion_stage": {"input_hashes": {"docling": conversion_sha,
                "docling_document": document_sha}, "attempt_sha256": intent_sha,
                "converter_profile_sha256": protocol["profile_sha256"], "session_start": start}})
        receipt = {"sample_id": "f001", "protocol_sha256": protocol_sha,
            "source_hashes": {key: row[key + "_sha256"] for key in ("source", "page", "image", "native")},
            "eligibility": "eligible", "state": "error", "document_sha256": document_sha,
            "conversion_relative": (attempt / "conversion.json").relative_to(self.root).as_posix(),
            "conversion_sha256": conversion_sha, "wall_seconds": 0.5,
            "assessment_relative": assessment_path.relative_to(self.root).as_posix(),
            "assessment_sha256": assessment_sha, "assessment_status": "error"}
        with patch.object(producer, "_verified_row", return_value=([], [100, 100], "eligible")), \
                patch.object(producer, "source_path", return_value=source), \
                patch.object(producer.SourceGeometry, "from_pdf", return_value=Mock()), \
                patch.object(producer, "verify_source_bound_assessment"), \
                patch("src.parallel_source_v4.extraction.validate_cached_input",
                      side_effect=AssertionError("success schema was applied to error partial")):
            producer._verify_receipt(self.root, row, receipt, self.output, None, protocol)


if __name__ == "__main__":
    unittest.main()
