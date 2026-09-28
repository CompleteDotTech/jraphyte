"""Causal checks for runtime drift, frozen imports and saved-native replay."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from src.parallel_source_v4.common import REPO, digest, method_hashes, read, read_hashed_json, write_once
from src.parallel_source_v4.extraction import frozen_cohort, preflight, predict, regression, run_cases, verify_preflight_inputs
from src.parallel_source_v4.runtime import (InputGateError, configure_baseline,
    capture_archived_native, runtime_receipt, verify_native_manifest)
from trace_gc.pdf_source_parallel_v4 import digest_value


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


class RuntimeTests(unittest.TestCase):
    def test_missing_cli_source_map_is_redacted_and_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            result=subprocess.run([sys.executable,'-m','src.parallel_source_v4.extraction','regression',
                '--data-root',d,'--source-map','missing-map.json','--output','new-output'],
                cwd=REPO,capture_output=True,text=True)
            self.assertEqual(result.returncode,2)
            value=json.loads(result.stdout)
            self.assertEqual(value['status'],'BLOCKED')
            self.assertIn('action',value)
            self.assertEqual(result.stderr,'')
            self.assertNotIn(d,result.stdout)

    def test_long_run_input_mutation_invalidates_preflight_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);path=root/'cache.json';write(path,{'before':True})
            gate={'input_file_hashes':{'cache.json':digest(path)}}
            write(path,{'after':True})
            with self.assertRaisesRegex(InputGateError,'experiment_input_changed_after_preflight'):
                verify_preflight_inputs(root,gate)

    def test_long_run_code_mutation_invalidates_preflight_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            gate={'input_file_hashes':{},'method_hashes':{'old':'hash'}}
            with patch('src.parallel_source_v4.extraction.method_hashes',return_value={'new':'hash'}):
                with self.assertRaisesRegex(InputGateError,'experiment_code_changed_after_preflight'):
                    verify_preflight_inputs(Path(d),gate)

    def test_runtime_drift_is_actionable_and_redacted(self):
        with tempfile.TemporaryDirectory() as d:
            lock=Path(d)/"runtime.json"
            write(lock, {"schema_version":1,"environment":{"python":"3.12.10"}})
            with patch("src.parallel_source_v4.runtime.runtime_environment",return_value={"python":"3.14.3"}):
                with self.assertRaises(InputGateError) as caught:
                    runtime_receipt(lock)
            self.assertEqual(caught.exception.code,"runtime_lock_mismatch")
            self.assertEqual(caught.exception.details["differing_fields"],["python"])
            self.assertNotIn(d,str(caught.exception.details))

    def test_matching_runtime_receipt_is_deterministic_and_lock_bound(self):
        with tempfile.TemporaryDirectory() as d:
            lock=Path(d)/"runtime.json"
            write(lock,{"schema_version":1,"environment":{"python":"fixture"}})
            with patch("src.parallel_source_v4.runtime.runtime_environment",return_value={"python":"fixture"}), \
                 patch("src.parallel_source_v4.runtime.DEPENDENCIES",()):
                a,b=runtime_receipt(lock),runtime_receipt(lock)
            self.assertEqual(a,b)
            self.assertEqual(a["lock_sha256"],digest(lock))
            self.assertEqual(a["runtime_sha256"],digest_value({k:v for k,v in a.items() if k!="runtime_sha256"}))

    def test_runtime_lock_changed_after_parse_never_gets_a_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            lock=Path(d)/'runtime.json'
            write(lock,{'schema_version':1,'environment':{'python':'fixture'}})
            def environment():
                write(lock,{'schema_version':1,'environment':{'python':'changed'}})
                return {'python':'fixture'}
            with patch('src.parallel_source_v4.runtime.runtime_environment',side_effect=environment), \
                 patch('src.parallel_source_v4.runtime.DEPENDENCIES',()):
                with self.assertRaisesRegex(InputGateError,'runtime_lock_changed_during_verification'):
                    runtime_receipt(lock)

    def test_environment_and_explicit_root_mismatch_prevents_import(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with patch.dict(os.environ,{"TRACE_GC_TEST_DATA_ROOT":str(root/"other")}), \
                 patch("src.parallel_source_v4.runtime.importlib.import_module") as imported:
                with self.assertRaisesRegex(InputGateError,"data_root_environment_mismatch"):
                    configure_baseline(root)
                imported.assert_not_called()

    def test_preimported_baseline_root_cannot_be_rebound(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with patch.dict(os.environ,{"TRACE_GC_TEST_DATA_ROOT":str(root)}), \
                 patch("src.parallel_source_v4.runtime.importlib.import_module",
                       return_value=SimpleNamespace(DATA=root/"stale")):
                with self.assertRaisesRegex(InputGateError,"baseline_import_root_mismatch"):
                    configure_baseline(root)

    def test_external_root_works_in_new_interpreter_without_sibling_layout(self):
        with tempfile.TemporaryDirectory() as d:
            command=("import os; from pathlib import Path; "
                     "from src.parallel_source_v4.runtime import configure_baseline; "
                     "root=Path(os.environ['TRACE_GC_TEST_DATA_ROOT']); "
                     "old=configure_baseline(root); assert old.OUT==root/'validation_expanded200'; print('ROOT_OK')")
            environment={**os.environ,"TRACE_GC_TEST_DATA_ROOT":d}
            result=subprocess.run([sys.executable,"-c",command],cwd=REPO,env=environment,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(result.stdout.strip(),"ROOT_OK")

    def test_baseline_helper_and_new_local_import_change_method_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            repo=Path(d)
            paths={
                "src/abstract_validation_expanded/extraction.py":"from src.abstract_validation.common import DATA\n",
                "src/abstract_validation/common.py":"DATA = 'first'\n",
                "src/parallel_source_v4/fidelity.py":"def metric():\n    from .new_helper import VALUE\n",
                "src/parallel_source_v4/new_helper.py":"VALUE = 1\n",
            }
            for name,text in paths.items():
                path=repo/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
            first=method_hashes(repo)
            self.assertIn("src/abstract_validation/common.py",first)
            self.assertIn("src/parallel_source_v4/new_helper.py",first)
            (repo/"src/abstract_validation/common.py").write_text("DATA = 'second'\n")
            second=method_hashes(repo)
            self.assertNotEqual(first,second)
            (repo/"src/parallel_source_v4/new_helper.py").write_text("VALUE = 2\n")
            self.assertNotEqual(second,method_hashes(repo))


class NativeManifestTests(unittest.TestCase):
    def fixture(self,root):
        native=root/"saved/native.json"
        file_sha=write_once(native,[])
        manifest={"schema_version":1,"extractor_identity":{"recorded_environment":{"python":"historical"}},
                  "cases":[{"id":"f001","native_relative":"saved/native.json","file_sha256":file_sha,
                            "native_sha256":digest_value([]),"page_size":[600,800],
                            "source_sha256":"a"*64,"page_sha256":"b"*64,"image_sha256":"c"*64}]}
        path=root/"manifest.json";sha=write_once(path,manifest)
        return path,sha,manifest

    def test_saved_native_is_verified_without_reextraction(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);path,sha,manifest=self.fixture(root)
            self.assertEqual(verify_native_manifest(root,path,sha),manifest)

    def test_manifest_outside_authorized_root_is_rejected_before_read(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'authorized';root.mkdir()
            outside=Path(d)/'private.json';write(outside,{'private':'must not be read'})
            with patch('src.parallel_source_v4.runtime.read_hashed_json') as opened:
                with self.assertRaisesRegex(InputGateError,'native_manifest_unreadable_or_invalid'):
                    verify_native_manifest(root,outside,digest(outside))
            opened.assert_not_called()

    def test_edit_native_bytes_is_not_a_new_valid_replay(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);path,sha,_=self.fixture(root)
            (root/"saved/native.json").write_text("[1]")
            with self.assertRaisesRegex(InputGateError,"native_file_hash_mismatch"):
                verify_native_manifest(root,path,sha)

    def test_mutated_manifest_does_not_pass_its_external_pin(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);path,sha,manifest=self.fixture(root)
            manifest["cases"][0]["source_sha256"]="f"*64
            write(path,manifest)
            with self.assertRaisesRegex(InputGateError,"native_manifest_hash_mismatch"):
                verify_native_manifest(root,path,sha)

    def test_expected_manifest_pin_is_mandatory(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);path,_,_=self.fixture(root)
            with self.assertRaisesRegex(InputGateError,"native_manifest_expected_hash_required"):
                verify_native_manifest(root,path,None)

    def test_native_change_after_consumption_invalidates_manifest_verification(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);path,sha,_=self.fixture(root)
            def mutate(*args):
                write(root/'saved/native.json',[{'changed':True}])
            with patch('src.parallel_source_v4.runtime.validate_lines',side_effect=mutate):
                with self.assertRaisesRegex(InputGateError,'native_inputs_changed_during_verification'):
                    verify_native_manifest(root,path,sha)

    def test_converter_mutation_after_preflight_cannot_be_an_isolated_success(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);path=root/"grobid.json"
            write(path,{"status":"success","text":""})
            with self.assertRaisesRegex(InputGateError,"converter_changed_after_preflight"):
                predict("parallel_grobid_v4",{"grobid":path,"docling_document":path,"docling":path},
                        {},expected_input_hashes={"docling_document":"0"*64})


class RegressionPreflightTests(unittest.TestCase):
    def fixture(self,root):
        """Authored 200-ID protocol; fake bytes are never parsed as real PDFs."""
        repo=root/"fixture-repo";data=root/"data";base=data/"validation_expanded200"
        rows=[];labels={};natives=[]
        for i in range(1,201):
            sid=f"f{i:03}";folder=data/("validation_v2" if i<=100 else "validation_expanded200")/"pages"/sid
            folder.mkdir(parents=True)
            source=data/"originals"/(sid+".pdf");source.parent.mkdir(exist_ok=True);source.write_bytes(sid.encode())
            (folder/"page.pdf").write_bytes(("page:"+sid).encode());(folder/"page.png").write_bytes(("image:"+sid).encode())
            identity={"id":sid,"source_sha256":digest(source),"page_sha256":digest(folder/"page.pdf"),
                      "image_sha256":digest(folder/"page.png")}
            write(folder/"receipt.json",{"physical_page":1,"page_size":[600,800],
                  "source_sha256":identity["source_sha256"],"page_pdf_sha256":identity["page_sha256"],
                  "image_sha256":identity["image_sha256"]})
            write(folder/"lines.json",[])
            native=data/"native"/(sid+".json");write(native,[])
            natives.append({**identity,"page_size":[600,800],"native_relative":native.relative_to(data).as_posix(),
                            "file_sha256":digest(native),"native_sha256":digest_value([])})
            for name in ("docling","grobid","mineru","olmocr"):
                write(base/name/(sid+".json"),{"status":"success","text":""})
            write(base/"docling"/(sid+".document.json"),{"texts":[],"body":{"children":[]}})
            write(base/"assessments/structure_v2"/(sid+".json"),{"status":"absent","text":"","eligible_for_jev":False})
            rows.append({"sample_id":sid,"source_relative":source.relative_to(data).as_posix()})
            labels[sid]={"status":"no_abstract_text","text":""}
        write(base/"manifest.json",{"pdfs":rows});write(base/"labels.json",labels)
        review=repo/"review/first_page_expanded200"
        write(review/"protocol.json",{"method_hashes":{},"manifest_sha256":digest(base/"manifest.json")})
        write(review/"reference_freeze.json",{"files":{"labels.json":digest(base/"labels.json")}})
        native_manifest=data/"native-manifest.json"
        write(native_manifest,{"schema_version":1,"cases":natives,"extractor_identity":{"fixture":True}})
        return repo,data,native_manifest

    def checked(self,repo,data,manifest,**kwargs):
        with patch("src.parallel_source_v4.extraction.runtime_receipt",return_value={"runtime_sha256":"a"*64}), \
             patch("src.parallel_source_v4.extraction.configure_baseline",
                   return_value=SimpleNamespace(prediction=lambda *a: {"status":"absent","text":"","eligible_for_jev":False})):
            return preflight(data,repo=repo,native_mode="replay",native_manifest=manifest,
                             native_manifest_sha256=digest(manifest),**kwargs)

    def test_all_inputs_verified_before_selector_and_native_changes_are_explicit(self):
        with tempfile.TemporaryDirectory() as d:
            repo,data,manifest=self.fixture(Path(d))
            with patch("src.parallel_source_v4.extraction.predict") as selected, \
                 patch("src.parallel_source_v4.extraction.source_lines",side_effect=AssertionError("reextraction forbidden")):
                result=self.checked(repo,data,manifest)
            self.assertEqual(result["status"],"PASS",result)
            self.assertEqual(len(result["cases"]),200)
            self.assertEqual(result["native_comparison"],{"status":"COMPARED","changed_ids":[]})
            self.assertEqual(result["native_mode"],"replay")
            selected.assert_not_called()
            self.assertIn("src/abstract_validation/common.py",method_hashes())

    def test_missing_saved_assessment_blocks_before_new_selector(self):
        with tempfile.TemporaryDirectory() as d:
            repo,data,manifest=self.fixture(Path(d))
            (data/"validation_expanded200/assessments/structure_v2/f173.json").unlink()
            with patch("src.parallel_source_v4.extraction.predict") as selected:
                result=self.checked(repo,data,manifest)
            self.assertEqual(result["reason"],"required_regression_input_missing")
            self.assertEqual(result["case_id"],"f173")
            self.assertEqual(result["input_kind"],"saved_assessment")
            selected.assert_not_called()

    def test_fresh_extraction_reports_native_changes_and_has_distinct_identity(self):
        class PDF(list):
            def __enter__(self):return self
            def __exit__(self,*args):return False
        with tempfile.TemporaryDirectory() as d:
            repo,data,manifest=self.fixture(Path(d))
            replay=self.checked(repo,data,manifest)
            page=SimpleNamespace(rect=SimpleNamespace(width=600,height=800))
            native=[{'id':0,'text':'An authored new native line.','bbox':[20,20,500,40],'page_no':1}]
            with patch.dict(sys.modules,{'fitz':SimpleNamespace(open=lambda *a,**kw:PDF([page]))}), \
                 patch('src.parallel_source_v4.extraction.source_lines',return_value=native), \
                 patch('src.parallel_source_v4.extraction.runtime_receipt',return_value={'runtime_sha256':'a'*64}), \
                 patch('src.parallel_source_v4.extraction.configure_baseline',
                       return_value=SimpleNamespace(prediction=lambda *a:{})), \
                 patch('src.parallel_source_v4.extraction.digest',side_effect=lambda p: 'e'*64 if p.name=='pdf_source_parallel_v4.py' else digest(p)):
                fresh=preflight(data,repo=repo,native_mode='fresh',native_manifest=manifest,
                                native_manifest_sha256=digest(manifest))
            self.assertEqual(fresh['status'],'PASS',fresh)
            self.assertEqual(len(fresh['native_comparison']['changed_ids']),200)
            self.assertNotEqual(fresh['native_inputs'],replay['native_inputs'])
            self.assertEqual(fresh['extractor_identity']['runtime_sha256'],'a'*64)

    def test_same_saved_inputs_replay_identical_assessments(self):
        with tempfile.TemporaryDirectory() as d:
            repo,data,manifest=self.fixture(Path(d))
            gate=self.checked(repo,data,manifest)
            outputs=[]
            with patch.dict(sys.modules,{'fitz':SimpleNamespace(VersionBind='fixture')}):
                for name in ('run1','run2'):
                    output=data/name
                    result=run_cases(gate['cases'][:2],gate['labels'],output,'fixture',
                        methods=('parallel_structure_v4',),input_receipt=gate,root=data)
                    outputs.append((result,output))
            self.assertEqual(outputs[0][0]['experiment_sha256'],outputs[1][0]['experiment_sha256'])
            self.assertEqual(outputs[0][0]['details'],outputs[1][0]['details'])
            for sid in ('f001','f002'):
                relative=Path('assessments/parallel_structure_v4')/(sid+'.json')
                self.assertEqual((outputs[0][1]/relative).read_bytes(),(outputs[1][1]/relative).read_bytes())

    def test_missing_cached_converter_blocks_instead_of_skipping_case(self):
        with tempfile.TemporaryDirectory() as d:
            repo,data,manifest=self.fixture(Path(d))
            (data/"validation_expanded200/mineru/f001.json").unlink()
            result=self.checked(repo,data,manifest)
            self.assertEqual(result["reason"],"required_regression_input_missing")
            self.assertEqual(result["input_kind"],"mineru")

    def test_malformed_cache_containers_block_before_selector(self):
        with tempfile.TemporaryDirectory() as d:
            repo,data,manifest=self.fixture(Path(d))
            malformed=[('grobid/f001.json',[]),('docling/f001.document.json',[]),
                       ('docling/f001.document.json',{'texts':[[]]}),
                       ('docling/f001.document.json',{'body':{'children':['bad']}}),
                       ('docling/f001.document.json',{'texts':[{'prov':[[]]}]}),
                       ('mineru/f001.json',{'blocks':[[]]}),
                       ('grobid/f001.json',{'status':'success','text':[]}),
                       ('assessments/structure_v2/f001.json',[])]
            for relative,value in malformed:
                with self.subTest(relative=relative,value=value):
                    path=data/'validation_expanded200'/relative;original=path.read_bytes();write(path,value)
                    with patch('src.parallel_source_v4.extraction.predict') as selected:
                        result=self.checked(repo,data,manifest)
                    path.write_bytes(original)
                    self.assertEqual(result['status'],'BLOCKED',result)
                    self.assertEqual(result['reason'],'invalid_cached_json_shape')
                    self.assertNotIn(d,json.dumps(result))
                    selected.assert_not_called()

    def test_replay_native_change_between_manifest_verification_and_read_is_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            repo,data,manifest=self.fixture(Path(d))
            def verified(*args):
                value=verify_native_manifest(*args)
                (data/'native/f001.json').write_text('[ ]\n')  # Same JSON, different frozen bytes.
                return value
            with patch('src.parallel_source_v4.extraction.verify_native_manifest',side_effect=verified):
                result=self.checked(repo,data,manifest)
            self.assertEqual(result['reason'],'native_file_changed_after_verification')

    def test_native_wrong_source_cannot_replay(self):
        with tempfile.TemporaryDirectory() as d:
            repo,data,manifest=self.fixture(Path(d))
            value=read(manifest);value["cases"][0]["page_sha256"]="e"*64;write(manifest,value)
            result=self.checked(repo,data,manifest)
            self.assertEqual(result["reason"],"native_manifest_source_mismatch")

    def test_runtime_mismatch_stops_before_import_or_assessment(self):
        with tempfile.TemporaryDirectory() as d:
            repo,data,manifest=self.fixture(Path(d))
            with patch("src.parallel_source_v4.extraction.runtime_receipt",
                       side_effect=InputGateError("runtime_lock_mismatch")), \
                 patch("src.parallel_source_v4.extraction.configure_baseline") as baseline, \
                 patch("src.parallel_source_v4.extraction.run_cases") as selected:
                result=regression(data,data/"new-output",native_mode="replay",native_manifest=manifest,
                                  native_manifest_sha256=digest(manifest))
            self.assertEqual(result["status"],"BLOCKED")
            baseline.assert_not_called();selected.assert_not_called()
            self.assertFalse((data/"new-output/assessments").exists())


class ArchiveCaptureTests(unittest.TestCase):
    def fixture(self,root):
        _,data,native_manifest=RegressionPreflightTests().fixture(root)
        rows=read(native_manifest)['cases'];run=data/'archive'
        for row in rows:
            sid=row['id'];write(run/'native'/(sid+'.json'),[])
            write(run/'assessments/fixture'/(sid+'.json'),{
                'source_sha256':row['source_sha256'],'page_sha256':row['page_sha256']})
        write(run/'results.json',{'details':{'fixture':[]},'environment':{'python':'archived'}})
        write(run/'preflight.json',{'status':'PASS','verified_sources':[
            {k:r[k] for k in ('id','source_sha256','page_sha256','image_sha256')} for r in rows]})
        write(run/'protocol.json',{'method_hashes':{}})
        return data,run

    def test_capture_pins_same_parsed_bytes_and_all_archive_provenance(self):
        with tempfile.TemporaryDirectory() as d:
            data,run=self.fixture(Path(d));output=data/'capture.json'
            result=capture_archived_native(data,run,digest(run/'results.json'),output)
            self.assertEqual(result['cases'],200)
            value=read(output)
            self.assertEqual(len(value['archive_input_hashes']),603)
            self.assertEqual(value['cases'][0]['file_sha256'],digest(run/'native/f001.json'))

    def test_archive_input_and_output_outside_root_are_rejected_before_read(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'authorized';root.mkdir()
            for run,output in ((Path(d)/'outside',root/'capture.json'),
                               (root/'archive',Path(d)/'capture.json')):
                with self.subTest(run=run.name,output=output.name), \
                     patch('src.parallel_source_v4.runtime.read_hashed_json') as opened:
                    with self.assertRaisesRegex(InputGateError,'archived_native_capture_failed'):
                        capture_archived_native(root,run,'a'*64,output)
                    opened.assert_not_called()
                    self.assertFalse(output.exists())

    def test_archived_method_traversal_is_rejected_before_reading_outside_root(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'authorized';run=root/'archive'
            identity={'id':'f001','source_sha256':'a'*64,'page_sha256':'b'*64,'image_sha256':'c'*64}
            write(run/'results.json',{'details':{'../../../../outside':[]}})
            write(run/'preflight.json',{'status':'PASS','verified_sources':[identity]})
            write(run/'protocol.json',{})
            write(root/'validation_v2/pages/f001/receipt.json',{
                'source_sha256':'a'*64,'page_pdf_sha256':'b'*64,'image_sha256':'c'*64,'page_size':[600,800]})
            write(run/'native/f001.json',[])
            def consume(path):
                self.assertIn(root,path.parents,'attempted read outside authorized root')
                return read_hashed_json(path)
            with patch('src.parallel_source_v4.runtime.read_hashed_json',side_effect=consume):
                with self.assertRaisesRegex(InputGateError,'archived_native_capture_failed'):
                    capture_archived_native(root,run,digest(run/'results.json'),root/'capture.json')
            self.assertFalse((root/'capture.json').exists())

    def test_change_to_any_consumed_archive_input_prevents_manifest_publication(self):
        with tempfile.TemporaryDirectory() as d:
            data,run=self.fixture(Path(d))
            targets=[run/'results.json',run/'preflight.json',run/'protocol.json',
                     data/'validation_v2/pages/f001/receipt.json',
                     run/'assessments/fixture/f001.json',run/'native/f001.json']
            for index,target in enumerate(targets):
                with self.subTest(target=target.name):
                    original=target.read_bytes();expected=digest(run/'results.json');output=data/f'capture-{index}.json'
                    def consume(path):
                        value=read_hashed_json(path)
                        if path==run/'assessments/fixture/f200.json':
                            target.write_bytes(original+b' ')
                        return value
                    with patch('src.parallel_source_v4.runtime.read_hashed_json',side_effect=consume):
                        with self.assertRaisesRegex(InputGateError,'archive_changed_during_capture'):
                            capture_archived_native(data,run,expected,output)
                    target.write_bytes(original)
                    self.assertFalse(output.exists())


class FrozenCohortIntegrityTests(unittest.TestCase):
    def fixture(self,root):
        try:import fitz
        except ImportError:self.skipTest('optional PyMuPDF unavailable')
        # Authored synthetic fixture, with no claim of unseen/human qualification.
        with fitz.open() as pdf:
            pdf.new_page(width=600,height=800);pdf.save(root/'page.pdf')
        (root/'source.pdf').write_bytes((root/'page.pdf').read_bytes())
        (root/'image.png').write_bytes(b'authored-image-identity-only')
        write(root/'native.json',[])
        write(root/'grobid.json',{'status':'error','text':''})
        write(root/'docling.json',{'status':'error'})
        write(root/'document.json',{'texts':[],'body':{'self_ref':'#/body','children':[]}})
        row={'sample_id':'authored','conversion_outputs':{'grobid':'grobid.json',
             'docling':'docling.json','docling_document':'document.json'}}
        for name,relative in {'source':'source.pdf','page':'page.pdf','image':'image.png','native':'native.json'}.items():
            row[name+'_relative']=relative;row[name+'_sha256']=digest(root/relative)
        freeze={'manifest':{'pdfs':[row]},'labels':{'authored':{'status':'no_abstract_text','text':''}},
                'cohort_kind':'synthetic_causal_fixture','method_hashes':method_hashes()}
        freeze['freeze_sha256']=digest_value(freeze)
        return freeze

    def test_native_mutation_after_freeze_verification_blocks_before_selection(self):
        from src.parallel_source_v4.freeze import verify_freeze
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);freeze=self.fixture(root)
            def verified(*args):
                verify_freeze(*args)
                (root/'native.json').write_text('[ ]\n')
            with patch('src.parallel_source_v4.extraction.runtime_receipt',return_value={'runtime_sha256':'fixture'}), \
                 patch('src.parallel_source_v4.extraction.verify_freeze',side_effect=verified), \
                 patch('src.parallel_source_v4.extraction.run_cases') as selected:
                result=frozen_cohort(root,freeze,root/'run',methods=('parallel_structure_v4',))
            self.assertEqual(result['reason'],'cohort_native_changed_after_verification')
            selected.assert_not_called()
            self.assertEqual(read(root/'run/results.json')['status'],'BLOCKED')
            self.assertNotIn(d,json.dumps(result))

    def test_inputs_runtime_and_code_changed_during_selection_cannot_complete(self):
        for target in ('source.pdf','page.pdf','image.png','native.json','grobid.json','runtime','code','freeze'):
            with self.subTest(target=target),tempfile.TemporaryDirectory() as d:
                root=Path(d);freeze=self.fixture(root);changed=False;hashes=method_hashes()
                def selected(*args,**kwargs):
                    nonlocal changed
                    changed=True
                    if target=='freeze':freeze['labels']['authored']['text']='changed'
                    elif target not in {'runtime','code'}:
                        path=root/target;path.write_bytes(path.read_bytes()+b' ')
                    return {'status':'COMPLETE_OFFLINE_ASSESSMENT_NOT_QUALIFICATION'}
                def runtime(*args):return {'runtime_sha256':'changed' if changed and target=='runtime' else 'fixture'}
                def code():return {'changed':'hash'} if changed and target=='code' else hashes
                with patch('src.parallel_source_v4.extraction.runtime_receipt',side_effect=runtime), \
                     patch('src.parallel_source_v4.extraction.method_hashes',side_effect=code), \
                     patch('src.parallel_source_v4.extraction.run_cases',side_effect=selected):
                    result=frozen_cohort(root,freeze,root/'run',methods=('parallel_structure_v4',))
                self.assertTrue(changed)
                self.assertEqual(result['status'],'BLOCKED',result)
                self.assertEqual(read(root/'run/results.json')['status'],'BLOCKED')
                self.assertNotIn(d,json.dumps(result))

    def test_stable_cohort_uses_frozen_native_bytes_and_records_input_identities(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);freeze=self.fixture(root)
            with patch('src.parallel_source_v4.extraction.runtime_receipt',return_value={'runtime_sha256':'fixture'}), \
                 patch('src.parallel_source_v4.extraction.source_lines',side_effect=AssertionError('reextraction forbidden')):
                result=frozen_cohort(root,freeze,root/'run',methods=('parallel_structure_v4',))
            self.assertEqual(result['status'],'COMPLETE_OFFLINE_ASSESSMENT_NOT_QUALIFICATION',result)
            self.assertEqual(result['native_inputs']['authored'],digest(root/'native.json'))
            self.assertEqual(len(result['input_file_hashes']),7)


if __name__ == "__main__":
    unittest.main()
