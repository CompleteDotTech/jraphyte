"""Publish aggregate local receipts without copying paper text into the repo."""
import datetime
import json
import math
import re
import statistics
from .common import OUT, PREVIOUS, REPO, digest, read, write
from .extraction import summary,frozen
from .retrieval import configuration


def compact(value):
    return {k:v for k,v in value.items() if k!='details'}


def interval(success,total):
    if not total:return None
    z=1.959963984540054;p=success/total;den=1+z*z/total
    center=(p+z*z/(2*total))/den
    radius=z*math.sqrt(p*(1-p)/total+z*z/(4*total*total))/den
    return [center-radius,center+radius]


def main():
    frozen();configuration()
    pilot=read(OUT/'fallback_manifest.json')['ids']
    assert len(pilot)==40
    log=(OUT/'unit_tests.log').read_text(encoding='utf-8')
    assert re.search(r'^OK(?: \(skipped=\d+\))?$',log,re.M),'Unit suite did not pass'
    tests=int(re.search(r'Ran (\d+) tests',log)[1])
    skipped=int(re.search(r'OK \(skipped=(\d+)\)',log)[1]) if 'OK (skipped=' in log else 0
    before,after=read(OUT/'gemini_before.json'),read(OUT/'gemini_after.json')
    with (OUT/'retrieval_fields.jsonl').open(encoding='utf-8') as stream:
        fields=list(map(json.loads,stream))
    operational={'retrieval_fields':{'papers':len(fields),'empty_title':sum(not r['title'] for r in fields),
        'empty_abstract':sum(not r['abstract'] for r in fields),'empty_native_page':sum(not r['body'] for r in fields),
        'errors':sum(bool(r.get('error')) for r in fields)},
        'cost':{'additional_estimated_usd':after['estimated_usd']-before['estimated_usd'],
            'additional_reserved_usd':after['reserved_usd']-before['reserved_usd'],'additional_calls':after['calls']-before['calls']}}
    for method,prefix,cohort in [('grobid','h','regression'),('grobid','f','fresh'),('docling','f','fresh')]:
        values=[read(p)['seconds'] for p in (OUT/method).glob(prefix+'*.json') if not p.name.endswith('.document.json')]
        operational[method+'_'+cohort]={'pages':len(values),'total_seconds':sum(values),'median_seconds':statistics.median(values)}
    write(OUT/'operational_summary.json',operational)
    result={'created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'scope':{'regression_pages':200,'fresh_pages':100,'fresh_strata':'50 prior ok and 50 prior no_abstract; diagnostic sample, not corpus prevalence',
            'fallback_pages':40,'fallback_sampling':'20 selected old failures plus 20 seeded random fresh pages; 21 complete abstracts, 19 absent, zero partial abstracts',
            'retrieval_documents':10000,'old_queries':100,'fresh_queries':30},
        'review':read(OUT/'reference_freeze.json'),
        'limitations':['Assistant-reviewed references; independent human validation outstanding.',
            'Source pages reviewed before opening fresh predictions, but regression tuning followed source review; not independent blind evaluation.',
            'Canonical character agreement ignores punctuation and is not mathematical fidelity validation.',
            'Known-item retrieval has one labeled target; other relevant papers were not exhaustively judged.',
            'Shared workstation timings are observations, not controlled throughput measurements.',
            'Fallback pilot has only six fresh complete abstracts and no partial abstracts; cannot establish partial-page safety.',
            'olmOCR NF4 with direct Transformers decoding differs from upstream BF16/FP8 pipeline and lacks retry/rotation stages.'],
        'extraction':{},'paired':{},'fallback_increment':{},'retrieval':{},
        'runtime':operational,'specter2':read(OUT/'specter2/stats.json')['groups'],
        'model_revisions':read(OUT/'model_revisions.json'),
        'unit_tests':{'run':tests,'passed':tests-skipped,'skipped':skipped,'log_sha256':digest(OUT/'unit_tests.log')},
        'production':{'corpus_worker_changed':False,'jev_calls':0,'graph_writes':0,'automatic_promotion':False}}
    result['verification']=read(OUT/'verification.json')
    assert result['verification']['status']=='pass'
    result['visual_audit']=read(OUT/'visual_audit.json')
    result['limitations'].append('Visual checks confirm formula errors can pass the character metric; known unsafe native transcriptions are held separately from frozen scores.')
    result['review_gate_audit']=compact(read(OUT/'review_gate_audit.json'))
    result['review_gate_audit'].pop('rows',None)
    for cohort in ['regression','fresh']:
        raw=read(OUT/('extraction_'+cohort+'.json'))
        result['extraction'][cohort]={name:compact(value) for name,value in raw.items() if name not in ['mineru','olmocr']}
        paired={name:summary([d for d in value['details'] if d['id'] in pilot]) for name,value in raw.items()}
        assert {'mineru','olmocr'}.issubset(paired)
        expected=20
        assert all(m['pages']==expected for m in paired.values())
        result['paired'][cohort]={name:compact(m) for name,m in paired.items()}
        base={d['id']:d for d in paired['structure_v2']['details']}
        result['fallback_increment'][cohort]={}
        for method in ['mineru','olmocr']:
            extra=[d for d in paired[method]['details'] if not base[d['id']]['eligible'] and d['eligible']]
            good=[d['id'] for d in extra if d['gold']=='complete' and d['text_match_98']]
            result['fallback_increment'][cohort][method]={'new_correct_proposals':good,'new_wrong_proposals':[d['id'] for d in extra if d['id'] not in good]}
    for method in ['mineru','olmocr']:
        runs=[read(OUT/method/(sid+'.json')) for sid in pilot]
        assert all(r['status'] in ['success','error','truncated'] for r in runs)
        times=[r['seconds'] for r in runs]
        result['runtime'][method]={'pages':len(runs),'success':sum(r['status']=='success' for r in runs),
            'errors':sum(r['status']=='error' for r in runs),'truncated':sum(r['status']=='truncated' for r in runs),
            'total_seconds':sum(times),'median_seconds':statistics.median(times),'configuration':read(OUT/method/'configuration.json')}
    for cohort,methods in read(OUT/'retrieval_metrics.json').items():
        result['retrieval'][cohort]={name:compact(m) for name,m in methods.items()}
    r=read(OUT/'retrieval_runtime.json')
    result['runtime']['retrieval']={'lexical_seconds':r['lexical_seconds'],'rerank_seconds':sum(x['seconds'] for x in r['reranking']),
        'mean_candidates':statistics.mean(x['candidate_count'] for x in r['reranking']),
        'target_coverage':sum(x['target_in_pool'] for x in r['reranking'])/len(r['reranking']),
        'cpu_cached_queries':read(OUT/'rerank_device_switch.json')['cpu_cached_queries'],'remaining_queries_device':'CUDA'}
    for method,m in result['extraction']['fresh'].items():
        m['proposal_precision_wilson_95']=interval(m['correct_proposals_98'],m['proposed'])
    paths=['reference_freeze.json','extraction_protocol.json','retrieval_protocol.json','extraction_regression.json','extraction_fresh.json',
        'retrieval_metrics.json','model_revisions.json','fallback_manifest.json','gemini_before.json','gemini_after.json',
        'review_gate_audit.json','regression_tuning_history.json','verification.json','visual_audit.json']
    result['artifact_hashes']={p:digest(OUT/p) for p in paths}
    write(OUT/'summary.json',result)
    write(REPO/'review/first_page_validation_v2/results.json',result)
    print({'written':str(REPO/'review/first_page_validation_v2/results.json')})


if __name__=='__main__':main()
