"""Document-scope reviewed spans remain tied to the original physical page."""
import unittest
from unittest.mock import patch

import fitz

from trace_gc.catalog import Catalog
from trace_gc.errors import ContractError
from trace_gc.paper_ingestion import reviewed_page_source, verify_page_source, CHECKS


def paper(second_page="Abstract. The measured result was 17 units."):
    document = fitz.open()
    document.new_page().insert_text((70, 70), "Title page. No abstract here.")
    document.new_page().insert_text((70, 70), second_page)
    data = document.tobytes()
    document.close()
    return data


class ReviewedDocumentPageTests(unittest.TestCase):
    def setUp(self):
        self.pdf = paper()
        with fitz.open(stream=self.pdf, filetype="pdf") as document:
            self.native = document[1].get_text("text")
        self.catalog = Catalog()
        self.args = dict(pdf_bytes=self.pdf, source_id="paper-1", version="source-v1",
                         security_scope="research", physical_page=2,
                         start=0, end=len(self.native.strip()), reviewer="assistant-1",
                         reviewer_kind="assistant", reviewed_at="2026-09-28T16:00:00Z",
                         checks={key: True for key in CHECKS})

    def test_second_page_source_and_evidence_reopen_to_exact_pdf_span(self):
        source_id = reviewed_page_source(self.catalog, **self.args)
        source = self.catalog.get(source_id, "source")
        self.assertEqual(source["page_lineage"]["physical_page"], 2)
        self.assertEqual(source["text"], self.native.strip())
        evidence_id = self.catalog.evidence(source_id, 10, len(source["text"]))
        self.catalog.verify_evidence(evidence_id)
        verify_page_source(source, pdf_bytes=self.pdf)
        with self.assertRaises(ContractError):
            verify_page_source(source, pdf_bytes=paper("A different second page."))

    def test_unreviewed_or_forged_native_span_cannot_enter_source(self):
        with self.assertRaises(ContractError):
            reviewed_page_source(self.catalog, **{**self.args, "checks": {**self.args["checks"], "notation": False}})
        with self.assertRaises(ContractError):
            reviewed_page_source(self.catalog, **{**self.args, "end": len(self.native) + 20})
        with self.assertRaises(ContractError):
            reviewed_page_source(self.catalog, **{**self.args, "physical_page": 3})
        source_id = reviewed_page_source(self.catalog, **self.args)
        forged = self.catalog.get(source_id, "source")
        forged["page_lineage"]["physical_page"] = 1
        with self.assertRaises(ContractError):
            verify_page_source(forged, pdf_bytes=self.pdf)

    def test_mutable_caller_buffer_is_frozen_before_render_and_native_read(self):
        from trace_gc import paper_ingestion
        mutable = bytearray(self.pdf)
        original_render = paper_ingestion.render_source
        def mutate_after_render(data, **kwargs):
            rendered = original_render(data, **kwargs)
            mutable[-30] ^= 1
            return rendered
        with patch.object(paper_ingestion, "render_source", side_effect=mutate_after_render):
            source_id = reviewed_page_source(self.catalog, **{**self.args, "pdf_bytes": mutable})
        source = self.catalog.get(source_id, "source")
        verify_page_source(source, pdf_bytes=self.pdf)
        with self.assertRaises(ContractError):
            verify_page_source(source, pdf_bytes=mutable)


if __name__ == "__main__":
    unittest.main()
