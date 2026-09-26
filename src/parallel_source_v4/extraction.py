"""Read-only cached-conversion experiment; no worker, provider or graph imports.

Regression replay is separate from a pre-frozen, source-reviewed unseen cohort.
All output goes to a new immutable external run directory. Exit 2 means blocked.
"""
from __future__ import annotations
import argparse
import datetime as dt
import importlib
import json
import os
from pathlib import Path
import re
import time
import sys

from trace_gc.pdf_source_parallel_v4 import digest_value, source_lines
from trace_gc.pdf_structure_parallel_v4 import assess_document, seal
from .adapters import document, item, grobid_assess, mineru_document, olmocr_assess
from .common import REPO, child, data_root, digest, method_hashes, read, verify_files, write_once, within
from .freeze import verify_freeze
from .metrics import score_case, summary, fallback_increment

METHODS = ('parallel_structure_v4', 'parallel_grobid_v4', 'parallel_mineru_v4', 'parallel_olmocr_v4')
# Evaluation holds, not selector exceptions. Preserved from the frozen receipt.
MATH_HOLDS = ['f026','f033','f103','f111','f122','f125','f131','f142','f146','f153','f154','f158','f166','f189']


def native_document(native: list[dict]) -> dict:
    """A separate native-only diagnostic, never presented as Docling output."""
    return document([item(i, x['text'], 'text', [x['bbox']]) for i,x in enumerate(native)])


def _cache(root: Path, method: str, sid: str, suffix='.json') -> Path:
    if not re.fullmatch(r'f\d{3}', sid):
        raise ValueError('unsupported_regression_case_id')
    old = root/'validation_v2'/method/(sid+suffix)
    return old if int(sid[1:]) <= 100 and old.is_file() else root/'validation_expanded200'/method/(sid+suffix)


def _folder(root: Path, sid: str) -> Path:
    return root/('validation_v2' if int(sid[1:]) <= 100 else 'validation_expanded200')/'pages'/sid


def blocked(code: str, **extra) -> dict:
    return {'schema_version':3, 'status':'BLOCKED', 'reason':code, 'new_paid_api_calls':0,
            'measured_api_spend_usd':0, 'production_graph_writes':0, 'independent_human_validation':'outstanding', **extra}


def preflight(root: Path, source_map: dict | None = None, *, repo: Path = REPO) -> dict:
    base=root/'validation_expanded200'
    if not (base/'manifest.json').is_file():
        return blocked('authorized_private_regression_data_unavailable', required_relative='validation_expanded200/manifest.json')
    try:
        protocol=read(repo/'review/first_page_expanded200/protocol.json')
        verify_files(repo,protocol['method_hashes'])
        reference=read(repo/'review/first_page_expanded200/reference_freeze.json')
        verify_files(base,reference['files'])
        if digest(base/'manifest.json') != protocol['manifest_sha256']:
            raise ValueError('regression_manifest_not_frozen_version')
        rows=read(base/'manifest.json')['pdfs']
        labels=read(base/'labels.json')
        if len(rows)!=200 or len({r['sample_id'] for r in rows})!=200 or set(labels)!={r['sample_id'] for r in rows}:
            raise ValueError('regression_requires_exact_200_cases')
        verified=[]; missing=[]
        for row in rows:
            sid=row['sample_id']; page=_folder(root,sid); receipt=read(page/'receipt.json')
            if receipt.get('physical_page')!=1:
                raise ValueError('cached_page_not_first_physical_page')
            relative=(source_map or {}).get(sid,row.get('source_relative'))
            source=child(root,relative) if relative else None
            if source is None:
                # The original source machine may still have its authorized path.
                candidate=Path(row.get('source_path',''))
                if candidate.is_absolute():
                    try:source=within(root,candidate)
                    except ValueError:pass
            if source is None or not source.is_file():
                missing.append({'id':sid,'gate':'authorized_original_source_unavailable_or_needs_relative_source_map'})
                continue
            hashes={'source':digest(source),'page':digest(page/'page.pdf'),'image':digest(page/'page.png')}
            expected={'source':receipt['source_sha256'],'page':receipt['page_pdf_sha256'],'image':receipt['image_sha256']}
            if hashes!=expected:
                raise ValueError('original_source_or_page_or_image_hash_mismatch:'+sid)
            verified.append({'id':sid, **{k+'_sha256':v for k,v in hashes.items()}})
        if missing:
            return blocked('regression_sources_incomplete',verified_sources=len(verified),missing=missing)
        return {'status':'PASS','verified_sources':verified, 'source_hash_verification':'original_source_page_and_image_bytes',
                'rows':rows,'labels':labels,'frozen_protocol_sha256':digest(repo/'review/first_page_expanded200/protocol.json')}
    except (OSError,KeyError,TypeError,ValueError) as exc:
        # Never copy arbitrary upstream messages or absolute private paths to logs.
        return blocked('regression_preflight_failed',error_class=type(exc).__name__)


def predict(method: str, paths: dict, kwargs: dict) -> dict:
    raw={}; inputs={}
    try:
        def load(name):
            path=paths[name]
            inputs[name]=digest(path)
            value=read(path)
            if value.get('page_sha256') and value['page_sha256']!=kwargs['page_sha256']:
                raise ValueError('converter_page_binding_mismatch')
            return value
        docstate={'status':'not_used'}
        doc=None
        if method in ('parallel_structure_v4','parallel_grobid_v4'):
            doc=load('docling_document')
            docstate=load('docling')
        scholarly=load('grobid') if paths.get('grobid') and paths['grobid'].is_file() else {'status':'error','text':''}
        field=scholarly.get('text','') if scholarly.get('status')=='success' else ''
        if method=='parallel_structure_v4':
            result=assess_document(doc,**kwargs,scholarly_abstract=field,conversion_status=docstate.get('status','error'))
        elif method=='parallel_grobid_v4':
            raw=scholarly
            result=grobid_assess(scholarly,doc,**kwargs)
        elif method=='parallel_mineru_v4':
            raw=load('mineru')
            result=assess_document(mineru_document(raw,kwargs['page_size']),**kwargs,scholarly_abstract=field,conversion_status=raw.get('status','error'))
        elif method=='parallel_olmocr_v4':
            raw=load('olmocr')
            result=olmocr_assess(raw,**kwargs,scholarly_abstract=field)
        else:
            raise ValueError('unknown_method')
        result['conversion_stage']={'status':raw.get('status',docstate.get('status')),
                                    'input_hashes':inputs,'new_model_conversion':False}
    except (OSError,ValueError,KeyError,TypeError) as exc:
        result=assess_document(document([]),**kwargs,conversion_status='error')
        result.update(reasons=['isolated_missing_or_invalid_conversion_cache'],error_class=type(exc).__name__)
        result['conversion_stage']={'status':'error','input_hashes':inputs,'new_model_conversion':False}
    result['source_hash_verification']='verified_by_offline_harness'
    return seal(result)


def run_cases(cases: list[dict], labels: dict, output: Path, cohort: str, methods=METHODS) -> dict:
    import fitz
    started=time.perf_counter(); by_method={m:[] for m in methods}
    for case in cases:
        sid=case['id']; page=case['page_path']
        if not re.fullmatch(r'[A-Za-z0-9_-]+',sid):raise ValueError('unsafe_sample_id')
        with fitz.open(page) as pdf:
            native=source_lines(pdf[0]); size=[pdf[0].rect.width,pdf[0].rect.height]
        kwargs={'page_size':size,'source_sha256':case['source_sha256'],'page_sha256':case['page_sha256'],'native_lines':native}
        write_once(output/'native'/f'{sid}.json',native)
        for method in methods:
            pred=predict(method,case['paths'],kwargs)
            write_once(output/'assessments'/method/f'{sid}.json',pred)
            reference={**labels[sid], 'math_review_required':labels[sid].get('math_review_required',False) or (cohort=='regression200' and sid in MATH_HOLDS)}
            by_method[method].append(score_case(sid,pred,reference))
    result={'schema_version':3,'status':'COMPLETE_OFFLINE_ASSESSMENT_NOT_QUALIFICATION','cohort':cohort,
            'metrics':{m:summary(rows) for m,rows in by_method.items()},'details':by_method,
            'runtime_seconds':time.perf_counter()-started,'environment':{'python':sys.version.split()[0],'pymupdf':fitz.VersionBind},'new_paid_api_calls':0,'measured_api_spend_usd':0,
            'production_graph_writes':0,'independent_human_validation':'outstanding','automatic_fallback_enabled':False}
    if 'parallel_structure_v4' in by_method:
        result['fallback_increment']={m:fallback_increment(by_method['parallel_structure_v4'],by_method[m]) for m in ('parallel_mineru_v4','parallel_olmocr_v4') if m in by_method}
    return result


def regression(root: Path, output: Path, source_map=None, methods=METHODS, *, replay_saved=True) -> dict:
    output=within(root,output)
    if output==root or output.relative_to(root).parts[0] in {'validation_expanded200','validation_v2','validation_200_10k','sample_comparison_100'}:
        raise ValueError('parallel_v4_outputs_must_not_enter_frozen_cache_directories')
    gate=preflight(root,source_map)
    write_once(output/'preflight.json',{k:v for k,v in gate.items() if k not in {'rows','labels'}})
    if gate['status']!='PASS':return gate
    write_once(output/'protocol.json',{'cohort':'regression200_already_examined','method_hashes':method_hashes(),
                                      'frozen_at':dt.datetime.now(dt.timezone.utc).isoformat(),'promotion':'source_review_required'})
    cases=[]
    for row,verified in zip(gate['rows'],gate['verified_sources']):
        sid=row['sample_id'];page=_folder(root,sid)
        cases.append({'id':sid,'page_path':page/'page.pdf',**verified,'paths':{
            'docling':_cache(root,'docling',sid),'docling_document':_cache(root,'docling',sid,'.document.json'),
            **{m:_cache(root,m,sid) for m in ('grobid','mineru','olmocr')}}})
    result=run_cases(cases,gate['labels'],output,'regression200',methods)
    # Read-only old prediction path: never call the old evaluate(), which writes
    # historical assessments. Original native lines and caches stay unchanged.
    old_details=[];replay=[]
    if replay_saved:
        os.environ['TRACE_GC_TEST_DATA_ROOT']=str(root)
        common=importlib.import_module('src.abstract_validation.common')
        if common.DATA.resolve()!=root:
            raise ValueError('frozen_harness_root_not_configured_restart_with_environment')
        old=importlib.import_module('src.abstract_validation_expanded.extraction')
        for case in cases:
            sid=case['id'];pred=old.prediction('structure_v2',sid)
            adapted={**pred,'proposal':pred.get('eligible_for_jev',False),'eligible_for_jev':False}
            old_details.append(score_case(sid,adapted,gate['labels'][sid]))
            saved=root/'validation_expanded200/assessments/structure_v2'/f'{sid}.json'
            if saved.is_file():
                previous=read(saved)
                replay.append({'id':sid,'saved_assessment_sha256':digest(saved),
                               'same_text':pred.get('text')==previous.get('text'),
                               'same_status':pred.get('status')==previous.get('status'),
                               'same_proposal':pred.get('eligible_for_jev')==previous.get('eligible_for_jev'),
                               'same_assessment_digest':pred.get('assessment_sha256')==previous.get('assessment_sha256')})
            else:replay.append({'id':sid,'saved_receipt_available':False})
        previous_good={d['id'] for d in old_details if d['proposed'] and d['gold']=='complete' and d['text_match_98']}
        current_good={d['id'] for d in result['details'].get('parallel_structure_v4',[]) if d['proposed'] and d['gold']=='complete' and d['text_match_98']}
        result['v2_replay']=replay
        replay_ok=all(all(row.get(k) is True for k in ('same_text','same_status','same_proposal','same_assessment_digest')) for row in replay)
        result['saved_replay_gate']={'status':'PASS' if replay_ok else 'FAIL_OR_MISSING_SAVED_RECEIPT'}
        result['v2_baseline']=summary(old_details)
        result['preserve_91_gate']={'status':'PASS' if len(previous_good)==91 and previous_good<=current_good else 'FAIL',
                                   'old_correct':len(previous_good),'lost_correct_ids':sorted(previous_good-current_good)}
        if result['preserve_91_gate']['status']!='PASS':result['status']='FAILED_REGRESSION_PRESERVATION_GATE'
        if not replay_ok:result['status']='FAILED_SAVED_REPLAY_GATE'
    else:result['preserve_91_gate']={'status':'NOT_RUN'}
    write_once(output/'results.json',result)
    return result


def frozen_cohort(root: Path, freeze: dict, output: Path, methods=METHODS) -> dict:
    verify_freeze(root,freeze)
    cases=[]
    for row in freeze['manifest']['pdfs']:
        paths={k:child(root,v) for k,v in row.get('conversion_outputs',{}).items()}
        cases.append({'id':row['sample_id'],'page_path':child(root,row['page_relative']),
                      'source_sha256':row['source_sha256'],'page_sha256':row['page_sha256'],'paths':paths})
    result=run_cases(cases,freeze['labels'],output,freeze['cohort_kind'],methods)
    result['freeze_sha256']=freeze['freeze_sha256']
    write_once(output/'results.json',result)
    return result


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=['preflight','regression','cohort'])
    parser.add_argument('--data-root')
    parser.add_argument('--source-map')
    parser.add_argument('--freeze')
    parser.add_argument('--output',required=True,help='New run path relative to the authorized test-data root')
    parser.add_argument('--methods',nargs='+',choices=METHODS,default=list(METHODS))
    args=parser.parse_args();root=data_root(args.data_root);output=child(root,args.output)
    mapping=read(child(root,args.source_map)) if args.source_map else None
    if args.stage=='preflight':
        result=preflight(root,mapping)
        write_once(output/'preflight.json',{k:v for k,v in result.items() if k not in {'rows','labels'}})
    elif args.stage=='regression':result=regression(root,output,mapping,tuple(args.methods))
    else:
        if not args.freeze:parser.error('cohort requires --freeze')
        result=frozen_cohort(root,read(child(root,args.freeze)),output,tuple(args.methods))
    print(json.dumps({k:result[k] for k in ('status','reason','runtime_seconds','new_paid_api_calls','measured_api_spend_usd') if k in result},sort_keys=True))
    return 2 if result['status']=='BLOCKED' else 1 if result['status'].startswith('FAILED_') else 0


if __name__=='__main__':raise SystemExit(main())
