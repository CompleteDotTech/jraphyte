"""Read-only evidence checks; full verification requires all 200 model attempts."""
import argparse
import datetime
import hashlib
import math
import sqlite3
from collections import Counter
from .common import DATA, INDEX, OLD, OUT, REPO, cache, digest, folder, read, rows, verify_protocol, write
from .references import freeze
from src.abstract_validation.common import reference_blocks
from src.abstract_validation.evaluate import compare
from src.abstract_validation_v2.extraction import summary


def ledger_snapshot():
    path = INDEX / 'retrieval_embeddings/calls.sqlite'
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as db:
        total = db.execute('SELECT count(*),max(id),coalesce(sum(estimated_usd),0) FROM calls').fetchone()
    return dict(zip(['calls','max_id','estimated_usd'],total))


def sources():
    import pymupdf
    verify_protocol(); freeze()
    manifest=read(OUT/'manifest.json'); data=rows(); labels=read(OUT/'labels.json')
    assert len(data)==len({r['work_id'] for r in data})==200
    assert not ({r['work_id'] for r in data[100:]} & set(manifest['excluded_new_work_ids']))
    assert data[:100]==read(OLD/'holdout_manifest.json')['pdfs']
    assert {sid:labels[sid] for sid in read(OLD/'labels.json')}==read(OLD/'labels.json')
    source_hashes=read(OUT/'source_hashes.json')
    for row in data:
        sid=row['sample_id']; page=folder(sid); receipt=read(page/'receipt.json')
        assert digest(row['source_path'])==labels[sid]['source_sha256']==receipt['source_sha256'],sid
        assert digest(page/'page.pdf')==labels[sid]['page_sha256'],sid
        assert digest(page/'page.png')==source_hashes[sid]['image_sha256'],sid
        assert digest(page/'reference_blocks.json')==source_hashes[sid]['reference_blocks_sha256'],sid
        with pymupdf.open(row['source_path']) as pdf:
            assert reference_blocks(pdf[0])==read(page/'reference_blocks.json'),sid
        with pymupdf.open(page/'page.pdf') as pdf:
            assert len(pdf)==1,sid
    assert digest(DATA/'run_jev_corpus.py')==read(OUT/'baselines/environment.json')['worker_sha256']
    after=ledger_snapshot();before=read(OUT/'api_ledger_before.json')
    assert after==before,'Paid API ledger changed; investigate before claiming zero spend'
    write(OUT/'api_ledger_after.json',after)
    result={'sources':200,'new_works':100,'prior_references_unchanged':True,'native_blocks_reproduced':200,
            'frozen_methods_unchanged':True,'worker_source_unchanged':True,'new_google_api_calls':after['calls']-before['calls'],
            'new_google_estimated_usd':after['estimated_usd']-before['estimated_usd']}
    write(OUT/'source_verification.json',result)
    return result


def full():
    result=sources()
    from .retrieval import configuration,inputs,shortlist_metrics
    configuration()
    labels=read(OUT/'labels.json'); metrics=read(OUT/'extraction_metrics.json')
    visual=read(REPO/'review/first_page_expanded200/visual_audit.json')
    for case in visual['cases']:
        assert digest(folder(case['id'])/'page.png')==case['source_image_sha256']
        assert digest(OUT/'assessments/structure_v2'/(case['id']+'.json'))==case['assessment_sha256']
    assert set(metrics)=={'current','geometry_v1','grobid','structure_v2','mineru','olmocr'}
    for method,groups in metrics.items():
        for group,stat in groups.items():
            for d in stat['details']:
                pred=read(OUT/'assessments'/method/(d['id']+'.json'))
                assert all(d[k]==v for k,v in compare(pred['text'],labels[d['id']]['text']).items()),(method,d['id'])
                assert d['eligible']==pred['eligible_for_jev']
            expected=summary(stat['details'])
            assert all(stat[k]==v for k,v in expected.items()),(method,group)
        assert groups['combined200']['pages']==200
    parser_states={}
    for method in ['mineru','olmocr']:
        states=[]
        for row in rows():
            sid=row['sample_id']; raw=read(cache(method,sid))
            assert raw['sample_id']==sid and raw['page_sha256']==digest(folder(sid)/'page.pdf'),sid
            assert raw['status'] in ['success','error','truncated'],sid
            if raw['status']!='success':
                assert not read(OUT/'assessments'/method/(sid+'.json'))['eligible_for_jev'],(method,sid)
            states.append(raw['status'])
        parser_states[method]=dict(Counter(states))
    ids,fields,queries=inputs()
    retrieved=read(OUT/'retrieval_metrics.json')
    for group,count in [('prior30',30),('added30',30),('combined60',60)]:
        for name,stat in retrieved[group].items():
            assert len(stat['details'])==stat['queries']==count
            ranks=[d['rank'] for d in stat['details']]
            for k in [1,3,10]:
                assert stat[f'recall_at_{k}']==sum(r is not None and r<=k for r in ranks)/count
            assert math.isclose(stat['mrr'],sum(1/r if r else 0 for r in ranks)/count,abs_tol=1e-12)
            for d in stat['details']:
                for rank,hit in enumerate(d['top10'],1):
                    if hit['id']==d['target_id']:assert rank==d['rank']
    for q in queries:
        receipt=read(OUT/'rerank'/(q['query_id']+'.json'))
        assert len(receipt['indices'])==len(receipt['scores']) and all(math.isfinite(v) for v in receipt['scores'])
        pairs=[(q['text'],fields[j]['title']+'\n'+fields[j]['abstract']+'\n'+fields[j]['body']) for j in receipt['indices']]
        import json
        assert hashlib.sha256(json.dumps(pairs).encode()).hexdigest()==receipt['input_sha256']
    result.update(status='pass',verified_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  extraction_methods=6,paired_pages_per_method=200,parser_states=parser_states,
                  retrieval_queries=60,retrieval_documents=10000,rerank_receipts_verified=60,
                  visual_failure_receipts_verified=len(visual['cases']),
                  independent_human_review='outstanding',automatic_production_promotion=False)
    result['benchmark_runner_hashes']={p.name:digest(p) for p in (REPO/'src/abstract_validation_expanded').glob('*.py')}
    write(OUT/'verification.json',result)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--sources-only',action='store_true')
    print(sources() if p.parse_args().sources_only else full())
