"""Offline positive and adversarial tests for the revision's record contracts."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from validate_package import ContractError, RECORD_TYPES, digest, load_json, validate_bundle


def fixture():
    return deepcopy(load_json(ROOT / "examples" / "bundle.json"))


def refresh_ledger(b):
    records = {}
    for name, (_, id_field) in RECORD_TYPES.items():
        records.update({r[id_field]:r for r in b[name]})
    previous = None
    for event in b["ledger"]:
        event["previous_event_hash"] = previous
        event["payload_hash"] = digest([records[x] for x in event["payload_refs"]])
        event["event_hash"] = digest({k:v for k,v in event.items() if k != "event_hash"})
        previous = event["event_hash"]


def rebind(b):
    """Refresh fixture hashes after an intentional semantic-program mutation.

    This only constructs synthetic tests; a real changed input requires new
    inference, not this rebinding operation.
    """
    candidates = {x["candidate_id"]:x for x in b["candidates"]}
    for p in b["packs"]:
        p["state_hash"] = digest(p["state"])
        p["request_hash"] = digest({"model":p["model_version"],"state":p["state"],"questions":p["questions"]})
        qs = {q["question_id"]:q for q in p["questions"]}
        for d in b["decisions"]:
            if d["pack_id"] == p["pack_id"] and d["question_id"] in qs:
                d["candidate_hash"] = digest(candidates[d["candidate_id"]])
                d["question_hash"] = digest(qs[d["question_id"]])
                d["state_hash"] = p["state_hash"]
                d["request_hash"] = p["request_hash"]
    refresh_ledger(b)


class ContractTests(unittest.TestCase):
    def rejects(self, b, code):
        with self.assertRaisesRegex(ContractError, code):
            validate_bundle(b)

    def test_01_valid_synthetic_bundle(self):
        result = validate_bundle(fixture())
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["model_calls"], 0)
        self.assertFalse(result["calibration_qualified"])

    def test_02_source_bytes_changed(self):
        b=fixture(); b["sources"][0]["text"] += " altered"
        self.rejects(b, "PROVENANCE_MISMATCH")

    def test_03_wrong_quote(self):
        b=fixture(); b["evidence"][0]["quoted_span"] = "A different quotation."
        self.rejects(b, "PROVENANCE_MISMATCH")

    def test_04_span_out_of_bounds(self):
        b=fixture(); b["evidence"][0]["span_end"] = 100000
        self.rejects(b, "PROVENANCE_MISMATCH")

    def test_05_source_version_changed(self):
        b=fixture(); b["evidence"][0]["source_version"] = "v2"
        self.rejects(b, "PROVENANCE_MISMATCH")

    def test_06_withdrawn_source(self):
        b=fixture(); b["sources"][0]["active"] = False
        self.rejects(b, "STALE_EVIDENCE")

    def test_07_missing_source(self):
        b=fixture(); b["sources"] = []
        self.rejects(b, "MISSING_REFERENCE")

    def test_08_noul_has_no_vendor_confidence(self):
        b=fixture(); b["decisions"][1]["raw_confidence"] = 0.9
        self.rejects(b, "SCHEMA_ERROR")

    def test_09_noul_raw_unknown_field(self):
        b=fixture(); b["decisions"][1]["raw_answer"]["confidence"] = 0.9
        self.rejects(b, "SCHEMA_ERROR")

    def test_10_score_mean_not_category(self):
        b=fixture(); b["decisions"][2]["semantic_outcome"] = "1"
        self.rejects(b, "SCORE_MEAN_AS_CATEGORY")

    def test_11_score_wrong_expected_value(self):
        b=fixture(); b["decisions"][2]["raw_answer"]["score"] = 1.5
        self.rejects(b, "SCORE_MEAN_MISMATCH")

    def test_12_distribution_sum(self):
        b=fixture(); d=b["decisions"][0]
        d["probability_distribution"]["SUPPORTS"] = 0.7
        d["raw_answer"]["probabilities"]["SUPPORTS"] = 0.7
        self.rejects(b, "MALFORMED_DISTRIBUTION")

    def test_13_boolean_probability(self):
        b=fixture(); b["decisions"][0]["probability_distribution"]["SUPPORTS"] = True
        self.rejects(b, "SCHEMA_ERROR")

    def test_14_missing_distribution_label(self):
        b=fixture(); del b["decisions"][0]["probability_distribution"]["CONTRADICTS"]
        self.rejects(b, "DISTRIBUTION_LABELS")

    def test_15_wrong_choice_polarity(self):
        b=fixture(); b["decisions"][0]["semantic_outcome"] = "CONTRADICTS"
        self.rejects(b, "CHOICE_OUTCOME_MISMATCH")

    def test_16_model_version_mismatch(self):
        b=fixture(); b["decisions"][0]["model"]["returned_version"] = "another-version"
        self.rejects(b, "MODEL_VERSION_MISMATCH")

    def test_17_candidate_mutated_after_decision(self):
        b=fixture(); b["candidates"][0]["assertion"]["predicate"] = "refutes"
        self.rejects(b, "CANDIDATE_BINDING")

    def test_18_question_mutated_without_new_request(self):
        b=fixture(); b["packs"][0]["questions"][0]["instructions"] += " Changed semantic criterion."
        self.rejects(b, "REQUEST_HASH_MISMATCH")

    def test_19_state_changed_without_new_request(self):
        b=fixture(); b["packs"][0]["state"]["claim"] = "An altered claim."
        self.rejects(b, "STATE_HASH_MISMATCH")

    def test_20_same_pack_answer_dependency(self):
        b=fixture(); b["packs"][0]["questions"][1]["depends_on_question_ids"] = ["q-support"]
        rebind(b); self.rejects(b, "PACK_DEPENDENCY_VIOLATION")

    def test_21_total_request_budget(self):
        b=fixture(); b["packs"][0]["token_accounting"]["request_cap"] = 100
        self.rejects(b, "PACK_BUDGET_EXCEEDED")

    def test_22_state_longest_budget(self):
        b=fixture(); b["packs"][0]["token_accounting"]["state_longest_cap"] = 150
        self.rejects(b, "PACK_BUDGET_EXCEEDED")

    def test_23_question_target_cannot_be_only_map_key(self):
        b=fixture(); b["packs"][0]["questions"][0]["instructions"] = "Is this supported?"
        rebind(b); self.rejects(b, "QUESTION_TARGET_AMBIGUOUS")

    def test_24_incomplete_closure(self):
        b=fixture(); b["packs"][0]["closure_complete"] = False
        self.rejects(b, "CLOSURE_INCOMPLETE")

    def test_25_omitted_evidence_dependency(self):
        b=fixture(); b["packs"][0]["closure_requirement_refs"] = ["candidate-demo"]
        self.rejects(b, "CLOSURE_INCOMPLETE")

    def test_26_fake_calibration_band(self):
        b=fixture(); b["decisions"][0]["confidence_band"] = "HIGH"
        self.rejects(b, "UNQUALIFIED_POLICY")

    def test_27_auto_rule_without_qualification(self):
        b=fixture(); b["policy"]["rules"][2]["automatic"] = True
        self.rejects(b, "UNQUALIFIED_POLICY")

    def test_28_plan_cannot_be_ready(self):
        b=fixture(); b["plans"][0]["status"] = "READY"
        self.rejects(b, "UNAUTHORIZED_MUTATION")

    def test_29_accepted_view_cannot_be_published(self):
        b=fixture(); b["graph"]["accepted_assertion_refs"] = ["candidate-demo"]
        self.rejects(b, "UNAUTHORIZED_MUTATION")

    def test_30_stale_plan_graph_version(self):
        b=fixture(); b["plans"][0]["expected_graph_version"] = 1
        self.rejects(b, "STALE_GRAPH_VERSION")

    def test_31_risk_cannot_be_lowered_by_operation(self):
        b=fixture(); b["plans"][0]["operations"][0]["risk_class"] = "R1"
        self.rejects(b, "RISK_UNDERCLASSIFIED")

    def test_32_duplicate_record_id(self):
        b=fixture(); b["evidence"].append(deepcopy(b["evidence"][0]))
        self.rejects(b, "DUPLICATE_ID")

    def test_33_manifest_must_enumerate_records(self):
        b=fixture(); b["graph"]["decision_refs"] = []
        self.rejects(b, "GRAPH_MANIFEST")

    def test_34_ledger_payload_tampering(self):
        b=fixture(); b["ledger"][0]["payload_hash"] = "0"*64
        self.rejects(b, "LEDGER_PAYLOAD")

    def test_35_ledger_chain_tampering(self):
        b=fixture(); b["ledger"][1]["previous_event_hash"] = "0"*64
        self.rejects(b, "LEDGER_CHAIN")

    def test_36_mode_cannot_impersonate_live(self):
        b=fixture(); b["decisions"][0]["execution_mode"] = "LIVE"
        self.rejects(b, "MODE_MISMATCH")

    def test_37_error_receipt_is_not_semantic_negative(self):
        b=fixture(); d=b["decisions"][0]
        d.update(status="ERROR", raw_answer=None, probability_distribution=None,
                 raw_confidence=None, semantic_outcome=None,
                 outcome_derivation="OPERATIONAL_FAILURE", error="Synthetic transport failure")
        refresh_ledger(b)
        self.assertEqual(validate_bundle(b)["status"], "PASS")

    def test_38_contradictory_evidence_is_preserved_not_dropped(self):
        b=fixture(); b["evidence"][0]["semantic_tags"].append("CONTRADICTING_EVIDENCE")
        refresh_ledger(b)
        self.assertEqual(validate_bundle(b)["status"], "PASS")

    def test_39_acyclic_candidate_dependencies(self):
        b=fixture(); b["candidates"][0]["prerequisite_candidate_refs"] = ["candidate-demo"]
        self.rejects(b, "DEPENDENCY_CYCLE")

    def test_40_empty_evidence_cannot_support_operation(self):
        b=fixture(); b["plans"][0]["operations"][0]["evidence_refs"] = []
        self.rejects(b, "MISSING_EVIDENCE")

    def test_41_score_probability_distribution_not_rewritten(self):
        b=fixture(); b["decisions"][2]["raw_answer"]["probabilities"] = {"0":0,"1":1,"2":0}
        self.rejects(b, "DISTRIBUTION_MISMATCH")

    def test_42_unknown_fields_are_not_silently_accepted(self):
        b=fixture(); b["plans"][0]["execute_sql"] = "FORBIDDEN"
        self.rejects(b, "SCHEMA_ERROR")


if __name__ == "__main__":
    unittest.main()
