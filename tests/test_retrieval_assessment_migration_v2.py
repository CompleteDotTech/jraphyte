"""Failure boundaries for the sealed-prefix assessment migration."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from src.parallel_source_v4 import assessment_migration_v2 as migration
from src.parallel_source_v4 import assessment_producer as producer
from src.parallel_source_v4.common import digest, write_once

try:
    import fitz
    from trace_gc.pdf_source_parallel_v4 import source_lines
    from trace_gc.pdf_structure_parallel_v4 import seal
except ImportError:
    fitz = None


class PrefixInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.origin = self.root / "old"
        self.checkout = self.root / "checkout"
        self.old_source = self.checkout / "src/parallel_source_v4/assessment_producer.py"
        self.old_source.parent.mkdir(parents=True)
        self.old_source.write_text("frozen", encoding="utf-8")
        (self.origin / "rows").mkdir(parents=True)
        (self.origin / "attempts/d00002").mkdir(parents=True)
        (self.origin / "protocol.json").write_text("{}", encoding="utf-8")
        self.protocol = {"ids": ["d00001", "d00002", "d00003"],
                         "origin_checkout": str(self.checkout),
                         "code_sha256": {"src/parallel_source_v4/assessment_producer.py": digest(self.old_source)}}
        self.receipt = {"sample_id": "d00001", "protocol_sha256": digest(self.origin / "protocol.json"),
                        "eligibility": "ineligible", "state": "ineligible",
                        "assessment_relative": None, "assessment_sha256": None}
        (self.origin / "rows/d00001.json").write_text(json.dumps(self.receipt), encoding="utf-8")

    def test_exact_empty_pre_intent_prefix(self):
        records = migration._prefix(self.root, self.origin, self.protocol, 1)
        self.assertEqual([r["sample_id"] for r in records], ["d00001"])

    def test_unknown_or_later_attempt_holds(self):
        (self.origin / "attempts/d00003").mkdir()
        with self.assertRaisesRegex(ValueError, "later_or_unknown_attempt"):
            migration._prefix(self.root, self.origin, self.protocol, 1)

    def test_intent_or_hidden_file_in_next_attempt_holds(self):
        (self.origin / "attempts/d00002/.intent.tmp").write_text("pending", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "next_attempt_not_plain_empty"):
            migration._prefix(self.root, self.origin, self.protocol, 1)

    def test_changed_call_order_source_holds(self):
        self.old_source.write_text("different", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "call_order_code_unverified"):
            migration._prefix(self.root, self.origin, self.protocol, 1)

    def test_fresh_output_cannot_be_inside_or_above_origin(self):
        for output in (self.origin / "new", self.root):
            with self.subTest(output=output), self.assertRaisesRegex(ValueError, "fresh_distinct"):
                migration.prepare_plan(self.root, self.origin, output, self.checkout,
                    self.root / "python", "head", digest(self.origin / "protocol.json"), 1, 64)


class GateTests(unittest.TestCase):
    def test_no_gate_cannot_reach_converter(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime = {"fixture": "no_gate_without_optional_pdf_dependencies"}
            plan = {"new_code_sha256": migration.method_hashes(migration.REPO),
                    "new_evaluator_runtime": runtime}
            (root / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
            with patch.object(migration, "runtime_receipt", return_value=runtime), \
                 patch.object(migration, "prepare_plan", return_value=(root / "plan.json", plan)), \
                 patch.object(migration.producer, "_run", side_effect=AssertionError("converter reached")):
                result = migration.run(root, root / "origin", root / "output", root / "old",
                    root / "python", "head", "0" * 64, 1, 64)
                self.assertEqual(result["status"], "PLAN_PREPARED_NO_MODEL_CALL")

    def test_drained_cli_has_distinct_exit_code(self):
        with tempfile.TemporaryDirectory() as temporary:
            args = ["migration_v2", "run", "--data-root", temporary,
                "--origin-output", "origin", "--new-output", "new",
                "--origin-checkout", temporary, "--origin-interpreter", str(Path(temporary) / "python"),
                "--origin-head", "head", "--origin-protocol-sha256", "0" * 64,
                "--expected-prefix-count", "1", "--gate-receipt", "receipt.json",
                "--gate-receipt-sha256", "0" * 64, "--gate-policy", "policy.json",
                "--gate-policy-sha256", "0" * 64, "--gate-configuration", "config.json",
                "--gate-source-map", "map.json"]
            with patch.object(sys, "argv", args), patch.object(migration, "run",
                    return_value={"status": "STOPPED_DRAINED"}):
                self.assertEqual(migration.main(), 4)


@unittest.skipUnless(fitz, "PyMuPDF required for real source geometry")
class MixedImportTests(unittest.TestCase):
    def test_reassess_mixed_origin_crash_resume_without_model_call(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            origin, output = root / "origin", root / "new"
            with fitz.open() as pdf:
                page = pdf.new_page(width=595, height=842)
                page.insert_text((40, 60), "Abstract", fontsize=12)
                payload = pdf.tobytes()
            (root / "source.pdf").write_bytes(payload)
            with fitz.open(stream=payload, filetype="pdf") as pdf:
                native = source_lines(pdf[0])
            rows = []
            records = []
            originals = {}
            for sid, old_schema in (("a", "retrieval-assessment-migrated-row-v1"),
                                    ("b", "retrieval-assessment-row-v1")):
                row = {"sample_id": sid, "physical_page": 1, "source_relative": "source.pdf",
                       "source_root_id": "data_root", "source_sha256": digest(root / "source.pdf"),
                       **{key + "_sha256": "0" * 64 for key in ("page", "image", "native")}}
                rows.append(row)
                folder = origin / "attempts" / sid
                conversion = {"status": "error", "wall_seconds": 0.2,
                              "session_start": {"relative": "origin/session.json", "sha256": "0" * 64}}
                conversion_sha = write_once(folder / "conversion.json", conversion)
                old_receipt = {"schema_version": old_schema, "sample_id": sid,
                               "eligibility": "eligible", "state": "error",
                               "conversion_relative": (folder / "conversion.json").relative_to(root).as_posix(),
                               "conversion_sha256": conversion_sha, "document_sha256": None,
                               "assessment_relative": "origin/old-assessment-" + sid + ".json",
                               "assessment_sha256": "1" * 64}
                originals[sid] = old_receipt
                records.append({"sample_id": sid, "origin_row_sha256": "2" * 64,
                                "eligibility": "eligible", "state": "error",
                                "assessment_relative": old_receipt["assessment_relative"],
                                "assessment_sha256": old_receipt["assessment_sha256"]})
            plan = {"schema_version": migration.VERSION, "ids": ["a", "b"],
                    "origin_run_relative": "origin", "origin_protocol_sha256": "3" * 64,
                    "profile_sha256": "4" * 64, "manifest_sha256": "5" * 64,
                    "source_root": None, "new_code_sha256": {"current": "code"},
                    "new_evaluator_runtime": {"runtime": "current"},
                    "new_max_documents_per_session": 64, "imports": records}
            plan_sha = write_once(root / "plan.json", plan)
            protocol = {"ids": plan["ids"], "code_sha256": plan["new_code_sha256"],
                        "evaluator_runtime": plan["new_evaluator_runtime"],
                        "manifest_sha256": plan["manifest_sha256"],
                        "profile_sha256": plan["profile_sha256"], "source_root": None,
                        "converter_session": {"max_documents": 64}, "scope": "FULL_CORPUS",
                        "extractor_version": "test-source-version",
                        "migration": {"relative": "plan.json", "sha256": plan_sha}}
            write_once(output / "protocol.json", protocol)
            manifest = {"pdfs": rows}
            real_write = migration.write_once
            crashed = False

            def crash_before_row(path, value):
                nonlocal crashed
                if path == output / "rows/a.json" and not crashed:
                    crashed = True
                    raise RuntimeError("crash_after_reassessment_before_row")
                return real_write(path, value)

            def old_receipt(_root, _plan, record, _row):
                return originals[record["sample_id"]], {}

            with patch.object(migration, "_origin_receipt", side_effect=old_receipt), \
                 patch.object(producer, "_verified_row", return_value=(native, [595, 842], "eligible")), \
                 patch.object(producer, "_check_code"), \
                 patch.object(migration, "write_once", side_effect=crash_before_row):
                with self.assertRaisesRegex(RuntimeError, "crash_after_reassessment_before_row"):
                    migration._initialize(root, output, manifest, protocol, None)
            first_assessment = digest(output / "assessments" / producer.METHOD / "a.json")
            with patch.object(migration, "_origin_receipt", side_effect=old_receipt), \
                 patch.object(producer, "_verified_row", return_value=(native, [595, 842], "eligible")), \
                 patch.object(producer, "_check_code"):
                migration._initialize(root, output, manifest, protocol, None)
                migration._initialize(root, output, manifest, protocol, None)
            self.assertEqual(digest(output / "assessments" / producer.METHOD / "a.json"), first_assessment)
            receipts = [migration._read(output / "rows" / (sid + ".json")) for sid in ("a", "b")]
            self.assertTrue(all(r["new_model_call"] is False for r in receipts))
            self.assertFalse((output / "attempts").exists())
            self.assertEqual([r["state"] for r in receipts], ["error", "error"])
            self.assertEqual({r["sample_id"] for r in receipts}, {"a", "b"})
            # The final map must include both current assessments, never stale origin files.
            with patch.object(migration, "_origin_receipt", side_effect=old_receipt), \
                 patch.object(producer, "_verified_row", return_value=(native, [595, 842], "eligible")), \
                 patch.object(producer, "_check_code"):
                summary = producer._finalize(root, manifest, protocol, output, None)
            self.assertEqual(summary["status"], "COMPLETE")
            mapping = migration._read(output / "assessment-map.json")
            self.assertEqual({entry["sample_id"] for entry in mapping["entries"]}, {"a", "b"})
            self.assertTrue(all(entry["assessment_relative"].startswith("new/") for entry in mapping["entries"]))
            assessment_path = output / "assessments" / producer.METHOD / "a.json"
            assessment = migration._read(assessment_path)
            assessment["conversion_stage"]["wall_seconds"] = 999.0
            seal(assessment)
            assessment_path.write_text(json.dumps(assessment), encoding="utf-8")
            row_path = output / "rows/a.json"
            changed_row = migration._read(row_path)
            changed_row["assessment_sha256"] = digest(assessment_path)
            row_path.write_text(json.dumps(changed_row), encoding="utf-8")
            with patch.object(migration, "_origin_receipt", side_effect=old_receipt), \
                 patch.object(producer, "_verified_row", return_value=(native, [595, 842], "eligible")):
                with self.assertRaisesRegex(ValueError, "sealed_prefix_reassessment_lineage_changed"):
                    producer._verify_receipt(root, rows[0], changed_row, output, None, protocol)


if __name__ == "__main__":
    unittest.main()
