"""Experimental v2 selector: document reading order and scholarly field checks.

This is a proposal generator. Production admission still requires source review.
The frozen v1 selector remains unchanged for reproducible comparisons.
"""
from __future__ import annotations
import difflib
import hashlib
import json
import math
import re
from .pdf_evidence import ABSTRACT, BODY, EMAIL, EXCLUDED, INTERNAL, INTRODUCTION, NARRATIVE, NUMBERED, SENTENCE_END, _items, _is_metadata, _overlap, canonical, normalize, assess_first_page

VERSION = 'page-one-structure-v2'
FIELD_BOUNDARY = re.compile(r'(?:^|(?<=[.!?])\s+|\n)\s*(?:Index\s+Terms|Key\s*words?|CCS\s+Concepts|PACS\s+(?:numbers|codes)|Funding|Acknowledg\w*|Correspondence|Author\s+contributions|Data\s+availability)\s*[:.—–-]?', re.I)
NOTICE = re.compile(r'^(?:funding\s*:|published\s+(?:in|by|as)|accepted\s+(?:for|by)|to appear in|this (?:is|article is|paper is) (?:a |an )?(?:preprint|author|accepted|revised|extended)|we (?:thank|congratulate)|discussion (?:of|on)|comment(?:ary)? (?:on|regarding)|submitted (?:to|on)|this research (?:was|is) (?:supported|funded)|this (?:work|paper|article) has been submitted|proceedings of|highlights\b|key points\b)', re.I)
TAIL_URL = re.compile(r'(?:^|\n)\s*(?:https?://|www\.)\S+(?:\s+\S+)?\s*$', re.I)


def body_items(document):
    objects = {x['self_ref']: x for key in ('texts', 'groups', 'pictures', 'tables') for x in document.get(key, [])}
    ordered, seen = [], set()
    def walk(node):
        ref = node.get('self_ref')
        if ref in seen:
            raise ValueError('Duplicate/cyclic document reading-order reference')
        seen.add(ref)
        if node.get('text') or node.get('orig'):
            ordered.append(node)
        for child in node.get('children', []):
            walk(objects[child.get('cref', child.get('$ref'))])
    walk(document['body'])
    return ordered


def _trim(text):
    text = ABSTRACT.sub('', text)
    boundary = FIELD_BOUNDARY.search(text)
    if boundary:
        text = text[:boundary.start()]
    text = TAIL_URL.sub('', text)
    return normalize(text), bool(boundary)


def _agreement(a, b):
    a, b = canonical(a), canonical(b)
    if not a or not b:
        return 0.0
    n = sum(x.size for x in difflib.SequenceMatcher(None,a,b,autojunk=False).get_matching_blocks())
    return min(n/len(a), n/len(b))


def assess_document(document, *, page_size, source_sha256, page_sha256, native_lines=None, scholarly_abstract='', max_input_chars=4000, conversion_status='success'):
    result = {'schema_version': 2, 'extractor_version': VERSION, 'physical_page': 1,
        'source_sha256': source_sha256, 'page_sha256': page_sha256, 'page_size': list(page_size),
        'status':'uncertain', 'text':'', 'eligible_for_jev':False, 'reasons':[], 'spans':[]}
    try:
        if conversion_status.lower().split('.')[-1]!='success':
            raise ValueError('Upstream conversion was not successful')
        if len(page_size)!=2 or not all(math.isfinite(x) and x>0 for x in page_size):
            raise ValueError('Invalid page dimensions')
        if any(not re.fullmatch('[a-f0-9]{64}',x) for x in (source_sha256,page_sha256)):
            raise ValueError('Invalid source hash')
        raw = body_items(document)
        # Validate all coordinates with the frozen v1 validator, then restore tree order.
        validated = {x['ref']:x for x in _items(raw,*page_size)}
        ordered = [validated[x['self_ref']] for x in raw if x['self_ref'] in validated]
        geometry = assess_first_page(raw,page_size=page_size,source_sha256=source_sha256,page_sha256=page_sha256,native_lines=native_lines)
        anchors = [i for i,x in enumerate(ordered) if ABSTRACT.match(x['text']) and x['label'] not in EXCLUDED]
        # Empty duplicated Abstract headers sometimes surround a keywords block.
        if len(anchors)>1 and all(not _trim(ordered[i]['text'])[0] for i in anchors[:-1]):
            between = ordered[anchors[0]+1:anchors[-1]]
            if all(_is_metadata(x) or ABSTRACT.match(x['text']) or x['label'] in EXCLUDED for x in between):
                anchors = anchors[-1:]
        if len(anchors)>1:
            result['reasons']=['multiple_substantive_abstract_regions']
        else:
            explicit = bool(anchors)
            start = anchors[0] if explicit else None
            # An unlabeled paragraph needs a scholarly field classifier as corroboration.
            if start is None and scholarly_abstract:
                scores = [(_agreement(x['text'],scholarly_abstract),i) for i,x in enumerate(ordered) if x['label'] not in EXCLUDED and not _is_metadata(x) and not NOTICE.match(x['text']) and len(x['text'])>=150 and NARRATIVE.search(x['text'])]
                if scores:
                    candidates=[i for score,i in scores if score>=.55 or canonical(ordered[i]['text'])[:60] in canonical(scholarly_abstract)[:100]]
                    if candidates:start=min(candidates)
            if start is None and geometry['text'] and geometry['spans']:
                ref=geometry['spans'][0].get('ref')
                candidate=next((i for i,x in enumerate(ordered) if x['ref']==ref),None)
                first_body=next((i for i,x in enumerate(ordered) if BODY.fullmatch(x['text']) or INTRODUCTION.match(x['text'])),len(ordered))
                if candidate is not None and candidate<first_body and len(ordered[candidate]['text'])>=150 and not NOTICE.match(ordered[candidate]['text']) and not _is_metadata(ordered[candidate]):
                    start=candidate
            if start is None:
                result.update(status='absent' if not scholarly_abstract else 'uncertain', reasons=['no_identified_page_one_abstract'])
            else:
                selected, boundary = [], None
                structured = sum(bool(re.match(r'^(?:Methods?|Results)\s*:',x['text'],re.I)) or (x['label']=='section_header' and x['text'].lower().strip(': .') in {'methods','results'}) for x in ordered[start:])>=2
                for i,x in enumerate(ordered[start:],start):
                    if selected and x['label'] in {'caption','picture','table'}:
                        boundary='figure_or_table';break
                    if x['label'] in EXCLUDED:
                        # Footnotes may occur between columns; they do not end the abstract.
                        continue
                    if i>start and (_is_metadata(x) or NOTICE.match(x['text']) or FIELD_BOUNDARY.match(x['text'])):
                        boundary='metadata_field'; break
                    section = NUMBERED.sub('',x['text']).split(':',1)[0].strip().lower().rstrip(': .')
                    header = x['label']=='section_header' or BODY.fullmatch(x['text']) or INTRODUCTION.match(x['text'])
                    if i>start and header and not (structured and not NUMBERED.match(x['text']) and section in INTERNAL):
                        boundary='body_section'; break
                    if NOTICE.match(x['text']):
                        boundary='publication_notice'; break
                    text, embedded = _trim(x['raw_text'])
                    if text:
                        selected.append(dict(x,text=text))
                    if embedded:
                        boundary='embedded_metadata'; break
                doc_text=normalize(' '.join(x['text'] for x in selected))
                native, seen = [], set()
                for x in selected:
                    for box in x['boxes']:
                        # Native line order stays local to each selected paragraph.
                        for line in native_lines or []:
                            b=line['bbox']; cy=(b[1]+b[3])/2
                            if line['id'] not in seen and box[1]-2<=cy<=box[3]+2 and _overlap(box,b)>=.8:
                                seen.add(line['id']);native.append(line)
                native_text,_=_trim('\n'.join(x['text'] for x in native))
                agreement=_agreement(doc_text,native_text) if native_lines else None
                # Native substitution needs stricter agreement; disagreement remains visible.
                text=native_text if agreement is not None and agreement>=.98 else doc_text
                field_match=_agreement(text,scholarly_abstract) if scholarly_abstract else None
                status='complete'; reasons=[]
                if not text:
                    status='absent';reasons.append('heading_without_abstract_text')
                elif not explicit and (field_match is None or field_match<.98) and boundary not in {'body_section','metadata_field','embedded_metadata'}:
                    status='uncertain';reasons.append('unlabeled_field_disagreement')
                elif agreement is not None and agreement<.98:
                    status='uncertain';reasons.append('native_and_model_disagree')
                elif not SENTENCE_END.search(re.sub(r'(?<=[.!?])(?:[†‡*\d]+|[a-z])$','',text).strip()):
                    status='partial';reasons.append('unfinished_final_sentence')
                elif not boundary:
                    # Even a terminal period can occur midway through an abstract at a page break.
                    bottom=max((x['bbox'][3] for x in selected),default=page_size[1])
                    if bottom>page_size[1]-.15*page_size[1]:
                        status='uncertain';reasons.append('page_bottom_without_closing_boundary')
                if len(text)>max_input_chars:
                    reasons.append('exceeds_request_character_budget')
                if not reasons:reasons=['identified_region_with_verified_text']
                result.update(status=status,text=text,eligible_for_jev=status=='complete' and len(text)<=max_input_chars,
                    reasons=reasons, explicit_heading=explicit, closing_boundary=boundary,
                    native_alignment=agreement, scholarly_alignment=field_match, docling_text=doc_text,
                    transcription='native_pdf' if text==native_text else 'layout_model',
                    spans=[{'ref':x['ref'],'boxes':x['boxes'],'text':x['text']} for x in selected])
                # Independent geometry and scholarly role agreement can repair a bad
                # reading-order tree, while retaining the original v2 proposal for audit.
                geometry_text,trimmed_metadata=_trim(geometry['text'])
                geometry_usable=geometry['eligible_for_jev'] or (trimmed_metadata and geometry['reasons']==['unfinished_final_sentence'] and SENTENCE_END.search(geometry_text))
                if geometry_usable and scholarly_abstract and _agreement(geometry_text,_trim(geometry.get('docling_text',''))[0])>=.98 and _agreement(geometry_text,scholarly_abstract)>=.98 and _agreement(result['text'],scholarly_abstract)<.98:
                    result.update(original_tree_text=result['text'],text=geometry_text,status='complete',
                        eligible_for_jev=len(geometry_text)<=max_input_chars,spans=geometry['spans'],
                        reasons=['geometry_and_scholarly_field_agree'],transcription=geometry.get('transcription','native_pdf'),
                        scholarly_alignment=_agreement(geometry_text,scholarly_abstract))
    except (KeyError,ValueError,TypeError,OverflowError) as exc:
        result.update(status='error',reasons=[type(exc).__name__+': '+str(exc)],eligible_for_jev=False)
    if result['eligible_for_jev'] and not native_lines:
        result.update(status='uncertain',eligible_for_jev=False,reasons=['no_native_source_verification'])
    return seal(result)


def seal(result):
    result.pop('assessment_sha256',None)
    result['text_sha256']=hashlib.sha256(result['text'].encode()).hexdigest()
    binding={k:result[k] for k in ('source_sha256','page_sha256','physical_page','text_sha256')}
    result['evidence_sha256']=hashlib.sha256(json.dumps(binding,sort_keys=True).encode()).hexdigest()
    result['assessment_sha256']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()
    return result
