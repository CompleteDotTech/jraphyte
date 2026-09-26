"""Append 100 unseen works without modifying the preceding frozen experiment."""
import datetime
import random
import sqlite3
from PIL import Image, ImageDraw
from .common import DATA, OLD, INDEX, OUT, SEED, code_hashes, digest, folder, read, render, write


def main():
    destination = OUT / 'manifest.json'
    if not destination.exists():
        prior = read(OLD / 'holdout_manifest.json')
        excluded = set(prior['excluded_work_ids']) | {r['work_id'] for r in prior['pdfs']}
        with sqlite3.connect((DATA / 'jev_corpus.sqlite').as_uri() + '?mode=ro', uri=True) as db:
            db.row_factory = sqlite3.Row
            states = {r['version_id']: dict(r) for r in db.execute('SELECT version_id,status,abstract_method,detail FROM paper')}
        pool = [dict(r, previous_state=states[r['version_id']]) for r in read(INDEX / 'retrieval_manifest.json')['pdfs'] if r['work_id'] not in excluded]
        rng = random.Random(SEED)
        rng.shuffle(pool)
        new = []
        for status in ('ok', 'no_abstract'):
            chosen = [r for r in pool if r['previous_state']['status'] == status][:50]
            assert len(chosen) == 50, status
            new.extend(chosen)
        rng.shuffle(new)
        for i, row in enumerate(new, 101):
            row['index_id'] = row['sample_id']
            row['sample_id'] = f'f{i:03}'
        combined = prior['pdfs'] + new
        assert len(combined) == len({r['work_id'] for r in combined}) == 200
        write(destination, {'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'seed': SEED, 'selection': 'Prior 100 plus 100 new works, 50 prior ok and 50 prior no_abstract in each cohort. Diagnostic sample, not population prevalence.',
            'scope': 'First physical page only', 'excluded_new_work_ids': sorted(excluded),
            'prior_manifest_sha256': digest(OLD / 'holdout_manifest.json'), 'pdfs': combined})
    manifest = read(destination)
    protocol = OUT / 'protocol.json'
    if not protocol.exists():
        write(protocol, {'frozen_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'method_hashes': code_hashes(), 'manifest_sha256': digest(destination),
            'models': read(OLD / 'model_revisions.json'), 'settings': 'Same parser settings, selector, thresholds, fields, embeddings and reranker as validation_v2. No tuning on added 100.',
            'evaluation': 'Report prior100, added100, combined200 separately; >=98% canonical precision and recall plus separate boundary and visual checks.',
            'review': 'Assistant source review before opening added-page predictions; independent human validation outstanding.'})
    new = manifest['pdfs'][100:]
    for row in new:
        render(row, folder(row['sample_id']))
    for start in range(0, 100, 4):
        sheet = Image.new('RGB', (2040, 2860), '#dddddd')
        draw = ImageDraw.Draw(sheet)
        for j, row in enumerate(new[start:start+4]):
            img = Image.open(folder(row['sample_id']) / 'page.png').convert('RGB')
            img.thumbnail((1000, 1380))
            x, y = j % 2 * 1020, j // 2 * 1430
            draw.text((x+12, y+8), row['sample_id'], fill='black', font_size=24)
            sheet.paste(img, (x+(1020-img.width)//2, y+42))
        target = OUT / 'review' / f'sheet_{start+101:03}_{start+104:03}.jpg'
        target.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(target, quality=94)
    query_ids = random.Random(SEED+1).sample([r['sample_id'] for r in new], 30)
    write(OUT / 'query_targets.json', {'seed': SEED+1, 'sample_ids': query_ids})
    print({'papers': 200, 'reused': 100, 'new': 100, 'new_source_sheets': 25, 'new_query_targets': 30})


if __name__ == '__main__':
    main()
