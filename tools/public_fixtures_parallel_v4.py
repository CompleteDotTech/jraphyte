#!/usr/bin/env python3
"""Generate/replay authored PDF counterexamples, NOT an unseen-paper cohort.

Prepare, inspect the five images, then replay with an explicit reviewer name.
Only native PDF extraction runs: Docling-like regions are hand-authored fixtures.
All PDF/image/native outputs must remain outside the source repository.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from datetime import datetime,timezone
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from trace_gc.pdf_source_parallel_v4 import source_lines,compare
from trace_gc.pdf_structure_parallel_v4 import assess_document
from src.parallel_source_v4.adapters import document,item
from src.parallel_source_v4.common import digest,read,write_once,method_hashes

ABSTRACT=('We investigate how transport changes in sparse networks under controlled perturbations. '
          'Our measurements establish a stable relationship between connectivity and response. '
          'The resulting estimates agree with independently generated observations.')
BODY=('The rest of this article develops the background and describes earlier experiments. '
      'We compare several unrelated descriptions before introducing the detailed protocol.')
KINDS=('overview','synopsis','wrong_column','dedication','authors')


def prepare(root:Path):
    import fitz
    root.mkdir(parents=True,exist_ok=False)
    for kind in KINDS:
        with fitz.open() as pdf:
            page=pdf.new_page(width=600,height=800)
            page.insert_text((40,45),'Synthetic source fixture: '+kind,fontsize=15)
            if kind=='authors':
                page.insert_textbox(fitz.Rect(40,100,550,200),'Alice Smith, Brian Jones, Carol White, David Green, Emily Black, Frank Brown, Georgia Gray, Henry Snow.',fontsize=12,fontname='hebo')
                page.insert_textbox(fitz.Rect(40,220,550,300),'Author contributions: We all contributed to writing and organizing this collaboration.',fontsize=10)
            else:
                if kind!='wrong_column':page.insert_text((40,90),'Abstract',fontsize=11,fontname='hebo')
                remaining=page.insert_textbox(fitz.Rect(40,110,285,250),ABSTRACT,fontsize=10,fontname='hebo' if kind in ('synopsis','wrong_column') else 'helv')
                if remaining<0:raise ValueError('fixture_text_did_not_fit')
                if kind=='overview':
                    page.insert_text((40,280),'Overview',fontsize=11,fontname='hebo')
                    page.insert_textbox(fitz.Rect(40,300,285,460),BODY,fontsize=10)
                elif kind=='synopsis':
                    page.insert_textbox(fitz.Rect(40,265,285,365),'The accompanying description gives a separate account of these results for a general audience.',fontsize=10,color=(0,0,.8))
                    page.insert_text((40,405),'1 Introduction',fontsize=11,fontname='hebo')
                elif kind=='wrong_column':
                    page.insert_textbox(fitz.Rect(330,100,570,280),BODY,fontsize=10)
                    page.insert_text((40,290),'1 Introduction',fontsize=11,fontname='hebo')
                else:page.insert_text((40,280),'Dedicated to our colleagues.',fontsize=10)
            pdf.save(root/(kind+'.pdf'));page.get_pixmap(dpi=100).save(root/(kind+'.png'))
            write_once(root/(kind+'.native.json'),source_lines(page))
    write_once(root/'preparation.json',{'cohort':'authored_causal_fixtures_not_unseen_papers',
              'models_invoked':0,'source_review':'inspect original page images before replay',
              'producer_sha256':digest(Path(__file__)),'files':{p.name:digest(p) for p in sorted(root.iterdir()) if p.is_file()}})


def layout_fixture(kind,native):
    groups=defaultdict(list)
    for row in native:groups[row['block_id']].append(row)
    blocks=list(groups.values())
    # Deliberately merge boundaries as a parser could; do not label the expected
    # output or insert the expected abstract into the selector's inputs.
    if kind in ('overview','dedication'):blocks=[blocks[0],[x for group in blocks[1:] for x in group]]
    elif kind=='synopsis':blocks=[blocks[0],[x for group in blocks[1:4] for x in group],blocks[4]]
    elif kind=='wrong_column':
        header=[b for b in blocks if b[0]['text'].startswith('Synthetic')]
        right=[b for b in blocks if b[0]['bbox'][0]>300]
        left=[b for b in blocks if b not in header and b not in right]
        blocks=header+right+left
    items=[]
    for block in blocks:
        b=[min(x['bbox'][0] for x in block),min(x['bbox'][1] for x in block),max(x['bbox'][2] for x in block),max(x['bbox'][3] for x in block)]
        items.append(item(len(items),'\n'.join(x['text'] for x in block),'text',[b]))
    return document(items)


def replay(root:Path,reviewer:str):
    prep=read(root/'preparation.json')
    for name,expected in prep['files'].items():
        if digest(root/name)!=expected:raise ValueError('fixture_source_changed_after_preparation')
    if prep['producer_sha256']!=digest(Path(__file__)):raise ValueError('fixture_producer_changed')
    write_once(root/'source_review.json',{'cohort':'synthetic_causal_fixture','reviewer_kind':'assistant','reviewer':reviewer,
        'source_first_attestation':True,'independent_human_validation':'outstanding','reviewed_at':datetime.now(timezone.utc).isoformat(),
        'source_preparation_sha256':digest(root/'preparation.json'),'method_hashes':method_hashes()})
    cases=[]
    for kind in KINDS:
        native=read(root/(kind+'.native.json'));source=digest(root/(kind+'.pdf'))
        result=assess_document(layout_fixture(kind,native),page_size=[600,800],source_sha256=source,page_sha256=source,native_lines=native)
        expected_state='absent' if kind=='authors' else 'uncertain' if kind=='synopsis' else 'complete'
        correct=result['status']==expected_state and (not result['text'] if kind=='authors' else compare(result['text'],ABSTRACT)['boundary_and_98_match'])
        cases.append({'id':kind,'expected_state':expected_state,'observed_state':result['status'],'expected_disposition_confirmed':correct,
                      'source_sha256':source,'image_sha256':digest(root/(kind+'.png')),'native_sha256':digest(root/(kind+'.native.json')),
                      'assessment_sha256':result['assessment_sha256'],'closing_boundary':result['closing_boundary'],'source_spans':len(result['spans']),
                      'proposal':result['proposal'],'verified_admission':result['verified_admission']})
        write_once(root/(kind+'.assessment.json'),result)
    result={'cohort':'synthetic_causal_fixtures_not_unseen_papers','pages':len(cases),'confirmed':sum(bool(c['expected_disposition_confirmed']) for c in cases),
            'cases':cases,'source_images_reviewed_by':'assistant','independent_human_validation':'outstanding',
            'docling_conversion':'NOT_RUN; hand-authored layout counterexamples','new_model_inferences':0,'new_paid_api_calls':0,'measured_api_spend_usd':0,
            'production_graph_writes':0,'new_unseen_paper_count':0,'method_hashes':method_hashes()}
    write_once(root/'results.json',result)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('stage',choices=['prepare','replay']);p.add_argument('--output',required=True,type=Path)
    p.add_argument('--reviewer',help='Attest that you inspected the images before replay; not independent human certification')
    args=p.parse_args();root=args.output.resolve()
    if root==ROOT or ROOT in root.parents:p.error('source PDFs and images must be outside the repository')
    if args.stage=='prepare':prepare(root);return 0
    if not args.reviewer:p.error('replay requires --reviewer after source-image inspection')
    result=replay(root,args.reviewer);print(json.dumps({'cohort':result['cohort'],'pages':result['pages'],'confirmed':result['confirmed']}))
    return 0 if result['confirmed']==result['pages'] else 1


if __name__=='__main__':raise SystemExit(main())
