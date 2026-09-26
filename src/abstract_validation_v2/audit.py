"""Exercise the real source-review gate on the new pages; make zero API calls."""
import sys
from collections import Counter
from trace_gc.pdf_admission import prepare_jev_request,source_review
from .common import DATA, OUT, digest, read, write, rows
from .references import freeze


def main():
    frozen=freeze();labels=read(OUT/'labels.json');plans=[]
    visual=read(OUT/'visual_audit.json')
    visual_sha=digest(OUT/'visual_audit.json')
    transcription_holds={r['id']:r for r in visual['cases'] if r['hold_source_transcription']}
    sys.path.insert(0,str(DATA))
    import run_jev_corpus as current
    for row in rows():
        sid=row['sample_id'];folder=OUT/'pages'/sid;receipt=read(folder/'receipt.json');label=labels[sid]
        candidate=read(OUT/'assessments/structure_v2'/(sid+'.json'))
        joined=' '.join(b['text'] for b in label['selected_blocks'])
        start=joined.index(label['text']) if label['text'] else 0
        review=source_review(source_sha256=receipt['source_sha256'],page_sha256=receipt['page_pdf_sha256'],
            image_sha256=receipt['image_sha256'],page_size=receipt['page_size'],
            blocks=read(folder/'reference_blocks.json'),selected_ids=label['block_ids'],start=start,end=start+len(label['text']),
            status={'partial_on_page_one':'partial','no_abstract_text':'absent'}.get(label['status'],label['status']),
            reviewer='assistant source-only boundary review',reviewer_kind='assistant',reviewed_at=frozen['frozen_at'],
            candidate_assessment_sha256=candidate['assessment_sha256'])
        kwargs={'paper_id':row['version_id'],'model':current.MODEL,'questions':current.QUESTIONS,
            'current_source_sha256':digest(row['source_path']),'current_page_sha256':digest(folder/'page.pdf'),
            'current_image_sha256':digest(folder/'page.png'),'max_characters':current.MAX_ABSTRACT_CHARS,'max_request_bytes':current.MAX_REQUEST_BYTES}
        assert not prepare_jev_request(**kwargs)['admitted']
        hold=transcription_holds.get(sid)
        if hold:
            assert hold['source_sha256']==kwargs['current_source_sha256']
            assert hold['page_sha256']==kwargs['current_page_sha256']
            assert hold['image_sha256']==kwargs['current_image_sha256']
            result={'admitted':False,'reason':'visual_transcription_requires_review',
                'visual_audit_sha256':visual_sha,'detail':hold['finding']}
        else:
            result=prepare_jev_request(**kwargs,review=review)
        write(OUT/'reviewed_evidence'/(sid+'.json'),review)
        request_path=OUT/'prepared_requests'/(sid+'.json')
        if result['admitted']:
            write(request_path,result)
        elif request_path.exists():
            # Preserve the previous draft and replace its active path with a hold.
            # These drafts have never been sent to Jev.
            previous=read(request_path)
            if previous.get('admitted'):
                write(OUT/'superseded_requests'/(sid+'.'+digest(request_path)+'.json'),previous)
            write(request_path,result)
        plans.append({'id':sid,'reference_status':label['status'],'candidate_eligible':candidate['eligible_for_jev'],
            'reviewed_request_prepared':result['admitted'],'reason':result.get('reason'),'request_bytes':result.get('request_bytes'),
            'request_sha256':result.get('request_sha256'),'review_sha256':review['review_sha256']})
    summary={'pages':len(plans),'candidate_only_admitted':0,'reviewed_requests_prepared':sum(p['reviewed_request_prepared'] for p in plans),
        'holds':dict(Counter(p['reason'] for p in plans if not p['reviewed_request_prepared'])),
        'visual_audit_sha256':visual_sha,
        'fresh_transcription_holds':visual['fresh_request_holds'],
        'prior_run_execution_holds':visual['prior_run_execution_holds'],
        'jev_calls':0,'database_writes':0,'reviewer':'assistant; independent human review outstanding',
        'execution_policy':'Prepared only, not scientifically certified. Execution must recheck current checkpoint, review, visual transcription holds and source hashes, reserve against the existing $50 corpus ledger, and preserve historical attempts.','rows':plans}
    write(OUT/'review_gate_audit.json',summary);print({k:v for k,v in summary.items() if k!='rows'})


if __name__=='__main__':main()
