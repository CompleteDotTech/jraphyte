import copy
import unittest

from trace_gc.pdf_admission import prepare_jev_request, source_review


class PdfAdmissionTests(unittest.TestCase):
    def review(self, text='We prove a result.', status='complete'):
        blocks = [{'id': 1, 'bbox': [30, 100, 500, 200], 'text': 'Abstract. ' + text}]
        return source_review(source_sha256='a'*64, page_sha256='b'*64, image_sha256='c'*64,
            page_size=[600, 800], blocks=blocks, selected_ids=[1], start=10, end=10+len(text),
            status=status, reviewer='test reviewer', reviewer_kind='assistant', reviewed_at='2026-09-25T00:00:00Z')

    def prepare(self, review=None, **kwargs):
        args = dict(paper_id='paper', model='jev-test', questions={'evaluation': {'instructions': 'Test?', 'criteria': {'YES': 'Yes.'}}},
                    current_source_sha256='a'*64, current_page_sha256='b'*64, current_image_sha256='c'*64, review=review)
        args.update(kwargs)
        return prepare_jev_request(**args)

    def test_geometry_alone_cannot_admit(self):
        self.assertEqual(self.prepare()['reason'], 'source_review_required')

    def test_complete_review_preserves_exact_evidence(self):
        text = 'We prove a result with Pass@1. E = mc².'
        result = self.prepare(self.review(text))
        self.assertTrue(result['admitted'])
        self.assertEqual(result['payload']['state']['abstract'], text)

    def test_tampered_or_stale_review_is_rejected(self):
        original = self.review()
        changed = copy.deepcopy(original)
        changed['text'] += ' Invented claim.'
        self.assertEqual(self.prepare(changed)['reason'], 'review_integrity_mismatch')
        for field in ['current_source_sha256', 'current_page_sha256', 'current_image_sha256']:
            self.assertEqual(self.prepare(original, **{field: 'd'*64})['reason'], 'reviewed_source_changed')

    def test_partial_and_uncertain_cannot_admit(self):
        for status in ['partial', 'uncertain', 'error']:
            self.assertFalse(self.prepare(self.review(status=status))['admitted'])

    def test_limits_preserve_full_text(self):
        review = self.review('We prove a result. ' * 20)
        self.assertEqual(self.prepare(review, max_characters=20)['reason'], 'complete_abstract_exceeds_character_budget')
        self.assertEqual(self.prepare(review, max_request_bytes=20)['reason'], 'complete_request_exceeds_byte_budget')
        self.assertEqual(review['text'], 'We prove a result. ' * 20)

    def test_review_text_must_be_a_source_span(self):
        with self.assertRaises(ValueError):
            source_review(source_sha256='a'*64, page_sha256='b'*64, image_sha256='c'*64,
                page_size=[600, 800], blocks=[], selected_ids=[], start=0, end=100,
                status='complete', reviewer='test', reviewer_kind='assistant', reviewed_at='now')


if __name__ == '__main__':
    unittest.main()
