"""Materialize source-reviewed block selections, then freeze their hashes.

The manual specs must be prepared by viewing source pages, before opening model
outputs. This command does not infer boundaries or write a reference from a model.
"""
import datetime
import re
from collections import Counter

from .common import OUT, digest, read, write


def freeze():
    destination = OUT / 'reference_freeze.json'
    if destination.exists():
        frozen = read(destination)
        for name, expected in frozen['files'].items():
            if digest(OUT / name) != expected:
                raise RuntimeError('Frozen references changed: ' + name)
        return frozen
    specs = read(OUT / 'review/specs.json')
    rows = read(OUT / 'holdout_manifest.json')['pdfs']
    assert set(specs) == {r['sample_id'] for r in rows}
    labels = {}
    for row in rows:
        sid = row['sample_id']
        spec = specs[sid]
        folder = OUT / 'pages' / sid
        receipt = read(folder / 'receipt.json')
        assert digest(folder / 'page.pdf') == receipt['page_pdf_sha256']
        assert digest(folder / 'page.png') == receipt['image_sha256']
        blocks = {b['id']: b for b in read(folder / 'reference_blocks.json')}
        selected = [blocks[i] for i in spec['block_ids']]
        text = ' '.join(b['text'] for b in selected)
        if spec.get('start_after'):
            assert text.count(spec['start_after']) == 1
            text = text.split(spec['start_after'], 1)[1]
        text = re.sub(r'^\s*A\s*B\s*S\s*T\s*R\s*A\s*C\s*T\b[\s.\-:—]*', '', text, flags=re.I).strip()
        assert bool(text) == (spec['status'] != 'no_abstract_text'), sid
        assert 'arXiv:' not in text, sid
        labels[sid] = {**spec, 'text': text, 'page': 1,
                       'source_sha256': receipt['source_sha256'],
                       'page_sha256': receipt['page_pdf_sha256'],
                       'selected_blocks': selected}
    write(OUT / 'labels.json', labels)
    frozen = {'frozen_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'reviewer': 'assistant', 'independent_human_review': 'outstanding',
              'method': 'source page images and native block boundaries reviewed before opening holdout predictions',
              'counts': dict(Counter(v['status'] for v in labels.values())),
              'files': {n: digest(OUT / n) for n in ['labels.json', 'review/specs.json', 'holdout_manifest.json']}}
    write(destination, frozen)
    return frozen


if __name__ == '__main__':
    print(freeze())
