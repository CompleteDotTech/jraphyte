"""No-converter negatives for the disabled V6 application effect boundary."""
from __future__ import annotations

from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from src import paper_converter_smoke as smoke
from src import paper_converter_trusted_application_v1 as application


class ActualClosureV6(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "data"
        self.root.mkdir()
        (self.root / "old").mkdir()
        (self.root / "old-python.exe").write_bytes(b"authored")
        enrollment = {
            "version": application.VERSION,
            "status": "ROOT_APPROVED_DISTINCT_SUCCESSOR",
            "data_root": str(self.root),
            "authority_sha256": "a" * 64,
            "old_registry_sha256": "b" * 64,
            "old_output": "old",
            "successor_plan_sha256": "c" * 64,
            "successor_output": "new",
            "old_runtime_executable_relative": "old-python.exe",
            "old_intent_started_at": "2026-09-30T22:47:00+00:00",
            "old_invalidation_at": "2026-09-30T22:48:16+00:00",
        }
        path = self.root.parent / "authored-enrollment.json"
        path.write_text(json.dumps(enrollment))
        self.app = application.RootEnrolledConverterApplication(
            self.root, path, application._sha(path.read_bytes()))
        self.proof = {
            "authority_sha256": "a" * 64,
            "old_registry_sha256": "b" * 64,
            "old_output": "old",
            "successor_plan": {"sha256": "c" * 64},
            "successor_output": "new",
            "old_runtime_executable_relative": "old-python.exe",
            "old_controller_pid": 71344,
            "old_worker_pid": None,
            "old_engine": "docling",
            "historical_outcome": "UNKNOWN_UNATTESTED_NO_RETRY",
        }

    def test_fake_capability_cannot_start(self):
        class Fake:
            def verify_authority(self, proof):
                return True

            def hold_live_exclusion(self, root, proof):
                raise AssertionError("effect must not reach fake exclusion")

        kwargs = {"authority_relative": "a.json", "authority_sha256": "a" * 64,
                  "receipt_relative": "r.json", "receipt_sha256": "b" * 64}
        with self.assertRaisesRegex(ValueError,
                                    "root_owned_concrete_application_required"):
            smoke.execute_successor(self.root, {"sha256": "c" * 64}, "new",
                                    trusted_application=Fake(), **kwargs)
        self.assertFalse((self.root / "new").exists())

    def test_docling_only_and_opaque_python_process_hold(self):
        self.assertTrue(self.app.verify_authority(self.proof))
        self.assertFalse(self.app.verify_authority(dict(self.proof, old_engine="grobid")))
        process = {"pid": 90001, "parent_pid": 0, "name": "python.exe",
                   "executable": "C:/Python/python.exe", "command_line": "",
                   "created_at": smoke.now()}
        with smoke.engine_lock(self.root):
            with patch.object(application, "current_processes", return_value=[process]):
                with self.assertRaisesRegex(RuntimeError,
                                            "Python process identity unavailable"):
                    self.app._observe(self.proof)
            process["command_line"] = "unrelated"
            process["created_at"] = None
            with patch.object(application, "current_processes", return_value=[process]):
                with self.assertRaisesRegex(RuntimeError,
                                            "Python process identity unavailable"):
                    self.app._observe(self.proof)


if __name__ == "__main__":
    unittest.main()
