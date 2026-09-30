"""Offline timing checks for direct phase-import mutation ownership."""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import tempfile
import threading
import unittest

from trace_gc.errors import ContractError
from trace_gc.paper_pilot import PaperPilot


class RecordingAuthority:
    def __init__(self):
        self.lock = threading.Lock()
        self.entries = 0

    @contextmanager
    def staging(self):
        with self.lock:
            self.entries += 1
            yield


class ImportLockTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ.get("ISSUE90_TEST_TMPDIR"))
        self.addCleanup(self.temp.cleanup)
        self.pointer = Path(self.temp.name) / "active.json"
        self.authority = RecordingAuthority()
        self.pilot = object.__new__(PaperPilot)
        self.pilot._mutex = threading.RLock()
        self.pilot._phase_authority = self.authority
        self.pilot.phase_import = {"activation_path": str(self.pointer)}

    def test_import_holds_shared_phase_lock_until_mutation_returns(self):
        entered = threading.Event()
        release = threading.Event()
        contender_entered = threading.Event()
        errors = []

        def mutation(**_kwargs):
            entered.set()
            if not release.wait(2):
                raise AssertionError("authored import fixture timed out")
            return {"status": "IMPORTED"}

        self.pilot._import_phase_locked = mutation

        def importer():
            try:
                self.assertEqual(self.pilot.import_phase(capsule_path="x",
                    capsule_sha256="y", authorization={}), {"status": "IMPORTED"})
            except BaseException as error:
                errors.append(error)

        def contender():
            with self.authority.staging():
                contender_entered.set()

        first = threading.Thread(target=importer)
        second = threading.Thread(target=contender)
        first.start()
        try:
            self.assertTrue(entered.wait(2))
            second.start()
            self.assertFalse(contender_entered.wait(.05))
        finally:
            release.set()
            first.join(2)
            second.join(2)
        self.assertFalse(first.is_alive() or second.is_alive())
        self.assertFalse(errors, errors)
        self.assertTrue(contender_entered.is_set())
        self.assertEqual(self.authority.entries, 2)

    def test_existing_pointer_rejects_before_import_body(self):
        self.pointer.write_bytes(b"authored-pointer")
        self.pilot._import_phase_locked = lambda **_kwargs: self.fail("mutation reached")
        with self.assertRaises(ContractError) as captured:
            self.pilot.import_phase(capsule_path="x", capsule_sha256="y", authorization={})
        self.assertEqual(captured.exception.code, "PHASE_INACTIVE")


if __name__ == "__main__":
    unittest.main()
