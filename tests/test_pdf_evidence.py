from __future__ import annotations

import copy
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from trace_gc.pdf_evidence import assess_first_page, reprocessing_action
from src.abstract_validation.embedding_batch import BudgetLedger


def item(text, y, *, x=70, right=530, height=20, label='text', page=1):
    return {'text': text, 'label': label, 'ref': str(y), 'prov': [
        {'page_no': page, 'bbox': {'l': x, 't': y, 'r': right, 'b': y+height, 'coord_origin': 'TOPLEFT'}, 'charspan': [0, len(text)]}]}


def assess(items, **kwargs):
    return assess_first_page(items, page_size=[600, 800], page_sha256='a'*64, source_sha256='b'*64, **kwargs)


class PdfEvidenceTests(unittest.TestCase):
    def test_spaced_heading_side_column_and_bad_reading_order(self):
        text = 'We investigate a physical system and derive a new exact solution.'
        result = assess([item('1. Introduction', 330, x=40, right=170, label='section_header'),
                         item('Keywords: physics', 160, x=40, right=160),
                         item('A B S T RAC T', 130, x=210, right=300, label='section_header'),
                         item(text, 160, x=210, right=550, height=140),
                         item('Body text that must not leak into the abstract.', 329, x=320, right=550)])
        self.assertEqual(result['text'], text)
        self.assertTrue(result['eligible_for_jev'])

    def test_short_abstract_not_discarded(self):
        result = assess([item('Abstract. We classify all solutions.', 150), item('Contents', 205, label='section_header')])
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['text'], 'We classify all solutions.')

    def test_adjacent_lines_paragraphs_and_metrics(self):
        result = assess([item('We study model behavior using Pass@1 and Eval@1 metrics.', 150),
                         item('Our experiments demonstrate consistent gains across systems.', 182),
                         item('The method also improves HR@1 and remains efficient.', 214),
                         item('Keywords: learning', 250)])
        self.assertIn('HR@1', result['text'])
        self.assertIn('experiments', result['text'])
        self.assertNotIn('Keywords', result['text'])
        self.assertTrue(result['eligible_for_jev'])

    def test_equation_preserved_with_original_transcription(self):
        equation = item('', 182, x=230, right=360, label='formula')
        equation['orig'] = 'E = mc2.'
        result = assess([item('We investigate a physical system and derive its energy.', 150), equation,
                         item('This expression gives a complete characterization.', 214), item('Contents', 260, label='section_header')])
        self.assertIn('E = mc2.', result['text'])
        self.assertEqual(len(result['spans']), 3)

    def test_structured_inline_introduction_is_not_body(self):
        result = assess([item('Abstract', 100, label='section_header'),
                         item('Introduction: We study a physical system.', 140),
                         item('Methods: We use controlled experiments.', 180),
                         item('Results: The measurements agree with theory.', 220),
                         item('1. Introduction', 270, label='section_header')])
        self.assertEqual(result['status'], 'complete')
        self.assertIn('Results:', result['text'])

    def test_partial_retained_without_admission(self):
        result = assess([item('Abstract', 100, label='section_header'),
                         item('We present a new method that enables', 140, height=580)])
        self.assertEqual(result['status'], 'partial')
        self.assertFalse(result['eligible_for_jev'])
        self.assertTrue(result['text'].endswith('enables'))

    def test_heading_only_is_absent(self):
        result = assess([item('Abstract', 740, label='section_header')])
        self.assertEqual(result['status'], 'absent')
        self.assertIn('assessment_sha256', result)

    def test_budget_never_truncates_complete_evidence(self):
        text = 'We present a result. ' * 250
        result = assess([item('Abstract. ' + text, 100, height=400)], max_input_chars=200)
        self.assertEqual(result['status'], 'complete')
        self.assertFalse(result['eligible_for_jev'])
        self.assertEqual(result['text'], text.strip())

    def test_missing_or_wrong_page_provenance_fails_closed(self):
        for items in [[item('Abstract. We find a new result.', 100, page=2)], [{'text': 'We find a new result.'}]]:
            result = assess(items)
            self.assertEqual(result['status'], 'error')
            self.assertFalse(result['eligible_for_jev'])

    def test_reuse_requires_source_text_and_context(self):
        result = assess([item('Abstract. We find a new result.', 100)])
        params = dict(previous_status='ok', previous_text_sha256=result['text_sha256'], previous_source_sha256='b'*64, evaluation_context_unchanged=True)
        self.assertEqual(reprocessing_action(result, **params), 'reuse_unchanged_evaluation')
        params['previous_source_sha256'] = 'c'*64
        self.assertEqual(reprocessing_action(result, **params), 'evaluate_changed_evidence')
        params['previous_source_sha256'] = 'b'*64
        params['evaluation_context_unchanged'] = False
        self.assertEqual(reprocessing_action(result, **params), 'evaluate_changed_evidence')

    def test_parallel_reservations_cannot_exceed_cap(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = BudgetLedger(Path(directory) / 'budget.sqlite', cap=.003)
            def attempt(i):
                try:
                    return ledger.reserve(str(i), 'a'*64, .001)
                except ValueError:
                    return None
            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(attempt, range(30)))
            self.assertEqual(sum(x is not None for x in results), 3)
            self.assertAlmostEqual(ledger.totals()['reserved_usd'], .003)
            with self.assertRaises(ValueError):
                BudgetLedger(ledger.path, cap=10)


if __name__ == '__main__':
    unittest.main()
