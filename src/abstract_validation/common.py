from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DATA = Path(os.environ.get('TRACE_GC_TEST_DATA_ROOT') or REPO.parent / 'TRACE-GC_RealPaper_Test').resolve()
OLD = DATA / 'sample_comparison_100'
OUT = DATA / 'validation_200_10k'


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def reference_blocks(page):
    """Native text blocks for manual source review, with stable text-only IDs."""
    blocks = [b for b in page.get_text('dict', sort=True)['blocks'] if b['type'] == 0]
    return [{'id': i, 'bbox': list(b['bbox']),
             'text': ' '.join(''.join(s['text'] for s in line['spans']) for line in b['lines'])}
            for i, b in enumerate(blocks)]


def render(row, folder):
    import fitz
    folder.mkdir(parents=True, exist_ok=True)
    if (folder / 'receipt.json').exists():
        return read(folder / 'receipt.json')
    source = Path(row['source_path'])
    with fitz.open(source) as document:
        page = document[0]
        one = fitz.open()
        one.insert_pdf(document, from_page=0, to_page=0)
        one.save(folder / 'page.pdf')
        one.close()
        page.get_pixmap(dpi=120).save(folder / 'page.png')
        lines = []
        for block in page.get_text('dict', sort=True)['blocks']:
            for line in block.get('lines', []):
                lines.append({'id': len(lines), 'bbox': list(line['bbox']),
                              'text': ''.join(s['text'] for s in line['spans'])})
        write(folder / 'lines.json', lines)
        write(folder / 'reference_blocks.json', reference_blocks(page))
        (folder / 'lines.txt').write_text('\n'.join(f"{x['id']:03}: {x['text']}" for x in lines), encoding='utf-8')
        receipt = {**row, 'source_sha256': digest(source), 'page_pdf_sha256': digest(folder / 'page.pdf'),
                   'image_sha256': digest(folder / 'page.png'), 'page_size': [page.rect.width, page.rect.height],
                   'native_characters': sum(len(x['text']) for x in lines), 'dpi': 120, 'physical_page': 1}
    write(folder / 'receipt.json', receipt)
    return receipt
