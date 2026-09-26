"""Review-gated admission of first-page evidence to a Jev request.

The geometry selector remains experimental. Its eligibility flag alone cannot
authorize this adapter. Review records are auditable attestations, not signatures
or proof that an independent human reviewed the page.
"""
from __future__ import annotations

import hashlib
import json
import math
import re


def sha256(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def seal(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')))


def source_review(*, source_sha256, page_sha256, image_sha256, page_size,
                  blocks, selected_ids, start, end, status, reviewer, reviewer_kind,
                  reviewed_at, candidate_assessment_sha256=None):
    """Record a review using only an exact span of selected source blocks.

    ``start:end`` indexes their space-joined text. It allows removal of an inline
    heading or surrounding metadata without permitting generated replacements.
    The caller supplies the reviewed block order, including column continuations.
    """
    if status not in {'complete', 'partial', 'absent', 'uncertain', 'error'}:
        raise ValueError('Unknown review disposition')
    if reviewer_kind not in {'assistant', 'human'} or not reviewer or not reviewed_at:
        raise ValueError('Reviewer identity and time are required')
    if any(not re.fullmatch('[a-f0-9]{64}', h) for h in [source_sha256, page_sha256, image_sha256]):
        raise ValueError('Invalid source hash')
    width, height = page_size
    if not all(math.isfinite(v) and v > 0 for v in page_size):
        raise ValueError('Invalid page dimensions')
    if len({b['id'] for b in blocks}) != len(blocks) or len(set(selected_ids)) != len(selected_ids):
        raise ValueError('Duplicate source block')
    lookup = {b['id']: b for b in blocks}
    selected = [lookup[i] for i in selected_ids]
    for b in selected:
        x0, y0, x1, y1 = b['bbox']
        if not all(math.isfinite(v) for v in b['bbox']) or not (0 <= x0 < x1 <= width+1 and 0 <= y0 < y1 <= height+1):
            raise ValueError('Invalid reviewed source box')
    source_text = ' '.join(b['text'] for b in selected)
    if not isinstance(start, int) or not isinstance(end, int) or not 0 <= start <= end <= len(source_text):
        raise ValueError('Invalid source character span')
    text = source_text[start:end]
    if (status in {'complete', 'partial'} and not text.strip()) or (status == 'absent' and text):
        raise ValueError('Review disposition conflicts with selected text')
    value = {'schema_version': 1, 'physical_page': 1, 'source_sha256': source_sha256,
             'page_sha256': page_sha256, 'image_sha256': image_sha256, 'page_size': list(page_size),
             'status': status, 'text': text, 'text_sha256': sha256(text),
             'selected_blocks': selected, 'character_span': [start, end],
             'reviewer': reviewer, 'reviewer_kind': reviewer_kind, 'reviewed_at': reviewed_at,
             'independent_review': False, 'candidate_assessment_sha256': candidate_assessment_sha256}
    value['review_sha256'] = seal(value)
    return value


def prepare_jev_request(*, paper_id, model, questions, current_source_sha256,
                        current_page_sha256, current_image_sha256, review=None,
                        max_characters=4000, max_request_bytes=16000):
    """Return an exact review-bound payload or a hold disposition; no API call.

    Current hashes must be recomputed by the file adapter immediately before use.
    This function never truncates text and never treats embeddings as evidence.
    """
    def hold(reason):
        return {'admitted': False, 'reason': reason}
    if review is None:
        return hold('source_review_required')
    value = dict(review)
    supplied = value.pop('review_sha256', None)
    if supplied != seal(value) or review.get('text_sha256') != sha256(review.get('text', '')):
        return hold('review_integrity_mismatch')
    if review.get('physical_page') != 1:
        return hold('first_page_scope_required')
    if (review['source_sha256'], review['page_sha256'], review['image_sha256']) != (current_source_sha256, current_page_sha256, current_image_sha256):
        return hold('reviewed_source_changed')
    if review['status'] != 'complete':
        return hold('review_' + review['status'])
    text = review['text']
    if len(text) > max_characters:
        return hold('complete_abstract_exceeds_character_budget')
    payload = {'model': model, 'state': {'paper_id': paper_id, 'abstract': text},
               'questions': {name: {'type': 'choice', **question} for name, question in questions.items()}}
    body = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    if len(body) > max_request_bytes:
        return hold('complete_request_exceeds_byte_budget')
    return {'admitted': True, 'payload': payload, 'request_bytes': len(body),
            'request_sha256': hashlib.sha256(body).hexdigest(), 'review_sha256': supplied,
            'evidence_sha256': seal({k: review[k] for k in ['source_sha256', 'page_sha256', 'physical_page', 'text_sha256']})}
