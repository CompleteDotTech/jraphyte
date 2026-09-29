"""Authored source-context consumer checks; no private paper content."""
import hashlib
import unittest

try:
    import fitz
except ImportError:
    fitz = None

from trace_gc.pdf_source_parallel_v4 import SourceGeometry, digest_value, source_lines
from trace_gc.pdf_structure_parallel_v4 import assess_document, verify_assessment
from src.parallel_source_v4.adapters import document, item, olmocr_assess
from src.parallel_source_v4.retrieval import extract_fields, verify_source_bound_assessment


@unittest.skipUnless(fitz, "optional PyMuPDF required for source geometry")
class SourceGeometryConsumerTests(unittest.TestCase):
    def source(self):
        with fitz.open() as pdf:
            page=pdf.new_page(width=600,height=800)
            paragraph=("Abstract We investigate how controlled transport changes in sparse networks "
                       "and show that the measured response remains stable under repeated perturbations.")
            first="Abstract We investigate how controlled transport changes in sparse networks"
            second="and show that the measured response remains stable under repeated perturbations."
            page.insert_text((40,80),first,fontsize=10)
            page.insert_text((40,96),second,fontsize=10)
            page.insert_text((40,130),"Introduction",fontsize=12)
            payload=pdf.tobytes()
        with fitz.open(stream=payload,filetype="pdf") as pdf:
            native=source_lines(pdf[0])
        source_sha=hashlib.sha256(payload).hexdigest()
        geometry=SourceGeometry.from_pdf(payload,native,expected_source_sha256=source_sha)
        kwargs={"native_lines":native,"page_size":[600,800],
                "source_sha256":source_sha,"page_sha256":source_sha}
        doc=document([item(0,paragraph,"text",[native[0]["bbox"],native[1]["bbox"]]),
                      item(1,"Introduction","section_header",[native[-1]["bbox"]])])
        return geometry,kwargs,doc

    def test_assessor_threads_source_geometry_and_seals_identity(self):
        geometry,kwargs,doc=self.source()
        result=assess_document(doc,**kwargs,source_geometry=geometry)
        verify_assessment(result)
        self.assertEqual(result["source_geometry_policy"]["source_sha256"],kwargs["source_sha256"])
        self.assertEqual(result["source_geometry_policy"]["native_sha256"],digest_value(kwargs["native_lines"]))
        self.assertEqual(result["source_alignment"]["status"],"located")
        self.assertEqual(result["spans"][0]["line_id"],kwargs["native_lines"][0]["id"])
        default=assess_document(doc,**kwargs)
        self.assertNotIn("source_geometry_policy",default)
        self.assertEqual(result["text"],default["text"])

    def test_detached_wrong_source_and_mutated_native_fail_closed(self):
        geometry,kwargs,doc=self.source()
        for bad in ({"source_geometry":geometry.descriptor()},
                    {"source_geometry":geometry,"source_sha256":"0"*64},
                    {"source_geometry":geometry,"native_lines":[]}):
            result=assess_document(doc,**{**kwargs,**bad})
            self.assertEqual(result["status"],"error")
            self.assertFalse(result["proposal"])

    def test_olmocr_direct_location_receives_same_context(self):
        geometry,kwargs,_=self.source()
        raw={"status":"success","raw_text":kwargs["native_lines"][0]["text"]+"\n\nIntroduction"}
        result=olmocr_assess(raw,**kwargs,source_geometry=geometry)
        self.assertEqual(result["paragraph_alignments"][0]["status"],"located")
        self.assertEqual(result["source_geometry_policy"]["source_sha256"],kwargs["source_sha256"])

    def test_retrieval_replays_enabled_assessment_with_same_pdf_context(self):
        geometry,kwargs,doc=self.source()
        assessment=assess_document(doc,**kwargs,source_geometry=geometry)
        verify_source_bound_assessment(assessment,kwargs["native_lines"],
            page_size=kwargs["page_size"],source_sha256=kwargs["source_sha256"],
            page_sha256=kwargs["page_sha256"],source_geometry=geometry)
        with self.assertRaisesRegex(ValueError,"source_geometry_verified_context_required"):
            verify_source_bound_assessment(assessment,kwargs["native_lines"],
                page_size=kwargs["page_size"],source_sha256=kwargs["source_sha256"],
                page_sha256=kwargs["page_sha256"])
        field=extract_fields("authored",kwargs["native_lines"],**{
            k:kwargs[k] for k in ("page_size","source_sha256","page_sha256")},
            abstract_assessment=assessment,source_geometry=geometry)
        self.assertFalse(field["eligible_for_jev"])


if __name__ == "__main__":
    unittest.main()
