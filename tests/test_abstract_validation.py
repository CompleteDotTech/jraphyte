import tempfile
import unittest
from pathlib import Path

from src.abstract_validation.embedding_batch import BudgetLedger


class EmbeddingLedgerTests(unittest.TestCase):
    def test_retry_keeps_failed_charge_reservation_and_exact_input(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger = BudgetLedger(Path(folder) / 'calls.sqlite', cap=.003)
            call = ledger.reserve('page_1', 'a'*64, .001)
            ledger.finish(call, 'error', 429, None, 'error.json')
            with self.assertRaises(ValueError):
                ledger.reserve('page_1', 'a'*64, .001)
            with self.assertRaises(ValueError):
                ledger.reserve('page_1', 'b'*64, .001, retry=True)
            retry = ledger.reserve('page_1', 'a'*64, .001, retry=True)
            ledger.finish(retry, 'ok', 200, .0001161, 'ok.json')
            self.assertAlmostEqual(ledger.totals()['reserved_usd'], .002)
            self.assertEqual(ledger.totals()['states'], {'error': 1, 'ok': 1})
            with self.assertRaises(ValueError):
                ledger.reserve('page_1', 'a'*64, .001, retry=True)

    def test_inflight_request_is_not_resubmitted(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger = BudgetLedger(Path(folder) / 'calls.sqlite')
            ledger.reserve('page_1', 'a'*64, .001)
            with self.assertRaises(ValueError):
                ledger.reserve('page_1', 'a'*64, .001, retry=True)


class RetrievalMetricsTests(unittest.TestCase):
    def test_rectangular_ranking_uses_target_identity(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest('Optional NumPy environment not installed')
        from src.abstract_validation.evaluate import ranking_metrics
        # Targets deliberately differ from query row numbers.
        scores = np.asarray([[1, 0, 3, 2], [3, 0, 1, 2]], dtype=float)
        queries = [{'query_id': 'q1', 'target_id': 'd'}, {'query_id': 'q2', 'target_id': 'a'}]
        result = ranking_metrics(scores, ['a', 'b', 'c', 'd'], queries)
        self.assertEqual([x['rank'] for x in result['details']], [2, 1])
        self.assertEqual(result['recall_at_1'], .5)
        self.assertEqual(result['mrr'], .75)


if __name__ == '__main__':
    unittest.main()
