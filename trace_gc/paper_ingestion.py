"""Reviewed document-page text sources with verifiable PDF/page lineage.

This contract is separate from the physical-first-page abstract benchmark. A
later-page span can be admitted here without changing that benchmark's label.
"""
from __future__ import annotations

from .canonical import bytes_digest, text_digest
from .errors import boundary, require
from .pdf_image_evidence import render_source
from .schema import validate

REPRESENTATION = "reviewed-native-pdf-page-v1"
CHECKS = ("source_identity", "reading_order", "boundaries", "notation")


def _native_text(pdf_bytes: bytes, physical_page: int) -> str:
    import fitz
    with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
        require(1 <= physical_page <= len(document), "PAPER_PAGE", "physical page absent")
        return document[physical_page - 1].get_text("text")


@boundary
def reviewed_page_source(catalog, *, pdf_bytes: bytes, source_id: str, version: str,
                         security_scope: str, physical_page: int, start: int, end: int,
                         reviewer: str, reviewer_kind: str, reviewed_at: str,
                         checks: dict[str, bool]) -> str:
    """Create a source from an exact, reviewed native page span; no graph write."""
    require(isinstance(pdf_bytes, (bytes, bytearray, memoryview)), "PAPER_SOURCE", "PDF bytes required")
    pdf_bytes = bytes(pdf_bytes)
    require(source_id and version and security_scope, "PAPER_SOURCE", "identity and scope required")
    require(type(physical_page) is int and physical_page >= 1, "PAPER_PAGE", "invalid page")
    require(reviewer and reviewer_kind in {"assistant", "human"}, "PAPER_REVIEW", "attributed review required")
    require(set(checks) == set(CHECKS) and all(value is True for value in checks.values()),
            "PAPER_REVIEW", "all source review checks must pass")
    metadata, _, _ = render_source(pdf_bytes, physical_page=physical_page, dpi=144)
    native = _native_text(pdf_bytes, physical_page)
    require(bytes_digest(pdf_bytes) == metadata["source_sha256"] and
            text_digest(native) == metadata["native_observation"]["text_sha256"],
            "PAPER_SOURCE", "native text changed between observations")
    require(type(start) is int and type(end) is int and 0 <= start < end <= len(native),
            "PAPER_SPAN", "invalid native page span")
    excerpt = native[start:end]
    require(excerpt.strip(), "PAPER_SPAN", "empty reviewed source")
    lineage = {"version": REPRESENTATION, "raw_document_sha256": bytes_digest(pdf_bytes),
               "physical_page": physical_page, "render_dpi": 144,
               "page_png_sha256": metadata["render"]["page_png_sha256"],
               "native_text_sha256": text_digest(native), "start": start, "end": end,
               "reviewer": reviewer, "reviewer_kind": reviewer_kind,
               "reviewed_at": reviewed_at, "checks": dict(checks)}
    body = {"source_id": source_id, "version": version, "representation": REPRESENTATION,
            "text": excerpt, "text_hash": text_digest(excerpt),
            "security_scope": security_scope, "parser_version": "PyMuPDF-" + metadata["render"]["renderer_version"],
            "raw_document_hash": bytes_digest(pdf_bytes), "page_lineage": lineage}
    validate("source", body)
    return catalog.put("source", body)


@boundary
def verify_page_source(source: dict, *, pdf_bytes: bytes | None = None) -> None:
    """Verify portable integrity and, when supplied, the original PDF bytes."""
    validate("source", source)
    require(source["representation"] == REPRESENTATION, "PAPER_SOURCE", "wrong representation")
    lineage = source["page_lineage"]
    require(source["raw_document_hash"] == lineage["raw_document_sha256"] and
            text_digest(source["text"]) == source["text_hash"] and
            len(source["text"]) == lineage["end"] - lineage["start"],
            "PAPER_SOURCE", "source/lineage mismatch")
    if pdf_bytes is None:
        return
    require(isinstance(pdf_bytes, (bytes, bytearray, memoryview)), "PAPER_SOURCE", "PDF bytes required")
    pdf_bytes = bytes(pdf_bytes)
    require(bytes_digest(pdf_bytes) == lineage["raw_document_sha256"],
            "PAPER_SOURCE_CHANGED", "original PDF differs")
    metadata, _, _ = render_source(pdf_bytes, physical_page=lineage["physical_page"], dpi=lineage["render_dpi"])
    native = _native_text(pdf_bytes, lineage["physical_page"])
    require(metadata["render"]["page_png_sha256"] == lineage["page_png_sha256"] and
            text_digest(native) == lineage["native_text_sha256"] and
            0 <= lineage["start"] < lineage["end"] <= len(native) and
            native[lineage["start"]:lineage["end"]] == source["text"],
            "PAPER_SOURCE_CHANGED", "page rendering or reviewed span differs")
