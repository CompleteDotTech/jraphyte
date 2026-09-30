"""Authored, offline checks for interrupted phase backup handling."""
from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

from src.paper_pilot_phase_export import _backup, _logical
from trace_gc.canonical import bytes_digest
from trace_gc.phase_transition import logical_state


class PhaseBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ.get("ISSUE90_TEST_TMPDIR"))
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = sqlite3.connect(self.root / "source.sqlite3")
        self.addCleanup(self.source.close)
        self.source.execute("CREATE TABLE evidence (id INTEGER PRIMARY KEY, value TEXT)")
        self.source.execute("INSERT INTO evidence VALUES (1, 'authored')")
        self.source.commit()

    def test_completed_pending_backup_promotes_once(self):
        target = self.root / "checkpoint.sqlite3"
        pending = target.with_name(target.name + ".pending")
        destination = sqlite3.connect(pending)
        try:
            self.source.backup(destination)
        finally:
            destination.close()
        expected = bytes_digest(pending.read_bytes())
        self.assertEqual(_backup(self.source, target), expected)
        self.assertFalse(pending.exists())
        reopened = sqlite3.connect(target)
        try:
            self.assertEqual(_logical(self.source), _logical(reopened))
        finally:
            reopened.close()

    def test_incomplete_pending_preserved_then_replaced(self):
        target = self.root / "checkpoint.sqlite3"
        pending = target.with_name(target.name + ".pending")
        pending.write_bytes(b"interrupted-authored-sqlite-backup")
        self.assertEqual(_backup(self.source, target), bytes_digest(target.read_bytes()))
        failures = list(self.root.glob("checkpoint.sqlite3.failed.*"))
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0].read_bytes(), b"interrupted-authored-sqlite-backup")

    def test_schema_objects_are_part_of_logical_snapshot(self):
        before = logical_state(self.source)
        self.source.execute("CREATE INDEX evidence_value ON evidence(value)")
        self.source.commit()
        self.assertNotEqual(before, logical_state(self.source))
        before = logical_state(self.source)
        self.source.execute("CREATE VIEW evidence_view AS SELECT value FROM evidence")
        self.source.commit()
        self.assertNotEqual(before, logical_state(self.source))


if __name__ == "__main__":
    unittest.main()
