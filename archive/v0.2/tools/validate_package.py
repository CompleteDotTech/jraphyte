#!/usr/bin/env python3
"""Offline TRACE-GC design-contract checks; never performs inference or graph writes.

This checker deliberately refuses deployment qualification. It validates the
included analysis-only fixture and selected cross-record invariants. A schema,
calibration identifier or model confidence cannot grant database authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
RECORD_TYPES = {
    "evidence": ("evidence", "evidence_id"),
    "candidates": ("candidate", "candidate_id"),
    "packs": ("question-pack", "pack_id"),
    "decisions": ("decision", "decision_id"),
    "resolutions": ("resolution", "resolution_id"),
    "plans": ("mutation-plan", "plan_id"),
    "ledger": ("ledger-event", "event_id"),
}


class ContractError(ValueError):
    """A locally checkable contract failed, with a stable diagnostic code."""


def require(condition: bool, code: str, detail: str) -> None:
    if not condition:
        raise ContractError(f"{code}: {detail}")


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def text_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_json(path: Path) -> Any:
    def reject_constant(value: str) -> None:
        raise ContractError(f"NONFINITE_JSON: {value}")
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_constant)


def validate_schema(name: str, record: Any) -> None:
    schema = load_json(ROOT / "schemas" / f"{name}.schema.json")
    Draft202012Validator.check_schema(schema)
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(record))
    if errors:
        error = errors[0]
        location = "/".join(map(str, error.absolute_path)) or "<root>"
        raise ContractError(f"SCHEMA_ERROR: {name}/{location}: {error.message}")


def check_distribution(values: Mapping[str, Any], labels: set[str]) -> None:
    require(set(values) == labels, "DISTRIBUTION_LABELS", "answer labels do not match the question")
    for key, value in values.items():
        require(type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1,
                "MALFORMED_DISTRIBUTION", f"invalid probability for {key}")
    require(math.isclose(sum(values.values()), 1.0, rel_tol=0, abs_tol=1e-6),
            "MALFORMED_DISTRIBUTION", "probabilities must sum to one; no silent renormalization")


def unique_index(records: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in records:
        require(item[key] not in result, "DUPLICATE_ID", str(item[key]))
        result[item[key]] = item
    return result


def validate_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    expected = {"notice", "sources", "graph", "policy", *RECORD_TYPES}
    require(set(bundle) == expected, "BUNDLE_FIELDS", "unexpected or missing bundle fields")
    require(isinstance(bundle["notice"], str) and "SYNTHETIC" in bundle["notice"],
            "FIXTURE_NOTICE", "this checker is for explicit synthetic analysis fixtures")
    indices: dict[str, dict[str, Any]] = {}
    all_records: dict[str, Any] = {}
    for collection, (name, key) in RECORD_TYPES.items():
        for record in bundle[collection]:
            validate_schema(name, record)
        indices[collection] = unique_index(bundle[collection], key)
        for id_, record in indices[collection].items():
            require(id_ not in all_records, "DUPLICATE_ID", f"cross-type collision {id_}")
            all_records[id_] = record
    validate_schema("graph", bundle["graph"])
    validate_schema("risk-policy", bundle["policy"])
    graph, policy = bundle["graph"], bundle["policy"]
    require(graph["execution_mode"] == "SYNTHETIC", "MODE_MISMATCH", "fixture graph must be synthetic")
    require(graph["status"] == "ANALYSIS_ONLY" and not graph["accepted_assertion_refs"],
            "UNAUTHORIZED_MUTATION", "this fixture cannot publish accepted assertions")
    require(policy["mode"] == "ANALYSIS_ONLY" and policy["calibration_ref"] is None,
            "UNQUALIFIED_POLICY", "deployment qualification is intentionally not implemented by this checker")
    require({r["risk_class"] for r in policy["rules"]} == {f"R{i}" for i in range(6)},
            "RISK_POLICY_COVERAGE", "R0 through R5 must appear exactly once")
    require(len({r["risk_class"] for r in policy["rules"]}) == len(policy["rules"]),
            "RISK_POLICY_COVERAGE", "duplicate risk class")
    require(all(not r["automatic"] and r["threshold"] is None and r["calibration_ref"] is None
                for r in policy["rules"]), "UNQUALIFIED_POLICY", "analysis-only policy has no automatic thresholds")

    def refs_exist(refs: list[str], collection: str, code: str = "MISSING_REFERENCE") -> None:
        require(set(refs) <= indices[collection].keys(), code, f"unresolved {collection} reference")

    sources = unique_index(bundle["sources"], "source_id")
    for source in sources.values():
        require(set(source) == {"source_id", "source_version", "representation_id", "text", "document_hash", "active"},
                "SOURCE_FIELDS", "source representation is incomplete or has unknown fields")
        require(isinstance(source["text"], str) and bool(source["text"]), "SOURCE_TEXT", "nonempty text required")
        require(type(source["active"]) is bool, "SOURCE_FIELDS", "active must be boolean")
        require(text_digest(source["text"]) == source["document_hash"], "PROVENANCE_MISMATCH", "source hash changed")
    for e in bundle["evidence"]:
        require(e["source_id"] in sources, "MISSING_REFERENCE", "source not found")
        source = sources[e["source_id"]]
        require(e["source_version"] == source["source_version"] and e["representation_id"] == source["representation_id"],
                "PROVENANCE_MISMATCH", "source version/representation changed")
        require(e["document_hash"] == source["document_hash"], "PROVENANCE_MISMATCH", "evidence document hash changed")
        require(0 <= e["span_start"] < e["span_end"] <= len(source["text"]), "PROVENANCE_MISMATCH", "invalid evidence offsets")
        require(source["text"][e["span_start"]:e["span_end"]] == e["quoted_span"],
                "PROVENANCE_MISMATCH", "quoted span differs from immutable source")
        refs_exist([e["candidate_id"]], "candidates")
        refs_exist(e["assessment_decision_refs"], "decisions")
        if e["validity_start"] and e["validity_end"]:
            from datetime import datetime
            require(datetime.fromisoformat(e["validity_start"].replace("Z", "+00:00")) <
                    datetime.fromisoformat(e["validity_end"].replace("Z", "+00:00")),
                    "TEMPORAL_ERROR", "validity end must follow start")

    pending: dict[str, set[str]] = {}
    for c in bundle["candidates"]:
        require(c["source_mode"] == "SYNTHETIC" and c["run_id"] == graph["run_id"], "MODE_MISMATCH", "candidate belongs to another run/mode")
        refs_exist(c["evidence_refs"], "evidence")
        refs_exist(c["prerequisite_candidate_refs"], "candidates")
        refs_exist(c["alternative_candidate_refs"], "candidates")
        require(all(indices["evidence"][r]["candidate_id"] == c["candidate_id"] for r in c["evidence_refs"]),
                "EVIDENCE_CANDIDATE_MISMATCH", "assessment belongs to another candidate")
        pending[c["candidate_id"]] = set(c["prerequisite_candidate_refs"])
    done: set[str] = set()
    while pending:
        ready = {k for k, dependencies in pending.items() if dependencies <= done}
        require(bool(ready), "DEPENDENCY_CYCLE", "candidate prerequisites must be acyclic")
        done |= ready
        pending = {k: deps for k, deps in pending.items() if k not in ready}

    questions: dict[tuple[str, str], dict[str, Any]] = {}
    for pack in bundle["packs"]:
        require(pack["run_id"] == graph["run_id"], "MODE_MISMATCH", "pack belongs to another run")
        require(pack["closure_complete"], "CLOSURE_INCOMPLETE", "required context cannot be silently truncated")
        require(pack["graph_snapshot_version"] == graph["initial_graph_version"] and pack["schema_hash"] == graph["schema_hash"],
                "STALE_GRAPH_VERSION", "pack snapshot differs from graph manifest")
        require(pack["model_version"] == policy["expected_model_version"] and
                pack["question_program_version"] == policy["question_program_version"], "MODEL_VERSION_MISMATCH", "program/model not bound to policy")
        refs_exist(pack["candidate_refs"], "candidates"); refs_exist(pack["evidence_refs"], "evidence")
        required = set(pack["candidate_refs"]) | set(pack["evidence_refs"])
        for ref in pack["candidate_refs"]:
            required |= set(indices["candidates"][ref]["evidence_refs"]) | set(indices["candidates"][ref]["prerequisite_candidate_refs"])
        require(required <= set(pack["closure_requirement_refs"]), "CLOSURE_INCOMPLETE", "declared closure omitted required references")
        require(set(pack["closure_requirement_refs"]) <= all_records.keys(), "MISSING_REFERENCE", "closure reference unresolved")
        for ref in pack["evidence_refs"]:
            e = indices["evidence"][ref]
            require(e["integrity_status"] == "VERIFIED" and sources[e["source_id"]]["active"],
                    "STALE_EVIDENCE", "decision evidence is unverified or withdrawn")
        ids = {q["question_id"] for q in pack["questions"]}
        require(len(ids) == len(pack["questions"]), "DUPLICATE_ID", "duplicate question ID")
        for q in pack["questions"]:
            require(q["candidate_id"] in pack["candidate_refs"], "MISSING_REFERENCE", "question target absent")
            require(q["candidate_id"] in q["instructions"], "QUESTION_TARGET_AMBIGUOUS", "target cannot be conveyed only by question key")
            require(not ids.intersection(q["depends_on_question_ids"]), "PACK_DEPENDENCY_VIOLATION", "same-pack answer dependency")
            refs_exist(q["prior_decision_refs"], "decisions")
            require(all(indices["decisions"][r]["pack_id"] != pack["pack_id"] for r in q["prior_decision_refs"]),
                    "PACK_DEPENDENCY_VIOLATION", "same-pack prior decision")
            labels = [o["label"] for o in q["criteria"]]
            require(len(labels) == len(set(labels)), "DISTRIBUTION_LABELS", "duplicate option label")
            if q["primitive"] == "NOUL":
                require(set(labels) == {"YES", "NO"}, "DISTRIBUTION_LABELS", "Noul needs YES/NO semantics")
            if q["primitive"] == "SCORE":
                require(labels == [str(i) for i in range(len(labels))], "DISTRIBUTION_LABELS", "ordered Score level indices required")
            questions[pack["pack_id"], q["question_id"]] = q
        require(pack["state_hash"] == digest(pack["state"]), "STATE_HASH_MISMATCH", "rendered state changed")
        require(pack["request_hash"] == digest({"model": pack["model_version"], "state": pack["state"], "questions": pack["questions"]}),
                "REQUEST_HASH_MISMATCH", "model/state/question request changed")
        token = pack["token_accounting"]
        require(set(token["question_tokens"]) == ids, "PACK_BUDGET_ACCOUNTING", "all question estimates required")
        require(token["state_tokens"] + sum(token["question_tokens"].values()) <= token["request_cap"],
                "PACK_BUDGET_EXCEEDED", "total request cap exceeded")
        require(token["state_tokens"] + max(token["question_tokens"].values()) <= token["state_longest_cap"],
                "PACK_BUDGET_EXCEEDED", "state plus longest question cap exceeded")

    for d in bundle["decisions"]:
        require(d["execution_mode"] == "SYNTHETIC", "MODE_MISMATCH", "fixture decision cannot impersonate live inference")
        require(d["pack_id"] in indices["packs"], "MISSING_REFERENCE", "decision pack absent")
        require((d["pack_id"], d["question_id"]) in questions, "MISSING_REFERENCE", "decision question absent")
        q, pack = questions[d["pack_id"], d["question_id"]], indices["packs"][d["pack_id"]]
        require(d["candidate_id"] == q["candidate_id"] and d["candidate_id"] in indices["candidates"], "CANDIDATE_BINDING", "decision target differs")
        require(d["candidate_hash"] == digest(indices["candidates"][d["candidate_id"]]), "CANDIDATE_BINDING", "candidate bytes changed")
        require(d["question_hash"] == digest(q) and d["question_schema_version"] == q["question_schema_version"],
                "QUESTION_HASH_MISMATCH", "question meaning/version changed")
        require(d["state_hash"] == pack["state_hash"] and d["request_hash"] == pack["request_hash"],
                "REQUEST_HASH_MISMATCH", "decision is not bound to this exact input")
        require(d["primitive"] == q["primitive"], "PRIMITIVE_MISMATCH", "response type differs")
        refs_exist(d["evidence_refs"], "evidence"); refs_exist(d["parent_decision_refs"], "decisions")
        require(set(d["evidence_refs"]) <= set(pack["evidence_refs"]), "EVIDENCE_CANDIDATE_MISMATCH", "decision evidence not in pack")
        require(d["confidence_band"] == "UNQUALIFIED" and d["calibration_ref"] is None,
                "UNQUALIFIED_POLICY", "fixture cannot manufacture calibration")
        require(d["policy_version"] == policy["policy_version"] and d["policy_result"] != "ACCEPT",
                "UNQUALIFIED_POLICY", "analysis-only decision cannot authorize acceptance")
        if d["status"] == "ERROR":
            continue
        require(d["model"]["requested_version"] == pack["model_version"] == d["model"]["returned_version"],
                "MODEL_VERSION_MISMATCH", "requested and returned versions differ")
        raw, values = d["raw_answer"], d["probability_distribution"]
        require(raw["type"].upper() == d["primitive"], "PRIMITIVE_MISMATCH", "raw response type differs")
        labels = {o["label"] for o in q["criteria"]}
        check_distribution(values, labels)
        if d["primitive"] == "NOUL":
            require(values == {"YES": raw["noul"], "NO": 1 - raw["noul"]}, "DISTRIBUTION_MISMATCH", "binary complement differs")
            require(d["raw_confidence"] is None and d["semantic_outcome"] is None and d["outcome_derivation"] == "BINARY_PROPOSITION",
                    "NOUL_CONTRACT", "no invented confidence or thresholded outcome")
        else:
            require(values == raw["probabilities"] and d["raw_confidence"] == raw["confidence"],
                    "DISTRIBUTION_MISMATCH", "raw observation was rewritten")
            if d["primitive"] == "CHOICE":
                require(raw["choice"] in values and values[raw["choice"]] == max(values.values()),
                        "CHOICE_OUTCOME_MISMATCH", "selected label not maximal")
                require(d["semantic_outcome"] == raw["choice"] and d["outcome_derivation"] == "RAW_CHOICE",
                        "CHOICE_OUTCOME_MISMATCH", "semantic outcome differs from raw choice")
            else:
                require(set(raw["legend"]) == labels, "DISTRIBUTION_LABELS", "Score legend differs")
                mean = sum(int(k) * p for k, p in values.items())
                require(math.isclose(raw["score"], mean, rel_tol=0, abs_tol=1e-6), "SCORE_MEAN_MISMATCH", "expected value differs")
                require(d["semantic_outcome"] is None and d["outcome_derivation"] == "NOT_DERIVED",
                        "SCORE_MEAN_AS_CATEGORY", "mean cannot be rounded into a semantic category")

    for r in bundle["resolutions"]:
        refs_exist([r["candidate_id"]], "candidates"); refs_exist(r["decision_refs"], "decisions"); refs_exist(r["evidence_refs"], "evidence")
        require(r["policy_version"] == policy["policy_version"] and r["calibration_ref"] is None,
                "UNQUALIFIED_POLICY", "resolver policy mismatch")
        require(r["outcome"] != "ACCEPT", "UNQUALIFIED_POLICY", "analysis-only resolution cannot accept")
        require(all(indices["decisions"][x]["candidate_id"] == r["candidate_id"] for x in r["decision_refs"]),
                "CANDIDATE_BINDING", "resolver combines another candidate's decisions")
        if r["outcome"] == "RETRIEVE_MORE_EVIDENCE":
            require(r["acquisition_request"] is not None and r["acquisition_request"]["max_requests"] > 0,
                    "ACQUISITION_BUDGET", "acquisition requires a remaining request budget")

    risk_floor = {"ATTACH_CANDIDATE_METADATA":1,"ADD_ASSERTION":2,"RETRACT_ASSERTION":3,
                  "ADD_IDENTITY_ASSERTION":4,"PROPOSE_SCHEMA_MIGRATION":5}
    for p in bundle["plans"]:
        require(p["run_id"] == graph["run_id"] and p["execution_mode"] == "SYNTHETIC", "MODE_MISMATCH", "plan run or mode differs")
        require(p["status"] not in {"READY", "COMMITTED"} and p["authorization"] != "AUTHORIZED",
                "UNAUTHORIZED_MUTATION", "fixture cannot publish a plan")
        require(p["expected_graph_version"] == graph["initial_graph_version"] and p["expected_schema_hash"] == graph["schema_hash"],
                "STALE_GRAPH_VERSION", "plan snapshot mismatch")
        require(p["policy_version"] == policy["policy_version"] and p["calibration_ref"] is None,
                "UNQUALIFIED_POLICY", "plan policy mismatch")
        for op in p["operations"]:
            refs_exist([op["candidate_ref"]], "candidates"); refs_exist([op["resolution_ref"]], "resolutions")
            refs_exist(op["evidence_refs"], "evidence"); refs_exist(op["decision_refs"], "decisions")
            require(int(op["risk_class"][1:]) >= risk_floor[op["operation"]], "RISK_UNDERCLASSIFIED", "operation cannot lower its risk floor")
            require(indices["resolutions"][op["resolution_ref"]]["candidate_id"] == op["candidate_ref"],
                    "CANDIDATE_BINDING", "plan resolution belongs to another candidate")
            require(bool(op["evidence_refs"]) and bool(op["decision_refs"]), "MISSING_EVIDENCE", "this fixture operation requires evidence and decisions")
            for ref in op["evidence_refs"]:
                require(p["precondition_evidence_hashes"].get(ref) == indices["evidence"][ref]["document_hash"],
                        "PROVENANCE_MISMATCH", "plan evidence precondition missing or changed")

    previous, seen = None, set()
    for i, event in enumerate(bundle["ledger"], 1):
        require(event["sequence"] == i and event["previous_event_hash"] == previous, "LEDGER_CHAIN", "event ordering/previous hash mismatch")
        require(set(event["parent_event_refs"]) <= seen, "LEDGER_CHAIN", "parent event not earlier in this ledger")
        require(set(event["payload_refs"]) <= all_records.keys(), "MISSING_REFERENCE", "ledger payload absent")
        require(event["payload_hash"] == digest([all_records[x] for x in event["payload_refs"]]), "LEDGER_PAYLOAD", "payload hash mismatch")
        body = {k:v for k,v in event.items() if k != "event_hash"}
        require(event["event_hash"] == digest(body), "LEDGER_HASH", "event content changed")
        previous = event["event_hash"]; seen.add(event["event_id"])
    for field, collection in [("evidence_refs","evidence"),("candidate_refs","candidates"),("pack_refs","packs"),
                              ("decision_refs","decisions"),("resolution_refs","resolutions"),("mutation_plan_refs","plans"),
                              ("ledger_event_refs","ledger")]:
        require(set(graph[field]) == indices[collection].keys(), "GRAPH_MANIFEST", f"{field} does not enumerate its records")
    return {"status":"PASS", "schema_count":9, "record_count":len(all_records)+2,
            "model_calls":0, "graph_commits":0, "calibration_qualified":False,
            "scope":"Offline synthetic schema and selected cross-record contracts only."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", nargs="?", type=Path, default=ROOT/"examples"/"bundle.json")
    args = parser.parse_args()
    try:
        print(json.dumps(validate_bundle(load_json(args.bundle)), indent=2))
    except (ContractError, OSError, json.JSONDecodeError) as exc:
        parser.exit(1, f"Validation failed: {exc}\n")


if __name__ == "__main__":
    main()
