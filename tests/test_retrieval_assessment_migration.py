"""Versioned migration guards; no converter, network, or private corpus access."""
from __future__ import annotations

import json
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

from src.parallel_source_v4.common import write_once, digest
from src.parallel_source_v4 import assessment_migration as migration
from src.parallel_source_v4 import assessment_producer as producer
from trace_gc.pdf_source_parallel_v4 import source_lines
try:
    import fitz
except ImportError:
    fitz = None


class MigrationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.old = self.root / "old"
        self.new = self.root / "new"
        self.old.mkdir()
        self.ids = ["a", "b", "c"]
        self.manifest = self.root / "manifest.json"
        self.profile = self.root / "profile.json"
        self.rows = [{"sample_id": sid,
            **{key + "_sha256": "0" * 64 for key in ("source", "page", "image", "native")}}
            for sid in self.ids]
        self.manifest_hash = write_once(self.manifest,
            {"query_independent": True, "pdfs": self.rows})
        self.profile_hash = write_once(self.profile, {"runtime": {"python": "3.12.10",
            "executable_sha256": "1" * 64, "packages": {}}})
        self.old_protocol = {"ids": self.ids, "manifest_relative": "manifest.json",
            "manifest_sha256": self.manifest_hash, "profile_relative": "profile.json",
            "profile_sha256": self.profile_hash, "source_root": None,
            "code_sha256": {"old": "code"}, "evaluator_runtime": {"old": "runtime"}}
        self.old_protocol_hash = write_once(self.old / "protocol.json", self.old_protocol)
        for sid in self.ids[:2]:
            folder = self.old / "attempts" / sid
            intent = {"sample_id": sid, "protocol_sha256": self.old_protocol_hash,
                **{key + "_sha256": "0" * 64 for key in ("source", "page", "image", "native")}}
            write_once(folder / "intent.json", intent)
            document_hash = write_once(folder / "document.json", {"texts": []})
            write_once(folder / "conversion.json", {"status": "success",
                "docling_status": "ConversionStatus.SUCCESS", "model_called": True,
                "document_sha256": document_hash, "error_class": None})
        self.row_hash = write_once(self.old / "rows" / "a.json", {"sample_id": "a"})

    def audit(self):
        return {"origin_protocol_sha256": self.old_protocol_hash,
                "completed_rows": 1, "row_hashes": [["a", self.row_hash]]}

    def test_sealed_prefix_and_one_pending_conversion(self):
        records = migration._origin_records(self.root, self.old, self.old_protocol)
        self.assertEqual([r["sample_id"] for r in records], ["a", "b"])
        self.assertIsNone(records[-1]["origin_receipt_sha256"])
        with patch.object(migration, "_origin_audit", return_value=self.audit()), \
                patch.object(migration, "method_hashes", return_value={"new": "code"}), \
                patch.object(migration, "runtime_receipt", return_value={"new": "runtime"}):
            path, plan = migration.prepare_plan(self.root, self.old, self.new,
                self.root / "frozen", self.root / "python.exe", "a" * 40,
                self.old_protocol_hash, 2)
        self.assertEqual(plan["imports"], records)
        self.assertEqual(plan["origin_rows_source_replayed"], 1)
        self.assertEqual(plan["new_model_calls_for_imports"], 0)
        self.assertEqual(json.loads(path.read_text())["origin_protocol_sha256"],
                         self.old_protocol_hash)

    def test_unknown_later_attempt_and_unsealed_pending_fail_closed(self):
        later = self.old / "attempts" / "c"
        later.mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, "later_origin_work_requires_reconciliation"):
            migration._origin_records(self.root, self.old, self.old_protocol)
        later.rmdir()
        (self.old / "attempts" / "b" / "conversion.json").unlink()
        with self.assertRaises(FileNotFoundError):
            migration._origin_records(self.root, self.old, self.old_protocol)

    def test_frozen_audit_must_match_exact_prefix(self):
        wrong = {"origin_protocol_sha256": self.old_protocol_hash,
                 "completed_rows": 1, "row_hashes": [["a", "f" * 64]]}
        with patch.object(migration, "_origin_audit", return_value=wrong):
            with self.assertRaisesRegex(ValueError, "frozen_source_replay_mismatch"):
                migration.prepare_plan(self.root, self.old, self.new,
                    self.root / "frozen", self.root / "python.exe", "a" * 40,
                    self.old_protocol_hash, 2)
        self.assertFalse(self.new.exists())

    def test_imported_receipt_requires_origin_paths_and_no_new_model_call(self):
        record = migration._origin_records(self.root, self.old, self.old_protocol)[0]
        plan = {"schema_version": migration.VERSION, "origin_run_relative": "old",
            "origin_protocol_sha256": self.old_protocol_hash, "manifest_sha256": self.manifest_hash,
            "profile_sha256": self.profile_hash, "source_root": None,
            "new_code_sha256": {"new": "code"}, "imports": [record]}
        plan_path = self.root / "plan.json"
        plan_hash = write_once(plan_path, plan)
        protocol = {"code_sha256": {"new": "code"}, "manifest_sha256": self.manifest_hash,
            "profile_sha256": self.profile_hash, "source_root": None,
            "migration": {"relative": "plan.json", "sha256": plan_hash}}
        receipt = {"migration_sha256": plan_hash,
            "conversion_relative": "forged/conversion.json",
            "assessment_relative": "new/assessments/parallel_structure_v4/a.json"}
        with self.assertRaisesRegex(ValueError, "migration_row_artifact_path_mismatch"):
            migration.verify_migrated_receipt(self.root, self.rows[0], receipt,
                self.new, None, protocol, [], [100, 100])

    @unittest.skipUnless(fitz, "optional PyMuPDF required for source replay")
    def test_import_crash_resume_reuses_conversion_without_model_call(self):
        with fitz.open() as pdf:
            page = pdf.new_page(width=595, height=842)
            page.insert_text((40, 60), "Abstract", fontsize=12)
            payload = pdf.tobytes()
        with fitz.open(stream=payload, filetype="pdf") as pdf:
            native = source_lines(pdf[0])
        source_hash = hashlib.sha256(payload).hexdigest()
        (self.root / "source.pdf").write_bytes(payload)
        row = {"sample_id": "a", "physical_page": 1, "source_relative": "source.pdf",
            "source_root_id": "data_root", "source_sha256": source_hash,
            **{key + "_sha256": "0" * 64 for key in ("page", "image", "native")}}
        runtime = json.loads(self.profile.read_text())["runtime"]
        converter_runtime = {key: runtime[key] for key in ("python", "executable_sha256", "packages")}
        start_path = self.root / "old" / "sessions" / "one" / "start.json"
        start_hash = write_once(start_path, {"protocol_sha256": self.old_protocol_hash,
            "code_sha256": self.old_protocol["code_sha256"],
            "converter_profile_sha256": self.profile_hash, "worker_pid": 42,
            "runtime": converter_runtime, "network_guard": "nonlocal_connect_denied"})
        attempt = self.old / "attempts" / "a"
        (attempt / "intent.json").unlink()
        (attempt / "conversion.json").unlink()
        (attempt / "document.json").unlink()
        write_once(attempt / "intent.json", {"sample_id": "a",
            "protocol_sha256": self.old_protocol_hash,
            **{key + "_sha256": row[key + "_sha256"]
               for key in ("source", "page", "image", "native")}})
        write_once(attempt / "conversion.json", {"status": "error",
            "docling_status": "ConversionStatus.ERROR", "document_sha256": None,
            "error_class": "ConversionError", "worker_pid": 42,
            "runtime": converter_runtime, "model_called": True,
            "session_start": {"relative": start_path.relative_to(self.root).as_posix(),
                              "sha256": start_hash}, "wall_seconds": 0.2})
        record = {
            "sample_id": "a", "origin_receipt_sha256": None,
            "origin_intent_sha256": digest(attempt / "intent.json"),
            "origin_conversion_sha256": digest(attempt / "conversion.json"),
            "origin_document_sha256": None}
        plan = {"schema_version": migration.VERSION, "ids": ["a"],
            "origin_run_relative": "old", "origin_protocol_sha256": self.old_protocol_hash,
            "profile_relative": "profile.json", "profile_sha256": self.profile_hash,
            "manifest_sha256": self.manifest_hash, "source_root": None,
            "new_code_sha256": {"new": "code"},
            "new_evaluator_runtime": {"new": "runtime"}, "imports": [record]}
        plan_hash = write_once(self.root / "plan.json", plan)
        self.new.mkdir()
        protocol = {"ids": ["a"], "code_sha256": plan["new_code_sha256"],
            "evaluator_runtime": plan["new_evaluator_runtime"],
            "manifest_sha256": self.manifest_hash, "profile_sha256": self.profile_hash,
            "source_root": None, "migration": {"relative": "plan.json", "sha256": plan_hash}}
        write_once(self.new / "protocol.json", protocol)
        manifest = {"pdfs": [row]}
        real_write = migration.write_once
        crashed = False
        def crash_before_row(path, value):
            nonlocal crashed
            if path == self.new / "rows" / "a.json" and not crashed:
                crashed = True
                raise RuntimeError("simulated_crash_after_assessment")
            return real_write(path, value)
        with patch.object(producer, "_verified_row", return_value=(native, [595, 842], "eligible")), \
                patch.object(producer, "_check_code"), \
                patch.object(migration, "write_once", side_effect=crash_before_row):
            with self.assertRaisesRegex(RuntimeError, "simulated_crash_after_assessment"):
                migration._initialize_imports(self.root, self.new, manifest, protocol, None)
        assessment_path = self.new / "assessments" / producer.METHOD / "a.json"
        first_hash = digest(assessment_path)
        self.assertFalse((self.new / "rows" / "a.json").exists())
        with patch.object(producer, "_verified_row", return_value=(native, [595, 842], "eligible")), \
                patch.object(producer, "_check_code"):
            migration._initialize_imports(self.root, self.new, manifest, protocol, None)
            migration._initialize_imports(self.root, self.new, manifest, protocol, None)
        receipt = migration._read(self.new / "rows" / "a.json")
        self.assertEqual(digest(assessment_path), first_hash)
        self.assertFalse(receipt["new_model_call"])
        self.assertEqual(receipt["conversion_sha256"], record["origin_conversion_sha256"])
        self.assertFalse((self.new / "attempts").exists())
        with self.assertRaisesRegex(ValueError, "migration_new_protocol_changed"):
            migration._initialize_imports(self.root, self.new, manifest,
                {**protocol, "evaluator_runtime": {"changed": True}}, None)
        original_conversion = (attempt / "conversion.json").read_bytes()
        (attempt / "conversion.json").write_bytes(b"{}")
        with patch.object(producer, "_verified_row", return_value=(native, [595, 842], "eligible")):
            with self.assertRaises(ValueError):
                migration._initialize_imports(self.root, self.new, manifest, protocol, None)
        (attempt / "conversion.json").write_bytes(original_conversion)
        alternate = {**plan, "origin_run_relative": "different-origin"}
        alternate_hash = write_once(self.root / "alternate-plan.json", alternate)
        alternate_protocol = {**protocol,
            "migration": {"relative": "alternate-plan.json", "sha256": alternate_hash}}
        with patch.object(producer, "_verified_row", return_value=(native, [595, 842], "eligible")):
            with self.assertRaises(ValueError):
                migration._initialize_imports(self.root, self.new, manifest, alternate_protocol, None)
        (self.root / "source.pdf").write_bytes(b"changed")
        with patch.object(producer, "_verified_row", return_value=(native, [595, 842], "eligible")), \
                patch.object(producer, "_check_code"):
            with self.assertRaises(ValueError):
                migration._initialize_imports(self.root, self.new, manifest, protocol, None)


if __name__ == "__main__":
    unittest.main()
