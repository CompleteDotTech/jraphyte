"""Freeze assistant-selected source spans and queries before prediction review."""
import datetime
import re
from collections import Counter
from .common import OUT, REPO, digest, rows, read, write


def freeze():
    dest=OUT/'reference_freeze.json'
    if dest.exists():
        result=read(dest)
        for name,value in result['files'].items():
            assert digest(OUT/name)==value, name
        return result
    specs=read(REPO/'review/first_page_validation_v2/specs.json')
    queries=read(REPO/'review/first_page_validation_v2/queries.json')
    source_hashes=read(REPO/'review/first_page_validation_v2/source_hashes.json')
    assert set(specs)=={r['sample_id'] for r in rows()}
    labels={}
    for row in rows():
        sid=row['sample_id']; spec=specs[sid]; folder=OUT/'pages'/sid
        receipt=read(folder/'receipt.json')
        assert {k:receipt[k] for k in source_hashes[sid]}==source_hashes[sid], 'Manual reference belongs to a different source: '+sid
        assert digest(folder/'page.pdf')==receipt['page_pdf_sha256']
        assert digest(folder/'page.png')==receipt['image_sha256']
        blocks={b['id']:b for b in read(folder/'reference_blocks.json')}
        selected=[blocks[i] for i in spec['block_ids']]
        text=' '.join(b['text'] for b in selected).strip()
        if spec.get('start_at'):
            assert text.count(spec['start_at'])==1
            text=text[text.index(spec['start_at']):]
        if spec.get('end_before'):
            assert text.count(spec['end_before'])==1
            text=text.split(spec['end_before'])[0].strip()
        if spec.get('end_trim'):
            assert text.endswith(spec['end_trim'])
            text=text[:-len(spec['end_trim'])].strip()
        text=re.sub(r'^\s*A\s*B\s*S\s*T\s*R\s*A\s*C\s*T\b[\s.\-:—]*','',text,flags=re.I).strip()
        assert bool(text)==(spec['status']!='no_abstract_text'),sid
        assert 'arXiv:' not in text,sid
        labels[sid]={**spec,'text':text,'source_sha256':receipt['source_sha256'],
            'page_sha256':receipt['page_pdf_sha256'],'selected_blocks':selected}
    assert set(queries)==set(read(OUT/'query_targets.json')['sample_ids'])
    by_id={r['sample_id']:r for r in rows()}
    fresh=[{'query_id':'v2_'+sid,'target_id':by_id[sid]['index_id'],'text':text,'cohort':'fresh30','source_id':sid} for sid,text in queries.items()]
    write(OUT/'review/specs.json',specs);write(OUT/'labels.json',labels)
    write(OUT/'fresh_queries.json',{'queries':fresh,'reviewer':'assistant','independent_human_review':'outstanding'})
    result={'frozen_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'reviewer':'assistant','independent_human_review':'outstanding',
        'method':'Source images and native blocks reviewed before opening fresh predictions. Selector implementation draft preceded source review; regression tuning follows source review. This is not an independent blind evaluation.',
        'math_note':'Native linear text is the scoring reference; character agreement does not certify mathematical notation fidelity.',
        'counts':dict(Counter(x['status'] for x in labels.values())),
        'files':{n:digest(OUT/n) for n in ['review/specs.json','labels.json','fresh_queries.json','holdout_manifest.json']}}
    write(dest,result);return result


if __name__=='__main__':print(freeze())
