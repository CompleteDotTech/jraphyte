"""Read-only native PDF and cached local OCR adapters; never download models."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from trace_gc.pdf_source_v3 import (align_text, assess_document, canonical, digest, seal)


def read_native_page(path: str | Path) -> dict[str, Any]:
    """Read physical page zero only, retaining font/color and exact run offsets.

    The full source hash and serialized first-page hash have different meanings.
    A retained experiment's page PDF must be checked against its own receipt;
    reserialization with another PyMuPDF version need not be byte-identical.
    """
    import fitz
    path = Path(path)
    # Parse the same bytes that are hashed, avoiding an open/hash TOCTOU gap.
    raw = path.read_bytes()
    with fitz.open(stream=raw, filetype="pdf") as pdf:
        if not len(pdf):
            raise ValueError("empty_pdf")
        page = pdf[0]
        lines = []
        # Vector panel fills are source evidence too: a synopsis can have black
        # text on a colored rectangle, with no font-color difference at all.
        fills = [d for d in page.get_drawings() if d.get("fill") is not None and d.get("fill_opacity", 1) > 0]
        for block_id, block in enumerate(page.get_text("dict", sort=True)["blocks"]):
            for native in block.get("lines", []):
                runs, text = [], ""
                for span in native["spans"]:
                    value = span["text"]
                    if not value:
                        continue
                    start = len(text)
                    text += value
                    runs.append({"start": start, "end": len(text), "text": value,
                                 **{k: span[k] for k in ("bbox", "font", "size", "flags", "color")}})
                if text.strip():
                    b = native["bbox"]
                    panels = [d for d in fills if d["rect"].contains(fitz.Rect(b))]
                    panel = min(panels, key=lambda d: d["rect"].get_area()) if panels else None
                    background = ({"bbox": list(panel["rect"]), "fill": list(panel["fill"]),
                                   "opacity": panel.get("fill_opacity", 1), "source": "native_vector_fill"} if panel else None)
                    lines.append({"id": len(lines), "page_no": 1, "block_id": block_id,
                                  "bbox": list(b), "text": text, "runs": runs, "background": background})
        single = fitz.open()
        try:
            single.insert_pdf(pdf, from_page=0, to_page=0)
            page_bytes = single.tobytes(no_new_id=True)
        finally:
            single.close()
        return {"physical_page": 1, "page_size": [page.rect.width, page.rect.height],
                "source_sha256": hashlib.sha256(raw).hexdigest(),
                "page_sha256": hashlib.sha256(page_bytes).hexdigest(),
                "native_lines": lines, "native_lines_sha256": digest(lines),
                "adapter": "pymupdf_page_zero_native_runs", "pymupdf_version": fitz.VersionBind}


def native_document(lines: list[dict[str, Any]]) -> dict[str, Any]:
    """A source-only document for focused fixtures or a labelled native path."""
    items = []
    for line in lines:
        b = line["bbox"]
        items.append({"self_ref": f"#/texts/{len(items)}", "text": line["text"],
                      "label": "text", "prov": [{"page_no": 1, "bbox": {
                          "l": b[0], "t": b[1], "r": b[2], "b": b[3], "coord_origin": "TOPLEFT"}}]})
    return {"texts": items, "body": {"self_ref": "#/body", "children": [{"cref": i["self_ref"]} for i in items]}}


def _plain(text: str) -> str:
    return re.sub(r"(?m)^\s*#{1,6}\s*", "", text).replace("**", "").replace("__", "").strip()


def olmocr_assess(raw: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Locate cached OCR paragraphs without claiming model-predicted boxes.

    Exact canonical source intervals repair wrapping/paragraph-merging failures.
    Approximate-only, ambiguous and image-only text stays review-only. Conversion
    truncation and request character budget are independent dimensions.
    """
    text = raw.get("raw_text", "")
    if text.lstrip().startswith("---"):
        parts = text.split("---", 2)
        text = parts[2] if len(parts) == 3 else ""
    paragraphs, items = [], []
    for index, part in enumerate(re.split(r"\n\s*\n|\n(?=#{1,6}\s)", text)):
        value = _plain(part)
        if not value:
            continue
        location = align_text(value, kwargs.get("native_lines") or [], tuple(kwargs["page_size"]))
        paragraphs.append({"paragraph_index": index, "text_sha256": hashlib.sha256(value.encode()).hexdigest(), **location})
        if location["status"] != "located":
            continue  # Never fabricate a full-page source rectangle.
        boxes = [s["bbox"] for s in location["spans"]]
        items.append({"self_ref": f"#/texts/{index}", "text": value,
                      "label": "section_header" if re.match(r"^\s*#{1,6}\s", part) else "text",
                      "prov": [{"page_no": 1, "bbox": {"l": b[0], "t": b[1], "r": b[2], "b": b[3], "coord_origin": "TOPLEFT"}} for b in boxes]})
    document = {"texts": items, "body": {"self_ref": "#/body", "children": [{"cref": i["self_ref"]} for i in items]}}
    result = assess_document(document, **kwargs, conversion_status=raw.get("status", "error"),
                             generation_tokens=raw.get("generated_tokens", raw.get("output_tokens")),
                             generation_limit=raw.get("max_new_tokens", 4096),
                             finish_reason=raw.get("finish_reason"))
    result["extractor_version"] += "+olmocr-native-intervals"
    result["conversion_receipt_sha256"] = digest(raw)
    result["model_predicted_coordinates"] = False
    result["ocr_paragraph_locations"] = paragraphs
    # Only require agreement for the selected abstract, not unrelated page notes.
    # Location is native-first; this makes no standalone model accuracy claim.
    candidate = canonical(result["text"])
    converted = canonical(_plain(text))
    agreement = bool(candidate) and converted.count(candidate) == 1
    result["selected_text_in_conversion"] = agreement
    if result["status"] not in {"error", "truncated", "absent"} and not agreement:
        result.update(status="uncertain", selector_proposal=False, proposed=False)
        result["reasons"].append("selected_source_not_uniquely_supported_by_conversion")
    return seal(result)


def mineru_assess(raw: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Require cached MinerU text to support the native-first selected interval."""
    w, h = kwargs["page_size"]
    items = []
    mapping = {"title": "section_header", "footnote": "footnote", "image_caption": "caption",
               "table_caption": "caption", "header": "page_header", "footer": "page_footer"}
    for block in raw.get("blocks", []):
        if not block.get("content"):
            continue
        b = block["bbox"]
        items.append({"self_ref": f"#/texts/{len(items)}", "text": _plain(block["content"]),
                      "label": mapping.get(block.get("type"), "text"), "prov": [{"page_no": 1,
                          "bbox": {"l": b[0]*w, "t": b[1]*h, "r": b[2]*w, "b": b[3]*h, "coord_origin": "TOPLEFT"}}]})
    document = {"texts": items, "body": {"self_ref": "#/body", "children": [{"cref": i["self_ref"]} for i in items]}}
    result = assess_document(document, **kwargs, conversion_status=raw.get("status", "error"))
    text = canonical(" ".join(i["text"] for i in items))
    candidate = canonical(result["text"])
    supported = bool(candidate) and text.count(candidate) == 1
    result["selected_text_in_conversion"] = supported
    result["conversion_receipt_sha256"] = digest(raw)
    result["extractor_version"] += "+mineru-native-intervals"
    if result["status"] not in {"absent", "truncated", "error"} and not supported:
        result.update(status="uncertain", selector_proposal=False, proposed=False)
        result["reasons"].append("selected_source_not_uniquely_supported_by_conversion")
    return seal(result)
