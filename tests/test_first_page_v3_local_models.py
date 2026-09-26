"""Offline model-boundary tests; fake scores are not model accuracy evidence."""
import json
import tempfile
import unittest
from pathlib import Path

from trace_gc.pdf_source_v3 import digest
from src.abstract_validation_v3.common import file_digest
from src.abstract_validation_v3.local_reranker import verify_snapshot
from src.abstract_validation_v3.retrieval_experiment import evaluate
from test_first_page_v3_differential import paired
from test_pdf_source_v3 import line


class LocalModelBoundaries(unittest.TestCase):
    def test_source_proposal_cannot_substitute_for_publication_review(self):
        from trace_gc.pdf_admission import prepare_jev_request
        from test_pdf_source_v3 import assess, ABSTRACT_TEXT
        proposal=assess([line(0,'Abstract '+ABSTRACT_TEXT),line(1,'1 Introduction',140)])
        self.assertTrue(proposal['proposed'])
        args=dict(paper_id='fixture', model='not-called', questions={},
                  current_source_sha256='a'*64, current_page_sha256='b'*64, current_image_sha256='c'*64)
        self.assertEqual(prepare_jev_request(**args)['reason'],'source_review_required')
        self.assertFalse(prepare_jev_request(**args,review=proposal)['admitted'])

    def fixture_snapshot(self, root):
        root.mkdir()
        (root/'config.json').write_text('{"num_labels":1}')
        # Integrity fixture only; never passed to a model loader.
        (root/'model.safetensors').write_bytes(b'not real weights')
        return {'model_revision':'a'*40,'files':{p.name:file_digest(p) for p in root.iterdir()}}

    def test_local_model_snapshot_hashes_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'snapshot';manifest=self.fixture_snapshot(root)
            receipt=verify_snapshot(root,manifest)
            self.assertEqual(receipt['local_files_verified'],2)
            self.assertFalse(receipt['upstream_revision_independently_verified'])
            (root/'config.json').write_text('{}')
            with self.assertRaises(ValueError):verify_snapshot(root,manifest)

    def test_no_model_download_or_pickle_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'missing'
            with self.assertRaises(ValueError):verify_snapshot(root,{'model_revision':'a'*40,'files':{}})
            manifest=self.fixture_snapshot(root)
            (root/'pytorch_model.bin').write_bytes(b'not real weights')
            with self.assertRaises(ValueError):verify_snapshot(root,manifest)

    def test_model_revision_and_symlink_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'snapshot';manifest=self.fixture_snapshot(root)
            with self.assertRaises(ValueError):verify_snapshot(root,{**manifest,'model_revision':'main'})
            try:
                (root/'unbound.json').symlink_to(root/'config.json')
            except OSError as exc:
                if getattr(exc, "winerror", None) == 1314:
                    self.skipTest("Windows symlink privilege unavailable")
                raise
            with self.assertRaises(ValueError):verify_snapshot(root,manifest)

    def test_local_scorer_gets_candidates_only_and_receipt_binds_pairs(self):
        fields={'one':{'title':'Layered transport','body':'controlled transport measurements'},
                'two':{'title':'Unrelated','body':'a different area'},
                'cover':{'title':'','body':'','indexable':False}}
        calls=[]
        class FakeLocal:
            def score(self,query,docs):
                calls.append((query,docs))
                return {'scores':[2.0 for _ in docs],'model_revision':'b'*40,'model_snapshot_sha256':'c'*64}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            r=evaluate({'fields':fields,'fields_sha256':digest(fields)},
                       [{'query_id':'q1','text':'transport','target_id':'one'}],root,local_scorer=FakeLocal())
            self.assertEqual(r['status'],'COMPLETE')
            self.assertEqual(r['reranker_metrics']['candidate_coverage_count'],1)
            self.assertEqual(len(calls[0][1]),1)
            self.assertNotIn('a different area',calls[0][1])
            self.assertEqual(calls[0][0],'transport')
            saved=json.loads((root/'local_scores/q1.json').read_text())
            self.assertEqual(saved['pairs_sha256'],digest([['transport',fields['one']['title']+' '+fields['one']['body']]]))

    def test_ended_sentence_cannot_blindly_wrap_to_other_column(self):
        lines=[line(0,'Abstract',200),line(1,'We measure a complete transport effect.',240),
               line(2,'we discuss a separate experiment with independent results.',100,330,570),
               line(3,'1 Introduction',140,330,570)]
        lines[1]['bbox'][3]=680
        _,new=paired(lines)
        self.assertEqual(new['status'],'uncertain')
        self.assertFalse(new['proposed'])
        self.assertNotIn('independent',new['text'])

    def test_near_top_fragment_cannot_be_joined_as_column_wrap(self):
        lines=[line(0,'Abstract',200),line(1,'We measure an unfinished',240),
               line(2,'effect using a distinct collection of experiments.',100,330,570),
               line(3,'1 Introduction',140,330,570)]
        _,new=paired(lines)
        self.assertEqual(new['status'],'partial')
        self.assertFalse(new['proposed'])


if __name__=='__main__':unittest.main()
