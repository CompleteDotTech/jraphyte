"""Offline input, freeze, replay, and archive contracts; temporary files only."""
import copy
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from src.parallel_source_v4.common import child, data_root, digest, write_once, read, verify_first_page_bundle
from src.parallel_source_v4.freeze import freeze_cohort, verify_freeze
from src.parallel_source_v4.extraction import preflight, predict, native_document, regression
from src.parallel_source_v4.prepare import prepare
from src.parallel_source_v4.fields import build_fields
from test_parallel_source_v4 import ABSTRACT, PARAMS, line, doc

from tools import package_project as package


class IOTests(unittest.TestCase):
    def test_private_root_env_override(self):
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'TRACE_GC_TEST_DATA_ROOT':d}):
            self.assertEqual(data_root(),Path(d).resolve())

    def test_private_root_inside_repo_rejected(self):
        with self.assertRaises(ValueError):data_root(Path(__file__).resolve().parents[1]/'private')

    def test_path_escape_and_windows_absolute_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            for value in ('../outside','/outside','C:\\private\\source.pdf'):
                with self.subTest(value=value):
                    with self.assertRaises(ValueError):child(Path(d),value)

    def test_immutable_receipt_idempotent_but_not_overwritable(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'receipt.json'
            first=write_once(path,{'value':1});self.assertEqual(write_once(path,{'value':1}),first)
            with self.assertRaises(ValueError):write_once(path,{'value':2})
            self.assertEqual(read(path),{'value':1})
            self.assertEqual(len(list(Path(d).glob('*.tmp'))),0)

    def test_missing_regression_is_blocked_not_passed(self):
        with tempfile.TemporaryDirectory() as d:
            result=preflight(Path(d))
            self.assertEqual(result['status'],'BLOCKED')
            self.assertEqual(result['reason'],'authorized_private_regression_data_unavailable')

    def test_parallel_v4_never_writes_into_frozen_regression_caches(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):regression(Path(d),Path(d)/'validation_expanded200/v3')

    def test_independent_olmocr_fallback_survives_missing_docling(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);path=root/'olmocr.json'
            write_once(path,{'status':'success','raw_text':'Abstract '+ABSTRACT+'\n\n# Introduction','page_sha256':'b'*64})
            result=predict('parallel_olmocr_v4',{'olmocr':path},{**PARAMS,'native_lines':[line(0,'Abstract '+ABSTRACT),line(1,'Introduction',200)]})
            self.assertTrue(result['proposal'],result)
            self.assertFalse(result['eligible_for_jev'])

    def test_converter_wrong_page_hash_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'olmocr.json';write_once(path,{'status':'success','raw_text':ABSTRACT,'page_sha256':'c'*64})
            result=predict('parallel_olmocr_v4',{'olmocr':path},{**PARAMS,'native_lines':[]})
            self.assertEqual(result['status'],'error');self.assertFalse(result['proposal'])


@unittest.skipUnless(importlib.util.find_spec('fitz') and importlib.util.find_spec('PIL'),
                     'optional PyMuPDF and Pillow unavailable')
class FreezeTests(unittest.TestCase):
    def inputs(self,root):
        import fitz
        from trace_gc.pdf_source_parallel_v4 import source_lines
        with fitz.open() as pdf:
            page=pdf.new_page(width=600,height=800)
            page.insert_textbox(fitz.Rect(40,70,560,200),ABSTRACT,fontsize=10)
            page.insert_text((40,250),'1 Introduction',fontsize=12)
            pdf.save(root/'source.pdf')
        prepared=prepare(root,[{'sample_id':'unseen','work_id':'work:new','source_relative':'source.pdf'}],root/'prepared')
        row=prepared['pdfs'][0]
        native=read(child(root,row['native_relative']))
        spans=[{'line_id':x['id'],'start':0,'end':len(x['text']),'text':x['text'],'bbox':x['bbox'],'page_no':1} for x in native[:-1]]
        labels={'unseen':{'status':'complete','text':ABSTRACT,'source_review':{
            'reviewer_kind':'assistant','reviewer':'fixture reviewer','source_before_predictions':True,
            'reviewed_at':'2026-01-01T00:00:00Z','image_sha256':row['image_sha256'],'native_sha256':row['native_sha256'],
            'reference_spans':spans,'closing_boundary':{'kind':'body_section','line_id':native[-1]['id']}}}}
        exposure=[{'work_id':'work:old','source_sha256':'a'*64,'page_sha256':'b'*64}]
        return {'pdfs':[row]},labels,exposure

    def test_source_first_freeze_is_bound_and_assistant_is_not_human(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);manifest,labels,exposure=self.inputs(root)
            result=freeze_cohort(root,manifest,labels,exposure,root/'freeze.json')
            verify_freeze(root,result)
            self.assertEqual(result['review_attribution'],{'assistant':1})
            self.assertIn('not inferred',result['independence'])

    def test_seen_work_cannot_be_unseen(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);manifest,labels,exposure=self.inputs(root)
            manifest['pdfs'][0]['work_id']='work:old'
            with self.assertRaises(ValueError):freeze_cohort(root,manifest,labels,exposure,root/'freeze.json')

    def test_seen_source_hash_cannot_be_unseen(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);manifest,labels,exposure=self.inputs(root)
            exposure[0]['source_sha256']=manifest['pdfs'][0]['source_sha256']
            with self.assertRaises(ValueError):freeze_cohort(root,manifest,labels,exposure,root/'freeze.json')

    def test_source_changed_since_review_cannot_freeze(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);manifest,labels,exposure=self.inputs(root);child(root,manifest['pdfs'][0]['image_relative']).write_bytes(b'changed')
            with self.assertRaises(ValueError):freeze_cohort(root,manifest,labels,exposure,root/'freeze.json')

    def test_review_after_prediction_cannot_be_unseen(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);manifest,labels,exposure=self.inputs(root);manifest['pdfs'][0]['predictions_examined']=True
            with self.assertRaises(ValueError):freeze_cohort(root,manifest,labels,exposure,root/'freeze.json')

    def test_existing_conversion_output_cannot_be_new_frozen_cohort(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);manifest,labels,exposure=self.inputs(root);(root/'prediction.json').write_text('{}')
            manifest['pdfs'][0]['conversion_outputs']={'docling':'prediction.json'}
            with self.assertRaises(ValueError):freeze_cohort(root,manifest,labels,exposure,root/'freeze.json')

    def test_no_exposure_registry_is_not_unseen(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);manifest,labels,_=self.inputs(root)
            with self.assertRaises(ValueError):freeze_cohort(root,manifest,labels,[],root/'freeze.json')

    def test_frozen_reference_edit_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);manifest,labels,exposure=self.inputs(root)
            result=freeze_cohort(root,manifest,labels,exposure,root/'freeze.json')
            result['labels']['unseen']['text']='changed'
            with self.assertRaises(ValueError):verify_freeze(root,result)

    def test_changed_methods_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);manifest,labels,exposure=self.inputs(root)
            result=freeze_cohort(root,manifest,labels,exposure,root/'freeze.json')
            with patch('src.parallel_source_v4.freeze.method_hashes',return_value={'changed':'hash'}):
                with self.assertRaises(ValueError):verify_freeze(root,result)

    def test_unsafe_case_id_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);manifest,labels,exposure=self.inputs(root)
            manifest['pdfs'][0]['sample_id']='../escape';labels={'../escape':labels['unseen']}
            with self.assertRaises(ValueError):freeze_cohort(root,manifest,labels,exposure,root/'freeze.json')


class PackageTests(unittest.TestCase):
    def test_env_variants_except_exact_example_excluded(self):
        for name in ('.env','.env.local','sub/.env.production','.env.example.backup'):
            self.assertFalse(package.safe_name(name))
        self.assertTrue(package.safe_name('.env.example'))

    def test_private_and_model_and_temporary_material_excluded(self):
        for name in ('paper.pdf','weights/model.safetensors','cache.pt','x.pyc','temp/run.json','pages/page.png',
                     'mineru/f001.json','docling/f001.document.json','private/source.json','font.ttf','bundle.zip','model.bin'):
            with self.subTest(name=name):self.assertFalse(package.safe_name(name))

    def test_renamed_pdf_or_key_rejected(self):
        self.assertFalse(package.safe_bytes('safe.txt',b'%PDF-1.7 fake'))
        self.assertFalse(package.safe_bytes('safe.txt',b'-----BEGIN '+b'PRIVATE KEY-----\nfixture'))

    def test_traversal_and_absolute_member_names_rejected(self):
        for name in ('../escape.py','/source.py','C:/source.py','..\\source.py'):
            self.assertFalse(package.safe_name(name))

    def test_zip_manifest_and_secret_exclusion(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'source';root.mkdir();(root/'hello.py').write_text('value = 1\n');(root/'.env').write_text('placeholder-secret')
            (root/'.env.example').write_text('KEY=replace-me\n');(root/'paper.pdf').write_bytes(b'%PDF-fixture')
            result=package.package(root,Path(d)/'source.zip',tracked_only=False)
            self.assertEqual(result['status'],'PASS');self.assertEqual(result['private_pdfs'],0)
            self.assertEqual(package.audit_archive(Path(d)/'source.zip')['sha256'],result['sha256'])

    def test_symlink_excluded_without_reading_target(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'source';root.mkdir();target=Path(d)/'outside.txt';target.write_text('private')
            try:
                (root/'link.txt').symlink_to(target)
            except OSError as exc:
                if getattr(exc, 'winerror', None) == 1314:
                    self.skipTest('Windows symlink privilege unavailable')
                raise
            self.assertFalse(package.included(root/'link.txt',root))

    def test_default_package_requires_real_git_index(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'x.py').write_text('x=1')
            with self.assertRaises(ValueError):package.archive_bytes(root)


@unittest.skipUnless(importlib.util.find_spec('fitz') and importlib.util.find_spec('PIL'),
                     'optional PyMuPDF and Pillow unavailable')
class PreparationTests(unittest.TestCase):
    def test_reject_changed_cached_first_page_content(self):
        import fitz
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with fitz.open() as pdf:
                page=pdf.new_page(width=600,height=800)
                page.insert_text((40,70),'Abstract',fontsize=15)
                page.insert_text((40,100),'A complete source paragraph.',fontsize=12)
                pdf.save(root/'source.pdf')
            manifest=prepare(root,[{'sample_id':'new','work_id':'new:fixture','source_relative':'source.pdf'}],root/'prepared')
            row=manifest['pdfs'][0]
            self.assertTrue(verify_first_page_bundle(root,row))
            cached=child(root,row['page_relative'])
            with fitz.open(cached) as pdf:
                pdf[0].insert_text((40,150),'VISIBLE TAMPER',fontsize=15)
                pdf.save(root/'tampered.pdf')
            (root/'tampered.pdf').replace(cached)
            with self.assertRaisesRegex(ValueError,'cached_page_does_not_match_first_physical_page'):
                verify_first_page_bundle(root,row)

    def test_prepare_source_first_and_build_query_independent_fields(self):
        import fitz
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'source.pdf'
            with fitz.open() as pdf:
                page=pdf.new_page(width=600,height=800)
                page.insert_text((40,70),'Graphical Abstract',fontsize=24)
                page.insert_text((40,450),'Quantum transport in disordered materials',fontsize=15)
                pdf.new_page().insert_text((40,70),'Abstract on the second page is excluded.')
                pdf.save(source)
            manifest=prepare(root,[{'sample_id':'new','work_id':'new:fixture','source_relative':'source.pdf'}],root/'prepared')
            row=manifest['pdfs'][0]
            self.assertFalse(row['predictions_examined'])
            with fitz.open(child(root,row['page_relative'])) as pagepdf:self.assertEqual(len(pagepdf),1)
            result=build_fields(root,manifest,root/'fields.json')
            self.assertEqual(result['fields'][0]['title'],'Quantum transport in disordered materials')
            self.assertNotIn('second page',result['fields'][0]['body'])
            self.assertTrue(result['query_independent'])


if __name__=='__main__':unittest.main()
