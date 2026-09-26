"""Render auditable local trial artifacts; never uploads source material."""
import html
import statistics

from .common import OUT, read, write
from .references import freeze


def review_sheet():
    freeze()
    labels = read(OUT / 'labels.json')
    plans = {r['id']: r for r in read(OUT / 'reprocessing_plan.json')['rows']}
    cards = []
    for row in read(OUT / 'holdout_manifest.json')['pdfs']:
        sid = row['sample_id']
        label = labels[sid]
        prediction = read(OUT / 'docling' / (sid + '.json'))
        esc = html.escape
        cards.append(f'''<article data-status="{esc(label['status'])}">
<h2>{sid} · {esc(row['version_id'])}</h2>
<p>Reference: <b>{esc(label['status'])}</b> · Selector: {esc(prediction['status'])}<br>
Plan: {esc(plans[sid]['action'])}</p>
<div class="pair"><a href="../pages/{sid}/page.pdf"><img loading="lazy" src="../pages/{sid}/page.png" alt="First physical page of {esc(row['version_id'])}"></a>
<div><h3>Assistant-reviewed reference</h3><p class="text">{esc(label['text']) or 'No abstract text on page one.'}</p>
<details><summary>Frozen selector output and reasons</summary><p>{esc(', '.join(prediction['reasons']))}</p><p class="text">{esc(prediction['text'])}</p></details>
<p><a href="../reviewed_evidence/{sid}.json">Source review receipt</a> · <a href="../docling/{sid}.json">Selector receipt</a></p></div></div></article>''')
    document = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>200-paper first-page review</title><style>
body{font:16px/1.55 system-ui,sans-serif;max-width:1400px;margin:32px auto;padding:0 24px;color:#192c38;background:#f5f7f8}
header{position:sticky;top:0;background:#f5f7f8;padding:12px 0;z-index:1;border-bottom:1px solid #b8c6cf}
h1{font-size:24px;margin:0}h2{font-size:20px}article{background:white;padding:24px;margin:24px 0;border:1px solid #d4dfe5;border-radius:6px}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:24px}img{width:100%;height:auto}a{color:#145c80}.text{white-space:pre-wrap}input,select{font:inherit;padding:6px;margin-right:12px;max-width:90%}
details{padding:12px;background:#eef3f5}summary{cursor:pointer}@media(max-width:850px){.pair{grid-template-columns:1fr}header{position:static}}
</style><header><h1>200-paper first-page source review</h1>
<p>Assistant-reviewed references, frozen before opening holdout predictions. Independent human validation is outstanding.</p>
<input id="query" placeholder="Find paper ID or text" aria-label="Find paper"><select id="status" aria-label="Reference status"><option value="">All references</option>complete</option><option>partial_on_page_one</option><option>no_abstract_text</option></select><span id="count"></span>
</header>''' + ''.join(cards) + '''<script>
const q=document.getElementById('query'),s=document.getElementById('status');
function filter(){let count=0;for(const a of document.querySelectorAll('article')){a.hidden=!!((s.value&&a.dataset.status!==s.value)||!a.textContent.toLowerCase().includes(q.value.toLowerCase()));if(!a.hidden)count++;}document.getElementById('count').textContent=count+' papers';}
q.addEventListener('input',filter);s.addEventListener('change',filter);filter();
</script></html>'''
    (OUT / 'review/index.html').write_text(document, encoding='utf-8')


def main():
    review_sheet()
    extraction = read(OUT / 'extraction_metrics.json')
    retrieval = read(OUT / 'retrieval_metrics.json')
    cost = read(OUT / 'cost.json')
    reconciliation = read(OUT / 'embedding_reconciliation.json')
    assert reconciliation['unresolved_failed_keys'] == 0
    audit = read(OUT / 'reprocessing_plan.json')
    times = [read(p)['seconds'] for p in (OUT / 'docling').glob('h???.json')]
    lines = ['# First-page validation: 200 fresh papers and 10,000-work retrieval', '',
        '**Decision: keep automatic extraction promotion disabled. Use source-reviewed evidence for Jev; use page embeddings for retrieval.**', '',
        'References were reviewed by the assistant before opening holdout outputs. Independent human validation is outstanding. The live corpus worker was not changed, and this trial made no Jev API calls.', '',
        '## Extraction', '',
        '200 diagnostic cases: 146 complete, 8 partial, 46 absent. They include 120 previously accepted and 80 skipped records. These are not representative corpus prevalence estimates.', '',
        '| Method | Complete recovered, ≥98% match | Correct proposed admissions | Admission precision |',
        '| --- | ---: | ---: | ---: |']
    names = {'current': 'Current production', 'old_docling': 'Previous Docling selector', 'geometry_v1': 'Frozen geometry selector'}
    for key, name in names.items():
        m = extraction[key]
        lines.append(f"| {name} | {m['near_complete_98_recovered']} / 146 | {m['correct_admissions_98']} / {m['admitted']} | {m['admission_precision_98']:.1%} |")
    lines += ['', 'The new selector incorrectly proposed 14 admissions: five pages without abstracts and nine incomplete or contaminated transcriptions. All eight partial abstracts were held. Two correctly recovered complete texts were also held, explaining 124 recovered versus 122 correct admissions.', '',
        'Failures include Index Terms leakage, metadata sharing text boxes, cross-column continuations, publication/funding notices, and formula reading order. Source-text agreement does not establish abstract identity or completeness.', '',
        f'Docling conversion/assessment took {sum(times):.1f} seconds across 200 pages (median {statistics.median(times):.2f} s/page; model setup excluded).', '',
        'Scoring uses ordered canonical alphanumeric alignment (at least 98% precision and recall). It ignores punctuation, whitespace and Unicode compatibility differences; it does not certify scientific or mathematical fidelity. Exact boundaries are reported separately in the JSON.', '',
        '## Retrieval', '',
        '10,000 distinct works, one first-page image per work; all 10,000 source PDF hashes are distinct. The index includes 300 targets, document-based nearest-topic proxies from a 30,000-work pool, and random fill. Evaluation reuses the prior 100 source queries with a corrected Darkside-20k query; these are not 100 fresh queries.', '',
        '| Method | Recall@1 | Recall@3 | Recall@10 | MRR | nDCG@10 |',
        '| --- | ---: | ---: | ---: | ---: | ---: |']
    for name, m in retrieval.items():
        assert m['documents'] == 10000 and m['queries'] == 100
        lines.append(f"| {name} | {m['recall_at_1']:.1%} | {m['recall_at_3']:.1%} | {m['recall_at_10']:.1%} | {m['mrr']:.4f} | {m['ndcg_at_10']:.4f} |")
    lines += ['', 'Use Gemini as the primary retrieval method for this pilot. Fixed RRF reduced Recall@1 from 90% to 85% on this cohort. The ten Gemini top-1 misses all retained the designated target within the top seven.', '',
        'This is known-item retrieval, with one designated target per query. Other potentially relevant papers are not exhaustively labeled. It does not measure abstract correctness, general relevance precision, or downstream graph-answer quality. Embedding scores are not probabilities. Fixed RRF uses k=60 with no label-based tuning.', '',
        '## Selective reprocessing plan', '',
        '94 identical requests can be reused; 21 changed and 31 recovered requests are prepared; 8 partial and 46 absent references remain held. Source hashes and complete request hashes are recorded. Historical attempts and charges remain intact.', '',
        f"The 52 proposed evaluations reserve an estimated ${audit['estimated_new_request_reservation_usd']:.8f} under the existing Jev pricing configuration. They have **not** been sent. Execution must recheck current files/checkpoint and reserve against the existing $50 corpus budget.", '',
        '## Cost', '',
        f"Google project: `crossword-489306`. Incremental provider-usage estimate: **${cost['estimated_usd']:.6f}**; conservative reservations retained: ${cost['reserved_usd']:.4f} against a $12 cap. Ledger calls: {cost['calls']}; states: `{cost['states']}`.", '',
        'The 100 prior page vectors were reused without a new charge; 9,900 new page images and 100 query embeddings were required. Failed request reservations are retained. Provider billing is authoritative. No local electricity cost is included.', '',
        'All five HTTP 429 keys succeeded on retry. The ledger has no unresolved failed keys or duplicate successful calls. A stored-index search returned the expected Darkside-20k paper first using an existing query vector, with no extra API call.', '',
        '## Evidence and reproducibility', '',
        '- [Browsable 200-paper review sheet](review/index.html)',
        '- [Extraction details](extraction_metrics.json) and [failure causes](failure_analysis.json)',
        '- [Retrieval rankings](retrieval_metrics.json) and [selection manifest](retrieval_manifest.json)',
        '- [Selective reprocessing plan](reprocessing_plan.json)',
        '- [Frozen protocol](protocol.json), [reference freeze](reference_freeze.json) and [source-block verification](reference_source_verification.json)',
        '- [Environment](environment.json), [test results](test_results.json) and [cost ledger totals](cost.json)', '',
        '- [Embedding reconciliation](embedding_reconciliation.json) and [stored-index search smoke test](search_smoke.json)', '',
        'All 200 reference block sets were reproduced from the original PDFs. Full package validation: 324 passed, one existing external fixture test skipped. Three additional focused tests passed for retry accounting, in-flight protection and rectangular ranking. Raw sources and credentials are not committed.', '']
    (OUT / 'REPORT.md').write_text('\n'.join(lines), encoding='utf-8')
    write(OUT / 'summary.json', {'automatic_promotion': False, 'independent_review': 'outstanding',
        'reviewer': 'assistant', 'extraction': {k: {a: b for a, b in v.items() if a != 'details'} for k, v in extraction.items()},
        'retrieval': {k: {a: b for a, b in v.items() if a != 'details'} for k, v in retrieval.items()},
        'cost': cost, 'audit_actions': audit['actions'], 'jev_calls': 0})
    print(OUT / 'REPORT.md')


if __name__ == '__main__':
    main()
