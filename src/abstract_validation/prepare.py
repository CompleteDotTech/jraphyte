"""Freeze a fresh stratified holdout and a query-independent retrieval pool.

Run with the existing optional PDF benchmark environment:
    python -m src.abstract_validation.prepare
All corpus and catalog connections are read-only. Output is outside the repository.
"""
from __future__ import annotations

import json
import random
import re
import sqlite3
import time
from concurrent.futures import ProcessPoolExecutor

from .common import DATA, OLD, OUT, digest, read, render, write

SEED = 20260925200


def native_text(row):
    import fitz
    try:
        with fitz.open(row['source_path']) as doc:
            text = doc[0].get_text(sort=True)
        return {**row, 'text': text, 'error': None}
    except Exception as exc:
        return {**row, 'text': '', 'error': type(exc).__name__}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    previous = read(OLD / 'manifest.json')['pdfs']
    old_works = {x['work_id'] for x in previous}
    known = {x.rsplit('v', 1)[0] for x in re.findall(r'26\d{2}\.\d+v\d+', (DATA / 'test_run_jev_corpus.py').read_text())}
    rng = random.Random(SEED)
    with sqlite3.connect((DATA / 'jev_corpus.sqlite').as_uri() + '?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        if not (OUT / 'holdout_manifest.json').exists():
            strata = [('explicit-heading', 40), ('unlabeled-before-introduction', 20),
                      ('unlabeled-layout-bounded', 20), ('unlabeled-line-run', 20), ('unlabeled-before-contents', 20),
                      ('no page-one abstract or bounded unlabeled summary', 20),
                      ('no bounded unlabeled summary before introduction', 20),
                      ('contents page has no page-one abstract', 20), ('explicit abstract text too short', 20)]
            rows, seen = [], set(old_works)
            for stratum, count in strata:
                field = 'abstract_method' if stratum.startswith(('explicit-', 'unlabeled-')) else 'detail'
                value = stratum if field == 'abstract_method' else 'AbstractUnavailable: ' + stratum
                pool = [dict(x) for x in db.execute(f'SELECT * FROM paper WHERE {field}=? ORDER BY version_id', (value,))]
                rng.shuffle(pool)
                selected = 0
                for row in pool:
                    if row['work_id'] in seen or row['version_id'].removeprefix('arXiv:').rsplit('v', 1)[0] in known:
                        continue
                    seen.add(row['work_id'])
                    row.update(sample_id=f'h{len(rows)+1:03}', stratum=stratum)
                    rows.append(row)
                    selected += 1
                    if selected == count:
                        break
                if selected != count:
                    raise RuntimeError(f'Insufficient fresh cases for {stratum}: {selected}')
            write(OUT / 'holdout_manifest.json', {'seed': SEED, 'scope': 'first physical page',
                'selection': 'diagnostic strata; not population prevalence', 'old_manifest_sha256': digest(OLD / 'manifest.json'),
                'excluded_work_ids': sorted(old_works), 'pdfs': rows})
        holdout = read(OUT / 'holdout_manifest.json')['pdfs']
        if not (OUT / 'pool_manifest.json').exists():
            # One version per work; no categories/titles are populated in this catalog.
            pool = [dict(x) for x in db.execute('SELECT version_id,work_id,source_path FROM paper ORDER BY version_id')]
            rng = random.Random(SEED + 1)
            rng.shuffle(pool)
            targets = [x for x in previous if not x.get('synthetic_from')] + holdout
            seen = {x['work_id'] for x in targets}
            distinct = []
            for row in pool:
                if row['work_id'] in seen:
                    continue
                seen.add(row['work_id'])
                distinct.append(row)
                if len(distinct) == 30000:
                    break
            write(OUT / 'pool_manifest.json', {'seed': SEED + 1, 'targets': targets, 'distractor_pool': distinct})
    for i, row in enumerate(holdout):
        render(row, OUT / 'pages' / row['sample_id'])
        if (i + 1) % 25 == 0:
            print(json.dumps({'holdout_rendered': i + 1}), flush=True)
    # Reference sheets deliberately contain no candidate model output.
    from PIL import Image, ImageDraw
    for first in range(0, len(holdout), 4):
        target = OUT / 'review' / f'sheet_{first+1:03}_{first+4:03}.jpg'
        if target.exists():
            continue
        canvas = Image.new('RGB', (2040, 2860), '#dddddd')
        draw = ImageDraw.Draw(canvas)
        for j, row in enumerate(holdout[first:first+4]):
            img = Image.open(OUT / 'pages' / row['sample_id'] / 'page.png').convert('RGB')
            img.thumbnail((1000, 1380))
            x, y = (j % 2) * 1020, (j // 2) * 1430
            draw.text((x + 12, y + 8), row['sample_id'] + ' ' + row['version_id'], fill='black', font_size=24)
            canvas.paste(img, (x + (1020 - img.width) // 2, y + 42))
        target.parent.mkdir(exist_ok=True)
        canvas.save(target, quality=92)
    pool = read(OUT / 'pool_manifest.json')
    cache = OUT / 'native_pool.jsonl'
    done = {}
    if cache.exists():
        with cache.open(encoding='utf-8') as stream:
            for line in stream:
                value = json.loads(line)
                done[value['work_id']] = value
    todo = [r for r in pool['targets'] + pool['distractor_pool'] if r['work_id'] not in done]
    started = time.monotonic()
    with cache.open('a', encoding='utf-8') as stream, ProcessPoolExecutor(max_workers=4) as workers:
        for i, value in enumerate(workers.map(native_text, todo, chunksize=30)):
            stream.write(json.dumps(value, ensure_ascii=False) + '\n')
            if (i + 1) % 1000 == 0:
                stream.flush()
                print(json.dumps({'pool_read_this_pass': i + 1, 'seconds': round(time.monotonic()-started)}), flush=True)
    print(json.dumps({'prepared': True, 'holdout': len(holdout), 'pool': 30300}), flush=True)


if __name__ == '__main__':
    main()
