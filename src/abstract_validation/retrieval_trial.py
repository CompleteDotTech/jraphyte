"""Ten-thousand-work first-page retrieval trial, with nearby-topic distractors."""
from __future__ import annotations

import argparse
import json
import random
import shutil
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed

from .common import OLD, OUT, digest, read, render, write
from .embedding_batch import BatchEmbedder


def prepare_index():
    if (OUT / 'retrieval_manifest.json').exists():
        return read(OUT / 'retrieval_manifest.json')
    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer
    pool = read(OUT / 'pool_manifest.json')
    with (OUT / 'native_pool.jsonl').open(encoding='utf-8') as stream:
        native = {x['work_id']: x for x in map(json.loads, stream)}
    rows = pool['targets'] + pool['distractor_pool']
    if len(native) != len(rows):
        raise RuntimeError('Native pool is incomplete')
    vectorizer = TfidfVectorizer(stop_words='english', ngram_range=(1, 2), min_df=2, max_features=180000, dtype=np.float32)
    vectors = vectorizer.fit_transform([native[r['work_id']]['text'] for r in rows])
    selected, neighbors = set(range(300)), {}
    for i in range(300):
        scores = (vectors[i] @ vectors.T).toarray()[0]
        scores[:300] = -1
        nearby = np.argsort(-scores, kind='stable')[:20]
        neighbors[rows[i]['work_id']] = [{'work_id': rows[int(j)]['work_id'], 'cosine': float(scores[j])} for j in nearby]
        selected.update(int(j) for j in nearby)
    remaining = [i for i in range(300, len(rows)) if i not in selected and not native[rows[i]['work_id']]['error']]
    random.Random(2026092510000).shuffle(remaining)
    selected.update(remaining[:10000-len(selected)])
    selected_rows = []
    for i in sorted(selected):
        row = rows[i]
        sid = row.get('sample_id', f'd{i-299:05}')
        selected_rows.append({**row, 'sample_id': sid, 'target': i < 300})
    assert len(selected_rows) == 10000 and len({r['work_id'] for r in selected_rows}) == 10000
    manifest = {'scope': 'first physical page only, one version per work', 'model': 'gemini-embedding-2',
        'selection': '300 targets plus 20 nearest first-page TF-IDF neighbors per target from 30000 distinct works, then random fill; selection does not use queries',
        'seed': 2026092510000, 'nearest_neighbors': neighbors, 'pdfs': selected_rows}
    write(OUT / 'retrieval_manifest.json', manifest)
    labels = read(OLD / 'labels.json')
    queries = [{'query_id': 'q_' + r['sample_id'], 'target_id': r['sample_id'], 'text': labels[r['sample_id']]['query'], 'cohort': 'previous100'} for r in selected_rows[:100]]
    next(q for q in queries if q['target_id'] == 'n052')['text'] = 'What data acquisition system is used for the Darkside-20k dark matter detector?'
    write(OUT / 'retrieval_queries.json', {'queries': queries, 'review': 'previous assistant-written source queries; n052 erratum corrected before retrieval'})
    return manifest


def render_one(row):
    sid = row['sample_id']
    if row['target'] and not sid.startswith('h'):
        return sid  # Original rendered page/cached Google vector are reused by hash.
    render(row, OUT / 'pages' / sid)
    return sid


def page_path(row):
    sid = row['sample_id']
    return (OLD if row['target'] and not sid.startswith('h') else OUT) / 'pages' / sid / 'page.png'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=['prepare', 'render', 'embed', 'queries'])
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--retry-errors', action='store_true')
    args = parser.parse_args()
    manifest = prepare_index()
    rows = manifest['pdfs']
    if args.stage == 'prepare':
        print(json.dumps({'documents': len(rows), 'manifest': str(OUT / 'retrieval_manifest.json')}))
        return
    if args.stage == 'render':
        with ProcessPoolExecutor(max_workers=4) as pool:
            for i, sid in enumerate(pool.map(render_one, rows, chunksize=10)):
                if (i+1) % 250 == 0:
                    print(json.dumps({'rendered': i+1}), flush=True)
        return
    client = BatchEmbedder(OUT / 'retrieval_embeddings')
    if args.stage == 'embed':
        for row in rows[:100]:
            sid = row['sample_id']
            old = read(OLD / 'results/gemini-embedding-2' / ('page_' + sid + '.json'))
            if old['input_sha256'] != digest(page_path(row)):
                raise RuntimeError('Previous cache no longer matches rendered page')
            dest = client.folder / ('page_' + sid + '.json')
            if not dest.exists():
                write(dest, {**old, 'imported_from': str(OLD), 'charged_in_this_trial': False})
        tasks = [('page_'+r['sample_id'], {'image': page_path(r)}) for r in rows]
    else:
        tasks = [(q['query_id'], {'text': q['text']}) for q in read(OUT / 'retrieval_queries.json')['queries']]
    failures, completed = [], 0
    started = time.monotonic()
    # Bounded submission lets systemic failures stop further paid calls promptly.
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        iterator = iter(tasks)
        pending = {}
        for _ in range(args.workers):
            task = next(iterator, None)
            if task:
                key, kwargs = task
                pending[pool.submit(client.embed, key, **kwargs, retry=args.retry_errors)] = key
        while pending:
            future = next(as_completed(pending))
            key = pending.pop(future)
            try:
                future.result()
                completed += 1
            except Exception as exc:
                failures.append({'key': key, 'error': str(exc)[:180]})
                write(OUT / ('retrieval_errors_' + args.stage + '.json'), failures)
            if (completed + len(failures)) % 100 == 0:
                progress = {'stage': args.stage, 'completed_this_pass': completed, 'failures': len(failures), 'seconds': round(time.monotonic()-started), **client.ledger.totals()}
                write(OUT / 'retrieval_progress.json', progress)
                print(json.dumps(progress), flush=True)
            if len(failures) < 5:
                task = next(iterator, None)
                if task:
                    key, kwargs = task
                    pending[pool.submit(client.embed, key, **kwargs, retry=args.retry_errors)] = key
    print(json.dumps({'stage': args.stage, 'completed_this_pass': completed, 'failures': failures, **client.ledger.totals()}), flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
