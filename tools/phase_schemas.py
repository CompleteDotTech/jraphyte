"""Strict versioned schemas for explicit PaperPilot phase handoff."""
from copy import deepcopy


def extend(schemas):
    text = {"type": "string", "minLength": 1}
    sha = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
    mapping = lambda value: {"type": "object", "additionalProperties": deepcopy(value)}
    def obj(fields):
        return {"type": "object", "properties": deepcopy(fields),
                "required": list(fields), "additionalProperties": False}
    event = {"type": "array", "prefixItems": [
        {"type": "integer", "minimum": 1}, text, sha], "minItems": 3, "maxItems": 3}
    schemas["paper-pilot-phase-capsule"] = obj({
        "version": {"const": "paper-pilot-phase-capsule-v1"},
        "run_id": text, "config": {"type": "object"},
        "old_implementation": {"type": "object"},
        "checkpoint_events": {"type": "array", "items": event, "minItems": 1},
        "checkpoint_head": sha, "blobs": mapping(text),
        "catalog_records": {"type": "array", "items": schemas["record"]},
        "database_state": obj({key: sha for key in
            ("checkpoint", "graph", "budget", "application_journal")}),
        "database_backup_sha256": obj({key: sha for key in
            ("checkpoint", "graph", "budget", "application_journal")}),
        "graph_state": {"type": "object"}, "source_statuses": {"type": "object"},
        "budget_snapshot": {"type": "object"},
        "application_journal_events": {"type": "array", "items": event, "minItems": 1},
        "application_journal_head": sha,
        "external_semantic_intent_sha256": sha,
        "external_semantic_intent": {"type": "object"},
        "external_semantic_intent_base64": text,
        "attempt_manifest_sha256": sha,
        "attempt_manifest": {"type": "object"},
        "attempt_manifest_base64": text,
        "attempt_inventory": mapping({"anyOf": [sha, {"type": "null"}]}),
        "source_receipt_sha256": mapping(sha), "source_open_sha256": sha,
    })
    schemas["paper-pilot-phase-import"] = obj({
        "version": {"const": "paper-pilot-phase-authorization-v1"},
        "operation": {"const": "PHASE_IMPORT"},
        "capsule_sha256": sha, "target_implementation_sha256": sha,
        "run_id": text,
    })
