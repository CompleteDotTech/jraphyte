"""Read-only phase capsule exporter for a separately opened historical pilot.

Run this source-checkout helper with the genuine historical package on sys.path.
It imports only public symbols from that historical package and stdlib; no new
trace_gc module is loaded into the old package namespace. The application owns
pilot construction, trust, locks, intent/attempt inventory, and source access.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import sqlite3

from trace_gc.canonical import bytes_digest, digest, dumps, loads
from trace_gc.paper_pilot import PaperPilot, implementation_identity

VERSION = "paper-pilot-phase-capsule-v1"
ATTEMPT_NAMES = frozenset({"semantic-attempt-started.json", "semantic-response.raw",
    "semantic-local-execution.json", "semantic-execution-outcome.json",
    "semantic-import-result.json"})


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def _logical(connection: sqlite3.Connection) -> str:
    objects = connection.execute("SELECT type,name,tbl_name,sql FROM sqlite_master "
                                 "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name").fetchall()
    tables = {"objects": [list(row) for row in objects], "tables": {}}
    for kind, name, _table, _sql in objects:
        if kind != "table":
            continue
        _require(name.replace("_", "").isalnum(), "invalid_source_table")
        rows = connection.execute(f'SELECT * FROM "{name}"').fetchall()
        encoded = [[base64.b64encode(item).decode("ascii") if isinstance(item, bytes) else item
                    for item in row] for row in rows]
        tables["tables"][name] = {"row_count": len(rows),
                                 "rows_sha256": digest(sorted(encoded, key=dumps))}
    return digest(tables)


def _backup(source: sqlite3.Connection, destination: Path) -> str:
    _require(not destination.exists(), "backup_target_exists")
    pending = destination.with_name(destination.name + ".pending")
    if pending.exists():
        try:
            probe = sqlite3.connect(f"file:{pending.as_posix()}?mode=ro&immutable=1", uri=True)
            try:
                probe.execute("PRAGMA query_only=ON")
                complete = _logical(source) == _logical(probe)
            finally:
                probe.close()
        except sqlite3.DatabaseError:
            complete = False
        if not complete:
            pending.rename(destination.with_name(destination.name + ".failed." + os.urandom(8).hex()))
    if pending.exists():
        os.replace(pending, destination)
        return bytes_digest(destination.read_bytes())
    dest = sqlite3.connect(pending)
    try:
        source.backup(dest)
        dest.commit()
        _require(_logical(source) == _logical(dest), "backup_content_changed")
    finally:
        dest.close()
    os.replace(pending, destination)
    return bytes_digest(destination.read_bytes())


def _events(connection: sqlite3.Connection) -> list[list]:
    rows = [list(row) for row in connection.execute(
        "SELECT seq,body,hash FROM events ORDER BY seq")]
    previous = None
    for index, (seq, raw, hash_) in enumerate(rows, 1):
        event = loads(raw)
        _require(seq == index and event["previous"] == previous and digest(event) == hash_,
                 "source_event_chain_changed")
        previous = hash_
    return rows


def export_phase(pilot, application_journal: sqlite3.Connection, destination: str | Path,
                 *, expected_historical_identity_sha256: str,
                 external_semantic_intent_path: str | Path,
                 external_semantic_intent_sha256: str,
                 attempt_manifest_path: str | Path,
                 attempt_manifest_sha256: str,
                 source_open_sha256: str) -> dict:
    """Export under the genuine historical pilot's owned controller capability."""
    _require(type(pilot) is PaperPilot and type(application_journal) is sqlite3.Connection and
             pilot.db is not None and not pilot._lock_file.closed and
             Path(pilot._lock_file.name).resolve(strict=True) ==
                (pilot.root / "controller.lock").resolve(strict=True) and
             Path(pilot.backend.path).resolve(strict=True) ==
                (pilot.root / "graph.sqlite3").resolve(strict=True) and
             Path(pilot.budget.path).resolve(strict=True) ==
                (pilot.root / "budget.sqlite3").resolve(strict=True),
             "historical_pilot_owner_or_store_missing")
    journal_path = application_journal.execute("PRAGMA database_list").fetchone()[2]
    _require(Path(journal_path).resolve(strict=True) ==
             (pilot.root / "application-journal.sqlite3").resolve(strict=True),
             "historical_application_journal_does_not_match_owner")
    with pilot._mutex, pilot.backend._lock, pilot.budget._lock:
        _require(not any(connection.in_transaction for connection in
                     (pilot.db, pilot.backend.db, pilot.budget.db, application_journal)),
                 "historical_transaction_in_progress")
        return _export_phase_locked(pilot, application_journal, destination,
            expected_historical_identity_sha256=expected_historical_identity_sha256,
            external_semantic_intent_path=external_semantic_intent_path,
            external_semantic_intent_sha256=external_semantic_intent_sha256,
            attempt_manifest_path=attempt_manifest_path,
            attempt_manifest_sha256=attempt_manifest_sha256,
            source_open_sha256=source_open_sha256)


def _export_phase_locked(pilot, application_journal: sqlite3.Connection, destination: str | Path,
                 *, expected_historical_identity_sha256: str,
                 external_semantic_intent_path: str | Path,
                 external_semantic_intent_sha256: str,
                 attempt_manifest_path: str | Path,
                 attempt_manifest_sha256: str,
                 source_open_sha256: str) -> dict:
    """Export only while the application has quiesced and owns the old pilot.

    An absent attempt file is recorded explicitly; this is not by itself proof
    that no outside executor made a call. The controller release must separately
    prove its attempt-before-provider ordering and sole ownership.
    """
    _require(digest(implementation_identity()) == expected_historical_identity_sha256,
             "historical_runtime_identity_changed")
    root = Path(destination)
    _require(not root.is_symlink() and not root.is_relative_to(pilot.root) and
             not pilot.root.is_relative_to(root), "capsule_destination_invalid")
    _require(pilot.db is not None, "historical_pilot_not_open")
    pilot.backend.audit()
    raw_intent = Path(external_semantic_intent_path).read_bytes()
    intent = loads(raw_intent)
    _require(bytes_digest(raw_intent) == external_semantic_intent_sha256 and
             intent.get("version") == "issue23-semantic-intent-v1" and
             intent.get("automatic_retry") is False and
             intent.get("attempts_authorized") == 1 and intent.get("graph_writes") == 0,
             "external_semantic_intent_changed")
    manifest_raw = Path(attempt_manifest_path).read_bytes()
    _require(bytes_digest(manifest_raw) == attempt_manifest_sha256,
             "attempt_manifest_changed")
    manifest = loads(manifest_raw)
    _require(set(manifest) == {"version", "run_id", "intent_sha256", "artifacts",
                               "source_receipts", "source_open_sha256", "expected_budget_used"} and
             manifest["version"] == "paper-pilot-phase-attempt-manifest-v1" and
             manifest["run_id"] == pilot.config["run_id"] and
             manifest["intent_sha256"] == external_semantic_intent_sha256 and
             manifest["source_open_sha256"] == source_open_sha256 and
             set(manifest["artifacts"]) == ATTEMPT_NAMES and
             manifest["expected_budget_used"] == pilot.budget.snapshot()["used"] and
             manifest["expected_budget_used"]["model_calls"] == 1 and
             manifest["expected_budget_used"]["request_bytes"] > 0 and
             manifest["expected_budget_used"]["retries"] == 0 and
             all(value is None or type(value) is str and len(value) == 64
                 for value in manifest["artifacts"].values()),
             "attempt_manifest_incomplete")
    def inventory():
        folder = Path(external_semantic_intent_path).resolve(strict=True).parent
        return {name: (bytes_digest((folder / name).read_bytes()) if (folder / name).exists() else None)
                for name in sorted(ATTEMPT_NAMES)}
    attempts = inventory()
    _require(attempts == manifest["artifacts"], "attempt_inventory_changed")
    connections = {"checkpoint": pilot.db, "graph": pilot.backend.db,
                   "budget": pilot.budget.db, "application_journal": application_journal}
    before = {key: _logical(value) for key, value in connections.items()}
    if root.exists():
        _require(root.is_dir() and not any(path.is_symlink() for path in root.iterdir()) and
                 {path.name for path in root.iterdir()} <=
                 {key + ".sqlite3" for key in connections} |
                 {key + ".sqlite3.pending" for key in connections} |
                 {"capsule.json"} |
                 {path.name for path in root.iterdir() if any(
                     path.name.startswith(key + ".sqlite3.failed.") for key in connections)},
                 "partial_export_has_unknown_files")
    else:
        root.mkdir(parents=True)
    backups = {}
    for key, value in connections.items():
        target = root / (key + ".sqlite3")
        if target.exists():
            source = sqlite3.connect(f"file:{target.as_posix()}?mode=ro&immutable=1", uri=True)
            try:
                source.execute("PRAGMA query_only=ON")
                _require(_logical(source) == before[key], "partial_backup_changed")
            finally:
                source.close()
            backups[key] = bytes_digest(target.read_bytes())
        else:
            backups[key] = _backup(value, target)
    _require(before == {key: _logical(value) for key, value in connections.items()},
             "cross_database_snapshot_changed")
    checkpoint = _events(pilot.db)
    journal = _events(application_journal)
    _require(checkpoint and journal and
             loads(checkpoint[0][1])["kind"] == "OPEN" and
             loads(journal[0][1])["kind"] == "FREEZE", "historical_open_or_freeze_missing")
    compile_rows = [row for row in pilot.requests.values()
                    if row["kind"] == "COMPILE" and "result" in row]
    _require(len(compile_rows) == 1 and
             all("result" in row for row in pilot.requests.values()) and
             compile_rows[0]["result"]["state"] == "WAIT_SEMANTIC_RESPONSE" and
             compile_rows[0]["id"] == intent["compile_id"] and
             compile_rows[0]["result"]["pack_sha256"] == intent["pack_sha256"] and
             compile_rows[0]["result"]["request_sha256"] == intent["request_sha256"] and
             not any(row["kind"] == "SEMANTIC_RESPONSE" for row in pilot.requests.values()) and
             pilot.budget.snapshot()["used"]["model_calls"] == 1 and
             pilot.budget.snapshot()["used"]["request_bytes"] > 0 and
             pilot.budget.snapshot()["used"]["retries"] == 0,
             "exact_pending_compile_required")
    source_receipts = {row["id"]: digest(row["args"]["receipt"])
                       for row in pilot.requests.values()
                       if row["kind"] in {"REVIEW_SOURCE", "REVIEW_SOURCE_IMAGE"}}
    _require(source_receipts and source_receipts == manifest["source_receipts"],
             "source_receipt_inventory_changed")
    capsule = {"version": VERSION, "run_id": pilot.config["run_id"],
               "config": pilot.config, "old_implementation": implementation_identity(),
               "checkpoint_events": checkpoint, "checkpoint_head": checkpoint[-1][2],
               "blobs": {sha: base64.b64encode(body).decode("ascii") for sha, body in
                         pilot.db.execute("SELECT hash,body FROM blobs ORDER BY hash")},
               "catalog_records": pilot.catalog.all(),
               "database_state": before, "database_backup_sha256": backups,
               "graph_state": pilot.backend.state(), "source_statuses": pilot.backend.statuses(),
               "budget_snapshot": pilot.budget.snapshot(),
               "application_journal_events": journal, "application_journal_head": journal[-1][2],
               "external_semantic_intent_sha256": external_semantic_intent_sha256,
               "external_semantic_intent": intent,
               "external_semantic_intent_base64": base64.b64encode(raw_intent).decode("ascii"),
               "attempt_manifest_sha256": attempt_manifest_sha256,
               "attempt_manifest": manifest,
               "attempt_manifest_base64": base64.b64encode(manifest_raw).decode("ascii"),
               "attempt_inventory": attempts,
               "source_receipt_sha256": source_receipts,
               "source_open_sha256": source_open_sha256}
    _require(digest(implementation_identity()) == expected_historical_identity_sha256,
             "historical_runtime_changed_during_export")
    raw = dumps(capsule).encode("utf-8") + b"\n"
    path = root / "capsule.json"
    if path.exists():
        _require(path.read_bytes() == raw, "existing_capsule_conflict")
    else:
        with path.open("xb") as handle:
            handle.write(raw)
            handle.flush(); os.fsync(handle.fileno())
    _require(path.read_bytes() == raw and attempts == inventory() and
             bytes_digest(Path(attempt_manifest_path).read_bytes()) == attempt_manifest_sha256,
             "export_readback_or_attempt_changed")
    return {"version": VERSION, "capsule_sha256": bytes_digest(raw),
            "checkpoint_head": capsule["checkpoint_head"],
            "database_state": before, "database_backup_sha256": backups,
            "model_call_authorized": False}
