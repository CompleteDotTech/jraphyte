"""Search the validated local page index; semantic queries can incur API cost."""
import argparse
import hashlib
import json

from .common import OUT, digest, read


def search(query, method='lexical', limit=5):
    import numpy as np
    index = read(OUT / 'index/manifest.json')
    if index['retrieval_manifest_sha256'] != digest(OUT / 'retrieval_manifest.json'):
        raise ValueError('Document manifest changed; rebuild the validated index')
    rows = read(OUT / 'retrieval_manifest.json')['pdfs']
    ids = index['document_ids']
    assert ids == [r['sample_id'] for r in rows]
    scores = []
    if method in {'lexical', 'hybrid'}:
        from sklearn.feature_extraction.text import TfidfVectorizer
        with (OUT / 'native_pool.jsonl').open(encoding='utf-8') as stream:
            native = {r['work_id']: r['text'] for r in map(json.loads, stream)}
        vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words='english', dtype=np.float32)
        dm = vectorizer.fit_transform([native[r['work_id']] for r in rows])
        scores.append((vectorizer.transform([query]) @ dm.T).toarray()[0])
    if method in {'semantic', 'hybrid'}:
        from .embedding_batch import BatchEmbedder
        if index['vectors_sha256'] != digest(OUT / 'index/page_vectors.npy'):
            raise ValueError('Stored vectors changed')
        # Reuse the evaluation query if its exact text was already embedded.
        known = next((q['query_id'] for q in read(OUT / 'retrieval_queries.json')['queries'] if q['text'] == query), None)
        key = known or ('search_' + hashlib.sha256(query.encode('utf-8')).hexdigest())
        cached = BatchEmbedder(OUT / 'retrieval_embeddings').embed(key, text=query)
        q = np.asarray(cached['vector'], dtype=np.float32)
        q /= np.linalg.norm(q)
        scores.append(np.load(OUT / 'index/page_vectors.npy', allow_pickle=False) @ q)
    if not scores:
        raise ValueError('Unknown search method')
    if len(scores) == 1:
        final = scores[0]
    else:
        final = np.zeros(len(ids), dtype=np.float32)
        for score in scores:
            order = np.argsort(-score, kind='stable')
            final[order] += 1 / (60 + np.arange(1, len(ids)+1))
    order = np.argsort(-final, kind='stable')[:limit]
    return {'query': query, 'method': method, 'scope': 'first page only; results are retrieval candidates, not reviewed evidence',
            'results': [{'id': ids[i], 'version_id': rows[i]['version_id'], 'source_path': rows[i]['source_path'],
                         'score': float(final[i])} for i in order]}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('query')
    parser.add_argument('--method', choices=['lexical', 'semantic', 'hybrid'], default='lexical',
                        help='Semantic/hybrid can charge the existing Google ledger for an uncached query')
    parser.add_argument('--limit', type=int, default=5)
    args = parser.parse_args()
    if not 1 <= args.limit <= 100:
        parser.error('--limit must be between 1 and 100')
    print(json.dumps(search(args.query, args.method, args.limit), ensure_ascii=False, indent=2))
