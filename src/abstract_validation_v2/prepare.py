"""Select unseen works before extraction; create source-only reference sheets."""
import random
import sqlite3
from PIL import Image, ImageDraw
from .common import DATA, OUT, PREVIOUS, SEED, digest, read, render, write


def main():
    manifest = OUT / 'holdout_manifest.json'
    if not manifest.exists():
        prior = read(PREVIOUS / 'retrieval_manifest.json')['pdfs']
        excluded = {x['work_id'] for x in read(PREVIOUS / 'holdout_manifest.json')['pdfs']}
        excluded |= {x['work_id'] for x in read(DATA / 'sample_comparison_100/manifest.json')['pdfs']}
        # Also exclude papers used in the original extractor's unit tests.
        import re
        excluded |= {'arXiv:' + x.rsplit('v', 1)[0] for x in re.findall(r'26\d{2}\.\d+v\d+', (DATA / 'test_run_jev_corpus.py').read_text())}
        with sqlite3.connect((DATA / 'jev_corpus.sqlite').as_uri() + '?mode=ro', uri=True) as db:
            db.row_factory = sqlite3.Row
            states = {x['version_id']: dict(x) for x in db.execute('SELECT version_id,status,abstract_method,detail FROM paper')}
        pool = [dict(r, previous_state=states[r['version_id']]) for r in prior if r['work_id'] not in excluded]
        rng = random.Random(SEED)
        rng.shuffle(pool)
        chosen = []
        for status, n in [('ok', 50), ('no_abstract', 50)]:
            subset = [r for r in pool if r['previous_state']['status'] == status][:n]
            if len(subset) != n:
                raise RuntimeError(f'Insufficient {status} records: {len(subset)}')
            chosen += subset
        rng.shuffle(chosen)
        for i, row in enumerate(chosen):
            row['index_id'] = row['sample_id']
            row['sample_id'] = f'f{i+1:03}'
        write(manifest, {'seed': SEED, 'scope': 'first physical page only',
            'selection': '50 previously ok and 50 previously no_abstract, sampled from existing 10k index; diagnostic, not population prevalence',
            'previous_index_sha256': digest(PREVIOUS / 'retrieval_manifest.json'),
            'excluded_work_ids': sorted(excluded), 'pdfs': chosen})
    rows = read(manifest)['pdfs']
    for row in rows:
        render(row, OUT / 'pages' / row['sample_id'])
    for first in range(0, len(rows), 4):
        canvas = Image.new('RGB', (2040, 2860), '#dddddd')
        draw = ImageDraw.Draw(canvas)
        for j, row in enumerate(rows[first:first+4]):
            img = Image.open(OUT / 'pages' / row['sample_id'] / 'page.png').convert('RGB')
            img.thumbnail((1000, 1380))
            x, y = j % 2 * 1020, j // 2 * 1430
            draw.text((x+12,y+8), row['sample_id'], fill='black', font_size=24)
            canvas.paste(img, (x+(1020-img.width)//2, y+42))
        dest = OUT / 'review' / f'sheet_{first+1:03}_{first+4:03}.jpg'
        dest.parent.mkdir(exist_ok=True)
        canvas.save(dest, quality=94)
    write(OUT / 'query_targets.json', {'seed': SEED+1, 'sample_ids': random.Random(SEED+1).sample([r['sample_id'] for r in rows],30)})
    print({'fresh_pages': len(rows), 'source_only_sheets': 25})


if __name__ == '__main__':
    main()
