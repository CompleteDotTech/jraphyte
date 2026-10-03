"""Authored corpus/OCR controls; no real model or private paper is used."""
import copy
import hashlib
import json
import tempfile
import unittest
import sys
from pathlib import Path

from src.parallel_source_v4 import retrieval_policy as policy
from src.parallel_source_v4.fields import build_fields, verify_fields
from trace_gc.pdf_source_parallel_v4 import digest_value
from src.parallel_source_v4.prepare import prepare
from trace_gc.pdf_image_evidence import render_source, image_candidate, candidate_hash


BASELINE = {"schema_version": policy.VERSION, "abstract_mode": "disabled", "assessment_method": None,
            "ocr_mode": "disabled", "ocr_identity": None}
try:
    import fitz
    import PIL
except ImportError:
    PDF_AVAILABLE = False
else:
    PDF_AVAILABLE = True


class CorpusPolicyTests(unittest.TestCase):
    def test_field_subprocess_preserves_selected_virtual_environment(self):
        import subprocess
        import venv
        from src.parallel_source_v4.retrieval_trial import _field_process
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            venv.EnvBuilder(with_pip=False, symlinks=sys.platform != "win32").create(root)
            executable = root / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
            script = "import json,sys; print(json.dumps({'prefix':sys.prefix,'executable':sys.executable}))"
            expected = json.loads(subprocess.check_output([str(executable), "-B", "-s", "-c", script]))
            observed = _field_process({"field_verifier_python": str(executable)}, ["-c", script])
            self.assertEqual(observed, expected)
            self.assertEqual(Path(observed["prefix"]).resolve(), root.resolve())

    def test_policy_has_no_id_or_query_exceptions(self):
        for changed in ({**BASELINE, "target_ids": ["f076"]}, {**BASELINE, "ocr_mode": "replace_corrupt"},
                        {**BASELINE, "assessment_method": "parallel_structure_v4"}):
            with self.assertRaises(ValueError):
                policy.validate_policy(changed)

    @unittest.skipUnless(PDF_AVAILABLE, "optional PyMuPDF/Pillow required")
    def test_denominator_retains_errors_empty_and_missing_assessments(self):
        import fitz
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            rows = []
            for name, text in (("native", "A source-grounded title about topology"), ("empty", "")):
                with fitz.open() as pdf:
                    page = pdf.new_page(width=200, height=200)
                    if text:
                        page.insert_text((10, 30), text, fontsize=8)
                    pdf.save(root / (name + ".pdf"))
                rows.append({"sample_id": name, "work_id": "fixture:" + name, "source_relative": name + ".pdf"})
            manifest = prepare(root, rows, root / "prepared")
            selected = {**BASELINE, "abstract_mode": "native_assessments", "assessment_method": "parallel_structure_v4"}
            result = build_fields(root, manifest, root / "fields.json", corpus_policy=selected)
            self.assertEqual(result["field_count"], 2)
            receipt = result["corpus_policy_receipt"]
            self.assertEqual(receipt["status"], "BLOCKED_MISSING_INPUTS")
            self.assertEqual(receipt["missing_input_ids"]["abstract"], ["native"])
            self.assertEqual(receipt["counts"]["abstract"], {"ineligible_empty_native": 1, "missing": 1})
            self.assertEqual(sum(receipt["denominator_axes"]["searchability"].values()), 2)
            with self.assertRaisesRegex(ValueError, "selective_titles"):
                build_fields(root, manifest, root / "targeted.json", corpus_policy=BASELINE, title_reviews={"native": {}})

    @unittest.skipUnless(PDF_AVAILABLE, "optional PyMuPDF/Pillow required")
    def test_reconstruction_rejects_forged_eligibility_and_missing_ocr_lineage(self):
        import fitz
        from src.parallel_source_v4.retrieval_trial import rebuild_fields, Blocked
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with fitz.open() as pdf:
                page = pdf.new_page(width=200, height=200)
                page.insert_text((10, 30), "Authored source title and content", fontsize=9)
                pdf.save(root / "source.pdf")
            manifest = prepare(root, [{"sample_id": "native", "work_id": "fixture:native", "source_relative": "source.pdf"}], root / "prepared")
            path = root / "fields.json"
            record = build_fields(root, manifest, path, corpus_policy=BASELINE)
            self.assertEqual(verify_fields(root, root / "prepared/manifest.json", path, None)["status"], "VERIFIED")
            config = {"field_verifier_python": sys.executable, "fields": "fields.json",
                      "preparation_manifest": "prepared/manifest.json", "source_root": str(root)}
            self.assertEqual(rebuild_fields(root, config)["status"], "VERIFIED")
            for attack in ("ineligible", "invented_ocr"):
                forged = copy.deepcopy(record)
                field = forged["fields"][0]
                if attack == "ineligible":
                    selected = {**BASELINE, "abstract_mode": "native_assessments", "assessment_method": "parallel_structure_v4"}
                    field["corpus_policy"]["abstract"] = "ineligible_empty_native"
                else:
                    selected = {**BASELINE, "ocr_mode": "empty_native_local", "ocr_identity": {
                        "engine": "Windows.Media.Ocr", "revision": "b"*64, "configuration": {"local_only": True}}}
                    field["corpus_policy"]["ocr"] = "candidate"
                    field["body"] = "Invented purported OCR text"
                    field["field_provenance"]["body"] = {"kind": "local_ocr_candidate"}
                forged["build_inputs"]["corpus_policy"] = selected
                forged["corpus_policy_receipt"] = policy.coverage(forged["fields"], selected)
                field["fields_sha256"] = digest_value({k:v for k,v in field.items() if k!='fields_sha256'})
                forged["fields_sha256"] = digest_value(forged["fields"])
                self.assertEqual(forged["corpus_policy_receipt"]["status"], "READY")
                path.write_text(json.dumps(forged), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "field_replay_derived_receipt_mismatch"):
                    verify_fields(root, root / "prepared/manifest.json", path, None)
                with self.assertRaisesRegex(Blocked, "field_reconstruction_or_runtime_verification_failed"):
                    rebuild_fields(root, config)

    def test_eligibility_is_source_only_and_bad_mapping_does_not_enable_ocr(self):
        matched = {"state": "matched_under_2_channel_tolerance"}
        self.assertEqual(policy.eligibility({}, [], matched), {"abstract": "empty_native", "ocr": "eligible"})
        self.assertEqual(policy.eligibility({}, [{"text": "\ufffd bad mapping"}], matched)["ocr"], "native_present")
        self.assertEqual(policy.eligibility({"native_extraction_state": "error"}, [], matched)["ocr"], "native_error")
        self.assertEqual(policy.eligibility({}, [], {"state": "render_mismatch_review_required"})["ocr"], "page_mismatch")
        with self.assertRaisesRegex(ValueError, "disabled_field_policy"):
            policy.field_decisions(BASELINE, {"abstract": "eligible", "ocr": "eligible"}, None, {"status": "success"})


@unittest.skipUnless(PDF_AVAILABLE, "optional PyMuPDF/Pillow required")
class LocalOCRPolicyTests(unittest.TestCase):
    def fixture(self, *, crop=None, output_status="complete", dpi=144):
        import fitz
        with fitz.open() as pdf:
            pdf.new_page(width=120, height=120)
            pdf_bytes = pdf.tobytes()
        metadata, page, crop_bytes = render_source(pdf_bytes, dpi=dpi, crop=crop)
        code = {"tools/windows_image_ocr.ps1": "a" * 64}
        identity = {"engine": "Windows.Media.Ocr", "revision": "b" * 64,
                    "configuration": {"local_only": True, "implementation_sha256": "a" * 64, "language": "en-US"}}
        frozen = {**BASELINE, "ocr_mode": "empty_native_local", "ocr_identity": identity}
        raw_record = {"version": "windows-local-image-ocr-v1", **identity, "text": "Authored OCR candidate",
                      "input_crop_sha256": metadata["crop"]["png_sha256"], "output_status": output_status}
        raw = json.dumps(raw_record).encode()
        candidate = image_candidate(pdf_bytes, source_id="paper", transcription=raw_record["text"], raw_output=raw,
                                    **identity, dpi=dpi, crop=crop, output_status=output_status,
                                    input_crop_sha256=raw_record["input_crop_sha256"])
        prep = {"version": "image-review-preparation-v1", "source_id": "paper", "source_relative": "source.pdf",
                "metadata": metadata, "code_sha256": code, "new_paid_api_calls": 0, "production_graph_writes": 0}
        prep_bytes = json.dumps(prep).encode()
        execution = {"version": "image-ocr-execution-v1", "status": "SOURCE_REVIEW_REQUIRED",
                     "candidate_sha256": candidate_hash(candidate), "preparation_sha256": hashlib.sha256(prep_bytes).hexdigest(),
                     "new_local_ocr_calls": 1, "new_paid_api_calls": 0, "production_graph_writes": 0, "code_sha256": code}
        blobs = {"preparation": prep_bytes, "candidate": json.dumps(candidate).encode(),
                 "execution": json.dumps(execution).encode(), "raw_ocr": raw, "page_image": page, "crop_image": crop_bytes}
        entry = {key: {"relative": key, "sha256": hashlib.sha256(value).hexdigest()} for key, value in blobs.items()}
        args = {"root": Path("."), "row": {"sample_id": "paper", "source_sha256": hashlib.sha256(pdf_bytes).hexdigest(),
                                            "page_sha256": "c" * 64, "image_sha256": "d" * 64},
                "pdf_bytes": pdf_bytes, "policy": frozen, "code": code, "read_asset": lambda value: blobs[value["relative"]]}
        return entry, args, blobs

    def test_bound_whole_page_raw_candidate_and_truncated_hold(self):
        for state, expected in (("complete", "success"), ("truncated", "truncated"), ("error", "error")):
            entry, args, _ = self.fixture(output_status=state)
            result = policy.local_ocr_cache(entry, **args)
            self.assertEqual(result["status"], expected)
            self.assertEqual(result["title"], "")
            self.assertNotIn("abstract", result)

    def test_crop_substitution_and_runtime_drift_rejected(self):
        entry, args, _ = self.fixture(crop=[0, 0, 60, 60])
        with self.assertRaisesRegex(ValueError, "unedited_full_first_page"):
            policy.local_ocr_cache(entry, **args)
        entry, args, _ = self.fixture(dpi=72)
        with self.assertRaisesRegex(ValueError, "unedited_full_first_page"):
            policy.local_ocr_cache(entry, **args)
        entry, args, _ = self.fixture()
        args["policy"] = copy.deepcopy(args["policy"])
        args["policy"]["ocr_identity"]["configuration"]["language"] = "de-DE"
        with self.assertRaisesRegex(ValueError, "runtime_identity"):
            policy.local_ocr_cache(entry, **args)

    def test_missing_producer_link_and_stale_code_rejected(self):
        entry, args, blobs = self.fixture()
        execution = json.loads(blobs["execution"])
        execution["preparation_sha256"] = "f" * 64
        blobs["execution"] = json.dumps(execution).encode()
        with self.assertRaisesRegex(ValueError, "lineage_mismatch"):
            policy.local_ocr_cache(entry, **args)
        entry, args, _ = self.fixture()
        args["code"] = {"tools/windows_image_ocr.ps1": "e" * 64}
        with self.assertRaisesRegex(ValueError, "lineage_mismatch"):
            policy.local_ocr_cache(entry, **args)


if __name__ == "__main__":
    unittest.main()
