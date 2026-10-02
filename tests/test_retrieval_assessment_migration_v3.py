"""Mixed prefix plus sealed pending conversion; no converter or corpus access."""
from __future__ import annotations

import json
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.parallel_source_v4 import assessment_migration_v3 as migration
from src.parallel_source_v4 import assessment_producer as producer
from src.parallel_source_v4.common import digest, write_once

try:
    import fitz
    from trace_gc.pdf_source_parallel_v4 import source_lines
except ImportError:
    fitz = None


class PendingInventoryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.origin = self.root / "old"
        self.checkout = self.root / "checkout"
        source = self.checkout / "src/parallel_source_v4/assessment_producer.py"
        source.parent.mkdir(parents=True)
        source.write_text("frozen", encoding="utf-8")
        self.protocol = {"ids": ["a", "b", "c"], "code_sha256": {
            "src/parallel_source_v4/assessment_producer.py": digest(source)},
            "manifest_relative": "manifest.json", "manifest_sha256": "0" * 64,
            "profile_relative": "profile.json", "profile_sha256": "1" * 64,
            "source_root": None, "query_independent": True, "scope": "FULL_CORPUS"}
        self.protocol_sha = write_once(self.origin / "protocol.json", self.protocol)
        self.protocol["stopped_execution_checkout"] = str(self.checkout)
        for sid in ("a", "b"):
            write_once(self.origin / "rows" / (sid + ".json"), {
                "sample_id": sid, "protocol_sha256": self.protocol_sha,
                "eligibility": "ineligible", "state": "ineligible",
                "assessment_relative": None, "assessment_sha256": None})
        self.pending = self.origin / "attempts" / "c"
        write_once(self.pending / "intent.json", {"sample_id": "c",
            "protocol_sha256": self.protocol_sha})
        document_sha = write_once(self.pending / "document.json", {"texts": [], "body": {"children": []}})
        write_once(self.pending / "conversion.json", {"status": "success",
            "docling_status": "ConversionStatus.SUCCESS", "model_called": True,
            "error_class": None, "document_sha256": document_sha})

    def test_exact_mixed_prefix_and_one_sealed_pending(self):
        records, pending = migration._prefix(self.root, self.origin, self.protocol, 2)
        self.assertEqual([r["sample_id"] for r in records], ["a", "b"])
        self.assertEqual(pending["sample_id"], "c")
        self.assertEqual(pending["origin_document_sha256"], digest(self.pending / "document.json"))
        self.assertIsNone(pending["origin_receipt_sha256"])

    def test_partial_or_extra_pending_holds(self):
        (self.pending / "document.json").unlink()
        with self.assertRaisesRegex(ValueError, "next_attempt_not_exact"):
            migration._prefix(self.root, self.origin, self.protocol, 2)
        write_once(self.pending / "document.json", {"texts": []})
        (self.pending / "worker-failure.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "next_attempt_not_exact"):
            migration._prefix(self.root, self.origin, self.protocol, 2)

    def test_changed_pending_document_holds(self):
        (self.pending / "document.json").write_text('{"texts":[{"text":"forged"}]}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "expected|hash"):
            migration._prefix(self.root, self.origin, self.protocol, 2)

    def test_later_attempt_holds(self):
        (self.origin / "attempts" / "later").mkdir()
        with self.assertRaisesRegex(ValueError, "later_or_unknown_attempt"):
            migration._prefix(self.root, self.origin, self.protocol, 2)

    def test_origin_producer_code_drift_holds(self):
        (self.checkout / "src/parallel_source_v4/assessment_producer.py").write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "call_order_code_unverified"):
            migration._prefix(self.root, self.origin, self.protocol, 2)

    def test_nested_checkout_cannot_substitute_stopped_execution_checkout(self):
        nested = self.root / "historical-nested-origin"
        source = nested / "src/parallel_source_v4/assessment_producer.py"
        source.parent.mkdir(parents=True)
        source.write_text("historical different producer", encoding="utf-8")
        self.protocol["stopped_execution_checkout"] = str(nested)
        with self.assertRaisesRegex(ValueError, "call_order_code_unverified"):
            migration._prefix(self.root, self.origin, self.protocol, 2)


class StageGuardTests(unittest.TestCase):
    def test_nested_v2_prefix_resolves_authenticated_converter_leaf(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan_sha = write_once(root / "old-v2-plan.json", {
                "schema_version": migration.migration_v2.VERSION,
                "imports": [{"sample_id": "a", "origin_row_sha256": "1" * 64}]})
            imported = {"schema_version": migration.migration_v2.ROW_VERSION,
                "sample_id": "a", "eligibility": "eligible"}
            protocol = {"migration": {"relative": "old-v2-plan.json", "sha256": plan_sha}}
            leaf = {"sample_id": "a", "eligibility": "eligible",
                "conversion_relative": "origin/attempts/a/conversion.json",
                "conversion_sha256": "2" * 64, "document_sha256": "3" * 64}
            with patch.object(migration.migration_v2, "_origin_receipt", return_value=(leaf, {})):
                self.assertEqual(migration._leaf_conversion_receipt(root, imported, protocol,
                    {"sample_id": "a"}), leaf)
            with patch.object(migration.migration_v2, "_origin_receipt", return_value=(imported, protocol)):
                with self.assertRaisesRegex(ValueError, "cycle"):
                    migration._leaf_conversion_receipt(root, imported, protocol, {"sample_id": "a"})

    def test_prepare_cannot_call_converter(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan = {"new_code_sha256": migration.method_hashes(migration.REPO),
                    "new_evaluator_runtime": {"fixture": "runtime"}}
            plan_path = root / "plan.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            with patch.object(migration, "prepare_plan", return_value=(plan_path, plan)), \
                 patch.object(migration, "runtime_receipt", return_value=plan["new_evaluator_runtime"]), \
                 patch.object(producer, "_run", side_effect=AssertionError("converter_called")):
                result = migration.run(root, root / "origin", root / "new", root / "old",
                    root / "python.exe", "a" * 40, "0" * 64, 2, 64)
            self.assertEqual(result["status"], "PLAN_PREPARED_NO_MODEL_CALL")

    def test_pending_import_cannot_claim_new_model_call(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "new"
            record = {"sample_id": "c", "origin_receipt_sha256": None,
                "origin_intent_sha256": "1" * 64, "origin_conversion_sha256": "2" * 64,
                "origin_document_sha256": "3" * 64}
            plan = {"schema_version": migration.VERSION, "pending_sealed_conversion": record,
                "new_code_sha256": {"code": "new"}, "manifest_sha256": "4" * 64,
                "profile_sha256": "5" * 64, "source_root": None,
                "new_max_documents_per_session": 64, "origin_protocol_sha256": "6" * 64}
            plan_sha = write_once(root / "plan.json", plan)
            protocol = {"code_sha256": plan["new_code_sha256"], "manifest_sha256": plan["manifest_sha256"],
                "profile_sha256": plan["profile_sha256"], "source_root": None,
                "converter_session": {"max_documents": 64},
                "migration": {"relative": "plan.json", "sha256": plan_sha}}
            write_once(output / "protocol.json", protocol)
            row = {"sample_id": "c", **{key + "_sha256": "0" * 64
                for key in ("source", "page", "image", "native")}}
            receipt = {"schema_version": migration.PENDING_ROW_VERSION, "sample_id": "c",
                "new_model_call": True}
            # Use a benign mocked origin conversion to reach exact receipt
            # comparison without any real converter or source access.
            with patch.object(migration, "_pending_origin", return_value=(
                    {"status": "success"}, {"texts": []})):
                with self.assertRaisesRegex(ValueError, "pending_import_row_lineage_changed"):
                    migration.verify_pending_receipt(root, row, receipt, output, None,
                        protocol, [], [100, 100])


@unittest.skipUnless(fitz, "PyMuPDF required for actual source geometry")
class ReassessmentTests(unittest.TestCase):
    def test_import_pending_cached_document_crash_resume_no_converter(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            origin, output = root / "origin", root / "new"
            with fitz.open() as pdf:
                page = pdf.new_page(width=595, height=842)
                page.insert_text((40, 60), "Abstract", fontsize=12)
                payload = pdf.tobytes()
            source = root / "source.pdf"
            source.write_bytes(payload)
            with fitz.open(stream=payload, filetype="pdf") as pdf:
                native = source_lines(pdf[0])
            rows = [{"sample_id": sid, "physical_page": 1, "source_relative": "source.pdf",
                "source_root_id": "data_root", "source_sha256": hashlib.sha256(payload).hexdigest(),
                **{key + "_sha256": "0" * 64 for key in ("page", "image", "native")}}
                for sid in ("a", "b")]
            original = {"sample_id": "a", "eligibility": "ineligible", "state": "ineligible",
                "assessment_relative": None, "assessment_sha256": None}
            record = {"sample_id": "b", "origin_receipt_sha256": None,
                "origin_intent_sha256": "1" * 64, "origin_conversion_sha256": "2" * 64,
                "origin_document_sha256": "3" * 64}
            plan = {"schema_version": migration.VERSION, "ids": ["a", "b"],
                "imports": [{"sample_id": "a", "origin_row_sha256": "4" * 64,
                    "eligibility": "ineligible", "state": "ineligible",
                    "assessment_relative": None, "assessment_sha256": None}],
                "pending_sealed_conversion": record,
                "origin_run_relative": "origin", "origin_protocol_sha256": "5" * 64,
                "new_code_sha256": {"code": "new"},
                "new_evaluator_runtime": {"runtime": "new"},
                "manifest_sha256": "6" * 64, "profile_sha256": "7" * 64,
                "source_root": None, "new_max_documents_per_session": 64}
            plan_sha = write_once(root / "plan.json", plan)
            protocol = {"ids": ["a", "b"], "code_sha256": plan["new_code_sha256"],
                "evaluator_runtime": plan["new_evaluator_runtime"],
                "manifest_sha256": plan["manifest_sha256"],
                "profile_sha256": plan["profile_sha256"], "source_root": None,
                "converter_session": {"max_documents": 64}, "scope": "FULL_CORPUS",
                "migration": {"relative": "plan.json", "sha256": plan_sha}}
            write_once(output / "protocol.json", protocol)
            conversion = {"status": "success", "session_start": {"relative": "origin/session.json",
                "sha256": "8" * 64}, "wall_seconds": 0.2}
            document = {"texts": [], "body": {"children": []}}
            real_write = migration.write_once
            tripped = False

            def crash_after_assessment(path, value):
                nonlocal tripped
                if path == output / "rows/b.json" and not tripped:
                    tripped = True
                    raise RuntimeError("interrupted_before_pending_row")
                return real_write(path, value)

            def verified(_root, row, _source_root):
                return native, [595, 842], "ineligible" if row["sample_id"] == "a" else "eligible"

            patches = (patch.object(migration, "_origin_receipt", return_value=(original, {})),
                patch.object(migration, "_pending_origin", return_value=(conversion, document)),
                patch.object(producer, "_verified_row", side_effect=verified),
                patch.object(producer, "_check_code"))
            with patches[0], patches[1], patches[2], patches[3], \
                 patch.object(migration, "write_once", side_effect=crash_after_assessment):
                with self.assertRaisesRegex(RuntimeError, "interrupted_before_pending_row"):
                    migration._initialize(root, output, {"pdfs": rows}, protocol, None)
            pending_assessment = output / "assessments" / producer.METHOD / "b.json"
            prior_sha = digest(pending_assessment)
            with patches[0], patches[1], patches[2], patches[3], \
                 patch.object(producer, "ConverterSession", side_effect=AssertionError("converter_constructed")):
                migration._initialize(root, output, {"pdfs": rows}, protocol, None)
                migration._initialize(root, output, {"pdfs": rows}, protocol, None)
            self.assertEqual(digest(pending_assessment), prior_sha)
            pending_row = migration._read(output / "rows/b.json")
            self.assertEqual(pending_row["schema_version"], migration.PENDING_ROW_VERSION)
            self.assertIs(pending_row["new_model_call"], False)
            self.assertFalse((output / "attempts").exists())


if __name__ == "__main__":
    unittest.main()
