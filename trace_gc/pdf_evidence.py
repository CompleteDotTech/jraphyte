"""Experimental, source-bound first-page abstract assessment.

This module selects existing page text. It neither generates an abstract nor
creates graph claims. Docling is an optional upstream adapter; the selector has
no third-party dependencies. A ``complete`` result is a layout-based assessment,
not a calibrated probability or a guarantee of scientific correctness.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import math
import re
import unicodedata

SELECTOR_VERSION = 'page-one-geometry-v1'
ABSTRACT = re.compile(r'^\s*a\s*b\s*s\s*t\s*r\s*a\s*c\s*t\b\s*[.:—–-]?\s*', re.I)
EMAIL = re.compile(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+')
METADATA = re.compile(r'^(?:©|copyright\b|permission\b|all rights reserved\b|keywords?\b|key words\b|PACS\b|CCS\b|ACM reference\b|(?:\d{4}\s+)?(?:mathematics|AMS) subject\b|JEL\b|article (?:info|history)\b|e-?mail\s*:|correspond(?:ing|ence|:)\b|date\s*:|blogpost\s*:|https?://|international symposium\b|preprint submitted\b|this (?:work|paper|article) (?:was|is) (?:supported|funded)|the authors? (?:is|are|have been) supported)', re.I)
AFFILIATION = re.compile(r'^(?:[\d,a-z𝑎-𝑧*†‡]+\s+)?(?:department|university|institute|instituto|school|faculty|laboratory|college|centre|center|international cent(?:er|re)|key laboratory)\b', re.I)
BODY = re.compile(r'^(?:(?:\d+(?:\.\d+)*|[IVX]+)[.)]?\s+)?(?:introduction|contents|table of contents|nomenclature|references|acknowledg\w*|preliminaries)\s*[.:]?$', re.I)
NUMBERED = re.compile(r'^(?:\d+(?:\.\d+)*|[IVX]+)[.)]?\s+', re.I)
INTERNAL = {'introduction', 'background', 'objective', 'objectives', 'methods', 'method', 'results', 'discussion', 'conclusion', 'conclusions', 'purpose', 'significance', 'design', 'setting', 'participants', 'interventions', 'findings', 'interpretation'}
NARRATIVE = re.compile(r'\b(?:we|this (?:paper|study|work|note|article)|is|are|can|shows?|proposes?|investigate[sd]?|introduce[sd]?|provides?|presents?|enables?|offers?|obtained|classif(?:y|ies|ied)|establish(?:es|ed)?|studies|study|demonstrate[sd]?|derive[sd]?|proves?|consider(?:s|ed)?|examines?|develop(?:s|ed)?|explore[sd]?)\b', re.I)
EXTRA_METADATA = re.compile(r'^(?:author notes?\s*:|acknowledg\w*\s*:|this manuscript contains|this study was approved|respondents were provided|essay written|repo\s*:|code\s*:|additional key words|supplementary materials)', re.I)
INTRODUCTION = re.compile(r'^(?:(?:\d+|[IVX]+)[.)]?\s+)?Introduction(?:\s*[.:—–-]|$)', re.I)
SENTENCE_END = re.compile(r'[.!?][\s\"\u201d\u2019\')\]}]*$')
EXCLUDED = {'page_header', 'page_footer', 'footnote', 'caption', 'picture', 'table', 'document_index'}


def normalize(text):
    return re.sub(r'\s+', ' ', text).strip()


def canonical(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', text).casefold() if c.isalnum())


def _section(text):
    return NUMBERED.sub('', text).strip().lower().rstrip(': .')


def _is_metadata(item):
    text = item['text']
    return bool(METADATA.search(text) or EXTRA_METADATA.search(text) or AFFILIATION.search(text) or
                (EMAIL.search(text) and len(text) < 220) or
                re.match(r'^(?:Fig\.?|Figure|Table)\s*\d', text, re.I))


def _overlap(a, b):
    overlap = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    return overlap / max(1, min(a[2]-a[0], b[2]-b[0]))


def _items(items, width, height):
    result = []
    for index, raw in enumerate(items):
        text = raw.get('text', '') or (raw.get('orig', '') if raw.get('label') == 'formula' else '')
        if not text.strip():
            continue
        boxes = []
        for provenance in raw.get('prov', []):
            if provenance.get('page_no') != 1:
                raise ValueError('Provenance outside first physical page')
            box = provenance['bbox']
            if box.get('coord_origin') == 'BOTTOMLEFT':
                coords = [box['l'], height-box['t'], box['r'], height-box['b']]
            elif box.get('coord_origin') == 'TOPLEFT':
                coords = [box['l'], box['t'], box['r'], box['b']]
            else:
                raise ValueError('Unknown coordinate origin')
            if not all(math.isfinite(x) for x in coords) or not (0 <= coords[0] < coords[2] <= width+1 and 0 <= coords[1] < coords[3] <= height+1):
                raise ValueError('Invalid page bounding box')
            boxes.append(coords)
        if not boxes:
            raise ValueError('Text has no source box')
        boxes.sort(key=lambda b: (b[1], b[0]))
        result.append({'text': normalize(text), 'raw_text': text, 'label': raw.get('label', 'text'),
                       'ref': raw.get('ref', raw.get('self_ref', str(index))), 'bbox': boxes[0], 'boxes': boxes,
                       'provenance': raw['prov']})
    return sorted(result, key=lambda x: (round(x['bbox'][1], 1), x['bbox'][0]))


def _assess_first_page(items, *, page_size, page_sha256, source_sha256, native_lines=None,
                      conversion_status='success', max_input_chars=4000):
    """Return text, geometry, hashes, disposition, and a separate admission flag.

    Partial text is retained verbatim. Character limits never silently truncate
    evidence. Native lines, when supplied, are selected only inside the chosen
    Docling regions and must agree with their transcription before substitution.
    """
    receipt = {'schema_version': 1, 'extractor_version': SELECTOR_VERSION, 'physical_page': 1,
               'source_sha256': source_sha256, 'page_sha256': page_sha256, 'page_size': list(page_size),
               'status': 'error', 'text': '', 'eligible_for_jev': False, 'reasons': [], 'spans': []}
    try:
        if any(not re.fullmatch(r'[a-f0-9]{64}', h) for h in (source_sha256, page_sha256)):
            raise ValueError('Source hashes must be SHA-256 hex digests')
        width, height = page_size
        if not all(math.isfinite(x) and x > 0 for x in (width, height)):
            raise ValueError('Invalid page dimensions')
        if conversion_status.lower().split('.')[-1] != 'success':
            raise ValueError('Upstream page conversion was not successful')
        ordered = _items(items, width, height)
        anchors = [x for x in ordered if ABSTRACT.match(x['text'])]
        if len(anchors) > 1:
            receipt.update(status='uncertain', reasons=['multiple_abstract_regions'])
            return receipt
        anchor = anchors[0] if anchors else None
        structured = bool(anchor and sum(1 for x in ordered if x['bbox'][1] > anchor['bbox'][1] and
                          (x['label'] == 'section_header' and _section(x['text']) in {'methods', 'results'} or
                           re.match(r'^(?:Methods?|Results)\s*:', x['text'], re.I))) >= 2)

        def stop_header(x):
            if x['label'] != 'section_header' and not BODY.fullmatch(x['text']):
                return False
            if structured and not NUMBERED.match(x['text']) and _section(x['text']) in INTERNAL:
                return False
            return x is not anchor

        if anchor:
            top = anchor['bbox'][1]
            # Body headers can be in the other column; apply their y boundary.
            body_y = min((x['bbox'][1] for x in ordered if x is not anchor and x['bbox'][1] > top+2 and
                          (BODY.fullmatch(x['text']) or INTRODUCTION.match(x['text'])) and not (structured and not NUMBERED.match(x['text']))), default=height)
            candidates = [x for x in ordered if x['bbox'][1] >= top-1 and x['bbox'][1] < body_y-1 and
                          (x is anchor or _overlap(anchor['bbox'], x['bbox']) > .35) and
                          x['label'] not in EXCLUDED and not _is_metadata(x) and
                          (x is anchor and ABSTRACT.sub('', x['text']) or x is not anchor and not stop_header(x))]
            if candidates:
                start = min(candidates, key=lambda x: (x['bbox'][1], abs(x['bbox'][0]-anchor['bbox'][0])))
            else:
                receipt.update(status='absent', reasons=['abstract_heading_without_page_one_prose'], selector='explicit_heading')
                return receipt
        else:
            body_y = min((x['bbox'][1] for x in ordered if BODY.fullmatch(x['text']) or INTRODUCTION.match(x['text'])), default=height)
            cover_notes = any(re.match(r'^(?:author notes?\s*:|this manuscript contains)', x['text'], re.I) for x in ordered)
            candidates = [x for x in ordered if x['bbox'][1] < body_y-1 and x['label'] in {'text', 'paragraph'} and
                          not _is_metadata(x) and len(x['text']) >= 45 and NARRATIVE.search(x['text'])]
            if not candidates or cover_notes:
                receipt.update(status='absent' if body_y < height or ordered else 'uncertain',
                               reasons=['no_bounded_page_one_abstract' if ordered else 'no_readable_page_text'], selector='unlabeled_geometry')
                return receipt
            start = candidates[0]
            top = start['bbox'][1]
        column = start['bbox']
        # If the heading contains no prose, start from the first prose/structured item.
        selected, boundary = [], None
        bottom = start['bbox'][1]
        for x in ordered:
            box = x['bbox']
            if box[1] < top-1 or _overlap(column, box) < .5:
                continue
            if box[1] >= body_y-4:
                boundary = 'body_section'
                break
            if x is anchor:
                stripped = ABSTRACT.sub('', x['text'])
                if not stripped:
                    continue
                x = dict(x, text=stripped, heading_removed=True)
            if not selected and box[1] < start['bbox'][1]-1:
                continue
            if selected and (x['label'] in EXCLUDED or _is_metadata(x) or stop_header(x)):
                boundary = 'metadata_or_section'
                break
            if x['label'] in EXCLUDED or _is_metadata(x):
                continue
            if selected and box[1]-bottom > 42:
                boundary = 'layout_gap'
                break
            if selected and x['label'] in {'text', 'paragraph'} and len(x['text']) > 100 and box[2]-box[0] < .82*(column[2]-column[0]) and (abs(box[0]-column[0]) > 35 or abs(box[2]-column[2]) > 35):
                boundary = 'column_transition'
                break
            selected.append(x)
            bottom = max(bottom, max(b[3] for b in x['boxes']))
        docling_text = normalize(' '.join(x['text'] for x in selected))
        if not docling_text:
            receipt.update(status='uncertain', reasons=['candidate_without_prose'])
            return receipt
        native = []
        seen = set()
        for item in selected:
            for box in item['boxes']:
                inside = []
                for line in native_lines or []:
                    b = line['bbox']
                    center_y = (b[1]+b[3])/2
                    if line['id'] not in seen and box[1]-3 <= center_y <= box[3]+3 and _overlap(box, b) >= .8:
                        inside.append(line)
                inside.sort(key=lambda x: (round(x['bbox'][1], 1), x['bbox'][0]))
                for line in inside:
                    seen.add(line['id'])
                    native.append(line)
        native_text = normalize(' '.join(x['text'] for x in native))
        if anchor:
            native_text = ABSTRACT.sub('', native_text)
        a, b = canonical(docling_text), canonical(native_text)
        matches = sum(m.size for m in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks()) if a and b else 0
        alignment = min(matches/len(a), matches/len(b)) if a and b else None
        use_native = alignment is not None and alignment >= .90
        text = native_text if use_native else docling_text
        spans = [{'ref': x['ref'], 'raw_text': x['raw_text'], 'selected_text': x['text'],
                  'label': x['label'], 'boxes': x['boxes'], 'provenance': x['provenance']} for x in selected]
        reasons = []
        if not SENTENCE_END.search(text):
            status = 'partial' if bottom > height*.68 and boundary != 'body_section' else 'uncertain'
            reasons.append('unfinished_final_sentence')
        elif bottom > height-65 and boundary not in {'body_section', 'metadata_or_section'}:
            status = 'uncertain'
            reasons.append('page_bottom_without_closing_boundary')
        elif alignment is not None and alignment < .90:
            status = 'uncertain'
            reasons.append('native_and_layout_transcriptions_disagree')
        else:
            status = 'complete'
            reasons.append('bounded_region_with_sentence_end')
        if len(text) > max_input_chars:
            reasons.append('exceeds_jev_character_budget')
        receipt.update(status=status, text=text, spans=spans, reasons=reasons, selector='explicit_heading' if anchor else 'unlabeled_geometry',
                       structured=structured, closing_boundary=boundary, transcription='native_pdf' if use_native else 'docling',
                       native_alignment=alignment, native_lines=native, docling_text=docling_text,
                       completeness_basis='layout_and_sentence_boundary_heuristic',
                       eligible_for_jev=status == 'complete' and len(text) <= max_input_chars)
        receipt['text_sha256'] = hashlib.sha256(text.encode('utf-8')).hexdigest()
        binding = {k: receipt[k] for k in ('source_sha256', 'page_sha256', 'physical_page', 'text_sha256')}
        receipt['evidence_sha256'] = hashlib.sha256(json.dumps(binding, sort_keys=True).encode()).hexdigest()
        receipt['assessment_sha256'] = hashlib.sha256(json.dumps(receipt, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        return receipt
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        receipt.update(status='error', eligible_for_jev=False, reasons=[type(exc).__name__ + ': ' + str(exc)])
        return receipt


def assess_first_page(items, **kwargs):
    """Assess a page and bind every disposition, including errors, to a receipt."""
    receipt = _assess_first_page(items, **kwargs)
    receipt['text_sha256'] = hashlib.sha256(receipt['text'].encode('utf-8')).hexdigest()
    binding = {k: receipt[k] for k in ('source_sha256', 'page_sha256', 'physical_page', 'text_sha256')}
    receipt['evidence_sha256'] = hashlib.sha256(json.dumps(binding, sort_keys=True).encode()).hexdigest()
    receipt.pop('assessment_sha256', None)
    receipt['assessment_sha256'] = hashlib.sha256(json.dumps(receipt, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return receipt


def reprocessing_action(assessment, *, previous_text_sha256=None, previous_status=None,
                        previous_source_sha256=None, evaluation_context_unchanged=False):
    """Plan a new evaluation without deleting any previous evaluation/charge."""
    if not assessment['eligible_for_jev']:
        return 'hold_' + assessment['status']
    if previous_status == 'ok' and previous_text_sha256 == assessment.get('text_sha256') and previous_source_sha256 == assessment.get('source_sha256') and evaluation_context_unchanged:
        return 'reuse_unchanged_evaluation'
    return 'evaluate_changed_evidence' if previous_status == 'ok' else 'evaluate_recovered_evidence'
