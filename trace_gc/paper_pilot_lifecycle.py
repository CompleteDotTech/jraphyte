"""Durable, application-owned PaperPilot successor and status recovery service.

The caller supplies the parent PaperPilot, exclusive quiescence, successor
config, trust and access policy. This module never creates an authority or
executes a model. It copies the parent graph using SQLite backup while keeping
the original checkpoint and budget as archived history, then leaves a fresh
successor checkpoint and bounded budget for the application to open normally.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import json
import os
import sqlite3
from typing import Any, Mapping

from .canonical import digest, dumps, loads
from .compiler import timestamp
from .errors import require
from .paper_pilot import PaperPilot

PARENT_READY_GATES = frozenset({"extraction", "graph", "retrieval", "answers"})


def _bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _write_once(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        require(path.read_bytes() == raw, "LIFECYCLE_HISTORY", "immutable receipt differs")
        return
    with path.open("xb") as output:
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())


def _backup(source: sqlite3.Connection, path: Path) -> str:
    target = sqlite3.connect(path)
    try:
        source.backup(target)
        require(target.execute("PRAGMA quick_check").fetchone() == ("ok",),
                "LIFECYCLE_BACKUP", "SQLite backup failed quick_check")
    finally:
        target.close()
    return _sha(path.read_bytes())


def _historical_local_execution(pilot, stage_id: str, raw: bytes,
                                receipt: Mapping[str, Any], local: Mapping[str, Any],
                                context: Mapping[str, Any]) -> None:
    """Verify a completed semantic call against its original execution context.

    Recomputing ``semantic_execution_context`` after publication would test a
    later graph version and incorrectly reject a genuine completed call.
    """
    compiled = pilot.requests[stage_id]["result"]
    pack = pilot.catalog.get(compiled["pack_id"], "pack")
    require(context.get("pack_sha256") == compiled["pack_sha256"] and
            context.get("graph_version") == pack["graph_version"] and
            context.get("schema_hash") == pack["schema_hash"] and
            local.get("execution_preflight_sha256") == digest(context),
            "LIFECYCLE_EXECUTION", "historical preflight differs from compiled pack")
    p = receipt["payload"]
    expected = pilot.execution_payload(stage_id, kind="SEMANTIC",
        response_sha256=_sha(raw), local_execution_sha256=digest(local),
        **{k: p[k] for k in ("generated_at", "usage", "cost",
                             "response_source", "provider_request_id")})
    pilot._trusted(receipt, "OBSERVATION", "SEMANTIC_IMPORT", expected)
    require((p["response_source"] == "ACTUAL_MODEL_EXECUTION" or
             (pilot.config["execution_mode"] == "SYNTHETIC" and
              p["response_source"] == "AUTHORED_SYNTHETIC")) and
            p["usage"] == {"input_tokens": local["input_tokens"],
                           "output_tokens": local["output_tokens"]} and
            p["generated_at"] == local["completed_at"] and
            p["cost"]["amount"] == local["cost_usd"] and
            timestamp(pilot.requests[stage_id]["created_at"]) <=
            timestamp(p["generated_at"]) <= timestamp(receipt["issued_at"]),
            "LIFECYCLE_EXECUTION", "historical local execution/receipt differs")


def parent_proof(pilot, *, assertion_ids: set[str], source_ids: set[str],
                 completed_request_ids: set[str],
                 imported_outputs: Mapping[str, bytes],
                 historical_execution_contexts: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Read back exact durable parent state while its application owns it."""
    require(type(pilot) is PaperPilot and pilot.db is not None and not pilot._lock_file.closed,
            "LIFECYCLE_OWNER", "parent PaperPilot must hold its checkpoint lock")
    audit = pilot.backend.audit()
    state = pilot.backend.state()
    statuses = pilot.backend.statuses()
    budget = pilot.budget.snapshot()
    require(set(state["assertions"]) == assertion_ids and
            set(statuses) == source_ids and
            all(row["active"] for row in state["assertions"].values()) and
            all(row["active"] and row["permission"] == "READ" and not row["tombstone"]
                for row in statuses.values()) and
            all(rid in pilot.requests and "result" in pilot.requests[rid]
                for rid in completed_request_ids),
            "LIFECYCLE_PARENT", "parent completion inventory differs")
    require(state["graph_version"] == audit["events"] and
            all(budget["used"][key] <= value for key, value in budget["limits"].items()),
            "LIFECYCLE_PARENT", "parent graph or budget differs")
    imports = {rid: row for rid, row in pilot.requests.items()
               if row["kind"] in {"SEMANTIC_RESPONSE", "ANSWER_RESPONSE"}}
    require(set(imports) == set(imported_outputs), "LIFECYCLE_IMPORT",
            "every durable semantic/answer import needs original response bytes")
    imported_hashes = {}
    for rid, row in imports.items():
        require("result" in row and type(imported_outputs[rid]) is bytes,
                "LIFECYCLE_IMPORT", "import is incomplete or response is not bytes")
        args = row["args"]
        raw = imported_outputs[rid]
        require(_sha(raw) == args["response_blob"], "LIFECYCLE_IMPORT",
                "original response differs from checkpoint blob")
        kind = "SEMANTIC" if row["kind"] == "SEMANTIC_RESPONSE" else "ANSWER"
        stage_id = args["compile_id"] if kind == "SEMANTIC" else args["prepared_id"]
        local = args.get("local_execution")
        if kind == "SEMANTIC" and local is not None:
            require(rid in historical_execution_contexts, "LIFECYCLE_EXECUTION",
                    "original local execution context is required")
            _historical_local_execution(pilot, stage_id, raw,
                                        args["execution_receipt"], local,
                                        historical_execution_contexts[rid])
        else:
            pilot._execution(stage_id, kind, raw, args["execution_receipt"])
        imported_hashes[rid] = _sha(raw)
    return {"run_id": pilot.config["run_id"], "config_sha256": digest(pilot.config),
            "checkpoint_head": pilot._head, "graph_version": state["graph_version"],
            "graph_state_sha256": digest(state), "graph_journal_head": audit["head_hash"],
            "assertion_ids": sorted(assertion_ids), "source_ids": sorted(source_ids),
            "completed_request_ids": sorted(completed_request_ids), "budget": budget,
            "access_sha256": digest(pilot.current_access()),
            "imported_output_sha256": imported_hashes,
            "historical_execution_context_sha256": {
                rid: digest(value) for rid, value in historical_execution_contexts.items()}}


def _successor_config(parent: Mapping[str, Any], successor: Mapping[str, Any],
                      changed_documents: set[str]) -> None:
    require(set(parent) == set(successor) and
            successor["run_id"] != parent["run_id"] and
            all(successor[key] == parent[key] for key in
                ("security_scope", "execution_mode", "questions", "semantic_model", "answer_model")),
            "LIFECYCLE_CONFIG", "successor changed protected cohort/model scope")
    original = {row["source_id"]: row for row in parent["documents"]}
    revised = {row["source_id"]: row for row in successor["documents"]}
    hexchars = set("0123456789abcdef")
    require(bool(successor["run_id"]) and
            len(successor["cohort_manifest_sha256"]) == 64 and
            set(successor["cohort_manifest_sha256"]) <= hexchars and
            all(set(row) == {"source_id", "version", "document_sha256", "physical_pages"} and
                row["source_id"] and row["version"] and
                len(row["document_sha256"]) == 64 and
                set(row["document_sha256"]) <= hexchars and
                bool(row["physical_pages"]) and
                all(type(page) is int and page > 0 for page in row["physical_pages"])
                for row in successor["documents"]) and
            len(revised) == len(successor["documents"]),
            "LIFECYCLE_CONFIG", "successor document frame is malformed")
    require(original.keys() == revised.keys() and
            {sid for sid in original if original[sid] != revised[sid]} == changed_documents and
            (not changed_documents or
             successor["cohort_manifest_sha256"] != parent["cohort_manifest_sha256"]),
            "LIFECYCLE_CONFIG", "declared changed-document frame differs")


def prepare_successor(parent_pilot, destination: str | Path, *, successor_config: Mapping[str, Any],
                      assertion_ids: set[str], source_ids: set[str],
                      completed_request_ids: set[str], changed_documents: set[str],
                      imported_outputs: Mapping[str, bytes],
                      historical_execution_contexts: Mapping[str, Mapping[str, Any]],
                      qualification_receipt_path: str | Path,
                      qualification_receipt_sha256: str,
                      qualification_trust,
                      qualification_report_path: str | Path,
                      qualification_report_sha256: str,
                      qualification_evaluator_path: str | Path,
                      qualification_evaluator_sha256: str,
                      required_qualification_gates: frozenset[str],
                      application_artifacts: Mapping[str, str | Path],
                      application_databases: Mapping[str, sqlite3.Connection],
                      application_quiescence=None) -> dict[str, Any]:
    """Archive parent and copy only its graph to a new successor directory.

    The application must hold all external graph writers still, including
    source/reviewer controllers, for the duration of this call. A partial
    directory remains held for explicit reconciliation; no implicit retry.
    """
    require(application_quiescence is not None, "LIFECYCLE_OWNER",
            "application-owned writer quiescence is required")
    require(qualification_trust is not parent_pilot.trust,
            "LIFECYCLE_QUALIFICATION", "qualification needs separate enrolled review authority")
    require(type(required_qualification_gates) is frozenset and
            required_qualification_gates == PARENT_READY_GATES,
            "LIFECYCLE_QUALIFICATION", "externally declared complete gate set required")
    target = Path(destination).resolve()
    require(not target.exists(), "LIFECYCLE_HISTORY", "successor already exists")
    require(not target.is_relative_to(parent_pilot.root.resolve()) and
            not parent_pilot.root.resolve().is_relative_to(target),
            "LIFECYCLE_HISTORY", "successor must be disjoint from parent history")
    _successor_config(parent_pilot.config, successor_config, changed_documents)
    with application_quiescence:
        with parent_pilot._mutex, parent_pilot.backend._lock, parent_pilot.budget._lock:
            before = parent_proof(parent_pilot, assertion_ids=assertion_ids,
                                  source_ids=source_ids,
                                  completed_request_ids=completed_request_ids,
                                  imported_outputs=imported_outputs,
                                  historical_execution_contexts=historical_execution_contexts)
            qualification_raw = Path(qualification_receipt_path).read_bytes()
            require(_sha(qualification_raw) == qualification_receipt_sha256,
                    "LIFECYCLE_QUALIFICATION", "externally pinned qualification differs")
            qualification = json.loads(qualification_raw)
            require(qualification["issuer"] not in parent_pilot.trust._issuers,
                    "LIFECYCLE_QUALIFICATION", "parent action signer cannot qualify itself")
            report_raw = Path(qualification_report_path).read_bytes()
            require(_sha(report_raw) == qualification_report_sha256,
                    "LIFECYCLE_QUALIFICATION", "externally pinned evaluator report differs")
            report = json.loads(report_raw)
            evaluator_raw = Path(qualification_evaluator_path).read_bytes()
            require(_sha(evaluator_raw) == qualification_evaluator_sha256,
                    "LIFECYCLE_QUALIFICATION", "approved evaluator code differs")
            policy = qualification_trust.verify(qualification, "AUTHORIZATION")
            require(all(policy.public_key != parent_policy.public_key
                        for parent_policy in parent_pilot.trust._issuers.values()),
                    "LIFECYCLE_QUALIFICATION", "parent action key reused under reviewer alias")
            require("PARENT_QUALIFICATION" in policy.operations and policy.can_review,
                    "LIFECYCLE_QUALIFICATION", "review authority is not enrolled")
            decision = qualification["payload"]
            artifact_hashes = {}
            artifact_bytes = {}
            for name, source in application_artifacts.items():
                relative = Path(name)
                require(not relative.is_absolute() and ".." not in relative.parts and
                        relative.parts and relative.parts[0] != "private_keys",
                        "LIFECYCLE_ARTIFACT", "invalid or secret archive name")
                artifact_bytes[name] = Path(source).read_bytes()
                artifact_hashes[name] = _sha(artifact_bytes[name])
            require(decision.get("kind") == "PARENT_QUALIFICATION" and
                    decision.get("phase") == "PARENT_READY_FOR_POSTPUBLICATION_SCENARIOS" and
                    decision.get("approved") is True and
                    decision.get("security_scope") == parent_pilot.config["security_scope"] and
                    decision.get("execution_mode") == parent_pilot.config["execution_mode"] and
                    decision.get("reviewer") and decision.get("evaluator_version") and
                    decision.get("evaluator_version") == report.get("evaluator_version") and
                    decision.get("evaluator_code_sha256") ==
                    report.get("evaluator_code_sha256") == qualification_evaluator_sha256 and
                    decision.get("report_sha256") == qualification_report_sha256 and
                    report.get("version") == "paper-pilot-parent-qualification-v1" and
                    report.get("phase") == "PARENT_READY_FOR_POSTPUBLICATION_SCENARIOS" and
                    report.get("status") == "PASS" and
                    report.get("recovery_status") in {"NOT_RUN", "HOLD"} and
                    set(decision.get("gates", {})) == required_qualification_gates and
                    decision["gates"] == report.get("gates") and
                    all(value == "PASS" for value in decision["gates"].values()) and
                    report.get("parent_run_id") == before["run_id"] and
                    report.get("config_sha256") == before["config_sha256"] and
                    report.get("checkpoint_head") == before["checkpoint_head"] and
                    report.get("graph_journal_head") == before["graph_journal_head"] and
                    report.get("imported_output_sha256") == before["imported_output_sha256"] and
                    decision.get("parent_run_id") == before["run_id"] and
                    decision.get("config_sha256") == before["config_sha256"] and
                    decision.get("checkpoint_head") == before["checkpoint_head"] and
                    decision.get("graph_journal_head") == before["graph_journal_head"] and
                    decision.get("imported_output_sha256") == before["imported_output_sha256"] and
                    decision.get("historical_execution_context_sha256") ==
                    before["historical_execution_context_sha256"] and
                    decision.get("artifact_sha256") == artifact_hashes,
                    "LIFECYCLE_QUALIFICATION", "parent qualification is not bound to durable run")
            remaining = {key: limit - before["budget"]["used"][key]
                         for key, limit in before["budget"]["limits"].items()}
            require(all(value >= 0 for value in remaining.values()),
                    "LIFECYCLE_BUDGET", "parent cumulative limit exceeded")
            target.mkdir(parents=True, exist_ok=False)
            archive = target / "parent_archive"
            archive.mkdir()
            successor = target / "successor"
            successor.mkdir()
            _write_once(target / "PREPARE_INTENT.json", _bytes({
                "version": "paper-pilot-successor-intent-v1", "parent_proof": before,
                "successor_config_sha256": digest(successor_config),
                "changed_documents": sorted(changed_documents)}))
            backup_hashes = {
                "graph.sqlite3": _backup(parent_pilot.backend.db, archive / "graph.sqlite3"),
                "checkpoint.sqlite3": _backup(parent_pilot.db, archive / "checkpoint.sqlite3"),
                "budget.sqlite3": _backup(parent_pilot.budget.db, archive / "budget.sqlite3"),
            }
            for name, connection in application_databases.items():
                require(name.endswith(".sqlite3") and "/" not in name and "\\" not in name and
                        name not in backup_hashes, "LIFECYCLE_BACKUP", "invalid application database name")
                backup_hashes[name] = _backup(connection, archive / name)
            _write_once(archive / "parent-config.json", _bytes(parent_pilot.config))
            _write_once(archive / "qualification.json", qualification_raw)
            _write_once(archive / "qualification-report.json", report_raw)
            _write_once(archive / "qualification-evaluator.py", evaluator_raw)
            for rid, raw in imported_outputs.items():
                require("/" not in rid and "\\" not in rid and rid not in {"", ".", ".."},
                        "LIFECYCLE_IMPORT", "invalid response ID")
                _write_once(archive / "imported_responses" / (rid + ".raw"), raw)
            for rid, context in historical_execution_contexts.items():
                require("/" not in rid and "\\" not in rid and rid not in {"", ".", ".."},
                        "LIFECYCLE_EXECUTION", "invalid execution context ID")
                _write_once(archive / "execution_contexts" / (rid + ".json"), _bytes(context))
            for name, source in application_artifacts.items():
                _write_once(archive / "application_artifacts" / name, artifact_bytes[name])
                require(_sha((archive / "application_artifacts" / name).read_bytes()) ==
                        artifact_hashes[name] and
                        _sha(Path(source).read_bytes()) == artifact_hashes[name],
                        "LIFECYCLE_ARTIFACT", "application artifact changed during archive")
            # SQLite backup, not file copying, includes committed WAL state.
            graph = sqlite3.connect(archive / "graph.sqlite3")
            try:
                successor_graph_sha = _backup(graph, successor / "graph.sqlite3")
            finally:
                graph.close()
            after = parent_proof(parent_pilot, assertion_ids=assertion_ids,
                                 source_ids=source_ids,
                                 completed_request_ids=completed_request_ids,
                                 imported_outputs=imported_outputs,
                                 historical_execution_contexts=historical_execution_contexts)
            require(after == before, "LIFECYCLE_PARENT", "parent changed during fork")
            result = {"version": "paper-pilot-successor-v1", "status": "PREPARED",
                      "parent": before, "successor_run_id": successor_config["run_id"],
                      "successor_config_sha256": digest(successor_config),
                      "changed_documents": sorted(changed_documents),
                      "remaining_budget_limits": remaining,
                      "parent_archive_sha256": backup_hashes,
                      "qualification_receipt_sha256": qualification_receipt_sha256,
                      "qualification_report_sha256": qualification_report_sha256,
                      "qualification_evaluator_sha256": qualification_evaluator_sha256,
                      "application_artifact_sha256": artifact_hashes,
                      "successor_graph_sha256": successor_graph_sha,
                      "checkpoint_transplanted": False, "budget_transplanted": False,
                      "new_model_calls": 0}
            _write_once(target / "FORK_MANIFEST.json", _bytes(result))
            return result


def status_change_once(backend, catalog, trust, *, source_id: str, active: bool,
                       permission: str, expected_epoch: int, expected_version: int,
                       key: str, reason: str, authorization: Mapping[str, Any],
                       intent_path: str | Path, at: str | None = None) -> dict[str, Any]:
    """Record caller-authorized intent before one backend transaction.

    On an unknown exception, retain the intent and reconcile separately.
    This method never retries an unknown outcome.
    """
    action = {"action": "STATUS_CHANGE", "source_id": source_id,
              "source_hash": catalog.hash(source_id), "active": active,
              "permission": permission, "expected_epoch": expected_epoch,
              "expected_version": expected_version,
              "security_scope": catalog.get(source_id, "source")["security_scope"],
              "reason": reason, "tombstone": False}
    require(authorization.get("payload") == action,
            "LIFECYCLE_AUTHORITY", "signed payload differs from status action")
    intent = {"version": "paper-pilot-status-intent-v1", "key": key,
              "action": action, "authorization_sha256": digest(authorization),
              "issued_at": authorization.get("issued_at"), "at": at}
    path = Path(intent_path)
    _write_once(path, _bytes(intent))
    result = backend.change_source_status(catalog, source_id, active=active,
        permission=permission, expected_epoch=expected_epoch,
        expected_version=expected_version, key=key, reason=reason,
        authorization=authorization, trust=trust, at=at)
    _write_once(path.with_name(path.stem + ".receipt.json"), _bytes({
        "event_hash": result["event"]["hash"], "receipt": result["receipt"]}))
    return result


def reconcile_status(backend, *, intent_path: str | Path,
                     authorization: Mapping[str, Any]) -> dict[str, Any]:
    """Read the authoritative journal; never issue a second status action."""
    intent = loads(Path(intent_path).read_text(encoding="utf-8"))
    require(intent["authorization_sha256"] == digest(authorization) and
            authorization.get("payload") == intent["action"],
            "LIFECYCLE_AUTHORITY", "reconciliation authority changed")
    backend.audit()
    row = backend.db.execute("SELECT body FROM trace_journal WHERE key=?",
                             (intent["key"],)).fetchone()
    if row is None:
        return {"state": "UNKNOWN_NOT_COMMITTED_HOLD", "automatic_retry": False}
    event = loads(row[0])
    require(event["operation"] == intent["action"] and
            event["authorization_hash"] == digest(authorization) and
            event["fingerprint"] == digest(intent["action"]),
            "LIFECYCLE_JOURNAL", "committed action differs from intent")
    result = {"replayed": True, "event": event,
              "receipt": event["transaction_receipt"]}
    _write_once(Path(intent_path).with_name(Path(intent_path).stem + ".receipt.json"),
                _bytes({"event_hash": event["hash"], "receipt": result["receipt"]}))
    return result
