import unittest


class ShortlistMetricsTests(unittest.TestCase):
    def test_unretrieved_target_gets_no_credit_from_tie_order(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest('Optional NumPy environment not installed')
        from src.abstract_validation_expanded.retrieval import shortlist_metrics
        # Target a has the first index but was never in the candidate pool.
        scores = np.asarray([[-1e6, 2., 1.], [0., 2., 1.]])
        queries = [{'query_id':'missing','target_id':'a'}, {'query_id':'found','target_id':'c'}]
        result = shortlist_metrics(scores, ['a','b','c'], queries, [[1,2],[1,2]])
        self.assertEqual([d['rank'] for d in result['details']], [None,2])
        self.assertEqual(result['recall_at_10'], .5)
        self.assertEqual(result['candidate_recall'], .5)
        self.assertEqual(result['mrr'], .25)
        self.assertNotIn('a', [d['id'] for d in result['details'][0]['top10']])


if __name__ == '__main__':
    unittest.main()
