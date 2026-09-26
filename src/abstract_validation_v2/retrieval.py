"""Fixed BM25F, SPECTER2 adapters, and a pooled cross-encoder experiment."""
import argparse
import datetime
import hashlib
import json
import time
from .common import OUT, PREVIOUS, REPO, read, write, digest
from .references import freeze


def configuration():
    freeze()
    dest=OUT/'retrieval_protocol.json'
    config={'fields_sha256':digest(OUT/'retrieval_fields.jsonl'),
        'fresh_queries_sha256':digest(OUT/'fresh_queries.json'),
        'old_queries_sha256':digest(PREVIOUS/'retrieval_queries.json'),
        'index_manifest_sha256':digest(PREVIOUS/'index/manifest.json'),
        'page_vectors_sha256':digest(PREVIOUS/'index/page_vectors.npy'),
        'code_sha256':digest(REPO/'src/abstract_validation_v2/retrieval.py'),
        'bm25f':{'weights':{'title':2.,'abstract':1.,'body':.25},'b':.75,'k1':1.2,'tokenizer':'sklearn CountVectorizer English stopwords unigram'},
        'specter2':{'document_adapter':'allenai/specter2','query_adapter':'allenai/specter2_adhoc_query','max_tokens':512,'input':'automatic title + SEP + production-v5 automatic abstract; no reference labels','similarity':'cosine'},
        'reranker':{'model':'cross-encoder/ms-marco-MiniLM-L-6-v2','max_tokens':512,'candidate_pool':'union of top50 BM25F, SPECTER2, Gemini; no target insertion','document':'automatic title + abstract + first-page body','score':'cross-encoder logit'},
        'revisions':read(OUT/'model_revisions.json')}
    if dest.exists():
        saved=read(dest);assert saved['configuration']==config,'Retrieval protocol changed after freeze';return saved
    result={'frozen_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'configuration':config}
    write(dest,result);return result


def inputs():
    ids=read(PREVIOUS/'index/manifest.json')['document_ids']
    with (OUT/'retrieval_fields.jsonl').open(encoding='utf-8') as stream:
        fields={r['id']:r for r in map(json.loads,stream)}
    assert len(fields)==len(ids)==10000
    queries=read(PREVIOUS/'retrieval_queries.json')['queries']+read(OUT/'fresh_queries.json')['queries']
    return ids,[fields[sid] for sid in ids],queries


def gemini():
    from src.abstract_validation.embedding_batch import BatchEmbedder
    client=BatchEmbedder(PREVIOUS/'retrieval_embeddings')
    before=OUT/'gemini_before.json'
    if not before.exists():write(before,client.ledger.totals())
    for q in read(OUT/'fresh_queries.json')['queries']:
        client.embed(q['query_id'],text=q['text'])
        print({'embedded':q['query_id']},flush=True)
    write(OUT/'gemini_after.json',client.ledger.totals())


def specter(device):
    import numpy as np
    import torch
    from transformers import AutoTokenizer
    from adapters import AutoAdapterModel
    torch.set_num_threads(4);torch.manual_seed(2026092502)
    ids,fields,queries=inputs();paths=read(OUT/'model_paths.json')
    started=time.perf_counter()
    tokenizer=AutoTokenizer.from_pretrained(paths['allenai/specter2_base'],local_files_only=True)
    model=AutoAdapterModel.from_pretrained(paths['allenai/specter2_base'],local_files_only=True).eval().to(device)
    model.load_adapter(paths['allenai/specter2'],load_as='paper')
    model.load_adapter(paths['allenai/specter2_adhoc_query'],load_as='query')
    model.to(device)  # Adapter loading creates new parameters on CPU.
    folder=OUT/'specter2';folder.mkdir(exist_ok=True)
    stats={}
    for group,texts,adapter in [('papers',[r['title']+tokenizer.sep_token+r['abstract'] for r in fields],'paper'),('queries',[q['text'] for q in queries],'query')]:
        model.set_active_adapters(adapter);vectors=[];truncated=0;durations=[]
        for start in range(0,len(texts),100):
            batch_texts=texts[start:start+100];file=folder/f'{group}_{start:05}.npz'
            expected=hashlib.sha256(json.dumps(batch_texts).encode()).hexdigest()
            if file.exists():
                data=np.load(file);assert str(data['input_sha256'])==expected
                vectors.append(data['vectors']);truncated+=int(data['truncated']);durations.append(float(data['seconds']));continue
            chunk_started=time.perf_counter();chunk=[];count=0
            for offset in range(0,len(batch_texts),4):
                batch=batch_texts[offset:offset+4]
                count+=sum(len(tokenizer.encode(t,truncation=False))>512 for t in batch)
                inp=tokenizer(batch,padding=True,truncation=True,max_length=512,return_tensors='pt').to(device)
                with torch.inference_mode():vec=model(**inp).last_hidden_state[:,0,:].float()
                vec=torch.nn.functional.normalize(vec,p=2,dim=1)
                chunk.append(vec.cpu().numpy());del inp,vec
            arr=np.concatenate(chunk);seconds=time.perf_counter()-chunk_started
            np.savez(file,vectors=arr,truncated=count,seconds=seconds,input_sha256=expected)
            vectors.append(arr);truncated+=count;durations.append(seconds)
            print({'specter':group,'completed':start+len(batch_texts),'seconds':round(seconds)},flush=True)
        np.save(folder/(group+'.npy'),np.concatenate(vectors))
        stats[group]={'count':len(texts),'truncated_at_512':truncated,'seconds':sum(durations)}
    write(folder/'stats.json',{'groups':stats,'this_pass_seconds':time.perf_counter()-started,'device':device,'document_ids':ids,'query_ids':[q['query_id'] for q in queries]})


def bm25_scores(fields,queries,weights):
    import numpy as np
    from scipy import sparse
    from sklearn.feature_extraction.text import CountVectorizer
    names=list(weights)
    cv=CountVectorizer(stop_words='english',dtype=np.float64)
    cv.fit([' '.join(r[n] for n in names) for r in fields])
    matrices={n:cv.transform([r[n] for r in fields]).tocsr() for n in names}
    union=sum(matrices.values());df=np.asarray((union>0).sum(axis=0)).ravel()
    idf=np.log(1+(len(fields)-df+.5)/(df+.5));weighted=sparse.csr_matrix(union.shape,dtype=np.float64)
    for name,mat in matrices.items():
        lengths=np.asarray(mat.sum(axis=1)).ravel();average=max(float(lengths.mean()),1.)
        norm=(1-.75)+.75*lengths/average
        weighted+=sparse.diags(weights[name]/norm)@mat
    weighted=weighted.tocsr();weighted.data=weighted.data*2.2/(1.2+weighted.data)
    weighted=weighted.multiply(idf)
    qm=cv.transform([q['text'] for q in queries]);qm.data[:]=1
    return (qm@weighted.T).toarray().astype(np.float32)


def rank(device):
    import numpy as np
    import torch
    from src.abstract_validation.evaluate import ranking_metrics
    from sentence_transformers import CrossEncoder
    torch.set_num_threads(4)
    ids,fields,queries=inputs();started=time.perf_counter()
    scores={};timings={}
    for method,weights in [('bm25_page',{'body':1.}),('bm25f',{'title':2.,'abstract':1.,'body':.25})]:
        t=time.perf_counter();scores[method]=bm25_scores(fields,queries,weights);timings[method]=time.perf_counter()-t
    stats=read(OUT/'specter2/stats.json')
    assert stats['document_ids']==ids and stats['query_ids']==[q['query_id'] for q in queries]
    scores['specter2']=np.load(OUT/'specter2/queries.npy')@np.load(OUT/'specter2/papers.npy').T
    vectors=[]
    for q in queries:
        saved=read(PREVIOUS/'retrieval_embeddings'/(q['query_id']+'.json'))
        assert saved['input_sha256']==hashlib.sha256(q['text'].encode()).hexdigest()
        vectors.append(saved['vector'])
    qv=np.asarray(vectors,dtype=np.float32);qv/=np.linalg.norm(qv,axis=1,keepdims=True)
    dv=np.load(PREVIOUS/'index/page_vectors.npy')
    assert dv.shape==(len(ids),768) and np.allclose(np.linalg.norm(dv,axis=1),1,atol=1e-5)
    scores['gemini']=qv@dv.T
    top={name:np.argsort(-value,axis=1,kind='stable')[:,:50] for name,value in scores.items() if name in ['bm25f','specter2','gemini']}
    # Unselected documents score below every selected document; no hidden full-index ranking.
    reranked=np.full((len(queries),len(ids)),-1e6,dtype=np.float32);receipts=[]
    model=CrossEncoder(read(OUT/'model_paths.json')['cross-encoder/ms-marco-MiniLM-L-6-v2'],max_length=512,device=device,local_files_only=True)
    for i,q in enumerate(queries):
        indices=sorted(set(int(j) for ranks in top.values() for j in ranks[i]))
        pairs=[(q['text'],fields[j]['title']+'\n'+fields[j]['abstract']+'\n'+fields[j]['body']) for j in indices]
        cache=OUT/'rerank'/(q['query_id']+'.json');expected=hashlib.sha256(json.dumps(pairs).encode()).hexdigest()
        if cache.exists():
            receipt=read(cache);assert receipt['input_sha256']==expected
            logits=np.asarray(receipt['scores'])
        else:
            t=time.perf_counter();logits=model.predict(pairs,batch_size=8,show_progress_bar=False,activation_fn=torch.nn.Identity())
            receipt={'input_sha256':expected,'indices':indices,'scores':logits.tolist(),'seconds':time.perf_counter()-t}
            write(cache,receipt)
        reranked[i,indices]=logits
        receipts.append({'query_id':q['query_id'],'candidate_count':len(indices),'target_in_pool':ids.index(q['target_id']) in indices,'seconds':receipt['seconds']})
        if (i+1)%10==0:print({'reranked':i+1},flush=True)
    scores['pooled_reranker']=reranked
    metrics={}
    for group,selection in [('regression100',list(range(100))),('fresh30',list(range(100,130)))]:
        metrics[group]={name:ranking_metrics(value[selection],ids,[queries[i] for i in selection]) for name,value in scores.items()}
        # Known-item metrics must never award a hit to an unscored document by arbitrary tie order.
        assert all(r['target_in_pool'] for r in [receipts[i] for i in selection]),'Target missing from rerank shortlist; implement explicit missing-rank metrics'
    write(OUT/'retrieval_metrics.json',metrics)
    write(OUT/'retrieval_runtime.json',{'lexical_seconds':timings,'reranking':receipts,'this_pass_seconds':time.perf_counter()-started,'device':device})
    for group,methods in metrics.items():
        print(group,{n:{k:v for k,v in m.items() if k!='details'} for n,m in methods.items()},flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['freeze','gemini','specter','rank']);p.add_argument('--device',default='cuda');a=p.parse_args()
    configuration()
    if a.stage=='gemini':gemini()
    if a.stage=='specter':specter(a.device)
    if a.stage=='rank':rank(a.device)
