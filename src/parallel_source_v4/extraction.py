"""Read-only cached-conversion experiment; no worker, provider or graph imports.

Regression replay is separate from a pre-frozen, source-reviewed unseen cohort.
All output goes to a new immutable external run directory. Exit 2 means blocked.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import time
import sys

from trace_gc.pdf_source_parallel_v4 import digest_value, source_lines, validate_lines
from trace_gc.pdf_structure_parallel_v4 import assess_document, seal
from .adapters import document, item, grobid_assess, mineru_document, olmocr_assess
from .common import REPO, child, data_root, digest, method_hashes, read, read_hashed_json, verify_files, write_once, within
from .freeze import verify_freeze
from .metrics import score_case, summary, fallback_increment
from .runtime import (DEFAULT_RUNTIME_LOCK, InputGateError, configure_baseline,
                      runtime_receipt, verify_native_manifest)

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


def validate_cached_input(name: str, value, *, case_id=None, page_size=None) -> None:
    """Reject malformed container/field types before any selector runs.

    Error and truncated converter receipts remain valid measured states. Content,
    geometry and source alignment still belong to the selector's hold decisions.
    """
    try:
        if name == 'baseline_native':
            validate_lines(value,page_size)
            return
        if not isinstance(value,dict):
            raise ValueError('object_required')
        for key in ('status','text','raw_text','page_sha256'):
            if key in value and not isinstance(value[key],str):
                raise ValueError('string_field_required')
        if name == 'mineru':
            blocks=value.get('blocks',[])
            if not isinstance(blocks,list) or any(not isinstance(b,dict) for b in blocks):
                raise ValueError('block_objects_required')
            for block in blocks:
                if block.get('content') is not None and not isinstance(block['content'],str):
                    raise ValueError('block_content_string_required')
                if block.get('type') is not None and not isinstance(block['type'],str):
                    raise ValueError('block_type_string_required')
                if 'bbox' in block and not isinstance(block['bbox'],list):
                    raise ValueError('block_box_list_required')
        if name == 'docling_document':
            objects=[]
            for key in ('texts','groups','pictures','tables'):
                collection=value.get(key,[])
                if not isinstance(collection,list) or any(not isinstance(v,dict) for v in collection):
                    raise ValueError('document_object_list_required')
                objects.extend(collection)
            if 'body' in value:
                if not isinstance(value['body'],dict):
                    raise ValueError('document_body_object_required')
                objects.append(value['body'])
            for item in objects:
                for key in ('text','orig','self_ref','label'):
                    if key in item and not isinstance(item[key],str):
                        raise ValueError('document_string_field_required')
                children=item.get('children',[])
                if not isinstance(children,list) or any(not isinstance(c,dict) or
                    not isinstance(c.get('cref',c.get('$ref')),str) for c in children):
                    raise ValueError('document_children_required')
                prov=item.get('prov',[])
                if not isinstance(prov,list) or any(not isinstance(p,dict) or not isinstance(p.get('bbox'),dict) for p in prov):
                    raise ValueError('document_provenance_required')
    except (TypeError,ValueError,KeyError,AttributeError) as exc:
        details={'input_kind':name,'action':'restore_valid_authorized_cache'}
        if case_id is not None:details['case_id']=case_id
        raise InputGateError('invalid_cached_json_shape',**details) from exc


def preflight(root: Path, source_map: dict | None = None, *, repo: Path = REPO,
              methods=METHODS, replay_saved=True, runtime_lock=DEFAULT_RUNTIME_LOCK,
              native_mode='fresh', native_manifest=None, native_manifest_sha256=None) -> dict:
    base=root/'validation_expanded200'
    if not (base/'manifest.json').is_file():
        return blocked('authorized_private_regression_data_unavailable', required_relative='validation_expanded200/manifest.json')
    try:
        runtime = runtime_receipt(runtime_lock)
        code_hashes = method_hashes(repo)
        if native_mode not in {'fresh', 'replay'}:
            raise InputGateError('invalid_native_mode')
        if not methods or len(set(methods)) != len(methods) or set(methods)-set(METHODS):
            raise InputGateError('invalid_or_duplicate_methods')
        baseline = configure_baseline(root) if replay_saved else None
        native_reference = None
        if native_manifest is not None:
            native_reference = verify_native_manifest(root, native_manifest, native_manifest_sha256)
        elif native_mode == 'replay':
            raise InputGateError('saved_native_manifest_required', action='capture_and_pin_saved_native_manifest')
        elif native_manifest_sha256 is not None:
            raise InputGateError('native_manifest_path_required')
        protocol,protocol_sha=read_hashed_json(repo/'review/first_page_expanded200/protocol.json')
        verify_files(repo,protocol['method_hashes'])
        reference,reference_sha=read_hashed_json(repo/'review/first_page_expanded200/reference_freeze.json')
        repository_inputs={'review/first_page_expanded200/protocol.json':protocol_sha,
                           'review/first_page_expanded200/reference_freeze.json':reference_sha}
        verify_files(base,reference['files'])
        manifest,manifest_sha=read_hashed_json(base/'manifest.json')
        if manifest_sha != protocol['manifest_sha256']:
            raise ValueError('regression_manifest_not_frozen_version')
        rows=manifest['pdfs']
        labels,labels_sha=read_hashed_json(base/'labels.json')
        if labels_sha!=reference['files']['labels.json']:
            raise InputGateError('regression_labels_changed_after_verification')
        if len(rows)!=200 or len({r['sample_id'] for r in rows})!=200 or set(labels)!={r['sample_id'] for r in rows}:
            raise ValueError('regression_requires_exact_200_cases')
        if source_map is not None and (not isinstance(source_map,dict) or set(source_map)!={r['sample_id'] for r in rows}):
            raise InputGateError('source_map_requires_exact_regression_case_set', action='supply_all_200_relative_source_paths')
        references = {r['id']: r for r in native_reference['cases']} if native_reference else {}
        if native_reference and set(references) != {r['sample_id'] for r in rows}:
            raise InputGateError('native_manifest_requires_exact_regression_case_set')
        verified=[]; missing=[]; cases=[]; baseline_predictions={}; native_receipts=[]; input_hashes={}
        for relative,sha in reference['files'].items():
            input_hashes[(base/relative).relative_to(root).as_posix()]=sha
        input_hashes[(base/'manifest.json').relative_to(root).as_posix()]=manifest_sha
        if native_reference:
            input_hashes[within(root,native_manifest).relative_to(root).as_posix()]=native_manifest_sha256
        for row in rows:
            sid=row['sample_id']; page=_folder(root,sid); receipt,receipt_sha=read_hashed_json(page/'receipt.json')
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
            for path,sha in ((source,hashes['source']),(page/'page.pdf',hashes['page']),
                             (page/'page.png',hashes['image']),(page/'receipt.json',receipt_sha)):
                input_hashes[path.relative_to(root).as_posix()]=sha
            identity={'id':sid, **{k+'_sha256':v for k,v in hashes.items()}}
            verified.append(identity)
            paths={'docling':_cache(root,'docling',sid),'docling_document':_cache(root,'docling',sid,'.document.json'),
                   **{m:_cache(root,m,sid) for m in ('grobid','mineru','olmocr')}}
            required={'grobid'}
            if baseline or set(methods)&{'parallel_structure_v4','parallel_grobid_v4'}:
                required.update({'docling','docling_document'})
            required.update(m.removeprefix('parallel_').removesuffix('_v4') for m in methods
                            if m in {'parallel_mineru_v4','parallel_olmocr_v4'})
            all_inputs={name: paths[name] for name in required}
            if baseline:
                all_inputs.update(baseline_native=page/'lines.json',
                                  saved_assessment=base/'assessments/structure_v2'/f'{sid}.json')
            for name,path in all_inputs.items():
                if not path.is_file():
                    raise InputGateError('required_regression_input_missing', case_id=sid, input_kind=name,
                                         action='restore_authorized_frozen_input')
                value,sha=read_hashed_json(path)
                input_hashes[path.relative_to(root).as_posix()]=sha
                validate_cached_input(name,value,case_id=sid,page_size=receipt['page_size'])
            if references:
                reference=references[sid]
                if any(reference[k]!=identity[k] for k in ('source_sha256','page_sha256','image_sha256')):
                    raise InputGateError('native_manifest_source_mismatch',case_id=sid)
                if reference['page_size']!=receipt['page_size']:
                    raise InputGateError('native_manifest_page_size_mismatch',case_id=sid)
            if native_mode=='replay':
                native_path=child(root,references[sid]['native_relative'])
                native,native_file_sha=read_hashed_json(native_path)
                if native_file_sha!=references[sid]['file_sha256']:
                    raise InputGateError('native_file_changed_after_verification',case_id=sid)
                input_hashes[native_path.relative_to(root).as_posix()]=native_file_sha
            else:
                import fitz
                page_bytes=(page/'page.pdf').read_bytes()
                if hashlib.sha256(page_bytes).hexdigest()!=hashes['page']:
                    raise InputGateError('page_changed_after_verification',case_id=sid)
                with fitz.open(stream=page_bytes,filetype='pdf') as pdf:
                    if len(pdf)!=1:
                        raise InputGateError('expected_single_first_page_extract',case_id=sid)
                    native=source_lines(pdf[0])
                    if [pdf[0].rect.width,pdf[0].rect.height]!=receipt['page_size']:
                        raise InputGateError('cached_page_size_changed',case_id=sid)
            native_sha=digest_value(native)
            if native_mode=='replay' and native_sha!=references[sid]['native_sha256']:
                raise InputGateError('native_representation_changed_after_verification',case_id=sid)
            native_identity={**identity,'page_size':receipt['page_size'],'native_sha256':native_sha,
                             'mode':native_mode,'reference_native_sha256':references.get(sid,{}).get('native_sha256'),
                             'changed_from_reference':native_sha!=references[sid]['native_sha256'] if references else None}
            native_receipts.append(native_identity)
            cases.append({**identity,'page_path':page/'page.pdf','page_size':receipt['page_size'],
                          'paths':paths,'native_lines':native,'native_identity':native_identity,
                          'input_hashes':{name:input_hashes[path.relative_to(root).as_posix()] for name,path in all_inputs.items()}})
            if baseline:
                # This runs only after root/runtime/source/input checks for this
                # case. The new selector is never called until ALL cases pass.
                baseline_predictions[sid]=baseline.prediction('structure_v2',sid)
        if missing:
            return blocked('regression_sources_incomplete',verified_sources=len(verified),missing=missing)
        verify_files(root,input_hashes)
        verify_files(repo,repository_inputs)
        if method_hashes(repo)!=code_hashes:
            raise InputGateError('experiment_code_changed_during_preflight',action='restart_with_stable_checkout')
        if runtime_receipt(runtime_lock)!=runtime:
            raise InputGateError('experiment_runtime_changed_during_preflight',action='restart_with_locked_runtime')
        return {'status':'PASS','verified_sources':verified, 'source_hash_verification':'original_source_page_and_image_bytes',
                'rows':rows,'labels':labels,'cases':cases,'baseline_predictions':baseline_predictions,
                'runtime':runtime,'method_hashes':code_hashes,'input_file_hashes':input_hashes,
                'repository_input_hashes':repository_inputs,
                'native_mode':native_mode,'native_inputs':native_receipts,
                'native_manifest_sha256':native_manifest_sha256 if native_reference else None,
                'extractor_identity':native_reference['extractor_identity'] if native_mode=='replay' else {
                    'runtime_sha256':runtime['runtime_sha256'],
                    'source_extractor_sha256':digest(repo/'trace_gc/pdf_source_parallel_v4.py')},
                'native_comparison':{'status':'COMPARED' if native_reference else 'NO_REFERENCE_SUPPLIED',
                    'changed_ids':[r['id'] for r in native_receipts if r['changed_from_reference']]},
                'frozen_protocol_sha256':protocol_sha}
    except InputGateError as exc:
        return blocked(exc.code,**exc.details)
    except (OSError,KeyError,TypeError,ValueError,AttributeError) as exc:
        # Never copy arbitrary upstream messages or absolute private paths to logs.
        return blocked('regression_preflight_failed',error_class=type(exc).__name__)


def public_preflight(gate: dict) -> dict:
    """Receipt contains hashes and state, never source/label/native text."""
    return {k:v for k,v in gate.items() if k not in {'rows','labels','cases','baseline_predictions'}}


def verify_preflight_inputs(root: Path, gate: dict, runtime_lock=DEFAULT_RUNTIME_LOCK) -> None:
    """An input changing during a long run cannot qualify under an old receipt."""
    try:
        verify_files(root,gate['input_file_hashes'])
        verify_files(REPO,gate.get('repository_input_hashes',{}))
    except (OSError,ValueError) as exc:
        raise InputGateError('experiment_input_changed_after_preflight',action='restore_inputs_and_use_new_output') from exc
    if method_hashes()!=gate['method_hashes']:
        raise InputGateError('experiment_code_changed_after_preflight',action='restart_with_stable_checkout')
    if runtime_receipt(runtime_lock)!=gate['runtime']:
        raise InputGateError('experiment_runtime_changed_after_preflight',action='restart_with_locked_runtime')


def predict(method: str, paths: dict, kwargs: dict, *, expected_input_hashes=None) -> dict:
    raw={}; inputs={}
    try:
        def load(name):
            path=paths[name]
            value,inputs[name]=read_hashed_json(path)
            if expected_input_hashes is not None and inputs[name]!=expected_input_hashes.get(name):
                raise InputGateError('converter_changed_after_preflight',input_kind=name)
            validate_cached_input(name,value,page_size=kwargs.get('page_size'))
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
    except InputGateError:
        raise
    except (OSError,ValueError,KeyError,TypeError,AttributeError) as exc:
        result=assess_document(document([]),**kwargs,conversion_status='error')
        result.update(reasons=['isolated_missing_or_invalid_conversion_cache'],error_class=type(exc).__name__)
        result['conversion_stage']={'status':'error','input_hashes':inputs,'new_model_conversion':False}
    result['source_hash_verification']='verified_by_offline_harness'
    return seal(result)


def run_cases(cases: list[dict], labels: dict, output: Path, cohort: str, methods=METHODS,
              *, input_receipt=None, root=None) -> dict:
    import fitz
    started=time.perf_counter(); by_method={m:[] for m in methods}; native_records=[]; assessment_files={}
    for case in cases:
        sid=case['id']; page=case['page_path']
        if not re.fullmatch(r'[A-Za-z0-9_-]+',sid):raise ValueError('unsafe_sample_id')
        if 'native_lines' in case:
            native=case['native_lines'];size=case['page_size']
        else:
            with fitz.open(page) as pdf:
                native=source_lines(pdf[0]); size=[pdf[0].rect.width,pdf[0].rect.height]
        kwargs={'page_size':size,'source_sha256':case['source_sha256'],'page_sha256':case['page_sha256'],'native_lines':native}
        native_path=output/'native'/f'{sid}.json'
        file_sha=write_once(native_path,native)
        if root is not None:
            native_records.append({**case['native_identity'], 'file_sha256':file_sha,
                                   'native_relative':native_path.relative_to(root).as_posix()})
        for method in methods:
            pred=predict(method,case['paths'],kwargs,expected_input_hashes=case.get('input_hashes'))
            relative=f'assessments/{method}/{sid}.json'
            assessment_files[relative]=write_once(output/relative,pred)
            reference={**labels[sid], 'math_review_required':labels[sid].get('math_review_required',False) or (cohort=='regression200' and sid in MATH_HOLDS)}
            by_method[method].append(score_case(sid,pred,reference))
    result={'schema_version':3,'status':'COMPLETE_OFFLINE_ASSESSMENT_NOT_QUALIFICATION','cohort':cohort,
            'metrics':{m:summary(rows) for m,rows in by_method.items()},'details':by_method,
            'runtime_seconds':time.perf_counter()-started,'environment':{'python':sys.version.split()[0],'pymupdf':fitz.VersionBind},'new_paid_api_calls':0,'measured_api_spend_usd':0,
            'production_graph_writes':0,'independent_human_validation':'outstanding','automatic_fallback_enabled':False,
            'assessment_files_sha256':assessment_files}
    if 'parallel_structure_v4' in by_method:
        result['fallback_increment']={m:fallback_increment(by_method['parallel_structure_v4'],by_method[m]) for m in ('parallel_mineru_v4','parallel_olmocr_v4') if m in by_method}
    if input_receipt is not None:
        identity=public_preflight(input_receipt)
        result['experiment_sha256']=digest_value(identity)
        result['execution_identity']={k:identity[k] for k in ('runtime','method_hashes','native_mode',
            'native_manifest_sha256','extractor_identity','native_comparison')}
        result['native_manifest_sha256']=write_once(output/'native_manifest.json',{
            'schema_version':1,'mode':identity['native_mode'],'cases':native_records,
            'extractor_identity':identity['extractor_identity'],'experiment_sha256':result['experiment_sha256']})
    return result


def regression(root: Path, output: Path, source_map=None, methods=METHODS, *, replay_saved=True,
               runtime_lock=DEFAULT_RUNTIME_LOCK,native_mode='fresh',native_manifest=None,native_manifest_sha256=None) -> dict:
    output=within(root,output)
    if output==root or output.relative_to(root).parts[0] in {'validation_expanded200','validation_v2','validation_200_10k','sample_comparison_100'}:
        raise ValueError('parallel_v4_outputs_must_not_enter_frozen_cache_directories')
    gate=preflight(root,source_map,methods=methods,replay_saved=replay_saved,runtime_lock=runtime_lock,
                   native_mode=native_mode,native_manifest=native_manifest,native_manifest_sha256=native_manifest_sha256)
    write_once(output/'preflight.json',public_preflight(gate))
    if gate['status']!='PASS':return gate
    write_once(output/'protocol.json',{'cohort':'regression200_already_examined','method_hashes':method_hashes(),
                                      'frozen_at':dt.datetime.now(dt.timezone.utc).isoformat(),'promotion':'source_review_required'})
    cases=gate['cases']
    try:
        verify_preflight_inputs(root,gate,runtime_lock)
        result=run_cases(cases,gate['labels'],output,'regression200',methods,input_receipt=gate,root=root)
    except InputGateError as exc:
        result=blocked(exc.code,**exc.details)
        write_once(output/'results.json',result)
        return result
    # Read-only old prediction path: never call the old evaluate(), which writes
    # historical assessments. Original native lines and caches stay unchanged.
    old_details=[];replay=[]
    if replay_saved:
        for case in cases:
            sid=case['id'];pred=gate['baseline_predictions'][sid]
            adapted={**pred,'proposal':pred.get('eligible_for_jev',False),'eligible_for_jev':False}
            old_details.append(score_case(sid,adapted,gate['labels'][sid]))
            saved=root/'validation_expanded200/assessments/structure_v2'/f'{sid}.json'
            if saved.is_file():
                previous,saved_sha=read_hashed_json(saved)
                if saved_sha!=gate['input_file_hashes'][saved.relative_to(root).as_posix()]:
                    result=blocked('saved_assessment_changed_after_preflight',case_id=sid)
                    write_once(output/'results.json',result)
                    return result
                replay.append({'id':sid,'saved_assessment_sha256':saved_sha,
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
    try:
        verify_preflight_inputs(root,gate,runtime_lock)
    except InputGateError as exc:
        result=blocked(exc.code,**exc.details)
    write_once(output/'results.json',result)
    return result


def frozen_cohort(root: Path, freeze: dict, output: Path, methods=METHODS, *, runtime_lock=DEFAULT_RUNTIME_LOCK) -> dict:
    output=within(root,output)
    try:
        runtime=runtime_receipt(runtime_lock)
        if not methods or len(set(methods))!=len(methods) or set(methods)-set(METHODS):
            raise InputGateError('invalid_or_duplicate_methods')
        verify_freeze(root,freeze)
        gate={'status':'PASS','runtime':runtime,'method_hashes':method_hashes(),
              'input_file_hashes':{},'freeze_sha256':freeze['freeze_sha256']}
        cases=[];native_inputs={}
        import fitz
        for row in freeze['manifest']['pdfs']:
            sid=row['sample_id']
            paths={k:child(root,v) for k,v in row.get('conversion_outputs',{}).items()}
            gate['input_file_hashes'].update({row[k+'_relative']:row[k+'_sha256']
                                             for k in ('source','page','image','native')})
            # Consume the exact frozen native/page bytes, including a recheck
            # between initial verification and use. Never silently re-extract.
            native,native_sha=read_hashed_json(child(root,row['native_relative']))
            if native_sha!=row['native_sha256']:
                raise InputGateError('cohort_native_changed_after_verification',case_id=sid)
            page_path=child(root,row['page_relative'])
            page_bytes=page_path.read_bytes()
            if hashlib.sha256(page_bytes).hexdigest()!=row['page_sha256']:
                raise InputGateError('cohort_page_changed_after_verification',case_id=sid)
            with fitz.open(stream=page_bytes,filetype='pdf') as pdf:
                if len(pdf)!=1:raise InputGateError('expected_single_first_page_extract',case_id=sid)
                size=[pdf[0].rect.width,pdf[0].rect.height]
            validate_lines(native,size)
            required={'grobid'}
            if set(methods)&{'parallel_structure_v4','parallel_grobid_v4'}:
                required.update({'docling','docling_document'})
            required.update(m.removeprefix('parallel_').removesuffix('_v4') for m in methods
                            if m in {'parallel_mineru_v4','parallel_olmocr_v4'})
            input_hashes={}
            for name in required | set(paths):
                if name not in paths or not paths[name].is_file():
                    raise InputGateError('required_cohort_input_missing',case_id=sid,input_kind=name,
                                         action='supply_post_freeze_conversion_cache')
                value,sha=read_hashed_json(paths[name])
                validate_cached_input(name,value,case_id=sid,page_size=size)
                input_hashes[name]=sha
                gate['input_file_hashes'][paths[name].relative_to(root).as_posix()]=sha
            native_inputs[sid]=native_sha
            cases.append({'id':sid,'page_path':page_path,
                          'source_sha256':row['source_sha256'],'page_sha256':row['page_sha256'],'paths':paths,
                          'native_lines':native,'page_size':size,'input_hashes':input_hashes})
        verify_preflight_inputs(root,gate,runtime_lock)
        verify_freeze(root,freeze)
        write_once(output/'preflight.json',gate)
        result=run_cases(cases,freeze['labels'],output,freeze['cohort_kind'],methods)
        verify_preflight_inputs(root,gate,runtime_lock)
        verify_freeze(root,freeze)
        result.update(freeze_sha256=freeze['freeze_sha256'],runtime=runtime,
                      method_hashes=gate['method_hashes'],input_file_hashes=gate['input_file_hashes'],
                      native_mode='frozen_source_reviewed',native_inputs=native_inputs)
    except InputGateError as exc:
        result=blocked(exc.code,**exc.details)
    except (OSError,ValueError,KeyError,TypeError,AttributeError) as exc:
        result=blocked('cohort_input_or_freeze_verification_failed',error_class=type(exc).__name__,
                       action='restore_frozen_inputs_and_use_new_output')
    if not (output/'preflight.json').exists():write_once(output/'preflight.json',result)
    write_once(output/'results.json',result)
    return result


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=['preflight','regression','cohort'])
    parser.add_argument('--data-root')
    parser.add_argument('--source-map')
    parser.add_argument('--freeze')
    parser.add_argument('--runtime-lock',type=Path,default=DEFAULT_RUNTIME_LOCK)
    parser.add_argument('--native-mode',choices=['fresh','replay'],default='fresh')
    parser.add_argument('--native-manifest',help='Pinned saved-native manifest relative to data root')
    parser.add_argument('--native-manifest-sha256',help='Externally recorded manifest SHA-256')
    parser.add_argument('--output',required=True,help='New run path relative to the authorized test-data root')
    parser.add_argument('--methods',nargs='+',choices=METHODS,default=list(METHODS))
    args=parser.parse_args()
    try:
        root=data_root(args.data_root);output=child(root,args.output)
        mapping=read(child(root,args.source_map)) if args.source_map else None
        identity={'runtime_lock':args.runtime_lock,'native_mode':args.native_mode,
                  'native_manifest':child(root,args.native_manifest) if args.native_manifest else None,
                  'native_manifest_sha256':args.native_manifest_sha256}
        if args.stage=='preflight':
            result=preflight(root,mapping,methods=tuple(args.methods),**identity)
            write_once(output/'preflight.json',public_preflight(result))
        elif args.stage=='regression':result=regression(root,output,mapping,tuple(args.methods),**identity)
        else:
            if not args.freeze:parser.error('cohort requires --freeze')
            if args.native_mode!='fresh' or args.native_manifest or args.native_manifest_sha256:
                parser.error('cohort uses its source-reviewed freeze; native replay options apply to regression')
            result=frozen_cohort(root,read(child(root,args.freeze)),output,tuple(args.methods),runtime_lock=args.runtime_lock)
    except InputGateError as exc:
        result=blocked(exc.code,**exc.details)
    except (OSError,ValueError,KeyError,TypeError,AttributeError) as exc:
        result=blocked('invalid_experiment_configuration_or_input',error_class=type(exc).__name__,
                       action='verify_authorized_root_input_files_and_new_output_path')
    print(json.dumps({k:result[k] for k in ('status','reason','action','error_class','case_id','input_kind',
        'differing_fields','runtime_seconds','new_paid_api_calls','measured_api_spend_usd') if k in result},sort_keys=True))
    return 2 if result['status']=='BLOCKED' else 1 if result['status'].startswith('FAILED_') else 0


if __name__=='__main__':raise SystemExit(main())
