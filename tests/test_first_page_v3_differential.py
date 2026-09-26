"""Mechanism-level counterexamples against immutable v2, not paper replay.

Expected scientific text is fixture-authored independently of both selectors.
These assertions intentionally preserve the old outputs for causal comparison.
"""
import hashlib
from pathlib import Path
import unittest

from trace_gc.pdf_structure import assess_document as old_assess
from trace_gc.pdf_source_v3 import assess_document as new_assess
from src.abstract_validation_v3.adapters import native_document
from test_pdf_source_v3 import ABSTRACT_TEXT, BODY_TEXT, line


def paired(lines, document=None, **kwargs):
    params = dict(page_size=(600,800), source_sha256='a'*64,
                  page_sha256='b'*64, native_lines=lines, **kwargs)
    doc = document or native_document(lines)
    return old_assess(doc, **params), new_assess(doc, **params)


class FrozenComparisonTests(unittest.TestCase):
    def test_historical_method_bytes_remain_frozen(self):
        root = Path(__file__).resolve().parents[1]
        expected = {'pdf_structure.py': 'ff84ed19946281f5d93d8cad3845ef1af0bccb03672ce71d05c80e23b03227f8',
                    'pdf_evidence.py': '5a76e52b0cc27e8e9c61ee28eb11b41b29d5b78233b7a4e91f0d93c8ff710aeb'}
        for name, sha in expected.items():
            with self.subTest(name=name):
                self.assertEqual(hashlib.sha256((root/'trace_gc'/name).read_bytes()).hexdigest(), sha)

    def test_inline_overview_old_proposal_contains_body_new_excludes_it(self):
        old,new = paired([line(0, 'Abstract '+ABSTRACT_TEXT+' Overview: '+BODY_TEXT)])
        self.assertTrue(old['eligible_for_jev'])
        self.assertIn(BODY_TEXT, old['text'])
        self.assertEqual(new['text'], ABSTRACT_TEXT)
        self.assertTrue(new['proposed'])
        self.assertFalse(new['eligible_for_jev'])

    def test_colored_synopsis_old_accepts_new_holds_safe_prefix(self):
        lines = [line(0,'Abstract',70),line(1,ABSTRACT_TEXT,90,bold=True),
                 line(2,'The special synopsis provides a separate account for readers.',120,color=255),
                 line(3,'1 Introduction',150)]
        old,new=paired(lines)
        self.assertTrue(old['eligible_for_jev'])
        self.assertIn('special synopsis', old['text'])
        self.assertEqual(new['text'], ABSTRACT_TEXT)
        self.assertEqual(new['status'],'uncertain')
        self.assertFalse(new['proposed'])

    def test_inline_dedication_old_accepts_new_excludes(self):
        old,new=paired([line(0,'Abstract '+ABSTRACT_TEXT+' Dedicated to our colleagues.')])
        self.assertTrue(old['eligible_for_jev'])
        self.assertIn('Dedicated',old['text'])
        self.assertEqual(new['text'],ABSTRACT_TEXT)
        self.assertTrue(new['proposed'])

    def test_missing_closure_above_bottom_old_accepts_new_abstains(self):
        old,new=paired([line(0,'Abstract '+ABSTRACT_TEXT)])
        self.assertTrue(old['eligible_for_jev'])
        self.assertEqual(new['text'],old['text'])
        self.assertEqual(new['status'],'uncertain')
        self.assertFalse(new['proposed'])

    def test_ordinary_bounded_source_is_retained_not_just_all_abstention(self):
        old,new=paired([line(0,'Abstract '+ABSTRACT_TEXT),line(1,'1 Introduction',140)])
        self.assertTrue(old['eligible_for_jev'])
        self.assertTrue(new['proposed'])
        self.assertEqual(new['text'],old['text'])
        self.assertEqual(new['text'],ABSTRACT_TEXT)

    def test_source_bound_column_wrap_retains_valid_frozen_proposal(self):
        first='We study the transport of evidence across columns and obtain a complete'
        last='description of the measured effect. The experiments confirm the predicted behavior.'
        lines=[line(0,'Abstract',200),line(1,first,240),line(2,last,100,330,570),line(3,'1 Introduction',140,330,570)]
        lines[1]['bbox'][3]=680
        old,new=paired(lines)
        self.assertTrue(old['eligible_for_jev'])
        self.assertEqual(old['text'],first+' '+last)
        self.assertEqual(new['text'],old['text'])
        self.assertTrue(new['proposed'])
        self.assertEqual(new['column_continuation']['to_line_id'],2)

    def test_bold_inline_heading_native_run_closes_same_region(self):
        text='Abstract '+ABSTRACT_TEXT+' Overview '+BODY_TEXT
        value=line(0,text)
        start=len('Abstract '+ABSTRACT_TEXT+' ')
        value['runs']=[{'start':0,'end':start,'font':'Regular','flags':0},
                       {'start':start,'end':start+len('Overview'),'font':'Bold','flags':16},
                       {'start':start+len('Overview'),'end':len(text),'font':'Regular','flags':0}]
        old,new=paired([value])
        self.assertIn(BODY_TEXT,old['text'])
        self.assertEqual(new['text'],ABSTRACT_TEXT)
        self.assertTrue(new['proposed'])


if __name__=='__main__':unittest.main()
