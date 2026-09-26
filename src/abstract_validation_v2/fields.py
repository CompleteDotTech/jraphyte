"""Query-independent retrieval fields; these are not admitted graph evidence."""
import json
import re
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from .common import DATA, OUT, PREVIOUS, read, write


def extract(row):
    import pymupdf as fitz
    sys.path.insert(0,str(DATA))
    from run_jev_corpus import abstract_from_pdf,AbstractUnavailable
    result={'id':row['sample_id'],'title':'','abstract':'','body':'','abstract_method':None}
    try:
        with fitz.open(row['source_path']) as pdf:
            page=pdf[0]
            blocks=page.get_text('dict',sort=True)['blocks']
            textblocks=[]
            for b in blocks:
                if b['type']!=0:continue
                spans=[s for line in b['lines'] for s in line['spans'] if s['text'].strip()]
                text=' '.join(''.join(s['text'] for s in line['spans']) for line in b['lines']).strip()
                if text:
                    textblocks.append({'text':text,'bbox':b['bbox'],'size':max((s['size'] for s in spans),default=0)})
            eligible=[b for b in textblocks if b['bbox'][1]<page.rect.height*.45 and len(b['text'])>12 and not re.search(r'arXiv:|@|^(?:Preprint|Prepared for|Draft version|Running Title)',b['text'],re.I)]
            if eligible:
                largest=max(b['size'] for b in eligible)
                titles=[b['text'] for b in eligible if b['size']>=largest*.92]
                result['title']=' '.join(titles)[:600]
            result['body']=' '.join(b['text'] for b in textblocks)
        try:
            _,result['abstract'],result['abstract_method']=abstract_from_pdf(row['source_path'])
        except AbstractUnavailable:
            pass
    except Exception as exc:
        result['error']=type(exc).__name__+': '+str(exc)[:100]
    return result


def main():
    cache=OUT/'retrieval_fields.jsonl'
    completed={}
    if cache.exists():
        with cache.open(encoding='utf-8') as stream:
            for line in stream:
                row=json.loads(line);completed[row['id']]=row
    rows=read(PREVIOUS/'retrieval_manifest.json')['pdfs']
    todo=[r for r in rows if r['sample_id'] not in completed]
    with cache.open('a',encoding='utf-8') as stream,ProcessPoolExecutor(max_workers=4) as pool:
        for i,result in enumerate(pool.map(extract,todo,chunksize=25)):
            stream.write(json.dumps(result,ensure_ascii=False)+'\n')
            if (i+1)%500==0:stream.flush();print({'fields_written':i+1+len(completed)},flush=True)
    print({'total':len(rows)},flush=True)


if __name__=='__main__':main()
