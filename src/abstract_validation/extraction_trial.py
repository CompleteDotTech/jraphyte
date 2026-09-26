"""Freeze, convert, and evaluate optional Docling extraction without corpus writes."""
from __future__ import annotations

import argparse
import json
import sys
import time

from trace_gc.pdf_evidence import assess_first_page, reprocessing_action
from .common import DATA, OLD, OUT, REPO, digest, read, write


def items_from_document(document):
    return [{'text': x.get('text', ''), 'orig': x.get('orig', ''), 'label': x['label'], 'prov': x.get('prov', []), 'ref': x['self_ref']}
            for x in document.get('texts', []) if x.get('text') or (x.get('label') == 'formula' and x.get('orig'))]


def assess(row, folder, document, status='success'):
    return assess_first_page(items_from_document(document), page_size=row['page_size'],
                            page_sha256=row['page_pdf_sha256'], source_sha256=row['source_sha256'],
                            native_lines=read(folder / 'lines.json'), conversion_status=status)


def development():
    sys.path.insert(0, str(DATA / 'src/sample_comparison'))
    from evaluate import compare
    labels = read(OLD / 'labels.json')
    outcomes = []
    for row in read(OLD / 'manifest.json')['pdfs']:
        sid = row['sample_id']
        cached = OLD / 'results/docling_selector_v2' / (sid + '.document.json')
        if not cached.exists():
            cached = OLD / 'results/docling' / (sid + '.document.json')
        document = read(cached)
        result = assess(row, OLD / 'pages' / sid, document)
        write(OUT / 'development' / (sid + '.json'), result)
        comparison = compare(result['text'], labels[sid]['text'])
        outcomes.append({'id': sid, 'gold': labels[sid]['status'], 'predicted': result['status'],
                         'eligible': result['eligible_for_jev'], 'reasons': result['reasons'], **comparison})
    write(OUT / 'development_metrics.json', outcomes)
    from collections import Counter
    print('states', dict(Counter(x['predicted'] for x in outcomes)))
    print('example comparison', outcomes[0])
    for x in outcomes:
        if x['gold'] == 'complete' and not x.get('text_match_98', False) or x['gold'] != 'complete' and x['eligible']:
            print(json.dumps(x))


def freeze():
    dest = OUT / 'protocol.json'
    if dest.exists():
        raise RuntimeError('Protocol already frozen; create another experiment to revise')
    write(dest, {'selector_sha256': digest(REPO / 'trace_gc/pdf_evidence.py'),
        'adapter_sha256': digest(__file__), 'holdout_manifest_sha256': digest(OUT / 'holdout_manifest.json'),
        'reference_policy': 'assistant review of first-page source before viewing holdout candidate outputs; no independent human review',
        'primary_metric': 'at least 98 percent ordered canonical-character precision and recall for complete references',
        'admission_gate': 'report precision, recall, completeness confusion; no corpus promotion without review of failures',
        'scope': '200 fresh works, first physical page, diagnostic strata not representative prevalence',
        'google_project': 'crossword-489306', 'google_reservation_cap_usd': 12.0,
        'google_expected_incremental_usd': 1.16, 'jev_calls': 0, 'corpus_database_access': 'read-only'})


def convert():
    protocol = read(OUT / 'protocol.json')
    if protocol['selector_sha256'] != digest(REPO / 'trace_gc/pdf_evidence.py'):
        raise RuntimeError('Selector changed after holdout freeze')
    import torch
    torch.set_num_threads(4)
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions
    from docling.datamodel.accelerator_options import AcceleratorOptions, AcceleratorDevice
    options = PdfPipelineOptions(do_ocr=True, do_table_structure=False)
    options.ocr_options = RapidOcrOptions(backend='torch')
    options.accelerator_options = AcceleratorOptions(num_threads=4, device=AcceleratorDevice.CPU)
    options.document_timeout = 180
    converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})
    write(OUT / 'docling_configuration.json', options.model_dump(mode='json'))
    for row in read(OUT / 'holdout_manifest.json')['pdfs']:
        sid = row['sample_id']
        folder = OUT / 'pages' / sid
        dest = OUT / 'docling' / (sid + '.json')
        if dest.exists():
            continue
        started = time.monotonic()
        try:
            converted = converter.convert(folder / 'page.pdf')
            document = converted.document.model_dump(mode='json')
            write(OUT / 'docling' / (sid + '.document.json'), document)
            result = assess(read(folder / 'receipt.json'), folder, document, str(converted.status))
        except Exception as exc:
            result = {'status': 'error', 'text': '', 'eligible_for_jev': False, 'reasons': [type(exc).__name__ + ': ' + str(exc)[:300]]}
        result['seconds'] = time.monotonic()-started
        write(dest, result)
        # Progress intentionally omits candidate content and its disposition.
        print(json.dumps({'converted': sid, 'seconds': round(result['seconds'], 2)}), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('stage', choices=['development', 'freeze', 'convert'])
    stage = p.parse_args().stage
    {'development': development, 'freeze': freeze, 'convert': convert}[stage]()
