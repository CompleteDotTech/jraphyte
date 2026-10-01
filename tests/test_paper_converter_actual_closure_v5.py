"""Authored no-converter checks for the historical unknown-PID closure branch."""
from __future__ import annotations

from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from src import paper_converter_reconciliation as rec
from src import paper_converter_smoke as smoke
from src import paper_converter_trusted_application_v1 as application


class ActualEvidenceClosure(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "data"
        self.root.mkdir()
        self.old = self.root / "old"
        self.old.mkdir()
        self.old_intent = {"controller_pid": 71344, "mode": "EXPOSED_DEVELOPMENT",
                           "started_at": "2026-09-30T22:47:00+00:00"}
        self.old_plan = {"mode": "EXPOSED_DEVELOPMENT", "engine": {"name": "docling"},
                         "code_identity": {"controller": rec.HISTORICAL_CONTROLLER_SHA256,
                                           "worker": rec.HISTORICAL_WORKER_SHA256}}
        self.invalidation = {"reason": "FileNotFoundError"}
        (self.old / "stdout.txt").write_text("authored deprecation warning\n")
        (self.old / "stderr.txt").write_text(
            json.dumps({"status": "WORKER_FAILED", "error": "ValueError"}) + "\n")
        (self.old / "INVALIDATED.json").write_text("{}\n")
        self.invalid_pin = smoke.descriptor(self.root, self.old / "INVALIDATED.json")
        evidence = self.root / "closure-observation.json"
        evidence.write_text('{"scope":"AUTHORED current census"}\n')
        observed = "2026-10-01T00:00:00+00:00"
        self.closure = {"version": rec.CLOSURE_VERSION_V2, "recorded_at": observed,
            "intent_sha256": "a" * 64,
            "worker": {"controller_pid": 71344, "worker_pid": None,
                       "current_absence_at": observed,
                       "owned_descendants_zero": True,
                       "evidence": smoke.descriptor(self.root, evidence),
                       "launcher_terminal_evidence": {
                           "controller_source_sha256": rec.HISTORICAL_CONTROLLER_SHA256,
                           "worker_source_sha256": rec.HISTORICAL_WORKER_SHA256,
                           "stdout": smoke.descriptor(self.root, self.old / "stdout.txt"),
                           "stderr": smoke.descriptor(self.root, self.old / "stderr.txt"),
                           "invalidation": self.invalid_pin,
                           "interpretation": "LAUNCHER_TERMINAL_PROVIDER_OUTCOME_UNKNOWN"}},
            "server": {"status": "NOT_APPLICABLE_LOCAL_ENGINE"}}
        self.closure_path = self.root / "closure.json"
        self._write_closure()

    def _write_closure(self):
        self.closure_path.write_text(json.dumps(self.closure, sort_keys=True) + "\n")
        self.closure_pin = smoke.descriptor(self.root, self.closure_path)

    def _verify(self):
        return rec._closure(self.root, self.closure_pin, self.old_intent,
            "a" * 64, self.old_plan, self.invalidation, self.invalid_pin, "old")

    def test_unknown_pid_requires_exact_old_source_and_original_terminal_bytes(self):
        self.assertIsNone(self._verify()["worker"]["worker_pid"])
        self.closure["worker"]["worker_pid"] = 12345
        self._write_closure()
        with self.assertRaisesRegex(ValueError, "unrecorded_pid_closure_scope_differs"):
            self._verify()
        self.closure["worker"]["worker_pid"] = None
        self._write_closure()
        (self.old / "stderr.txt").write_text('{"status":"PASS"}\n')
        with self.assertRaises(ValueError):
            self._verify()

    def test_live_collector_requires_engine_lock_and_rejects_old_runtime_process(self):
        (self.root / "old-python.exe").write_bytes(b"authored interpreter")
        enrollment = {"version": application.VERSION,
                      "status": "ROOT_APPROVED_DISTINCT_SUCCESSOR",
                      "data_root": str(self.root),
                      "authority_sha256": "b" * 64,
                      "old_registry_sha256": "c" * 64,
                      "old_output": "old",
                      "successor_plan_sha256": "d" * 64,
                      "successor_output": "new",
                      "old_runtime_executable_relative": "old-python.exe",
                      "old_intent_started_at": self.old_intent["started_at"],
                      "old_invalidation_at": "2026-09-30T22:48:16+00:00"}
        path = self.root.parent / "ROOT_ENROLLMENT.APPROVED.json"
        path.write_text(json.dumps(enrollment) + "\n")
        app = application.RootEnrolledConverterApplication(self.root, path,
            application._sha(path.read_bytes()))
        proof = {"authority_sha256": "b" * 64,
                 "old_registry_sha256": "c" * 64,
                 "old_output": "old",
                 "old_runtime_executable_relative": "old-python.exe",
                 "successor_plan": {"sha256": "d" * 64},
                 "successor_output": "new",
                 "historical_outcome": "UNKNOWN_UNATTESTED_NO_RETRY",
                 "old_controller_pid": 71344, "old_worker_pid": None,
                 "old_engine": "docling"}
        with self.assertRaisesRegex(RuntimeError, "owned converter engine lock"):
            app._observe(proof)
        wrong_runtime = dict(proof, old_runtime_executable_relative="another-python.exe")
        self.assertFalse(app.verify_authority(wrong_runtime))
        with smoke.engine_lock(self.root):
            with patch.object(application, "current_processes", return_value=[]):
                with app.hold_live_exclusion(self.root, proof) as exclusion:
                    self.assertTrue(exclusion.reobserve()["descendants_absent"])
            old_process = {"pid": 90001, "parent_pid": 0, "name": "python.exe",
                           "executable": str(self.root / "old-python.exe"),
                           "command_line": "other", "created_at": smoke.now()}
            with patch.object(application, "current_processes", return_value=[old_process]):
                with self.assertRaisesRegex(RuntimeError, "possible original converter worker"):
                    app._observe(proof)


if __name__ == "__main__":
    unittest.main()
