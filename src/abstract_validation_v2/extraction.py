"""Score proposals separately from the source-review admission gate."""
import argparse
import datetime
import re
import sys
from collections import Counter
from .common import DATA, OUT, PREVIOUS, REPO, digest, read, write
from .convert import cases
from .references import freeze
from src.abstract_validation.evaluate import compare
from trace_gc.pdf_structure import assess_document
from trace_gc.pdf_evidence import assess_first_page


def baseline():
    sys.path.insert(0,str(DATA))
    from run_jev_corpus import abstract_from_pdf,AbstractUnavailable
    import pymupdf
    for row,folder in cases('fresh'):
        sid=row['sample_id'];dest=OUT/'baselines/current'/(sid+'.json')
        if dest.exists():continue
        try:
            _,text,method=abstract_from_pdf(row['source_path'])
            result={'text':text,'method':method,'status':'complete','eligible_for_jev':bool(text)}
        except AbstractUnavailable as exc:
            result={'text':'','status':'absent','eligible_for_jev':False,'reasons':[str(exc)]}
        write(dest,result)
    write(OUT/'baselines/environment.json',{'python':sys.version,'pymupdf':pymupdf.__version__,'worker_sha256':digest(DATA/'run_jev_corpus.py')})


def frozen():
    freeze()
    paths=['trace_gc/pdf_structure.py','src/abstract_validation_v2/extraction.py','src/abstract_validation_v2/adapters.py']
    dest=OUT/'extraction_protocol.json'
    hashes={p:digest(REPO/p) for p in paths}
    if dest.exists():
        result=read(dest);assert result['files']==hashes,'Extraction changed after protocol freeze';return result
    result={'frozen_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':hashes,
        'threshold':'ordered canonical alphanumeric precision AND recall >=98%; complete source reference required for correct proposal',
        'scope':'regression200; new100; fallback paired40 subset',
        'promotion':'experimental proposals only; production source-review gate unchanged'}
    write(dest,result);return result


def prediction(method,sid,folder):
    receipt=read(folder/'receipt.json');native=read(folder/'lines.json')
    kwargs={'page_size':receipt['page_size'],'source_sha256':receipt['source_sha256'],
        'page_sha256':receipt['page_pdf_sha256'],'native_lines':native}
    old=sid.startswith('h')
    if method=='current':
        pred=read((PREVIOUS if old else OUT)/'baselines/current'/(sid+'.json'))
        return {**pred,'status':'complete' if pred['text'] else 'absent','eligible_for_jev':bool(pred['text'])}
    if method=='geometry_v1':
        if old:return read(PREVIOUS/'docling'/(sid+'.json'))
        raw=read(OUT/'docling'/(sid+'.document.json'))
        return assess_first_page(raw['texts'],**kwargs,conversion_status=read(OUT/'docling'/(sid+'.json'))['status'])
    scholarly=read(OUT/'grobid'/(sid+'.json')).get('text','')
    if method=='grobid':
        return {'text':scholarly.strip(),'status':'complete' if scholarly.strip() else 'absent','eligible_for_jev':bool(scholarly.strip())}
    if method=='structure_v2':
        raw=read((PREVIOUS if old else OUT)/'docling'/(sid+'.document.json'))
        status='success' if old else read(OUT/'docling'/(sid+'.json'))['status']
        return assess_document(raw,**kwargs,scholarly_abstract=scholarly,conversion_status=status)
    from .adapters import mineru_document,olmocr_assess
    raw=read(OUT/method/(sid+'.json'))
    assert raw['page_sha256']==kwargs['page_sha256']
    if method=='mineru':
        return assess_document(mineru_document(raw,kwargs['page_size']),**kwargs,scholarly_abstract=scholarly,conversion_status=raw['status'])
    return olmocr_assess(raw,**kwargs,scholarly_abstract=scholarly)


def summary(details):
    complete=[d for d in details if d['gold']=='complete'];proposed=[d for d in details if d['eligible']]
    good=[d for d in proposed if d['gold']=='complete' and d['text_match_98']]
    return {'pages':len(details),'complete_available':len(complete),
        'text_recovered_98':sum(d['text_match_98'] for d in complete),
        'proposed':len(proposed),'correct_proposals_98':len(good),
        'proposal_precision_98':len(good)/len(proposed) if proposed else None,
        'correct_proposal_recall_98':len(good)/len(complete) if complete else None,
        'wrong_proposals':[d['id'] for d in proposed if d not in good],
        'absent_proposed':[d['id'] for d in proposed if d['gold']=='no_abstract_text'],
        'partial_proposed':[d['id'] for d in proposed if d['gold']=='partial_on_page_one'],
        'states':dict(Counter(d['predicted'] for d in details)),'details':details}


def evaluate(cohort,methods):
    if cohort=='fresh':frozen()
    labels=read((PREVIOUS if cohort=='regression' else OUT)/'labels.json');metrics={}
    for method in methods:
        details=[]
        for row,folder in cases(cohort):
            sid=row['sample_id']
            if method in ('mineru','olmocr') and sid not in read(OUT/'fallback_manifest.json')['ids']:continue
            pred=prediction(method,sid,folder);gold=labels[sid]
            write(OUT/'assessments'/method/(sid+'.json'),pred)
            details.append({'id':sid,'gold':gold['status'],'predicted':pred['status'],
                'eligible':pred['eligible_for_jev'],'characters':len(pred['text']),'reasons':pred.get('reasons',[]),
                **compare(pred['text'],gold['text'])})
        metrics[method]=summary(details)
        print(cohort,method,{k:v for k,v in metrics[method].items() if k!='details'},flush=True)
    destination=OUT/('extraction_'+cohort+'.json')
    previous=read(destination) if destination.exists() else {}
    write(destination,{**previous,**metrics})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['baseline','freeze','regression','fresh']);p.add_argument('--methods',nargs='+',default=['current','geometry_v1','grobid','structure_v2']);a=p.parse_args()
    if a.stage=='baseline':baseline()
    elif a.stage=='freeze':print(frozen())
    else:evaluate(a.stage,a.methods)
