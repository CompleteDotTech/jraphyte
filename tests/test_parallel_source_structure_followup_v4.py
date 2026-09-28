"""Authored missing-candidate and source-order cases; never corpus evidence."""
import unittest
from unittest.mock import patch

from test_parallel_source_v4 import ABSTRACT, BODY, assess, doc, line
from src.parallel_source_v4.adapters import document, item
from trace_gc.pdf_source_parallel_v4 import canonical, compare, locate, validate_source_spans
from trace_gc.pdf_structure_parallel_v4 import verify_assessment


class SourceOrderFollowupTests(unittest.TestCase):
    def assert_complete(self, result, expected, native):
        self.assertTrue(result['proposal'], result)
        self.assertTrue(compare(result['text'], expected)['boundary_and_98_match'], result)
        validate_source_spans(result['spans'], native)
        verify_assessment(result)
        self.assertFalse(result['eligible_for_jev'])
        self.assertFalse(result['verified_admission'])

    def test_overlapping_converter_body_box_cannot_preempt_owned_abstract(self):
        native = [line(0, 'Abstract', 70, x=120, right=180),
                  line(1, ABSTRACT, 100), line(2, '1 Introduction', 150),
                  line(3, BODY, 180), line(4, 'A separate body continuation.', 80, x=320, right=560)]
        source = doc(native, labels={0:'section_header',2:'section_header'})
        # A converter joins two body columns into a union box beginning beside
        # the Abstract heading. Neither that box nor its broken text owns the
        # uniquely located paragraph between the native Abstract/Introduction.
        source['texts'][4]['text'] = BODY+' A separate body continuation.'
        source['texts'][4]['prov'][0]['bbox'].update(l=40,t=75,r=560,b=230)
        self.assert_complete(assess(native, source), ABSTRACT, native)

    def test_numbered_body_transition_after_narrow_abstract_retains_prefix_for_review(self):
        native = [line(0, 'Abstract', 70, x=220, right=290),
                  line(1, ABSTRACT, 100, x=220, right=560, size=8),
                  line(2, '1 Introduction', 150, x=40, right=150, size=12, bold=True),
                  line(3, BODY, 151, x=320, right=560, size=10),
                  line(4, BODY+' Additional context.', 176, size=10)]
        source = doc(native, labels={0:'section_header',2:'section_header'})
        result = assess(native, source)
        self.assertTrue(compare(result['text'], ABSTRACT)['boundary_and_98_match'], result)
        self.assertFalse(result['proposal'])
        self.assertEqual(result['closing_boundary']['kind'], 'unresolved_section_ownership')
        self.assertEqual(result['closing_boundary']['candidate_boundary']['source_location'], 'located')

    def test_other_column_heading_and_font_change_cannot_truncate_complete_proposal(self):
        continuation = 'Our equations describe x = y and provide quantitative agreement with measured results.'
        native = [line(0, 'Abstract', 70, x=330, right=430),
                  line(1, ABSTRACT, 100, x=320, right=560, size=8),
                  line(2, '1 Introduction', 125, x=40, right=150, size=12, bold=True),
                  line(3, continuation, 126, x=320, right=560, size=10),
                  line(4, 'Keywords: transport', 160, x=320, right=560)]
        result = assess(native, doc(native, labels={0:'section_header',2:'section_header'}))
        self.assertFalse(result['proposal'])
        self.assertIsNone(result['section_owner'])

    def test_source_offsets_order_split_heading_before_converter_earlier_prose(self):
        native = [line(0, 'Abstract '+ABSTRACT, 70), line(1, 'Keywords: transport', 150)]
        source = document([item(0, ABSTRACT, 'text', [native[0]['bbox']]),
                           item(1, 'Abstract', 'section_header', [native[0]['bbox']]),
                           item(2, native[1]['text'], 'text', [native[1]['bbox']])])
        self.assert_complete(assess(native, source), ABSTRACT, native)

    def test_oversized_model_box_with_following_native_content_is_retained(self):
        native = [line(0, 'Abstract', 70), line(1, ABSTRACT, 100),
                  line(2, '1 Introduction', 150)]
        source = doc(native, labels={0:'section_header',2:'section_header'})
        source['texts'][1]['prov'][0]['bbox'].update(t=75)
        self.assert_complete(assess(native, source), ABSTRACT, native)

    def test_font_increase_without_outer_heading_retains_abstract_continuation(self):
        continuation = 'Our equations describe x = y and provide quantitative agreement with measured results.'
        native = [line(0, 'Abstract', 70), line(1, ABSTRACT, 100, size=8),
                  line(2, continuation, 125, size=10), line(3, '1 Introduction', 150)]
        self.assert_complete(assess(native), ABSTRACT+' '+continuation, native)

    def test_unlocated_overlap_candidate_is_retained_without_a_proposal(self):
        native = [line(0, 'Abstract', 70), line(1, BODY, 100), line(2, '1 Introduction', 160)]
        source = doc(native)
        source['texts'][1]['text'] = ABSTRACT
        source['texts'][1]['prov'][0]['bbox'].update(t=75)
        result = assess(native, source)
        self.assertEqual(result['text'], ABSTRACT)
        self.assertEqual(result['status'], 'uncertain')
        self.assertFalse(result['proposal'])
        self.assertFalse(result['spans'])

    def test_global_fuzzy_alignment_cannot_drop_short_owned_wrap_line(self):
        first = ABSTRACT+' '+BODY+' '+ABSTRACT
        second = BODY+' '+ABSTRACT
        native = [line(0, 'Abstract', 70), line(1, first, 100),
                  line(2, 'Small but vital.', 115, right=112),
                  line(3, 'Unrelated right column material.', 100, x=320, right=560),
                  line(4, second, 140), line(5, '1 Introduction', 170)]
        source = document([item(0, 'Abstract', 'section_header', [native[0]['bbox']]),
                           item(1, first+' Small but vital.', 'text', [[40,100,280,127]]),
                           item(2, second, 'text', [native[4]['bbox']]),
                           item(3, '1 Introduction', 'section_header', [native[5]['bbox']])])
        result = assess(native, source)
        self.assert_complete(result, first+' Small but vital. '+second, native)
        self.assertIn('Small but vital.', result['text'])
        self.assertIn(2, [s['line_id'] for s in result['spans']])

    def test_same_positions_in_swapped_source_order_cannot_be_proposed(self):
        native = [line(0, 'Abstract', 70), line(1, ABSTRACT, 100),
                  line(2, BODY, 125), line(3, '1 Introduction', 160)]
        expected = ABSTRACT+' '+BODY
        source = document([item(0, 'Abstract', 'section_header', [native[0]['bbox']]),
                           item(1, expected, 'text', [[40,100,280,137]]),
                           item(2, '1 Introduction', 'section_header', [native[3]['bbox']])])
        def reordered(text, lines, **kwargs):
            result = locate(text, lines, **kwargs)
            if not kwargs.get('region_boxes') and canonical(text) == canonical(expected):
                result['spans'] = list(reversed(result['spans']))
                result['text'] = '\n'.join(s['text'] for s in result['spans'])
            return result
        with patch('trace_gc.pdf_structure_parallel_v4.locate', side_effect=reordered):
            result = assess(native, source)
        self.assertFalse(result['proposal'])
        self.assertEqual(result['status'], 'uncertain')
        self.assertIn('global_alignment_changes_owned_source_extent', result['reasons'])
        self.assertTrue(compare(result['text'], expected)['boundary_and_98_match'])

    def test_same_height_other_column_heading_does_not_close_abstract(self):
        native = [line(0, 'Abstract', 70), line(1, ABSTRACT, 100),
                  line(2, '1 Introduction', 100, x=320, right=560, size=12, bold=True),
                  line(3, BODY, 130, x=320, right=560)]
        result = assess(native, doc(native, labels={2:'section_header'}))
        self.assertFalse(result['proposal'])

    def test_unheaded_narrowing_without_outer_heading_stays_held(self):
        native = [line(0, 'Abstract', 70, x=220, right=290),
                  line(1, ABSTRACT, 100, x=220, right=560, size=8),
                  line(2, BODY, 151, x=320, right=560, size=10),
                  line(3, BODY+' Additional context.', 151, size=10)]
        self.assertFalse(assess(native)['proposal'])


class FrontmatterCandidateTests(unittest.TestCase):
    def frontmatter(self, text=ABSTRACT):
        return [line(0, 'A study of transport in scientific networks', 35, x=90, right=530, size=18),
                line(1, 'Alice Smith and Bob Jones', 65, x=120, right=490, size=11),
                line(2, 'University of Example, Department of Physics', 83, x=90, right=530, size=9),
                line(3, text, 115, x=90, right=530, size=9),
                line(4, '1 Introduction', 160, size=12, bold=True),
                line(5, BODY, 185, size=10)]

    def test_plain_frontmatter_candidate_survives_empty_scholarly_field(self):
        native = self.frontmatter()
        result = assess(native, doc(native, labels={0:'title',4:'section_header'}))
        self.assertTrue(compare(result['text'], ABSTRACT)['boundary_and_98_match'], result)
        self.assertNotEqual(result['status'], 'absent')
        validate_source_spans(result['spans'], native)

    def test_funding_frontmatter_is_not_an_abstract(self):
        native = self.frontmatter('This work was funded by the Example Foundation. '+ABSTRACT)
        self.assertFalse(assess(native, doc(native, labels={0:'title',4:'section_header'}))['proposal'])

    def test_many_author_names_support_a_held_frontmatter_candidate(self):
        native = self.frontmatter()
        authors = 'Alice Smith, Bob Jones, Chris Brown, David Green, Emma White and Frank Black'
        native[1] = line(1, authors, 65, x=120, right=490, size=11)
        result = assess(native, doc(native, labels={0:'title',4:'section_header'}))
        self.assertTrue(compare(result['text'], ABSTRACT)['boundary_and_98_match'], result)
        self.assertIn('unlabelled_frontmatter_ownership_requires_source_review', result['reasons'])
        self.assertFalse(result['proposal'])
        self.assertIsNone(result['section_owner'])

    def test_plain_body_without_frontmatter_ownership_is_not_promoted(self):
        native = [line(0, ABSTRACT, 100, x=90, right=530, size=9),
                  line(1, '1 Introduction', 160, size=12, bold=True), line(2, BODY, 185)]
        self.assertFalse(assess(native)['proposal'])


if __name__ == '__main__':
    unittest.main()
