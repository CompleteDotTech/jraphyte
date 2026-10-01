import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.package_project import package, audit_archive, safe_name, safe_bytes, included
from trace_gc.pdf_source_v3 import digest, assess_document
from src.abstract_validation_v3.common import data_root, write_once, resolve_source, safe_id, file_digest
from src.abstract_validation_v3.evaluate import summary, paired_fallback, run_regression
from src.abstract_validation_v3.freeze import freeze_cohort, evaluate_frozen
from src.abstract_validation_v3.prepare import prepare
from src.abstract_validation_v3.adapters import read_native_page, native_document


class PackageSafetyTests(unittest.TestCase):
    def test_nested_private_inputs_and_weights_are_excluded(self):
        denied=[".env","x/.env.local","x/.env.production","x/.ENV.SECRET","x/paper.pdf","model.safetensors",
                "x/model.pt","x/model.pth","x/model.bin","model.gguf","checkpoint.ckpt","x/model.onnx",
                "TRACE-GC_RealPaper_Test/labels.json","models/settings.json","dist/secret.whl","x/a.zip",
                "x/cache.sqlite3-wal","temp/receipt.json","x/a.json.tmp","x/.cache/token.json"]
        for name in denied:
            with self.subTest(name=name):self.assertFalse(safe_name(name))
        for name in [".env.example","x/.env.example","src/selector.py","review/receipt.json"]:
            self.assertTrue(safe_name(name))

    def test_poison_files_do_not_enter_source_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent=Path(tmp);root=parent/"project";root.mkdir()
            for name,data in {"src/example.py":b"print('example')\n",".env.example":b"API_KEY=\n",
                              ".env":b"private fixture", "paper.pdf":b"%PDF-not-real", "model.safetensors":b"model",
                              "outputs/result.json":b"{}"}.items():
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
            result=package(root,parent/"source.zip",tracked_only=False)
            self.assertEqual(result["files_in_zip"],3)
            self.assertEqual(audit_archive(parent/"source.zip")["private_pdfs"],0)
            self.assertEqual({r["path"] for r in json.loads((root/"MANIFEST.json").read_text())["files"]},{"src/example.py",".env.example"})

    def test_exact_manifest_in_enters_source_archive_without_neighboring_in_files(self):
        for name in ("MANIFEST.in.bak", "other.in", ".env.production"):
            self.assertFalse(safe_name(name))
        self.assertTrue(safe_name("MANIFEST.in"))
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp); root = parent / "project"; root.mkdir()
            (root / "MANIFEST.in").write_text("include src/example.py\n")
            (root / "other.in").write_text("unreviewed instructions\n")
            (root / "MANIFEST.in.bak").write_text("stale instructions\n")
            (root / "src").mkdir(); (root / "src/example.py").write_text("value = 1\n")
            result = package(root, parent / "source.zip", tracked_only=False)
            self.assertEqual(result["status"], "PASS")
            paths = {row["path"] for row in json.loads((root / "MANIFEST.json").read_text())["files"]}
            self.assertEqual(paths, {"MANIFEST.in", "src/example.py"})
            self.assertEqual(audit_archive(parent / "source.zip")["files_in_zip"], 3)

    def test_renamed_pdf_and_private_key_content_abort_packaging(self):
        for payload in (b"%PDF-1.7 disguised", b"-----BEGIN "+b"PRIVATE KEY-----\nfixture"):
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)/"project";root.mkdir();(root/"looks_safe.txt").write_bytes(payload)
                with self.assertRaises(ValueError):package(root,Path(tmp)/"out.zip",tracked_only=False)

    def test_legacy_cp1252_text_is_kept_but_binary_bytes_are_rejected(self):
        self.assertTrue(safe_bytes("report.md", b"7 cases \xd7 3 runs\n"))
        self.assertFalse(safe_bytes("report.md", b"7 cases \xd7\x00\x01"))

    def test_symlink_cannot_smuggle_external_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"project";root.mkdir();secret=Path(tmp)/"secret.txt";secret.write_text("private fixture")
            link=root/"normal.txt"
            try:
                link.symlink_to(secret)
            except OSError as exc:
                if getattr(exc, "winerror", None) == 1314:
                    self.skipTest("Windows symlink privilege unavailable")
                raise
            self.assertFalse(included(link,root))

    def test_source_zip_reproducible_and_manifest_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"project";root.mkdir();(root/"code.py").write_text("x=1\n")
            first=package(root,Path(tmp)/"one.zip",tracked_only=False)
            second=package(root,Path(tmp)/"two.zip",tracked_only=False)
            self.assertEqual(first["sha256"],second["sha256"])


class ReceiptSafetyTests(unittest.TestCase):
    def test_environment_root_is_configurable_and_private(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{"TRACE_GC_TEST_DATA_ROOT":tmp}):
            self.assertEqual(data_root(),Path(tmp).resolve())
        with self.assertRaises(ValueError):data_root(Path(__file__).resolve().parents[1])

    def test_path_escape_and_unsafe_receipt_ids_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("../private.pdf","/tmp/private.pdf",r"C:\private.pdf"):
                with self.assertRaises(ValueError):resolve_source(Path(tmp),name)
        for ident in ("../case","q/one","q\\one","a..b"):
            with self.assertRaises(ValueError):safe_id(ident)

    def test_immutable_receipts_are_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"receipt.json"
            h=write_once(p,{"status":"held"})
            self.assertEqual(write_once(p,{"status":"held"}),h)
            with self.assertRaises(ValueError):write_once(p,{"status":"complete"})
            self.assertEqual(json.loads(p.read_text())["status"],"held")

    def test_missing_private_inputs_produce_blocked_not_fake_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=run_regression(Path(tmp)/"missing",Path(tmp)/"results",{})
            self.assertEqual(r["status"],"BLOCKED")
            self.assertEqual(r["pages_evaluated"],0)
            self.assertIsNone(r["precision"])
            self.assertEqual(r["source_hash_verification"],"NOT_RUN")

    def test_false_proposals_and_matching_holds_are_counted_separately(self):
        rows=[{"id":"a","gold":"complete","predicted":"uncertain","proposed":False,"text_match_98":True,"boundary_and_98_match":True},
              {"id":"b","gold":"no_abstract_text","predicted":"complete","proposed":True,"text_match_98":False,"boundary_and_98_match":False}]
        result=summary(rows)
        self.assertEqual(result["false_proposals"],["b"])
        self.assertEqual(result["withheld_complete"],["a"])
        self.assertEqual(result["matching_text_withheld"],["a"])
        self.assertEqual(result["verified_admissions"],0)

    def test_fallback_measurement_never_enables_automatic_use(self):
        p=[{"id":"a","gold":"complete","proposed":False,"text_match_98":True}]
        f=[{"id":"a","gold":"complete","proposed":True,"text_match_98":True}]
        result=paired_fallback(p,f)
        self.assertEqual(result["new_correct"],["a"])
        self.assertFalse(result["automatic_use_enabled"])
        with self.assertRaises(ValueError):paired_fallback(p,[])


try:
    import fitz
except ImportError:
    fitz=None


@unittest.skipIf(fitz is None,"optional PyMuPDF source fixture dependency unavailable")
class PhysicalPageFixtures(unittest.TestCase):
    def make_pdf(self, path):
        pdf=fitz.open();page=pdf.new_page(width=600,height=800)
        page.insert_text((40,40),"Controlled transport measurements",fontsize=20)
        page.insert_text((40,90),"Abstract",fontsize=12,fontname="hebo")
        page.insert_text((40,115),"We investigate layered transport using controlled measurements.",fontsize=10,fontname="hebo")
        page.insert_text((40,130),"The results show reproducible responses to boundary conditions.",fontsize=10,fontname="hebo")
        page.insert_text((40,170),"1 Introduction",fontsize=12,fontname="hebo")
        page.insert_text((40,195),"This is the body, not abstract text.",fontsize=10)
        page2=pdf.new_page(width=600,height=800);page2.insert_text((40,80),"Abstract This second-page text must never be selected.")
        pdf.save(path);pdf.close()

    def test_vector_colored_panel_is_detected_when_font_color_is_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"panel.pdf"
            pdf=fitz.open(); page=pdf.new_page(width=600,height=800)
            page.insert_text((40,70),"Abstract",fontsize=12)
            page.insert_text((40,95),"We study transport and establish reproducible experimental results.",fontsize=10)
            page.draw_rect(fitz.Rect(35,110,520,150),color=None,fill=(0.85,0.9,1.0),overlay=False)
            page.insert_text((40,135),"This separate synopsis summarizes the work for a different audience.",fontsize=10)
            page.insert_text((40,180),"1 Introduction",fontsize=12)
            pdf.save(path);pdf.close()
            native=read_native_page(path); lines=native["native_lines"]
            self.assertTrue(any(l.get("background") for l in lines))
            p=assess_document(native_document(lines),page_size=native["page_size"],native_lines=lines,
                              source_sha256=native["source_sha256"],page_sha256=native["page_sha256"])
            self.assertEqual(p["status"],"uncertain")
            self.assertNotIn("synopsis",p["text"])
            self.assertFalse(p["proposed"])
            self.assertEqual(p["closing_boundary"]["style"]["background"]["source"],"native_vector_fill")

    def test_real_pdf_runs_and_first_physical_page_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"fixture.pdf";self.make_pdf(path)
            native=read_native_page(path)
            self.assertNotIn("second-page"," ".join(l["text"] for l in native["native_lines"]))
            self.assertTrue(any(r["flags"]&16 for l in native["native_lines"] for r in l["runs"]))
            p=assess_document(native_document(native["native_lines"]),page_size=native["page_size"],
                              source_sha256=native["source_sha256"],page_sha256=native["page_sha256"],native_lines=native["native_lines"])
            self.assertTrue(p["proposed"])
            self.assertNotIn("body",p["text"])
            self.assertNotIn("second-page",p["text"])

    def prepared_review(self, root):
        source=root/"fixture.pdf";self.make_pdf(source)
        rows=prepare([{"id":"new-fixture","work_id":"new-work","source_path":"fixture.pdf"}],root,root/"views")
        row=rows[0];lines=json.loads((root/row["lines_path"]).read_text())
        chosen=[l for l in lines if l["text"].startswith(("We investigate","The results"))]
        spans=[{"line_id":l["id"],"physical_page":1,"start":0,"end":len(l["text"]),"text":l["text"],"bbox":l["bbox"]} for l in chosen]
        review={"status":"complete","text":" ".join(s["text"] for s in spans),"spans":spans,
                "reviewer":"synthetic fixture attestation; not empirical review","reviewer_kind":"assistant",
                "reviewed_at":"2026-01-01T00:00:00+00:00","prediction_seen":False,"image_reviewed":True,"native_spans_reviewed":True,
                **{k:row[k] for k in ("source_sha256","page_sha256","image_sha256","native_lines_sha256")}}
        return rows,{"new-fixture":review}

    def test_freeze_then_evaluate_requires_same_sources_and_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);rows,reviews=self.prepared_review(root)
            protocol=freeze_cohort(rows,reviews,root=root,out=root/"frozen",seen_source_hashes={"a"*64},seen_work_ids={"old-work"})
            self.assertTrue(protocol["review_declarations_are_attestations"])
            result=evaluate_frozen(root/"frozen",root,root/"run")
            self.assertEqual(result["metrics"]["correct_proposals_98"],1)
            self.assertEqual(result["independent_human_validation"],"not_certified")
            (root/rows[0]["image_path"]).write_bytes(b"changed")
            with self.assertRaises(ValueError):evaluate_frozen(root/"frozen",root,root/"tampered")

    def test_seen_work_and_prediction_first_labels_cannot_be_unseen(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);rows,reviews=self.prepared_review(root)
            for known_hashes,known_works in (({rows[0]["source_sha256"]},{"other"}),({"a"*64},{"new-work"})):
                with self.assertRaises(ValueError):
                    freeze_cohort(rows,reviews,root=root,out=root/"fail",seen_source_hashes=known_hashes,seen_work_ids=known_works)
            reviews["new-fixture"]["prediction_seen"]=True
            with self.assertRaises(ValueError):
                freeze_cohort(rows,reviews,root=root,out=root/"fail",seen_source_hashes={"a"*64},seen_work_ids={"other"})

    def test_empty_cohort_cannot_be_published_as_unseen(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                freeze_cohort([],{},root=Path(tmp),out=Path(tmp)/"frozen",seen_source_hashes={"a"*64},seen_work_ids={"old"})


if __name__=="__main__":unittest.main()
