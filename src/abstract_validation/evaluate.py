"""Extraction correctness and known-item retrieval are scored independently."""
import argparse
import difflib
import hashlib
import math
import statistics
import sys
import unicodedata
from collections import Counter

from .common import DATA, OUT, REPO, digest, read, write
from .references import freeze


def canonical(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', text).casefold() if c.isalnum())


def compare(predicted, reference):
    a, b = canonical(predicted), canonical(reference)
    matches = sum(m.size for m in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks())
    precision = matches / len(a) if a else float(not b)
    recall = matches / len(b) if b else 1.0
    boundary = (a.startswith(b[:48]) and a.endswith(b[-48:])) if b else not bool(a)
    return {'precision': precision, 'recall': recall, 'boundary_match': boundary,
            'text_match_98': precision >= .98 and recall >= .98,
            'boundary_and_98_match': precision >= .98 and recall >= .98 and boundary}


def extraction():
    freeze()  # Verify the frozen references, never replace them.
    assert read(OUT / 'protocol.json')['selector_sha256'] == digest(REPO / 'trace_gc/pdf_evidence.py')
    labels = read(OUT / 'labels.json')
    rows = read(OUT / 'holdout_manifest.json')['pdfs']
    sys.path.insert(0, str(DATA / 'src/sample_comparison'))
    from extract import select_docling
    write(OUT / 'baselines/docling_selector_environment.json', {'selector_sha256': digest(DATA / 'src/sample_comparison/extract.py'),
          'conversion': 'same frozen Docling documents as geometry-v1; recursive body reading order'})
    metrics = {}
    for method in ['current', 'old_docling', 'geometry_v1']:
        details = []
        for row in rows:
            sid = row['sample_id']
            if method == 'current':
                pred = read(OUT / 'baselines/current' / (sid + '.json'))
                pred = {**pred, 'status': 'complete' if pred['text'] else 'absent', 'eligible_for_jev': bool(pred['text'])}
            elif method == 'old_docling':
                document = read(OUT / 'docling' / (sid + '.document.json'))
                objects = {x['self_ref']: x for key in ['texts', 'groups', 'pictures', 'tables'] for x in document.get(key, [])}
                items = []
                def walk(node):
                    if node.get('text'):
                        items.append(node)
                    for child in node.get('children', []):
                        walk(objects[child.get('$ref', child.get('cref'))])
                walk(document['body'])
                text, selected, _ = select_docling(items)
                pred = {'text': text, 'status': 'complete' if text else 'absent', 'eligible_for_jev': bool(text)}
                write(OUT / 'baselines/old_docling' / (sid + '.json'), {**pred, 'selected': selected})
            else:
                pred = read(OUT / 'docling' / (sid + '.json'))
            truth = labels[sid]
            details.append({'id': sid, 'stratum': row['stratum'], 'previous_status': row['status'],
                'gold': truth['status'], 'predicted': pred['status'], 'eligible': pred['eligible_for_jev'],
                'nonempty': bool(pred['text']), 'characters': len(pred['text']), 'reasons': pred.get('reasons', []),
                **compare(pred['text'], truth['text'])})
        complete = [x for x in details if x['gold'] == 'complete']
        admitted = [x for x in details if x['eligible']]
        good = [x for x in admitted if x['gold'] == 'complete' and x['text_match_98']]
        summary = {'pages': len(details), 'complete_available': len(complete),
            'near_complete_98_recovered': sum(x['text_match_98'] for x in complete),
            'boundary_and_98_recovered': sum(x['boundary_and_98_match'] for x in complete),
            'admitted': len(admitted), 'correct_admissions_98': len(good),
            'admission_precision_98': len(good)/len(admitted) if admitted else None,
            'correct_admission_recall_98': len(good)/len(complete),
            'wrong_admissions': [x['id'] for x in admitted if x not in good],
            'absent_admitted': [x['id'] for x in admitted if x['gold'] == 'no_abstract_text'],
            'partial_admitted': [x['id'] for x in admitted if x['gold'] == 'partial_on_page_one'],
            'states': dict(Counter(x['predicted'] for x in details))}
        metrics[method] = {**summary, 'details': details}
        print(method, summary, flush=True)
    write(OUT / 'extraction_metrics.json', metrics)
    return metrics


def ranking_metrics(scores, document_ids, queries):
    import numpy as np
    positions = {sid: i for i, sid in enumerate(document_ids)}
    assert scores.shape == (len(queries), len(document_ids))
    assert len(positions) == len(document_ids) and np.isfinite(scores).all()
    details = []
    for i, query in enumerate(queries):
        order = np.argsort(-scores[i], kind='stable').tolist()
        rank = order.index(positions[query['target_id']]) + 1
        details.append({**query, 'rank': rank, 'top10': [{'id': document_ids[j], 'score': float(scores[i, j])} for j in order[:10]]})
    ranks = [x['rank'] for x in details]
    return {'queries': len(queries), 'documents': len(document_ids),
            **{f'recall_at_{k}': sum(r <= k for r in ranks)/len(ranks) for k in [1, 3, 10]},
            'mrr': statistics.mean(1/r for r in ranks),
            'ndcg_at_10': statistics.mean(1/math.log2(r+1) if r <= 10 else 0 for r in ranks),
            'details': details}


def retrieval():
    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer
    from .embedding_batch import BudgetLedger
    from .retrieval_trial import page_path
    manifest = read(OUT / 'retrieval_manifest.json')
    rows = manifest['pdfs']
    ids = [r['sample_id'] for r in rows]
    assert len(ids) == 10000 and len({r['work_id'] for r in rows}) == 10000
    queries = read(OUT / 'retrieval_queries.json')['queries']
    documents = {}
    import json
    with (OUT / 'native_pool.jsonl').open(encoding='utf-8') as stream:
        for line in stream:
            r = json.loads(line)
            documents[r['work_id']] = r['text']
    tfidf = TfidfVectorizer(ngram_range=(1, 2), stop_words='english', dtype=np.float32)
    dm = tfidf.fit_transform([documents[r['work_id']] for r in rows])
    qm = tfidf.transform([q['text'] for q in queries])
    lexical_scores = (qm @ dm.T).toarray()
    vectors = []
    for row in rows:
        cached = read(OUT / 'retrieval_embeddings' / ('page_' + row['sample_id'] + '.json'))
        assert cached['input_sha256'] == digest(page_path(row)), row['sample_id']
        assert cached['model'] == 'gemini-embedding-2' and cached['project'] == 'crossword-489306'
        vectors.append(cached['vector'])
    d = np.asarray(vectors, dtype=np.float32)
    query_vectors = []
    for query in queries:
        cached = read(OUT / 'retrieval_embeddings' / (query['query_id'] + '.json'))
        assert cached['input_sha256'] == hashlib.sha256(query['text'].encode('utf-8')).hexdigest()
        assert cached['model'] == 'gemini-embedding-2' and cached['project'] == 'crossword-489306'
        query_vectors.append(cached['vector'])
    q = np.asarray(query_vectors, dtype=np.float32)
    assert d.shape == (10000, 768) and q.shape == (len(queries), 768)
    assert np.isfinite(d).all() and np.isfinite(q).all()
    assert (np.linalg.norm(d, axis=1) > 0).all() and (np.linalg.norm(q, axis=1) > 0).all()
    d /= np.linalg.norm(d, axis=1, keepdims=True)
    q /= np.linalg.norm(q, axis=1, keepdims=True)
    index = OUT / 'index'
    index.mkdir(exist_ok=True)
    np.save(index / 'page_vectors.npy', d, allow_pickle=False)
    write(index / 'manifest.json', {'model': 'gemini-embedding-2', 'project': 'crossword-489306',
        'dimensions': 768, 'scope': 'first physical page', 'document_ids': ids,
        'retrieval_manifest_sha256': digest(OUT / 'retrieval_manifest.json'),
        'vectors_sha256': digest(index / 'page_vectors.npy')})
    semantic_scores = q @ d.T
    metrics = {'native_tfidf': ranking_metrics(lexical_scores, ids, queries),
               'gemini_embedding_2': ranking_metrics(semantic_scores, ids, queries)}
    # Fixed reciprocal rank fusion; no tuning on the result labels.
    fusion = np.zeros_like(semantic_scores)
    for scores in [lexical_scores, semantic_scores]:
        order = np.argsort(-scores, axis=1, kind='stable')
        for i in range(len(queries)):
            fusion[i, order[i]] += 1/(60 + np.arange(1, len(ids)+1))
    metrics['rrf_60'] = ranking_metrics(fusion, ids, queries)
    write(OUT / 'retrieval_metrics.json', metrics)
    write(OUT / 'cost.json', BudgetLedger(OUT / 'retrieval_embeddings/calls.sqlite').totals())
    print({k: {a: b for a, b in v.items() if a != 'details'} for k, v in metrics.items()})
    return metrics


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=['extraction', 'retrieval'])
    {'extraction': extraction, 'retrieval': retrieval}[parser.parse_args().stage]()
