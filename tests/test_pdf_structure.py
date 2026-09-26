import hashlib
import json
import unittest
from trace_gc.pdf_structure import assess_document,body_items


class StructureTests(unittest.TestCase):
    def make(self,rows):
        items=[];lines=[]
        for i,(text,label,box) in enumerate(rows):
            items.append({'self_ref':f'#/texts/{i}','text':text,'label':label,'prov':[{'page_no':1,'bbox':dict(l=box[0],t=box[1],r=box[2],b=box[3],coord_origin='TOPLEFT')}]})
            lines.append({'id':i,'text':text,'bbox':box})
        doc={'texts':list(reversed(items)),'body':{'self_ref':'#/body','children':[{'cref':x['self_ref']} for x in items]}}
        return doc,dict(page_size=[600,800],source_sha256='a'*64,page_sha256='b'*64,native_lines=lines)

    def test_tree_order_cross_column_and_interrupted_footnote(self):
        a='We study the transport of evidence across columns and obtain a complete'
        b='description of the measured effect. The experiments confirm the predicted behavior.'
        doc,kwargs=self.make([('Abstract','section_header',[40,200,260,220]),(a,'text',[40,225,270,680]),
            ('Author affiliation and contact.','footnote',[40,710,270,730]),
            (b,'text',[315,100,560,190]),('1 Introduction','section_header',[315,200,560,220])])
        p=assess_document(doc,**kwargs)
        self.assertTrue(p['eligible_for_jev']);self.assertEqual(p['text'],a+' '+b)
        self.assertNotIn('affiliation',p['text'])

    def test_embedded_metadata_is_not_evidence(self):
        text='We evaluate a complete scientific model and find reproducible effects. Index Terms: models, metadata'
        doc,k=self.make([('Abstract. '+text,'text',[40,150,270,300]),('1 Introduction','section_header',[40,330,270,350])])
        p=assess_document(doc,**k)
        self.assertTrue(p['eligible_for_jev']);self.assertTrue(p['text'].endswith('effects.'))

    def test_page_break_is_held_with_partial_text_preserved(self):
        text='We find that the method improves prediction, although the remaining'
        doc,k=self.make([('Abstract','section_header',[40,600,500,625]),(text,'text',[40,630,550,775])])
        p=assess_document(doc,**k)
        self.assertFalse(p['eligible_for_jev']);self.assertEqual(p['text'],text)

    def test_failed_conversion_and_missing_source_are_held(self):
        doc,k=self.make([('Abstract. We report a complete result with supporting experiments.','text',[40,160,550,240]),('1 Introduction','section_header',[40,260,550,280])])
        self.assertEqual(assess_document(doc,**k,conversion_status='partial_success')['status'],'error')
        k['native_lines']=[]
        self.assertFalse(assess_document(doc,**k)['eligible_for_jev'])

    def test_cycle_fails_closed_and_receipt_binds_disposition(self):
        doc,k=self.make([('Abstract. A scientific result.','text',[40,160,550,240])])
        doc['texts'][0]['children']=[{'cref':'#/texts/0'}]
        with self.assertRaises(ValueError):body_items(doc)
        p=assess_document(doc,**k)
        self.assertEqual(p['status'],'error')
        digest=p.pop('assessment_sha256')
        self.assertEqual(digest,hashlib.sha256(json.dumps(p,sort_keys=True).encode()).hexdigest())

    def test_funding_note_cannot_become_unlabeled_abstract(self):
        text='Funding: This research was supported by an international collaborative research programme. We gratefully acknowledge the support of all participating institutions and their staff.'
        doc,k=self.make([(text,'text',[40,150,550,300]),('Keywords: funding','text',[40,310,550,340])])
        p=assess_document(doc,**k,scholarly_abstract=text)
        self.assertFalse(p['eligible_for_jev'])


if __name__=='__main__':unittest.main()
