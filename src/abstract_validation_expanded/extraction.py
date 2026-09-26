"""Apply frozen methods to the expanded paired sample; never call an API."""
import argparse
from .common import OUT, cache, folder, read, rows, verify_protocol, write
from .references import freeze
from src.abstract_validation.evaluate import compare
from src.abstract_validation_v2.extraction import summary
from src.abstract_validation_v2.adapters import mineru_document, olmocr_assess
from trace_gc.pdf_evidence import assess_first_page
from trace_gc.pdf_structure import assess_document

METHODS = ['current', 'geometry_v1', 'grobid', 'structure_v2', 'mineru', 'olmocr']


def prediction(method, sid):
    page = folder(sid); receipt = read(page / 'receipt.json')
    kwargs = {'page_size': receipt['page_size'], 'source_sha256': receipt['source_sha256'],
              'page_sha256': receipt['page_pdf_sha256'], 'native_lines': read(page / 'lines.json')}
    if method == 'current':
        return read(cache('baselines/current', sid))
    grobid = read(cache('grobid', sid))
    scholarly = grobid.get('text', '')
    if method == 'grobid':
        return {**grobid, 'text': scholarly.strip(), 'status': 'complete' if scholarly.strip() else ('error' if grobid['status']=='error' else 'absent'), 'eligible_for_jev': bool(scholarly.strip())}
    source = 'docling' if method in ('geometry_v1', 'structure_v2') else method
    raw = read(cache(source, sid))
    if raw.get('page_sha256'):
        assert raw['page_sha256'] == kwargs['page_sha256'], sid
    if raw['status'] == 'error':
        return {'status': 'error', 'text': '', 'eligible_for_jev': False, 'reasons': [raw.get('error','Conversion error')]}
    if source == 'docling':
        document = read(cache('docling', sid, '.document.json'))
        if method == 'geometry_v1':
            return assess_first_page(document['texts'], **kwargs, conversion_status=raw['status'])
        return assess_document(document, **kwargs, scholarly_abstract=scholarly, conversion_status=raw['status'])
    if method == 'mineru':
        return assess_document(mineru_document(raw, kwargs['page_size']), **kwargs, scholarly_abstract=scholarly, conversion_status=raw['status'])
    return olmocr_assess(raw, **kwargs, scholarly_abstract=scholarly)


def evaluate(methods):
    verify_protocol(); freeze()
    labels = read(OUT / 'labels.json')
    path = OUT / 'extraction_metrics.json'
    metrics = read(path) if path.exists() else {}
    for method in methods:
        details = []
        for row in rows():
            sid = row['sample_id']; pred = prediction(method, sid); gold = labels[sid]
            write(OUT / 'assessments' / method / (sid+'.json'), pred)
            details.append({'id': sid, 'gold': gold['status'], 'predicted': pred['status'],
                            'eligible': pred['eligible_for_jev'], 'characters': len(pred['text']),
                            'math_review_required': gold.get('math_review_required',False) or sid in ['f026','f033'],
                            'reasons': pred.get('reasons',[]), **compare(pred['text'], gold['text'])})
        metrics[method] = {}
        for group, selected in [('prior100',details[:100]),('added100',details[100:]),('combined200',details)]:
            metrics[method][group] = summary(selected)
            metrics[method][group]['boundary_and_98_correct_proposals'] = sum(d['eligible'] and d['gold']=='complete' and d['boundary_and_98_match'] for d in selected)
            print(method, group, {k:v for k,v in metrics[method][group].items() if k not in ['details','states']}, flush=True)
        write(path, metrics)
    return metrics


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--methods', nargs='+', choices=METHODS, default=METHODS)
    evaluate(p.parse_args().methods)
