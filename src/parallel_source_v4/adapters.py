"""Local converter adapters. Fields and model text remain untrusted candidates."""
from __future__ import annotations

import re
from trace_gc.pdf_source_parallel_v4 import compare, digest_value, locate, validate_box
from trace_gc.pdf_structure_parallel_v4 import assess_document, seal


def document(items: list[dict]) -> dict:
    return {"texts": items, "body": {"self_ref": "#/body", "children": [{"cref": x["self_ref"]} for x in items]}}


def plain(text: str) -> str:
    # Retain formula commands, signs, exponents and punctuation for source review.
    return re.sub(r"(?m)^\s*#{1,6}\s*", "", text).replace("**", "").replace("__", "").strip()


def item(index: int, text: str, label: str, boxes: list, *, estimated=False, missing=False) -> dict:
    return {"self_ref": f"#/texts/{index}", "text": plain(text), "label": label,
            "prov": [{"page_no": 1, "bbox": {"l": b[0], "t": b[1], "r": b[2], "b": b[3], "coord_origin": "TOPLEFT"}} for b in boxes],
            "coordinate_source": "native_alignment_estimate" if estimated else "layout_model",
            "source_location_missing": missing}


def conversion_state(raw: dict) -> str:
    state = str(raw.get("status", "error")).lower().split(".")[-1]
    reason = str(raw.get("finish_reason", "")).lower()
    used = raw.get("generated_tokens", raw.get("output_tokens"))
    limit = raw.get("max_new_tokens", raw.get("generation_token_limit", 4096))
    if state in {"truncated", "length", "max_tokens"} or reason in {"length", "max_tokens"}:
        return "truncated"
    if isinstance(used, int) and isinstance(limit, int) and used >= limit and reason not in {"eos", "stop"}:
        return "truncated"
    return state


def mineru_document(raw: dict, page_size: list) -> dict:
    labels = {"title": "section_header", "page_number": "page_footer", "header": "page_header",
              "footer": "page_footer", "aside_text": "page_header", "image": "picture",
              "image_caption": "caption", "table_caption": "caption", "table": "table",
              "footnote": "footnote", "equation": "formula"}
    items = []
    for block in raw.get("blocks", []):
        if not block.get("content"):
            continue
        if block.get("page_no", 1) != 1:
            raise ValueError("mineru_block_outside_first_page")
        b = block["bbox"]
        if len(b) != 4 or any(not isinstance(x, (int, float)) or not 0 <= x <= 1 for x in b):
            raise ValueError("invalid_normalized_mineru_box")
        box = validate_box([b[0]*page_size[0], b[1]*page_size[1], b[2]*page_size[0], b[3]*page_size[1]], page_size)
        items.append(item(len(items), block["content"], labels.get(block.get("type"), "text"), [box]))
    return document(items)


def olmocr_assess(raw: dict, **kwargs) -> dict:
    raw_text = raw.get("raw_text", "")
    if not isinstance(raw_text, str):
        raise ValueError("ocr_text_not_string")
    text = raw_text
    yaml_valid = True
    if text.lstrip().startswith("---"):
        parts = re.split(r"(?m)^---\s*$", text.strip(), maxsplit=2)
        yaml_valid = len(parts) == 3
        text = parts[-1] if yaml_valid else ""
    parts = [p for p in re.split(r"\n\s*\n|\n(?=#{1,6}\s)", text) if p.strip()]
    items, unlocated, alignments = [], [], []
    for index, paragraph in enumerate(parts):
        value = plain(paragraph)
        alignment = locate(value, kwargs.get("native_lines") or [])
        located = alignment["status"] == "located"
        boxes = [s["bbox"] for s in alignment["spans"]] if located else []
        if not located:
            unlocated.append(index)
        label = "section_header" if re.match(r"^\s*#{1,6}\s", paragraph) else "text"
        if re.match(r"^(?:arXiv:|<!--)", value):
            label = "page_header"
        items.append(item(index, value, label, boxes, estimated=True, missing=not located))
        alignments.append({"paragraph": index, **{k: v for k, v in alignment.items() if k not in {"text", "spans"}}})
    state = conversion_state(raw) if yaml_valid else "error"
    result = assess_document(document(items), **kwargs, conversion_status=state)
    selected = [int(ref.rsplit("/", 1)[-1]) for ref in result.get("region_refs", [])]
    closing_ref = (result.get("closing_boundary") or {}).get("ref")
    closing = int(closing_ref.rsplit("/", 1)[-1]) if closing_ref else len(items)
    interfering = [i for i in unlocated if selected and min(selected) <= i <= closing]
    if interfering and result["status"] not in {"error", "truncated"}:
        result.update(status="uncertain", proposal=False, complete_candidate=False,
                      reasons=result["reasons"]+["unlocated_ocr_paragraph_inside_candidate_boundary"])
    result.update(coordinate_source="native paragraph alignment estimates; olmOCR supplies no predicted coordinates",
                  unlocated_paragraphs=unlocated, interfering_unlocated_paragraphs=interfering,
                  paragraph_alignments=alignments, raw_output_sha256=digest_value(raw_text),
                  generation={"status": state, "token_limit": raw.get("max_new_tokens", 4096),
                              "generated_tokens": raw.get("generated_tokens", raw.get("output_tokens")),
                              "finish_reason": raw.get("finish_reason")})
    return seal(result)


def grobid_assess(raw: dict, source_document: dict, **kwargs) -> dict:
    field = raw.get("text", "").strip()
    state = conversion_state(raw)
    # A 500 error is isolated to this conversion, not an absent-abstract inference.
    result = assess_document(source_document, **kwargs, scholarly_abstract=field, conversion_status=state)
    result["field_candidate"] = bool(field)
    result["field_sha256"] = digest_value(field)
    result["field_source_verified"] = False
    if state != "success":
        return seal(result)
    agreement = compare(field, result["text"])
    if field and result["status"] == "complete" and result["spans"] and agreement["text_match_98"]:
        result["field_source_verified"] = True
    elif field:
        result["source_region_candidate_sha256"] = result["text_sha256"]
        result.update(text=field, spans=[], proposal=False, complete_candidate=False,
                      status="partial" if result["status"] == "partial" else "uncertain",
                      reasons=result["reasons"]+["scholarly_field_not_verified_as_complete_page_one_abstract"])
    else:
        result.update(text="", spans=[], status="absent", proposal=False, complete_candidate=False,
                      reasons=["empty_scholarly_field"])
    limit=kwargs.get("max_input_chars",4000)
    result["request_budget"]={"limit_characters":limit,"characters":len(result["text"]),
                              "status":"within_budget" if len(result["text"])<=limit else "exceeded","text_truncated":False}
    return seal(result)
