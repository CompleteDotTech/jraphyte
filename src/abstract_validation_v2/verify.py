"""Verify retained sources, frozen protocols, and cached results without API calls."""
import datetime
import hashlib
import json
from collections import Counter

from src.abstract_validation.common import reference_blocks
from src.abstract_validation.evaluate import compare
from .common import DATA, OUT, PREVIOUS, REPO, digest, read, write
from .extraction import frozen, summary
from .retrieval import configuration


def main():
    import pymupdf

    frozen()
    configuration()
    fresh = read(OUT / 'holdout_manifest.json')
    previous = read(PREVIOUS / 'holdout_manifest.json')['pdfs']
    assert len(fresh['pdfs']) == 100
    assert len({r['work_id'] for r in fresh['pdfs']}) == 100
    assert not ({r['work_id'] for r in fresh['pdfs']} & set(fresh['excluded_work_ids']))
    labels = read(OUT / 'labels.json')
    verified = []
    for row in fresh['pdfs']:
        sid = row['sample_id']
        folder = OUT / 'pages' / sid
        receipt = read(folder / 'receipt.json')
        assert digest(row['source_path']) == receipt['source_sha256'] == labels[sid]['source_sha256'], sid
        assert digest(folder / 'page.pdf') == receipt['page_pdf_sha256'] == labels[sid]['page_sha256'], sid
        assert digest(folder / 'page.png') == receipt['image_sha256'], sid
        with pymupdf.open(row['source_path']) as pdf:
            assert reference_blocks(pdf[0]) == read(folder / 'reference_blocks.json'), sid
        with pymupdf.open(folder / 'page.pdf') as pdf:
            assert len(pdf) == 1, sid
        verified.append(receipt['source_sha256'])
    old_hashes = {read(PREVIOUS / 'pages' / r['sample_id'] / 'receipt.json')['source_sha256'] for r in previous}
    assert len(set(verified)) == 100 and not (set(verified) & old_hashes)
    assert digest(DATA / 'run_jev_corpus.py') == read(OUT / 'baselines/environment.json')['worker_sha256']
    visual = read(OUT / 'visual_audit.json')
    assert visual == read(REPO / 'review/first_page_validation_v2/visual_audit.json')
    for check in visual['cases']:
        base = PREVIOUS if check['id'].startswith('h') else OUT
        folder = base / 'pages' / check['id']
        assert digest(folder / 'page.png') == check['image_sha256']
        assert digest(folder / 'page.pdf') == check['page_sha256']
        assert hashlib.sha256(read(base / 'labels.json')[check['id']]['text'].encode()).hexdigest() == check['reference_text_sha256']
        for method, expected in check['assessment_hashes'].items():
            assert digest(OUT / 'assessments' / method / (check['id'] + '.json')) == expected
    gate = read(OUT / 'review_gate_audit.json')
    assert gate['visual_audit_sha256'] == digest(OUT / 'visual_audit.json')
    assert gate['candidate_only_admitted'] == 0
    for sid in visual['fresh_request_holds']:
        assert not read(OUT / 'prepared_requests' / (sid + '.json'))['admitted']
    assert sum(read(p).get('admitted', False) for p in (OUT / 'prepared_requests').glob('*.json')) == gate['reviewed_requests_prepared']

    pilot = read(OUT / 'fallback_manifest.json')['ids']
    assert len(pilot) == len(set(pilot)) == 40
    parsers = {}
    for method in ('mineru', 'olmocr'):
        raw = [read(OUT / method / (sid + '.json')) for sid in pilot]
        for sid, item in zip(pilot, raw):
            folder = (PREVIOUS if sid.startswith('h') else OUT) / 'pages' / sid
            assert item['sample_id'] == sid and item['page_sha256'] == digest(folder / 'page.pdf'), sid
            assessment = read(OUT / 'assessments' / method / (sid + '.json'))
            if item['status'] != 'success':
                assert not assessment['eligible_for_jev'], sid
        parsers[method] = dict(Counter(r['status'] for r in raw))

    # Rescore saved outputs against the frozen references, including the retained
    # beginning/end checks. The latter ignore punctuation and are not exact math.
    boundaries = {}
    for cohort, base in (('regression', PREVIOUS), ('fresh', OUT)):
        gold = read(base / 'labels.json')
        boundaries[cohort] = {}
        for method, result in read(OUT / ('extraction_' + cohort + '.json')).items():
            for detail in result['details']:
                pred = read(OUT / 'assessments' / method / (detail['id'] + '.json'))
                expected = compare(pred['text'], gold[detail['id']]['text'])
                assert all(detail[k] == v for k, v in expected.items()), (method, detail['id'])
                assert detail['eligible'] == pred['eligible_for_jev']
            assert summary(result['details']) == result, method
            complete = [d for d in result['details'] if d['gold'] == 'complete']
            admitted = [d for d in complete if d['eligible']]
            boundaries[cohort][method] = {
                'complete_references': len(complete),
                'boundary_and_98_recovered': sum(d['boundary_and_98_match'] for d in complete),
                'boundary_and_98_correct_proposals': sum(d['boundary_and_98_match'] for d in admitted),
                'boundary_definition': 'First and last 48 canonical alphanumeric characters, plus >=98% ordered precision and recall; not exact typography or mathematical fidelity.',
            }

    index = read(PREVIOUS / 'retrieval_manifest.json')['pdfs']
    assert len(index) == len({r['work_id'] for r in index}) == 10000
    metrics = read(OUT / 'retrieval_metrics.json')
    for group, expected_count in (('regression100', 100), ('fresh30', 30)):
        queries = read((PREVIOUS if group == 'regression100' else OUT) / ('retrieval_queries.json' if group == 'regression100' else 'fresh_queries.json'))['queries']
        assert len(queries) == expected_count
        for method, result in metrics[group].items():
            assert len(result['details']) == expected_count
            assert [r['query_id'] for r in result['details']] == [q['query_id'] for q in queries]
            for k in (1, 3, 10):
                assert result[f'recall_at_{k}'] == sum(d['rank'] <= k for d in result['details']) / expected_count
            for detail in result['details']:
                for position, hit in enumerate(detail['top10'], 1):
                    if hit['id'] == detail['target_id']:
                        assert detail['rank'] == position, (method, detail['query_id'])
        for q in queries:
            cached = read(PREVIOUS / 'retrieval_embeddings' / (q['query_id'] + '.json'))
            assert cached['input_sha256'] == hashlib.sha256(q['text'].encode()).hexdigest()
            assert cached['model'] == 'gemini-embedding-2' and cached['project'] == 'crossword-489306'

    result = {
        'verified_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'status': 'pass', 'fresh_source_pdfs_verified': 100,
        'fresh_native_reference_blocks_reproduced': 100,
        'fresh_source_overlap_with_previous_200': 0,
        'frozen_protocols_verified': True, 'live_worker_source_unchanged': True,
        'fallback_cache_inputs_verified': 80, 'parser_states': parsers,
        'visual_cases_bound_to_sources': len(visual['cases']),
        'known_transcription_holds_enforced': visual['fresh_request_holds'],
        'retrieval_works': 10000, 'query_inputs_verified': 130,
        'extraction_boundary_metrics': boundaries,
        'api_calls': 0, 'independent_human_review': 'outstanding',
        'verifier_sha256': digest(REPO / 'src/abstract_validation_v2/verify.py'),
    }
    write(OUT / 'verification.json', result)
    print(json.dumps({k: v for k, v in result.items() if k != 'extraction_boundary_metrics'}, indent=2))


if __name__ == '__main__':
    main()
