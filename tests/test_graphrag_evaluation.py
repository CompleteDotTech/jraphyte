import unittest
from trace_gc.errors import ContractError
from trace_gc.retrieval.evaluation import retrieval_metrics, synthesis_metrics, efficiency_metrics, heldout_policy_gate, propose_retrieval_changes

class EvaluationTests(unittest.TestCase):
    def test_retrieval_metrics_known_vector(self):
        m = retrieval_metrics(["a", "x", "b"], {"a": 2, "b": 1}, k=2)
        self.assertEqual(m["precision_at_k"], .5)
        self.assertEqual(m["recall_at_k"], .5)
        self.assertEqual(m["mrr"], 1)
        self.assertGreater(m["ndcg_at_k"], 0)
        self.assertLess(m["ndcg_at_k"], 1)
    def test_duplicates_and_saturation(self):
        m = retrieval_metrics(["a", "a"], {"a": 1}, k=1, previous_ids=["a"])
        self.assertEqual(m["context_redundancy"], .5)
        self.assertTrue(m["retrieval_saturation"])
    def test_no_labels_not_invented(self):
        m = retrieval_metrics([], {}, k=3)
        self.assertIsNone(m["recall_at_k"])
        self.assertIsNone(m["provenance_recall"])
    def test_synthesis_metrics(self):
        m = synthesis_metrics(predicted_edges=["a", "b"], expected_edges=["a", "c"],
            entity_decisions=[{"same_entity": False, "predicted_same": True}],
            assertion_labels=[{"supported": True}, {"supported": False}],
            decisions=[{"decision": "ABSTAIN", "ambiguous": True, "has_conflict": True, "conflict_handled": True}])
        self.assertEqual(m["edge_f1"], .5)
        self.assertEqual(m["false_merge_rate"], 1)
        self.assertEqual(m["unsupported_assertion_rate"], .5)
        self.assertEqual(m["abstention_quality"], 1)
    def test_efficiency_zero_denominator_is_null(self):
        m = efficiency_metrics([])
        self.assertIsNone(m["cost_units_per_accepted_assertion"])
        self.assertIsNone(m["currency_cost"])
    def args(self):
        return dict(baseline="base", development_scores={"base": .5, "new": .7}, heldout_scores={"base": .5, "new": .6},
                    development_groups=["development"], heldout_groups=["holdout"], locked_candidate="new")
    def test_heldout_improvement_required(self):
        value = heldout_policy_gate(**self.args())
        self.assertTrue(value["retained_change"])
        self.assertFalse(value["production_qualified"])
    def test_heldout_regression_not_retained(self):
        args = self.args()
        args["heldout_scores"]["new"] = .4
        self.assertFalse(heldout_policy_gate(**args)["retained_change"])
    def test_safety_regression_not_retained(self):
        self.assertFalse(heldout_policy_gate(**self.args(), safety_passed=False)["retained_change"])
    def test_holdout_leakage_rejected(self):
        args = self.args()
        args["heldout_groups"] = ["development"]
        with self.assertRaisesRegex(ContractError, "EVALUATION_LEAKAGE"):
            heldout_policy_gate(**args)
    def test_selection_cannot_peek_at_holdout(self):
        args = self.args()
        args["locked_candidate"] = "base"
        with self.assertRaisesRegex(ContractError, "EVALUATION_PROTOCOL"):
            heldout_policy_gate(**args)
    def test_failure_driven_proposal(self):
        values = propose_retrieval_changes(["CONTRADICTION_NOT_RETRIEVED"])
        self.assertIn("CONFLICT", values[0]["proposed_channels"])
        self.assertTrue(values[0]["review_required"])
