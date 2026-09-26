"""Produce a selective reprocessing plan without mutating the active Jev job."""
import datetime
import sys
from collections import Counter

from trace_gc.pdf_admission import prepare_jev_request, source_review
from .common import DATA, OUT, digest, read, write
from .references import freeze


def main():
    frozen = freeze()
    labels = read(OUT / 'labels.json')
    sys.path.insert(0, str(DATA))
    import run_jev_corpus as current
    plans = []
    for row in read(OUT / 'holdout_manifest.json')['pdfs']:
        sid = row['sample_id']
        folder = OUT / 'pages' / sid
        receipt = read(folder / 'receipt.json')
        label = labels[sid]
        candidate = read(OUT / 'docling' / (sid + '.json'))
        joined = ' '.join(b['text'] for b in label['selected_blocks'])
        start = joined.index(label['text']) if label['text'] else 0
        review = source_review(source_sha256=receipt['source_sha256'], page_sha256=receipt['page_pdf_sha256'],
            image_sha256=receipt['image_sha256'], page_size=receipt['page_size'],
            blocks=read(folder / 'reference_blocks.json'), selected_ids=label['block_ids'],
            start=start, end=start+len(label['text']),
            status={'partial_on_page_one': 'partial', 'no_abstract_text': 'absent'}.get(label['status'], label['status']),
            reviewer='assistant source-only boundary review', reviewer_kind='assistant', reviewed_at=frozen['frozen_at'],
            candidate_assessment_sha256=candidate.get('assessment_sha256'))
        write(OUT / 'reviewed_evidence' / (sid + '.json'), review)
        result = prepare_jev_request(paper_id=row['version_id'], model=current.MODEL, questions=current.QUESTIONS,
            current_source_sha256=digest(row['source_path']), current_page_sha256=digest(folder / 'page.pdf'),
            current_image_sha256=digest(folder / 'page.png'), review=review,
            max_characters=current.MAX_ABSTRACT_CHARS, max_request_bytes=current.MAX_REQUEST_BYTES)
        # Exact request identity includes paper id, question set, model and evidence.
        if result['admitted']:
            unchanged = (row['status'] == 'ok' and row.get('pdf_sha256') == review['source_sha256']
                         and row.get('request_sha256') == result['request_sha256'])
            action = 'reuse_exact_request' if unchanged else ('evaluate_changed_evidence' if row['status'] == 'ok' else 'evaluate_recovered_evidence')
            write(OUT / 'prepared_requests' / (sid + '.json'), result)
        else:
            action = 'hold_' + result['reason']
        plans.append({'id': sid, 'version_id': row['version_id'], 'previous_status': row['status'],
            'previous_request_sha256': row.get('request_sha256'), 'previous_charged_usd': row.get('charged_usd'),
            'previous_reserved_usd': row.get('reserved_usd'), 'reference_status': label['status'],
            'candidate_status': candidate['status'], 'candidate_proposed_admission': candidate['eligible_for_jev'],
            'review_sha256': review['review_sha256'], 'action': action,
            'prepared_request_sha256': result.get('request_sha256'), 'request_bytes': result.get('request_bytes'),
            'estimated_reservation_usd': result.get('request_bytes', 0)*current.USD_PER_MILLION_INPUT/1e6 if action.startswith('evaluate_') else 0})
    report = {'generated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'scope': '200 diagnostic holdout records only; historical fields from frozen selection snapshot',
        'promotion': 'automatic selector admission disabled; explicit source review required',
        'reviewer': 'assistant; independent human validation outstanding',
        'actions': dict(Counter(p['action'] for p in plans)), 'rows': plans,
        'historical_charges_preserved': sum(p['previous_charged_usd'] or 0 for p in plans),
        'estimated_new_request_reservation_usd': sum(p['estimated_reservation_usd'] for p in plans),
        'jev_calls_made': 0, 'database_writes': 0,
        'execution_policy': 'Prepared only. A future executor must recheck source/review/request hashes and current checkpoint, reserve against the SAME $50 corpus ledger, and append a new attempt without deleting historical results.'}
    write(OUT / 'reprocessing_plan.json', report)
    print({k: v for k, v in report.items() if k != 'rows'})


if __name__ == '__main__':
    main()
