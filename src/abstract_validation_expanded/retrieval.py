"""Local-only known-item retrieval; no cloud client or paid candidate pool."""
import hashlib
import json
import math
import time
from .common import INDEX, OLD, OUT, digest, read, verify_protocol, write
from .references import freeze
from src.abstract_validation_v2.retrieval import bm25_scores
from src.abstract_validation.evaluate import ranking_metrics


def inputs():
    ids = read(INDEX / 'index/manifest.json')['document_ids']
    with (OLD / 'retrieval_fields.jsonl').open(encoding='utf-8') as stream:
        by_id = {r['id']: r for r in map(json.loads, stream)}
    queries = read(OUT / 'queries.json')['queries']
    assert len(ids) == len(by_id) == 10000 and len(queries) == 60
    return ids, [by_id[sid] for sid in ids], queries


def configuration():
    verify_protocol(); freeze()
    config = {'method': 'Same local BM25 and SPECTER2 settings as v2; top50 BM25F plus top50 SPECTER2 union reranked without target insertion.',
              'paid_api_calls': 0, 'device': 'cpu', 'threads': 4,
              'models': read(OLD / 'model_revisions.json'),
              'runner_sha256': digest(__file__), 'old_runner_sha256': verify_protocol()['method_hashes']['src/abstract_validation_v2/retrieval.py'],
              'inputs': {str(p.relative_to(OUT.parent)): digest(p) for p in [OUT/'queries.json', OLD/'retrieval_fields.jsonl', OLD/'specter2/papers.npy', OLD/'specter2/queries.npy', INDEX/'index/manifest.json']}}
    dest = OUT / 'retrieval_protocol.json'
    if dest.exists():
        assert read(dest) == config, 'Frozen retrieval configuration changed'
    else:
        write(dest, config)
    return config


def specter_queries(queries):
    import numpy as np
    import torch
    from transformers import AutoTokenizer
    from adapters import AutoAdapterModel
    dest = OUT / 'specter2/queries.npy'
    if dest.exists():
        assert read(OUT / 'specter2/stats.json')['query_ids'] == [q['query_id'] for q in queries]
        return np.load(dest)
    paths = read(OLD / 'model_paths.json'); started = time.perf_counter()
    torch.set_num_threads(4); torch.manual_seed(2026092502)
    tokenizer = AutoTokenizer.from_pretrained(paths['allenai/specter2_base'], local_files_only=True)
    model = AutoAdapterModel.from_pretrained(paths['allenai/specter2_base'], local_files_only=True).eval()
    model.load_adapter(paths['allenai/specter2_adhoc_query'], load_as='query'); model.set_active_adapters('query')
    old_stats = read(OLD / 'specter2/stats.json')
    old_q = np.load(OLD / 'specter2/queries.npy')
    vectors = [old_q[[old_stats['query_ids'].index(q['query_id']) for q in queries[:30]]]]
    truncated = 0
    for start in range(30,60,4):
        texts = [q['text'] for q in queries[start:start+4]]
        truncated += sum(len(tokenizer.encode(t, truncation=False)) > 512 for t in texts)
        inp = tokenizer(texts, padding=True, truncation=True, max_length=512, return_tensors='pt')
        with torch.inference_mode():
            vec = torch.nn.functional.normalize(model(**inp).last_hidden_state[:,0,:].float(),p=2,dim=1)
        vectors.append(vec.numpy())
    arr = np.concatenate(vectors)
    dest.parent.mkdir(exist_ok=True); np.save(dest,arr)
    write(OUT/'specter2/stats.json', {'query_ids':[q['query_id'] for q in queries], 'reused_queries':30, 'new_queries':30,
                                    'new_query_truncated_512':truncated,'seconds':time.perf_counter()-started,'device':'cpu'})
    print({'specter_queries':60,'new':30,'seconds':round(time.perf_counter()-started)},flush=True)
    return arr


def shortlist_metrics(scores, ids, queries, pools):
    """Absent shortlist targets have no rank and zero reciprocal-rank credit."""
    import numpy as np
    details=[]
    for i,q in enumerate(queries):
        order=sorted(pools[i],key=lambda j:(-float(scores[i,j]),j))
        target=ids.index(q['target_id'])
        rank=order.index(target)+1 if target in order else None
        details.append({**q,'rank':rank,'top10':[{'id':ids[j],'score':float(scores[i,j])} for j in order[:10]]})
    n=len(details)
    return {'queries':n,'documents':len(ids),
            **{f'recall_at_{k}':sum(d['rank'] is not None and d['rank']<=k for d in details)/n for k in [1,3,10]},
            'mrr':sum(1/d['rank'] if d['rank'] else 0 for d in details)/n,
            'ndcg_at_10':sum(1/math.log2(d['rank']+1) if d['rank'] and d['rank']<=10 else 0 for d in details)/n,
            'candidate_recall':sum(d['rank'] is not None for d in details)/n,'details':details}


def main():
    configuration()
    import numpy as np
    import torch
    from sentence_transformers import CrossEncoder
    torch.set_num_threads(4)
    ids,fields,queries=inputs(); started=time.perf_counter()
    qv=specter_queries(queries)
    assert read(OLD/'specter2/stats.json')['document_ids']==ids
    scores={'specter2':qv@np.load(OLD/'specter2/papers.npy').T}; timings={}
    for name,weights in [('bm25_page',{'body':1.}),('bm25f',{'title':2.,'abstract':1.,'body':.25})]:
        t=time.perf_counter();scores[name]=bm25_scores(fields,queries,weights);timings[name]=time.perf_counter()-t
    top={name:np.argsort(-scores[name],axis=1,kind='stable')[:,:50] for name in ['bm25f','specter2']}
    reranked=np.full((60,10000),-1e6,dtype=np.float32);receipts=[];pools=[]
    model=CrossEncoder(read(OLD/'model_paths.json')['cross-encoder/ms-marco-MiniLM-L-6-v2'],max_length=512,device='cpu',local_files_only=True)
    for i,q in enumerate(queries):
        indices=sorted(set(int(j) for value in top.values() for j in value[i])); pools.append(indices)
        pairs=[(q['text'],fields[j]['title']+'\n'+fields[j]['abstract']+'\n'+fields[j]['body']) for j in indices]
        expected=hashlib.sha256(json.dumps(pairs).encode()).hexdigest(); dest=OUT/'rerank'/(q['query_id']+'.json')
        if dest.exists():
            receipt=read(dest);assert receipt['input_sha256']==expected and receipt['indices']==indices
            logits=np.asarray(receipt['scores'])
        else:
            t=time.perf_counter();logits=model.predict(pairs,batch_size=8,show_progress_bar=False,activation_fn=torch.nn.Identity())
            receipt={'input_sha256':expected,'indices':indices,'scores':logits.tolist(),'seconds':time.perf_counter()-t}
            write(dest,receipt)
        reranked[i,indices]=logits
        receipts.append({'query_id':q['query_id'],'candidate_count':len(indices),'target_in_pool':ids.index(q['target_id']) in indices,'seconds':receipt['seconds']})
        if (i+1)%10==0:print({'reranked':i+1,'of':60},flush=True)
    metrics={}
    for group,selection in [('prior30',list(range(30))),('added30',list(range(30,60))),('combined60',list(range(60)))]:
        qs=[queries[i] for i in selection]
        metrics[group]={name:ranking_metrics(value[selection],ids,qs) for name,value in scores.items()}
        metrics[group]['local_pooled_reranker']=shortlist_metrics(reranked[selection],ids,qs,[pools[i] for i in selection])
    write(OUT/'retrieval_metrics.json',metrics)
    write(OUT/'retrieval_runtime.json',{'lexical_seconds':timings,'reranking':receipts,'this_pass_seconds':time.perf_counter()-started,'device':'cpu','new_api_calls':0})
    for group, methods in metrics.items():
        print(group,{n:{k:v for k,v in m.items() if k!='details'} for n,m in methods.items()},flush=True)


if __name__=='__main__':
    main()
