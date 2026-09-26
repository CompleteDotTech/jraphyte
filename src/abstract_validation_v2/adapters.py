"""Explicit adapters: OCR remains distinct from native source projection."""
import re
from trace_gc.pdf_structure import assess_document,seal
from trace_gc.pdf_evidence import canonical


def plain(text):
    # Formatting only. Retain mathematical commands so disagreement stays visible.
    return re.sub(r'(?m)^\s*#{1,6}\s*','',text).replace('**','').replace('__','').strip()


def document(items):
    return {'texts':items,'body':{'self_ref':'#/body','children':[{'cref':x['self_ref']} for x in items]}}


def item(index,text,label,boxes):
    return {'self_ref':f'#/texts/{index}','text':plain(text),'label':label,
        'prov':[{'page_no':1,'bbox':{'l':b[0],'t':b[1],'r':b[2],'b':b[3],'coord_origin':'TOPLEFT'}} for b in boxes]}


def mineru_document(raw,size):
    labels={'title':'section_header','page_number':'page_footer','header':'page_header','footer':'page_footer',
        'aside_text':'page_header','image':'picture','image_caption':'caption','table_caption':'caption','table':'table','footnote':'footnote','equation':'formula'}
    items=[]
    for block in raw.get('blocks',[]):
        if not block.get('content'):continue
        b=block['bbox'];box=[b[0]*size[0],b[1]*size[1],b[2]*size[0],b[3]*size[1]]
        items.append(item(len(items),block['content'],labels.get(block['type'],'text'),[box]))
    return document(items)


def olmocr_assess(raw,**kwargs):
    text=raw.get('raw_text','')
    # Official prompt returns a YAML header followed by page markdown.
    if text.lstrip().startswith('---'):
        parts=text.split('---',2)
        text=parts[2] if len(parts)==3 else ''
    parts=re.split(r'\n\s*\n|\n(?=#{1,6}\s)',text)
    items=[];unanchored=[]
    for part in parts:
        if not part.strip():continue
        value=plain(part);target=canonical(value)
        matched=[line for line in kwargs['native_lines'] or [] if len(canonical(line['text']))>=8 and canonical(line['text']) in target]
        # These boxes are native alignment estimates, not model-supplied coordinates.
        boxes=[line['bbox'] for line in matched]
        if not boxes:
            unanchored.append(len(items));boxes=[[0,0,*kwargs['page_size']]]
        label='section_header' if re.match(r'^\s*#{1,6}\s',part) else 'text'
        if re.match(r'^(?:arXiv:|<!--)',value):label='page_header'
        items.append(item(len(items),value,label,boxes))
    result=assess_document(document(items),**kwargs,conversion_status=raw['status'])
    selected={s['ref'] for s in result['spans']}
    if any(f'#/texts/{i}' in selected for i in unanchored):
        result.update(status='uncertain',eligible_for_jev=False,reasons=result['reasons']+['ocr_region_without_native_alignment'])
    result['coordinate_source']='estimated by matching model paragraph lines to native text; not predicted by olmOCR'
    result['unanchored_paragraphs']=unanchored
    return seal(result)
