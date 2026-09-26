"""Freeze source-only annotations; preserve the prior 100 references verbatim."""
import datetime
import re
from collections import Counter
from .common import OLD, OUT, REPO, digest, folder, read, rows, verify_protocol, write


def freeze():
    verify_protocol()
    dest = OUT / 'reference_freeze.json'
    if dest.exists():
        saved = read(dest)
        for path, sha in saved['files'].items():
            assert digest(OUT / path) == sha, path
        assert saved['source_specs_sha256'] == digest(REPO / 'review/first_page_expanded200/specs.json')
        assert saved['source_queries_sha256'] == digest(REPO / 'review/first_page_expanded200/queries.json')
        return saved
    specs = read(REPO / 'review/first_page_expanded200/specs.json')
    queries = read(REPO / 'review/first_page_expanded200/queries.json')
    assert set(specs) == {f'f{i:03}' for i in range(101, 201)}
    assert set(queries) == set(read(OUT / 'query_targets.json')['sample_ids'])
    labels = read(OLD / 'labels.json')
    assert len(labels) == 100
    sources = {}
    for row in rows():
        sid = row['sample_id']; page = folder(sid)
        receipt = read(page / 'receipt.json')
        assert digest(page / 'page.pdf') == receipt['page_pdf_sha256'], sid
        assert digest(page / 'page.png') == receipt['image_sha256'], sid
        sources[sid] = {k: receipt[k] for k in ['source_sha256', 'page_pdf_sha256', 'image_sha256']}
        sources[sid]['reference_blocks_sha256'] = digest(page / 'reference_blocks.json')
        if sid in labels:
            assert labels[sid]['page_sha256'] == receipt['page_pdf_sha256']
            continue
        spec = specs[sid]
        blocks = {b['id']: b for b in read(page / 'reference_blocks.json')}
        selected = [blocks[i] for i in spec['block_ids']]
        text = ' '.join(b['text'] for b in selected).strip()
        if spec.get('start_at'):
            assert text.count(spec['start_at']) == 1, sid
            text = text[text.index(spec['start_at']):]
        if spec.get('end_before'):
            assert text.count(spec['end_before']) == 1, sid
            text = text.split(spec['end_before'])[0].strip()
        if spec.get('end_trim'):
            assert text.endswith(spec['end_trim']), sid
            text = text[:-len(spec['end_trim'])].strip()
        text = re.sub(r'^\s*A\s*B\s*S\s*T\s*R\s*A\s*C\s*T\b[\s.\-:—]*', '', text, flags=re.I).strip()
        assert bool(text) == (spec['status'] != 'no_abstract_text'), sid
        assert 'arXiv:' not in text, sid
        labels[sid] = {**spec, 'text': text, 'source_sha256': receipt['source_sha256'],
                       'page_sha256': receipt['page_pdf_sha256'], 'selected_blocks': selected}
    by_id = {r['sample_id']: r for r in rows()}
    added = [{'query_id': 'expanded_'+sid, 'target_id': by_id[sid]['index_id'],
              'text': text, 'cohort': 'added30', 'source_id': sid} for sid, text in queries.items()]
    prior = read(OLD / 'fresh_queries.json')['queries']
    write(OUT / 'labels.json', labels)
    write(OUT / 'queries.json', {'queries': prior + added, 'reviewer': 'assistant', 'independent_human_review': 'outstanding'})
    write(OUT / 'source_hashes.json', sources)
    saved = {'frozen_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
             'reviewer': 'assistant', 'independent_human_review': 'outstanding',
             'method': 'Added100 original page images and native source spans reviewed before opening their predictions. Prior100 labels reused unchanged. Methods frozen before selection; no tuning on added100.',
             'math_note': 'Canonical text matching does not certify mathematical notation; flagged sources require visual review.',
             'boundary_sensitive_reference': 'f151 has an Executive Summary, classified as no abstract; report sensitivity separately.',
             'counts': {group: dict(Counter(v['status'] for k,v in labels.items() if group == 'combined200' or (int(k[1:]) <= 100) == (group == 'prior100'))) for group in ['prior100','added100','combined200']},
             'source_specs_sha256': digest(REPO / 'review/first_page_expanded200/specs.json'),
             'source_queries_sha256': digest(REPO / 'review/first_page_expanded200/queries.json'),
             'files': {p: digest(OUT / p) for p in ['labels.json','queries.json','source_hashes.json','manifest.json']}}
    write(dest, saved)
    return saved


if __name__ == '__main__':
    print(freeze())
