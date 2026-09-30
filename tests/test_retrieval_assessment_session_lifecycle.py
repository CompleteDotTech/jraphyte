"""Bounded resident converter control; no converter or model calls."""
from __future__ import annotations

import tempfile
import unittest
import contextlib
import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

from src.parallel_source_v4 import assessment_producer as producer
from src.parallel_source_v4 import assessment_migration as migration
from src.parallel_source_v4.common import write_once


class SessionLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / "run"
        self.output.mkdir()
        write_once(self.output / "protocol.json", {"identity": "fixed", "converter_session": {
            "drain": "external_request_after_verified_row_v1", "max_documents": 64,
            "drain_timeout_seconds": 30}})

    def request(self, request_id="a" * 32):
        request = {"version": "assessment-graceful-drain-v1", "request_id": request_id,
                   "protocol_sha256": producer.digest(self.output / "protocol.json"),
                   "requested_at": "2026-09-30T00:00:00Z"}
        path = self.output / "control" / "drain-requests" / (request_id + ".json")
        write_once(path, request)
        return path

    def test_drain_ack_requires_verified_row_and_child_exit(self):
        self.request()
        row = self.output / "rows" / "f001.json"
        write_once(row, {"sample_id": "f001", "state": "sealed"})
        child_path = self.output / "sessions" / "drains" / "one.json"
        write_once(child_path, {"status": "drained"})
        class Child:
            root = self.root
            last_drain_receipt = {"relative": "run/sessions/drains/one.json",
                                  "sha256": producer.digest(child_path)}
            calls = 0
            def close(self):
                self.calls += 1
        child = Child()
        self.assertTrue(producer._external_drain(self.output, {}, child, row))
        ack, _ = producer._read(self.output / "control" / ("drain-ack-" + "a" * 32 + ".json"))
        self.assertEqual(ack["status"], "STOPPED_DRAINED")
        self.assertEqual(ack["last_verified_row_sha256"], producer.digest(row))
        self.assertEqual(child.calls, 1)
        self.assertFalse(producer._external_drain(self.output, {}, child, row))
        self.assertEqual(child.calls, 1)

    def test_drain_unknown_child_and_multiple_requests_hold(self):
        self.request()
        class Unknown:
            def close(self):
                raise ValueError("converter_drain_outcome_unknown")
        with self.assertRaisesRegex(ValueError, "converter_drain_outcome_unknown"):
            producer._external_drain(self.output, {}, Unknown())
        self.assertFalse((self.output / "control" / ("drain-ack-" + "a" * 32 + ".json")).exists())
        self.request("b" * 32)
        with self.assertRaisesRegex(ValueError, "multiple_pending_external_drains"):
            producer._external_drain(self.output, {}, Unknown())

    def test_old_ack_tampering_blocks_a_later_request(self):
        self.request()
        class Child:
            root = self.root
            last_drain_receipt = None
            def close(self):
                pass
        child = Child()
        self.assertTrue(producer._external_drain(self.output, {}, child))
        self.request("b" * 32)
        old_ack = self.output / "control" / ("drain-ack-" + "a" * 32 + ".json")
        old_ack.write_text('{"status":"forged"}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "external_drain_request_changed"):
            producer._external_drain(self.output, {}, child)

    def test_protocol_limit_is_pinned_and_drift_rejected(self):
        manifest = self.root / "manifest.json"
        profile = self.root / "profile.json"
        write_once(manifest, {"stage": "retrieval_source_first_no_predictions", "query_independent": True,
                              "pdfs": [{"sample_id": "f001", "physical_page": 1}]})
        write_once(profile, {})
        with patch.object(producer, "_profile"), patch.object(producer, "method_hashes", return_value={}), \
                patch.object(producer, "runtime_receipt", return_value={}):
            _, frozen = producer._freeze(self.root, manifest, profile, self.root / "new", None,
                                         max_documents_per_session=2)
            self.assertEqual(frozen["converter_session"]["max_documents"], 2)
            with self.assertRaisesRegex(ValueError, "assessment_producer_protocol_changed"):
                producer._freeze(self.root, manifest, profile, self.root / "new", None,
                                 max_documents_per_session=3)
            with self.assertRaisesRegex(ValueError, "bounded_converter_session_limit_required"):
                producer._freeze(self.root, manifest, profile, self.root / "other", None,
                                 max_documents_per_session=0)

    def test_resume_drain_replays_earlier_row_before_ack(self):
        rows = [{"sample_id": "f001"}, {"sample_id": "f002"}]
        write_once(self.root / "profile.json", {})
        write_once(self.output / "rows" / "f001.json", {"sample_id": "f001"})
        write_once(self.output / "rows" / "f002.json", {"sample_id": "f002"})
        self.request()
        protocol = {"ids": ["f001", "f002"], "profile_sha256": producer.digest(self.root / "profile.json")}
        with patch.object(producer, "_freeze", return_value=({"pdfs": rows}, protocol)), \
                patch.object(producer, "_verify_receipt", side_effect=ValueError("old_row_corrupt")), \
                patch.object(producer, "ConverterSession") as child, \
                patch.object(producer, "_attempt") as attempted:
            with self.assertRaisesRegex(ValueError, "old_row_corrupt"):
                producer._run(self.root, self.root / "manifest.json", self.root / "profile.json",
                              self.output, None)
        attempted.assert_not_called()
        child.return_value.close.assert_not_called()
        self.assertFalse((self.output / "control" / ("drain-ack-" + "a" * 32 + ".json")).exists())

    def test_rotation_occurs_only_after_second_verified_row(self):
        ids = ["f001", "f002", "f003"]
        rows = [{"sample_id": sid, **{key + "_sha256": "0" * 64 for key in
                ("source", "page", "image", "native")}} for sid in ids]
        write_once(self.root / "profile.json", {})
        protocol = {"ids": ids, "converter_session": {"max_documents": 2},
                    "profile_sha256": producer.digest(self.root / "profile.json")}
        events = []
        class Session:
            def __init__(self, *_):
                self.documents = 0
                events.append(("start", id(self)))
            def close(self):
                events.append(("close", self.documents))
        def attempt(*args):
            session = args[-1]
            session.documents += 1
            events.append(("convert", args[2]["sample_id"]))
            return {"state": "error", "assessment_relative": None, "assessment_sha256": None}
        def verify(_root, row, *_args):
            events.append(("verify", row["sample_id"]))
        with patch.object(producer, "_freeze", return_value=({"pdfs": rows}, protocol)), \
                patch.object(producer, "_profile"), patch.object(producer, "_check_code"), \
                patch.object(producer, "_verified_row", return_value=([], [100, 100], "eligible")), \
                patch.object(producer, "_attempt", side_effect=attempt), \
                patch.object(producer, "_verify_receipt", side_effect=verify), \
                patch.object(producer, "_finalize", return_value={"status": "COMPLETE"}), \
                patch.object(producer, "ConverterSession", Session):
            result = producer._run(self.root, self.root / "manifest.json", self.root / "profile.json",
                                   self.output, None, max_documents_per_session=2)
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual([e for e in events if e[0] == "convert"],
                         [("convert", sid) for sid in ids])
        second_verified = events.index(("verify", "f002"))
        self.assertEqual(events[second_verified + 1], ("close", 2))
        self.assertEqual(events[-1], ("close", 1))

    def test_drain_binds_worker_pid_even_when_launcher_pid_differs(self):
        start_path = self.output / "sessions" / "one" / "start.json"
        write_once(start_path, {"worker_pid": 222})
        descriptor = {"relative": start_path.relative_to(self.root).as_posix(),
                      "sha256": producer.digest(start_path)}
        session = producer.ConverterSession(self.root, self.output, {})
        session.documents = 1
        session.worker_pid = 222
        session.session_start = descriptor
        session.worker_handle = 999
        class Input:
            def write(self, raw):
                nonce = producer.parse_bound_json(raw)["drain"]
                write_once(self_output / "sessions" / "drains" / (nonce + ".json"),
                           {"nonce": nonce, "documents": 1, "session_start": descriptor,
                            "protocol_sha256": producer.digest(self_output / "protocol.json"),
                            "worker_pid": 222})
            def flush(self):
                pass
        self_output = self.output
        class Launcher:
            pid = 111
            returncode = None
            stdin = Input()
            def poll(self):
                return self.returncode
            def wait(self, timeout):
                self.returncode = 0
        session.process = Launcher()
        with patch.object(producer, "_windows_handle_exited", return_value=True), \
                patch.object(producer, "_close_windows_handle"):
            session.close()
        self.assertIsNotNone(session.last_drain_receipt)

    def test_forced_timeout_targets_verified_worker_before_launcher(self):
        session = producer.ConverterSession(self.root, self.output, {})
        session.worker_pid = 222
        session.worker_handle = 999
        session.session_start = {"relative": "sessions/one/start.json", "sha256": "0" * 64}
        events = []
        class Launcher:
            pid = 111
            returncode = None
            def poll(self): return self.returncode
            def kill(self):
                events.append("kill_launcher")
                self.returncode = 1
            def wait(self, timeout): events.append("wait_launcher")
        session.process = Launcher()
        with patch.object(producer.os, "name", "nt"), \
                patch.object(producer, "_terminate_windows_handle", side_effect=lambda _: events.append("kill_worker") or True), \
                patch.object(producer, "_close_windows_handle"):
            session.close(force=True)
        self.assertEqual(events[:2], ["kill_worker", "kill_launcher"])
        self.assertIsNone(session.process)

    def test_graceful_drain_holds_if_worker_handle_remains_alive(self):
        start_path = self.output / "sessions" / "one" / "start.json"
        write_once(start_path, {"worker_pid": 222})
        descriptor = {"relative": start_path.relative_to(self.root).as_posix(),
                      "sha256": producer.digest(start_path)}
        session = producer.ConverterSession(self.root, self.output, {})
        session.worker_pid, session.worker_handle, session.session_start = 222, 999, descriptor
        self_output = self.output
        class Input:
            def write(self, raw):
                nonce = producer.parse_bound_json(raw)["drain"]
                write_once(self_output / "sessions" / "drains" / (nonce + ".json"),
                           {"nonce": nonce, "documents": 0, "session_start": descriptor,
                            "protocol_sha256": producer.digest(self_output / "protocol.json"),
                            "worker_pid": 222})
            def flush(self): pass
        class Launcher:
            pid = 111
            returncode = None
            stdin = Input()
            def poll(self): return self.returncode
            def wait(self, timeout): self.returncode = 0
        session.process = Launcher()
        with patch.object(producer, "_windows_handle_exited", return_value=False):
            with self.assertRaisesRegex(ValueError, "converter_worker_exit_unproven"):
                session.close()
        self.assertIsNotNone(session.process)
        self.assertEqual(session.worker_handle, 999)

    @unittest.skipUnless(os.name == "nt", "Windows owned-process handle smoke")
    def test_real_venv_child_handle_terminates_only_owned_stub(self):
        stamp = self.root / "stub-start.json"
        script = self.root / "owned-stub.py"
        script.write_text(
            "import json,os,time\n"
            "from pathlib import Path\n"
            "from src.parallel_source_v4.assessment_producer import _windows_process_handle,_close_windows_handle\n"
            "h,t=_windows_process_handle(os.getpid()); _close_windows_handle(h)\n"
            f"Path({str(stamp)!r}).write_text(json.dumps({{'pid':os.getpid(),'parent':os.getppid(),'ticks':t}}))\n"
            "time.sleep(60)\n", encoding="utf-8")
        proc = subprocess.Popen([sys.executable, "-B", str(script)], cwd=producer.REPO,
                                env={**os.environ, "PYTHONPATH": str(producer.REPO)},
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        handle = None
        try:
            for _ in range(100):
                if stamp.is_file():
                    break
                if proc.poll() is not None:
                    self.fail("owned stub exited before launch receipt")
                time.sleep(0.05)
            self.assertTrue(stamp.is_file())
            body = json.loads(stamp.read_text(encoding="utf-8"))
            self.assertTrue(body["pid"] == proc.pid or body["parent"] == proc.pid)
            handle, ticks = producer._windows_process_handle(body["pid"])
            self.assertEqual(ticks, body["ticks"])
            self.assertTrue(producer._terminate_windows_handle(handle))
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=10)
            self.assertEqual(producer.ctypes.windll.kernel32.WaitForSingleObject(
                producer.ctypes.c_void_p(handle), 0), 0)
        finally:
            if handle is not None:
                producer._close_windows_handle(handle)
            if proc.poll() is None:
                proc.kill(); proc.wait(timeout=10)

    def test_drain_is_distinct_nonzero_terminal_status_in_both_clis(self):
        drained = {"status": "STOPPED_DRAINED", "document_count": 3,
                   "eligible_count": None, "state_counts": {}}
        complete = dict(drained, status="COMPLETE")
        argv = ["producer", "run", "--data-root", str(self.root), "--manifest", "manifest.json",
                "--profile", "profile.json", "--output", "run"]
        with patch("sys.argv", argv), patch.object(producer, "_run", return_value=drained), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(producer.main(), 4)
        with patch("sys.argv", argv), patch.object(producer, "_run", return_value=complete), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(producer.main(), 0)
        argv = ["migration", "--data-root", str(self.root), "--origin-output", "old",
                "--new-output", "run", "--origin-checkout", str(self.root),
                "--origin-interpreter", str(self.root / "python.exe"), "--origin-head", "a",
                "--origin-protocol-sha256", "b", "--expected-import-count", "0"]
        with patch("sys.argv", argv), patch.object(migration, "run_migrated", return_value=drained), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(migration.main(), 4)


if __name__ == "__main__":
    unittest.main()
