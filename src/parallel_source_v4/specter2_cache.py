"""Produce target-independent, locally pinned SPECTER2 rankings for retrieval.

The output is a discovery cache, never graph evidence or an admission decision.
Every vector batch is checkpointed with its exact text-input and protocol hash.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import re
import sys
from io import BytesIO
from pathlib import Path

from trace_gc.pdf_source_parallel_v4 import digest_value
from .common import REPO, child, data_root, digest, write_once
from .retrieval import normalize_queries

REVISION = re.compile(r'[0-9a-f]{40}\Z')
DEPENDENCIES = ('torch','transformers','adapters','numpy','tokenizers','safetensors')


def read_hashed_json(path: Path):
    raw=path.read_bytes()
    def unique_pairs(pairs):
        value={}
        for key,item in pairs:
            if key in value:raise ValueError('duplicate_key_in_specter2_input')
            value[key]=item
        return value
    def reject_constant(value):
        raise ValueError('nonfinite_specter2_input:'+value)
    return json.loads(raw.decode('utf-8'),object_pairs_hook=unique_pairs,
                      parse_constant=reject_constant),hashlib.sha256(raw).hexdigest()


def verify_models(root: Path, manifest: dict) -> dict[str,Path]:
    if manifest.get('schema_version')!='local-specter2-model-v1' or set(manifest.get('models',{}))!={'base','paper','query'}:
        raise ValueError('specter2_requires_explicit_three_model_manifest')
    if (manifest.get('max_tokens')!=512 or
            manifest.get('document_template')!='title + tokenizer.sep_token + abstract' or
            manifest.get('query_template')!='query_text' or
            manifest.get('pooling')!='last_hidden_state_cls_l2_normalized' or
            manifest.get('similarity')!='cosine'):
        raise ValueError('specter2_model_policy_mismatch')
    paths={}
    for kind,row in manifest['models'].items():
        if not isinstance(row,dict) or not REVISION.fullmatch(row.get('model_revision','')) or row.get('directory')!=kind:
            raise ValueError('specter2_model_revision_or_directory_invalid')
        folder=child(root,kind)
        if not folder.is_dir() or folder.is_symlink():raise ValueError('specter2_local_model_directory_required')
        actual={p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file()}
        if actual!=set(row.get('files',{})) or any(p.is_symlink() for p in folder.rglob('*')):
            raise ValueError('specter2_model_manifest_must_cover_entire_snapshot')
        if any(Path(name).suffix.lower() in {'.py','.pkl','.pickle','.pt','.pth'} for name in actual):
            raise ValueError('specter2_model_executable_or_unexpected_weights')
        for relative,expected in row['files'].items():
            if not isinstance(expected,str) or not re.fullmatch(r'[0-9a-f]{64}',expected) or digest(child(folder,relative))!=expected:
                raise ValueError('specter2_model_file_hash_mismatch')
        paths[kind]=folder
    return paths


def produce(root: Path, fields_file: Path, queries_file: Path, model_root: Path,
            model_manifest_file: Path, output: Path, *, device='cpu', batch_size=16, top_k=50) -> dict:
    if batch_size<=0 or top_k<=0:raise ValueError('positive_batch_and_depth_required')
    import numpy as np
    import torch
    from adapters import AutoAdapterModel
    from transformers import AutoTokenizer
    fields_record,fields_file_sha=read_hashed_json(fields_file)
    query_record,query_file_sha=read_hashed_json(queries_file)
    model_manifest,model_manifest_sha=read_hashed_json(model_manifest_file)
    fields=fields_record['fields'] if isinstance(fields_record,dict) else fields_record
    if isinstance(query_record,dict) and 'queries' not in query_record:
        raise ValueError('specter2_requires_explicit_query_identifiers')
    queries=normalize_queries(query_record)
    if not isinstance(fields,list) or not fields or not queries:
        raise ValueError('specter2_requires_nonempty_fields_and_queries')
    ids=[row['id'] for row in fields]
    qids=[row['id'] for row in queries]
    if len(ids)!=len(set(ids)) or len(qids)!=len(set(qids)):
        raise ValueError('duplicate_specter2_document_or_query_id')
    if any(not isinstance(row.get('title'),str) or not isinstance(row.get('abstract'),str) for row in fields):
        raise ValueError('specter2_requires_text_fields')
    no_dense_input=[i for i,row in enumerate(fields) if not (row['title'].strip() or row['abstract'].strip())]
    if len(no_dense_input)==len(fields):
        raise ValueError('specter2_requires_at_least_one_title_or_abstract')
    if device.startswith('cuda') and not torch.cuda.is_available():
        raise ValueError('requested_cuda_device_unavailable')
    paths=verify_models(model_root,model_manifest)
    packages={name:importlib.metadata.version(name) for name in DEPENDENCIES}
    ranking_inputs=[{'id':q['id'],'query':q['query']} for q in queries]
    protocol={'schema_version':'specter2-vector-protocol-v1','fields_file_sha256':fields_file_sha,
              'fields_sha256':digest_value(fields),
              'ranking_inputs_sha256':digest_value(ranking_inputs),
              'document_ids_sha256':digest_value(ids),'query_ids_sha256':digest_value(qids),
              'model_manifest_sha256':model_manifest_sha,'model_revisions':{k:v['model_revision'] for k,v in model_manifest['models'].items()},
              'model_file_hashes':{k:v['files'] for k,v in model_manifest['models'].items()},
              'code_sha256':digest(REPO/'src/parallel_source_v4/specter2_cache.py'),
              'retrieval_code_sha256':digest(REPO/'src/parallel_source_v4/retrieval.py'),
              'runtime':{'python':sys.version.split()[0],**packages},'device':device,
              'batch_size':batch_size,'top_k':top_k,'max_tokens':512,
              'empty_title_and_abstract_policy':'retain_document_mask_from_dense_rankings',
              'document_template':model_manifest['document_template'],
              'query_template':model_manifest['query_template'],
              'target_ids_used_for_ranking':False}
    output=Path(output)
    if output.exists():
        saved,_=read_hashed_json(output/'protocol.json')
        if saved!=protocol:raise ValueError('specter2_resume_protocol_mismatch')
    else:
        output.mkdir(parents=True)
        write_once(output/'protocol.json',protocol)
    os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
    os.environ['HF_HUB_DISABLE_TELEMETRY']='1';os.environ['TORCH_FORCE_WEIGHTS_ONLY_LOAD']='1'
    torch.set_num_threads(4);torch.manual_seed(20260928)
    tokenizer=AutoTokenizer.from_pretrained(str(paths['base']),local_files_only=True,trust_remote_code=False)
    model=AutoAdapterModel.from_pretrained(str(paths['base']),local_files_only=True,trust_remote_code=False).eval().to(device)
    model.load_adapter(str(paths['paper']),load_as='paper')
    model.load_adapter(str(paths['query']),load_as='query')
    model.to(device).eval()
    if any(module.training for module in model.modules()):
        raise ValueError('specter2_model_must_be_in_eval_mode')
    texts={'papers':[row['title']+tokenizer.sep_token+row['abstract'] for row in fields],
           'queries':[q['query'] for q in queries]}
    batches={};vectors={}
    for group,adapter in (('papers','paper'),('queries','query')):
        model.set_active_adapters(adapter)
        if model.active_adapters is None or list(model.active_adapters.flatten())!=[adapter]:
            raise ValueError('specter2_expected_adapter_not_active:'+adapter)
        parts=[];receipts=[]
        for start in range(0,len(texts[group]),batch_size):
            batch=texts[group][start:start+batch_size]
            input_sha=digest_value(batch)
            path=output/group/f'{start:05d}.npz'
            receipt_path=output/group/f'{start:05d}.receipt.json'
            if path.is_file():
                if not receipt_path.is_file():
                    raise ValueError('specter2_checkpoint_missing_immutable_receipt')
                payload=path.read_bytes()
                checkpoint_sha=hashlib.sha256(payload).hexdigest()
                with np.load(BytesIO(payload),allow_pickle=False) as saved:
                    if str(saved['input_sha256'])!=input_sha or str(saved['protocol_sha256'])!=digest_value(protocol):
                        raise ValueError('specter2_checkpoint_input_or_protocol_mismatch')
                    array=saved['vectors']
                    truncated=int(saved['truncated'])
                receipt,receipt_sha=read_hashed_json(receipt_path)
                expected={'schema_version':'specter2-batch-v1','start':start,'count':len(batch),
                          'input_sha256':input_sha,'protocol_sha256':digest_value(protocol),
                          'checkpoint_sha256':checkpoint_sha,'truncated':truncated}
                if receipt!=expected:
                    raise ValueError('specter2_checkpoint_immutable_receipt_mismatch')
            else:
                if receipt_path.exists():
                    raise ValueError('specter2_checkpoint_missing_for_immutable_receipt')
                token_lengths=[len(tokenizer.encode(t,truncation=False)) for t in batch]
                truncated=sum(n>512 for n in token_lengths)
                tokens=tokenizer(batch,padding=True,truncation=True,max_length=512,return_tensors='pt').to(device)
                with torch.inference_mode():
                    value=model(**tokens).last_hidden_state[:,0,:].float()
                    value=torch.nn.functional.normalize(value,p=2,dim=1)
                array=value.cpu().numpy().astype(np.float32)
                path.parent.mkdir(parents=True,exist_ok=True)
                temp=path.with_name(path.stem+'.partial.npz')
                buffer=BytesIO()
                np.savez(buffer,vectors=array,input_sha256=input_sha,protocol_sha256=digest_value(protocol),truncated=truncated)
                payload=buffer.getvalue()
                checkpoint_sha=hashlib.sha256(payload).hexdigest()
                temp.write_bytes(payload)
                os.replace(temp,path)
                receipt={'schema_version':'specter2-batch-v1','start':start,'count':len(batch),
                         'input_sha256':input_sha,'protocol_sha256':digest_value(protocol),
                         'checkpoint_sha256':checkpoint_sha,'truncated':truncated}
                receipt_sha=write_once(receipt_path,receipt)
            if array.shape!=(len(batch),768) or not np.isfinite(array).all() or not np.allclose(np.linalg.norm(array,axis=1),1,atol=1e-5):
                raise ValueError('specter2_invalid_vector_batch')
            parts.append(array)
            receipts.append({'start':start,'count':len(batch),'input_sha256':input_sha,
                             'checkpoint_sha256':checkpoint_sha,'receipt_sha256':receipt_sha,
                             'truncated':truncated})
            print(json.dumps({'group':group,'completed':start+len(batch),'total':len(texts[group])}),flush=True)
        vectors[group]=np.concatenate(parts)
        batches[group]=receipts
    scores=vectors['queries']@vectors['papers'].T
    scores[:,no_dense_input]=-np.inf
    order_ids=np.asarray(ids)
    depth=min(top_k,len(ids)-len(no_dense_input))
    rankings={qid:[ids[int(j)] for j in np.lexsort((order_ids,-scores[i]))[:depth]] for i,qid in enumerate(qids)}
    if (digest(fields_file)!=fields_file_sha or digest(queries_file)!=query_file_sha or
            digest(model_manifest_file)!=model_manifest_sha):
        raise ValueError('specter2_inputs_changed_during_run')
    for group,receipts in batches.items():
        for receipt in receipts:
            if digest(output/group/f"{receipt['start']:05d}.npz")!=receipt['checkpoint_sha256']:
                raise ValueError('specter2_checkpoint_changed_during_run')
            if digest(output/group/f"{receipt['start']:05d}.receipt.json")!=receipt['receipt_sha256']:
                raise ValueError('specter2_checkpoint_receipt_changed_during_run')
    verify_models(model_root,model_manifest)
    if (digest(REPO/'src/parallel_source_v4/specter2_cache.py')!=protocol['code_sha256'] or
            digest(REPO/'src/parallel_source_v4/retrieval.py')!=protocol['retrieval_code_sha256'] or
            {name:importlib.metadata.version(name) for name in DEPENDENCIES}!=packages):
        raise ValueError('specter2_code_or_runtime_changed_during_run')
    result={'binding_version':'ranking-inputs-v2','channel':'specter2',
            'fields_sha256':protocol['fields_sha256'],'ranking_inputs_sha256':protocol['ranking_inputs_sha256'],
            'model_revision':model_manifest['models']['base']['model_revision'],
            'model_revisions':protocol['model_revisions'],'model_manifest_sha256':model_manifest_sha,
            'protocol_sha256':digest_value(protocol),'document_ids_sha256':protocol['document_ids_sha256'],
            'query_ids_sha256':protocol['query_ids_sha256'],'rankings':rankings,
            'ranking_sha256':digest_value(rankings),'vector_batches':batches,
            'document_count':len(ids),'query_count':len(qids),'top_k':top_k,
            'dense_input_absent_ids':[ids[i] for i in no_dense_input],
            'dense_input_absent_count':len(no_dense_input),
            'new_paid_api_calls':0,'production_graph_writes':0,'target_ids_used_for_ranking':False}
    if (output/'dense_cache.json').is_file():
        existing,_=read_hashed_json(output/'dense_cache.json')
        if existing!=result:raise ValueError('specter2_completed_cache_is_not_reproducible')
        return existing
    write_once(output/'dense_cache.json',result)
    return result


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('data-root','fields','queries','model-root','model-manifest','output'):
        p.add_argument('--'+name,required=True)
    p.add_argument('--device',default='cpu');p.add_argument('--batch-size',type=int,default=16)
    p.add_argument('--top-k',type=int,default=50)
    args=p.parse_args();root=data_root(args.data_root)
    result=produce(root,child(root,args.fields),child(root,args.queries),child(root,args.model_root),
                   child(root,args.model_manifest),child(root,args.output),device=args.device,
                   batch_size=args.batch_size,top_k=args.top_k)
    print(json.dumps({'status':'LOCAL_DENSE_CACHE_READY_NOT_RETRIEVAL_QUALITY',
                      'documents':result['document_count'],'queries':result['query_count'],
                      'ranking_sha256':result['ranking_sha256']}))
    return 0


if __name__=='__main__':raise SystemExit(main())
