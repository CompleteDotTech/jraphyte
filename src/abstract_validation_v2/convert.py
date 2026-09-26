"""Cache source-only page conversions. Predictions are assessed separately."""
import argparse
import time
import xml.etree.ElementTree as ET
from .common import OUT, PREVIOUS, rows, page_folder, read, write


def cases(cohort):
    if cohort=='regression':
        return [(r,PREVIOUS/'pages'/r['sample_id']) for r in read(PREVIOUS/'holdout_manifest.json')['pdfs']]
    return [(r,page_folder(r)) for r in rows()]


def main():
    p=argparse.ArgumentParser();p.add_argument('method',choices=['docling','grobid']);p.add_argument('--cohort',default='fresh',choices=['fresh','regression']);args=p.parse_args()
    out=OUT/args.method
    if args.method=='docling':
        import torch
        torch.set_num_threads(4)
        from docling.document_converter import DocumentConverter,PdfFormatOption
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions,RapidOcrOptions
        from docling.datamodel.accelerator_options import AcceleratorOptions,AcceleratorDevice
        opts=PdfPipelineOptions(do_ocr=True,do_table_structure=False)
        opts.ocr_options=RapidOcrOptions(backend='torch')
        opts.accelerator_options=AcceleratorOptions(num_threads=4,device=AcceleratorDevice.CPU)
        opts.document_timeout=180
        converter=DocumentConverter(format_options={InputFormat.PDF:PdfFormatOption(pipeline_options=opts)})
        write(out/'configuration.json',opts.model_dump(mode='json'))
    else:
        import requests
        version=requests.get('http://127.0.0.1:18070/api/version',timeout=30);version.raise_for_status()
        write(out/'configuration.json',{'version':version.text,'consolidateHeader':0,'input':'isolated first-page PDF'})
    for row,folder in cases(args.cohort):
        sid=row['sample_id'];dest=out/(sid+'.json')
        if dest.exists():continue
        started=time.perf_counter()
        try:
            if args.method=='docling':
                converted=converter.convert(folder/'page.pdf')
                write(out/(sid+'.document.json'),converted.document.model_dump(mode='json'))
                result={'status':str(converted.status)}
            else:
                with (folder/'page.pdf').open('rb') as stream:
                    response=requests.post('http://127.0.0.1:18070/api/processHeaderDocument',files={'input':('page.pdf',stream,'application/pdf')},data={'consolidateHeader':'0'},timeout=180)
                response.raise_for_status()
                out.mkdir(exist_ok=True)
                (out/(sid+'.xml')).write_text(response.text,encoding='utf-8')
                root=ET.fromstring(response.content) if response.content else None
                abstracts=root.findall('.//{http://www.tei-c.org/ns/1.0}abstract') if root is not None else []
                result={'text':' '.join(' '.join(x.itertext()) for x in abstracts),'status':'success'}
        except Exception as exc:
            result={'status':'error','text':'','error':type(exc).__name__+': '+str(exc)[:300]}
        result['seconds']=time.perf_counter()-started
        write(dest,result)
        print({'converted':sid,'method':args.method,'seconds':round(result['seconds'],2)},flush=True)


if __name__=='__main__':main()
