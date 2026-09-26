"""Run the unchanged page-one conversion configurations on uncached inputs."""
import argparse
import sys
import time
import xml.etree.ElementTree as ET
from .common import DATA, OUT, cache, digest, folder, rows, verify_protocol, write


def main():
    p = argparse.ArgumentParser()
    p.add_argument('method', choices=['docling', 'grobid', 'current'])
    args = p.parse_args()
    verify_protocol()
    if args.method == 'docling':
        import torch
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions
        from docling.datamodel.accelerator_options import AcceleratorOptions, AcceleratorDevice
        torch.set_num_threads(4)
        opts = PdfPipelineOptions(do_ocr=True, do_table_structure=False)
        opts.ocr_options = RapidOcrOptions(backend='torch')
        opts.accelerator_options = AcceleratorOptions(num_threads=4, device=AcceleratorDevice.CPU)
        opts.document_timeout = 180
        converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})
        write(OUT / 'docling/configuration.json', opts.model_dump(mode='json'))
    elif args.method == 'grobid':
        import requests
        response = requests.get('http://127.0.0.1:18070/api/version', timeout=30)
        response.raise_for_status()
        write(OUT / 'grobid/configuration.json', {'version':response.text, 'consolidateHeader':0, 'input':'isolated first-page PDF'})
    else:
        sys.path.insert(0, str(DATA))
        from run_jev_corpus import abstract_from_pdf, AbstractUnavailable
        import pymupdf
        write(OUT / 'baselines/environment.json', {'python':sys.version, 'pymupdf':pymupdf.__version__, 'worker_sha256':digest(DATA / 'run_jev_corpus.py')})
    method = 'baselines/current' if args.method == 'current' else args.method
    for row in rows():
        sid = row['sample_id']
        dest = cache(method, sid)
        if dest.exists():
            continue
        page = folder(sid) / 'page.pdf'
        started = time.perf_counter()
        try:
            if args.method == 'docling':
                result = converter.convert(page)
                write(OUT / 'docling' / (sid + '.document.json'), result.document.model_dump(mode='json'))
                result = {'status':str(result.status)}
            elif args.method == 'grobid':
                with page.open('rb') as stream:
                    response = requests.post('http://127.0.0.1:18070/api/processHeaderDocument', files={'input':('page.pdf',stream,'application/pdf')}, data={'consolidateHeader':'0'}, timeout=180)
                response.raise_for_status()
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.with_suffix('.xml').write_text(response.text, encoding='utf-8')
                root = ET.fromstring(response.content) if response.content else None
                abstracts = root.findall('.//{http://www.tei-c.org/ns/1.0}abstract') if root is not None else []
                result = {'status':'success', 'text':' '.join(' '.join(a.itertext()) for a in abstracts)}
            else:
                try:
                    _, text, name = abstract_from_pdf(row['source_path'])
                    result = {'status':'complete', 'eligible_for_jev':True, 'method':name, 'text':text}
                except AbstractUnavailable as exc:
                    result = {'status':'absent', 'eligible_for_jev':False, 'text':'', 'reasons':[str(exc)]}
        except Exception as exc:
            result = {'status':'error', 'text':'', 'eligible_for_jev':False, 'error':type(exc).__name__+': '+str(exc)[:300]}
        result.update(seconds=time.perf_counter()-started, page_sha256=digest(page))
        write(dest, result)
        print({'converted':sid, 'method':args.method, 'seconds':round(result['seconds'],2), 'status':result['status']}, flush=True)


if __name__ == '__main__':
    main()
