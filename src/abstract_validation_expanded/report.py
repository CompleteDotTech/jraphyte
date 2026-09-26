"""Generate a compact, reproducible report only after the full paired run verifies."""
import datetime
import math
import statistics
from collections import Counter
from .common import OLD, OUT, REPO, cache, digest, read, rows, write


def compact(value):
    return {k:v for k,v in value.items() if k!='details'}


def interval(correct,total):
    if not total:return None
    z=1.959963984540054;p=correct/total;den=1+z*z/total
    mid=(p+z*z/(2*total))/den
    half=z*math.sqrt(p*(1-p)/total+z*z/(4*total*total))/den
    return [mid-half,mid+half]


def main():
    verified=read(OUT/'verification.json');assert verified['status']=='pass'
    raw=read(OUT/'extraction_metrics.json');retrieval=read(OUT/'retrieval_metrics.json')
    result={'status':'complete','generated_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'scope':{'papers':200,'prior_papers_reused':100,'new_papers':100,'retrieval_queries':60,'retrieval_documents':10000},
            'reference':read(OUT/'reference_freeze.json'),'verification':verified,
            'extraction':{m:{g:compact(v) for g,v in groups.items()} for m,groups in raw.items()},
            'retrieval':{g:{m:compact(v) for m,v in methods.items()} for g,methods in retrieval.items()},
            'historical_gemini_prior30':compact(read(OLD/'retrieval_metrics.json')['fresh30']['gemini']),
            'cost':{'new_paid_api_calls':0,'new_estimated_api_usd':0,'local_electricity_and_hardware_cost':'not measured','prior_paid_results':'historical reference only; no new Gemini vectors or candidates used'},
            'runtime':{},'fallback_increment':{},'production':{'jev_calls_from_experiment':0,'graph_writes':0,'automatic_promotion':False},
            'limitations':['Assistant-reviewed references; independent human validation outstanding.',
                           'Diagnostic sample balanced by prior ok/no_abstract status, not representative corpus prevalence.',
                           'Prior100 was already evaluated; added100 uses methods frozen before selection and predictions.',
                           'Canonical character matching is not exact punctuation, layout, or scientific formula fidelity.',
                           'One labeled target per retrieval query; other relevant papers were not exhaustively judged.',
                           'Local reranker candidate pool excludes Gemini; its prior30 result differs from the earlier three-method pool.',
                           'olmOCR uses NF4 direct Transformers decoding, a 4096-token cap, and native alignment; this is not the complete upstream pipeline.',
                           'MinerU and olmOCR results use the same conservative v2 selector and native-text projection; these are pipeline scores, not standalone OCR accuracy.',
                           'Shared workstation timings are observed times, not controlled throughput measurements. Recorded inference time excludes model loading, paused time, and any interrupted attempt that did not save a result; olmOCR resumed from its 149 saved results.']}
    for method,groups in result['extraction'].items():
        for value in groups.values():value['proposal_precision_wilson_95']=interval(value['correct_proposals_98'],value['proposed'])
    for method in ['mineru','olmocr']:
        runs=[read(cache(method,r['sample_id'])) for r in rows()]
        new=[read(p) for p in (OUT/method).glob('f*.json')]
        result['runtime'][method]={'pages':len(runs),'new_inferences':len(new),'reused':len(runs)-len(new),
                                   'states':dict(Counter(r['status'] for r in runs)),
                                   'new_inference_seconds':sum(r['seconds'] for r in new),
                                   'all_cached_seconds':sum(r['seconds'] for r in runs),
                                   'median_seconds':statistics.median(r['seconds'] for r in runs)}
    for cohort in ['prior100','added100','combined200']:
        base={d['id']:d for d in raw['structure_v2'][cohort]['details']}
        result['fallback_increment'][cohort]={}
        for method in ['mineru','olmocr']:
            extras=[d for d in raw[method][cohort]['details'] if not base[d['id']]['eligible'] and d['eligible']]
            good=[d['id'] for d in extras if d['gold']=='complete' and d['text_match_98']]
            result['fallback_increment'][cohort][method]={'new_correct':good,'new_wrong':[d['id'] for d in extras if d['id'] not in good]}
    labels=read(OUT/'labels.json')
    result['math_review_holds']=[sid for sid,g in labels.items() if g.get('math_review_required') or sid in ['f026','f033']]
    result['boundary_sensitive_reference']={'id':'f151','label':'Executive Summary only, no separate abstract',
        'method_proposals':{m:next(d['eligible'] for d in groups['combined200']['details'] if d['id']=='f151') for m,groups in raw.items()},
        'sensitivity':'If accepted as an abstract, complete-reference denominator increases from 111 to 112; inspect proposals before calculating affected precision.'}
    runtime=read(OUT/'retrieval_runtime.json')
    result['runtime']['retrieval']={'device':runtime['device'],'rerank_seconds':sum(r['seconds'] for r in runtime['reranking']),
                                  'target_in_candidate_pool':sum(r['target_in_pool'] for r in runtime['reranking']),
                                  'queries':60,'lexical_seconds':runtime['lexical_seconds']}
    paths=['manifest.json','protocol.json','reference_freeze.json','source_hashes.json','labels.json','queries.json',
           'extraction_metrics.json','retrieval_protocol.json','retrieval_metrics.json','retrieval_runtime.json',
           'verification.json','api_ledger_before.json','api_ledger_after.json']
    result['artifact_hashes']={p:digest(OUT/p) for p in paths}
    write(OUT/'summary.json',result);write(REPO/'review/first_page_expanded200/results.json',result)
    write(REPO/'review/first_page_expanded200/source_hashes.json',read(OUT/'source_hashes.json'))
    document(result)
    print({'status':'complete','report':str(REPO/'docs/25_first_page_expanded200.md')})


def document(result):
    lines=['# Expanded 200-paper local comparison','',
           'The fresh evaluation was expanded from 100 to 200 distinct papers: the earlier 100 plus 100 additional works. Each cohort contains 50 previously successful and 50 previously skipped papers. This is a diagnostic sample, not an estimate of corpus prevalence.','',
           'All six extraction pipelines used the same 200 physical first pages. The prior 100 source references and parser caches were preserved. Added references and 30 new queries were frozen before opening their predictions; the methods were frozen before selection. References were reviewed by the assistant; independent human validation remains outstanding.','',
           '## Extraction','',
           'References: **111 complete abstracts, 7 partial abstracts, 82 pages without an abstract**. Correct means a complete source reference with at least 98% ordered canonical alphanumeric precision and recall. A proposal is not permission to send text to Jev.','',
           '| Pipeline | Correct / proposed | Precision | Complete abstracts recovered as correct proposals | Correct with boundary check |',
           '|---|---:|---:|---:|---:|']
    names={'current':'Production baseline','geometry_v1':'Docling + geometry v1','grobid':'GROBID','structure_v2':'Docling + structure v2','mineru':'MinerU + structure v2','olmocr':'olmOCR + structure v2'}
    for method,groups in result['extraction'].items():
        m=groups['combined200'];p=m['proposal_precision_98']
        lines.append(f"| {names[method]} | {m['correct_proposals_98']}/{m['proposed']} | {p:.1%} | {m['correct_proposals_98']}/111 | {m['boundary_and_98_correct_proposals']} |")
    lines += ['', '### Added 100 separately','', '| Pipeline | Correct / proposed | Precision |', '|---|---:|---:|']
    for method,groups in result['extraction'].items():
        m=groups['added100'];lines.append(f"| {names[method]} | {m['correct_proposals_98']}/{m['proposed']} | {m['proposal_precision_98']:.1%} |")
    lines += ['', '### Remaining structure-selector errors','',
              '- f030 (prior): inline Overview text extends the selected region.',
              '- f119: a separate colored synopsis is appended to the bold abstract.',
              '- f150: the wrong column is selected instead of the bold abstract.',
              '- f192: a dedication is appended to the abstract.',
              '- f199: an author list is proposed as an unlabelled abstract.', '',
              'These are retained test failures. No selector tuning was performed on the added 100. Mathematical notation also needs source review: normalized text agreement can hide detached radicals, flattened fractions, or lost superscripts. Flagged cases are listed in the results artifact; no production requests were prepared or executed by this experiment.', '',
              'f151 contains an Executive Summary and is classified as no separate abstract. Its per-method proposals are retained for a sensitivity check; counting this as an abstract would raise the complete-reference denominator to 112.', '',
              '## Local fallback increment','',
              'When used only where structure v2 abstained, the following additional proposals appeared. These counts describe the frozen pipeline, not standalone OCR accuracy.','',
              '| Fallback | Additional correct | Additional wrong |','|---|---:|---:|']
    for method,m in result['fallback_increment']['combined200'].items():
        lines.append(f"| {names[method]} | {len(m['new_correct'])} | {len(m['new_wrong'])} |")
    lines += ['', '## Retrieval','',
              '60 source-authored known-item queries (30 prior, 30 added) were searched against the same 10,000-paper index. The local reranker uses the union of the top 50 BM25F and top 50 SPECTER2 candidates, with no target insertion. An absent target gets zero reciprocal-rank credit.','',
              '| Local method | Top 1 / 60 | Top 10 / 60 | Added top 1 / 30 | MRR |','|---|---:|---:|---:|---:|']
    for name,m in result['retrieval']['combined60'].items():
        fresh=result['retrieval']['added30'][name]
        lines.append(f"| {name} | {round(m['recall_at_1']*60)} | {round(m['recall_at_10']*60)} | {round(fresh['recall_at_1']*30)} | {m['mrr']:.3f} |")
    lines += ['', 'The shared top-10 misses were f076 (an image-only book cover whose local text fields are empty) and f115 (a graphical-abstract cover). For f115, the automatic title field contains only `Graphical Abstract`, its abstract field is empty, and the real paper title appears only in the body. SPECTER2 therefore receives an uninformative input; BM25F ranks the target 226, full-page BM25 ranks it 44, and the local reranker never sees it. The observed failure comes from title extraction and candidate selection.', '',
              'Gemini was not run on the added queries. Its earlier 27/30 top-1 and 30/30 top-10 result is a historical reference only. The earlier reranker used Gemini candidates, so its result is not the same configuration as this local-only reranker.', '',
              '## Runtime and cost','', '| Vision pipeline | New inferences / reused | New inference minutes | Output states |', '|---|---:|---:|---|']
    for method in ['mineru','olmocr']:
        r=result['runtime'][method];lines.append(f"| {method} | {r['new_inferences']} / {r['reused']} | {r['new_inference_seconds']/60:.1f} | {r['states']} |")
    lines += ['', '**New paid API calls: 0. New estimated API spend: $0.** Local electricity and hardware costs were not measured. Both model weights were already downloaded. The Google ledger was read in read-only mode and verified unchanged. No Jev calls or graph writes were made by the experiment.', '',
              '## Interpretation and limits','',
              'Keep source review mandatory. The expanded test exposes additional false proposals, so these results do not qualify automatic acceptance. Use retrieval as a way to find papers; it does not validate extracted abstract boundaries or scientific notation.', '',
              *['- '+s for s in result['limitations']], '',
              '## Reproduce','', 'From the repository root, using the existing CPU/Docling environment for preparation, conversion and scoring, and the model environment for vision and retrieval:', '',
              '```text','python -m src.abstract_validation_expanded.prepare','python -m src.abstract_validation_expanded.convert current',
              'python -m src.abstract_validation_expanded.convert docling','python -m src.abstract_validation_expanded.convert grobid',
              'python -m src.abstract_validation_expanded.references','python -m src.abstract_validation_expanded.vision mineru',
              'python -m src.abstract_validation_expanded.vision olmocr','python -m src.abstract_validation_expanded.extraction',
              'python -m src.abstract_validation_expanded.retrieval','python -m src.abstract_validation_expanded.verify',
              'python -m src.abstract_validation_expanded.report','```','',
              'The baseline was run with the production Python/PyMuPDF environment. GROBID uses the existing pinned local container at 127.0.0.1:18070. The model environment uses local-only model paths, CPU retrieval, MinerU BF16 and olmOCR NF4, with unchanged v2 settings. All retained source pages, 400 vision input receipts, and frozen protocols are hash checked. Empty successful GROBID conversions are labeled absent in the assessment; this reporting correction was checked to leave all 200 texts and proposal decisions unchanged.', '',
              'Private source PDFs, rendered pages, full parser outputs, and model weights remain outside this checkout in `../TRACE-GC_RealPaper_Test/validation_expanded200`. Portable source hashes, annotation specs, query text, and compact results are under `review/first_page_expanded200/`.']
    (REPO/'docs/25_first_page_expanded200.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


if __name__=='__main__':
    main()
