"""Experimental parallel first-physical-page selector v4; never a publication authority.

Frozen v1/v2 modules are deliberately not modified. A proposal requires a unique
source location and an explainable closing boundary. Missing evidence is a hold.
"""
from __future__ import annotations

import hashlib
import math
import re
from .pdf_source_parallel_v4 import (canonical, compare, digest_value, locate, normalize, overlap,
                            style, validate_box, validate_lines, validate_source_spans)

VERSION = "page-one-parallel-structure-v4"
ABSTRACT = re.compile(r"^\s*a\s*b\s*s\s*t\s*r\s*a\s*c\s*t\b\s*[.:—–-]?\s*", re.I)
EXCLUDED = {"page_header", "page_footer", "footnote", "caption", "picture", "table", "document_index"}
BODY_WORDS = r"(?:overview|introduction|background|preliminaries|related\s+work|methods?|materials\s+and\s+methods|results|discussion|conclusions?|references|contents|table\s+of\s+contents)"
METADATA_WORDS = r"(?:key\s*words?|index\s+terms|PACS(?:\s+(?:numbers|codes))?|CCS\s+concepts|funding|acknowledg\w*|correspondence|author\s+(?:contributions?|notes?|information|details)|data\s+availability|dedicat(?:ion|ed\s+to)|in\s+memory\s+of|to\s+the\s+memory\s+of|synopsis)"
METADATA_START = re.compile(r"^\s*(?:"+METADATA_WORDS+r"|(?:[\d,a-z*†‡]+\s+)?(?:department|university|institute|school|faculty|laboratory|college|cent(?:re|er))\b|©|copyright\b|all\s+rights\s+reserved|e-?mail\b|https?://|we\s+(?:thank|congratulate)\b|this\s+(?:work|paper|research)\s+(?:was|is)\s+(?:funded|supported)\b)", re.I)
NON_ABSTRACT = re.compile(r"^\s*(?:graphical\s+abstract|highlights?|key\s+points|executive\s+summary|(?:Fig(?:ure)?\.?|Table)\s*\d+|author\s+(?:list|notes?|details)|dedication|contents|table\s+of\s+contents)\b", re.I)
NARRATIVE = re.compile(r"\b(?:we|this\s+(?:paper|study|work|article)|propos\w+|investigat\w+|demonstrat\w+|establish\w+|present\w+|introduc\w+|obtain\w+|develop\w+|show\w+|prove\w+)\b", re.I)
SENTENCE_END = re.compile(r"[.!?][\s\"'’”\])}†‡*\d]*$")
INTERNAL = {"background", "objective", "objectives", "methods", "method", "results", "discussion", "conclusion", "conclusions", "purpose", "findings", "interpretation"}
NUMBER = r"(?:(?:\d+(?:\.\d+)*|[IVX]+)[.)]?\s+)?"


def body_items(document: dict) -> list[dict]:
    objects = {}
    for key in ("texts", "groups", "pictures", "tables"):
        for item in document.get(key, []):
            ref = item.get("self_ref")
            if not isinstance(ref, str) or ref in objects:
                raise ValueError("duplicate_or_missing_document_reference")
            objects[ref] = item
    ordered, seen = [], set()
    stack = [document["body"]]
    while stack:
        item = stack.pop()
        ref = item.get("self_ref")
        if not isinstance(ref, str) or ref in seen:
            raise ValueError("duplicate_or_cyclic_reading_order")
        seen.add(ref)
        if item.get("text") or item.get("orig"):
            ordered.append(item)
        children = item.get("children", [])
        for child in reversed(children):
            key = child.get("cref", child.get("$ref"))
            if key not in objects:
                raise ValueError("dangling_reading_order_reference")
            stack.append(objects[key])
    return ordered


def regions(document: dict, page_size: list[float]) -> list[dict]:
    result = []
    for order, raw in enumerate(body_items(document)):
        text = raw.get("text") or raw.get("orig", "")
        if not isinstance(text, str):
            raise ValueError("region_text_not_string")
        if not text.strip():
            continue
        boxes = []
        for prov in raw.get("prov", []):
            if prov.get("page_no") != 1:
                raise ValueError("region_outside_first_physical_page")
            b = prov["bbox"]
            origin = b.get("coord_origin")
            if origin == "TOPLEFT":
                box = [b["l"], b["t"], b["r"], b["b"]]
            elif origin == "BOTTOMLEFT":
                box = [b["l"], page_size[1]-b["t"], b["r"], page_size[1]-b["b"]]
            else:
                raise ValueError("unknown_coordinate_origin")
            boxes.append(validate_box(box, page_size))
        # Only OCR adapters may deliberately retain unlocated paragraphs.
        unlocated = bool(raw.get("source_location_missing"))
        if not boxes and not unlocated:
            raise ValueError("region_has_no_source_box")
        bbox = [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)] if boxes else None
        result.append({"ref": raw["self_ref"], "text": text, "label": raw.get("label", "text"),
                       "boxes": boxes, "bbox": bbox, "tree_order": order,
                       "coordinate_source": raw.get("coordinate_source", "layout_model"), "unlocated": unlocated})
    return result


def _author_like(text: str) -> bool:
    tokens = re.findall(r"[A-Za-z]+", text)
    if len(tokens) < 10:
        return False
    capitalized = sum(t[:1].isupper() for t in tokens)/len(tokens)
    initials = len(re.findall(r"\b[A-Z]\.", text))
    return capitalized > .72 and (initials >= 3 or text.count(",") >= 4)


def _role_rejected(text: str) -> bool:
    return bool(NON_ABSTRACT.match(text) or METADATA_START.match(text) or _author_like(text))


def _header(text: str) -> bool:
    return bool(re.fullmatch(r"\s*"+NUMBER+BODY_WORDS+r"\s*[.:—–-]?\s*", text, re.I))


def _structured(text: str) -> bool:
    return bool(re.search(r"(?:^|\n)\s*Methods?\s*:", text, re.I) and re.search(r"(?:^|\n)\s*Results\s*:", text, re.I))


def _cut(text: str, structured: bool) -> tuple[str, dict | None]:
    """Find semantic boundaries without deleting interior words like 'overview'."""
    starts = [(0, text)]
    starts.extend((m.end(), text[m.end():]) for m in re.finditer(r"\n|(?<=[.!?])\s+(?=[A-Z])", text))
    for pos, suffix in starts:
        if not suffix.strip():
            continue
        # A section word in a running sentence is not a heading. Require a
        # standalone heading, separator or a numeric structural prefix.
        meta = re.match(r"\s*("+METADATA_WORDS+r")\b\s*(?:[:.—–-]|\s|$)", suffix, re.I)
        section = re.match(r"\s*("+NUMBER+BODY_WORDS+r")\s*(?:[:.—–-]\s*|\n|$)", suffix, re.I)
        match = meta or section
        if not match:
            continue
        name = normalize(match.group(1)).lower().rstrip(": .")
        if structured and section and name in INTERNAL:
            continue
        return text[:pos].rstrip(), {"kind": "embedded_metadata" if meta else "embedded_body_section",
                                    "offset": pos, "label": match.group(1)}
    return text, None


def _style_cut(alignment: dict, native: list[dict]) -> tuple[str, dict | None]:
    if alignment.get("status") != "located":
        return alignment.get("text", ""), None
    by_id = {str(x["id"]): x for x in native}
    selected = alignment["spans"]
    pieces, previous = [], None
    for span in selected:
        line = by_id[str(span["line_id"])]
        current = style(line)
        if previous and pieces and SENTENCE_END.search("\n".join(pieces)):
            prior, prior_style = previous
            separate = (line.get("block_id") is not None and prior.get("block_id") is not None and line["block_id"] != prior["block_id"])
            block_text="\n".join(s["text"] for s in selected if by_id[str(s["line_id"])].get("block_id")==line.get("block_id"))
            if separate and _author_like(block_text):
                return "\n".join(pieces), {"kind":"native_author_metadata_block", "next_line_id":line["id"],
                                              "source_block_id":line["block_id"]}
            color_change = current and prior_style and current["color"] != prior_style["color"]
            if separate and color_change and current.get("fraction", 0) >= .8 and len(canonical(span["text"])) >= 24:
                return "\n".join(pieces), {"kind": "separate_source_style_region", "next_line_id": line["id"],
                                              "before_style": prior_style, "after_style": current}
        # Bold inline source headings can live in the very same model region.
        for run in line.get("spans", []):
            if run["start"] < span["start"] or run["end"] > span["end"]:
                continue
            value = line["text"][run["start"]:run["end"]].strip()
            bold = bool(run.get("flags", 0) & 16 or "bold" in str(run.get("font", "")).lower())
            if bold and _header(value):
                prefix = span["text"][:run["start"]-span["start"]]
                preceding = "\n".join(pieces+[prefix]).rstrip()
                if preceding and SENTENCE_END.search(preceding):
                    return preceding, {"kind": "native_styled_section_start", "line_id": line["id"],
                                       "start": run["start"], "end": run["end"], "label": value}
        pieces.append(span["text"])
        previous = line, current
    return "\n".join(pieces), None


def _source_bold(region: dict, native: list[dict]) -> bool:
    if not region["bbox"]:
        return False
    selected = [x for x in native if region["bbox"][1]-2 <= (x["bbox"][1]+x["bbox"][3])/2 <= region["bbox"][3]+2 and overlap(region["bbox"], x["bbox"]) >= .8]
    styles = [(style(x), len(canonical(x["text"]))) for x in selected]
    total = sum(n for s, n in styles if s)
    return bool(total and sum(n for s, n in styles if s.get("bold"))/total >= .8)


BLOCKING_HEADING = re.compile(r"^\s*(?:graphical\s+abstract|highlights?|key\s+points|executive\s+summary|contents|table\s+of\s+contents|dedication|authors?|author\s+(?:list|notes?|details|contributions)|affiliations?)\s*[.:]?\s*$",re.I)


def _field_context(region: dict, ordered: list[dict], native: list[dict]) -> dict | None:
    """A header-stripped scholarly field is still inside its source section.

    A Highlights paragraph can match native text perfectly without being an
    abstract. Preceding same-column source headings are decisive context.
    """
    if not region["bbox"]:return None
    before=[x for x in ordered if x["bbox"] and x["ref"]!=region["ref"] and
            x["bbox"][3] <= region["bbox"][1]+2 and overlap(region["bbox"],x["bbox"]) >= .5 and
            (BLOCKING_HEADING.fullmatch(x["text"]) or _header(x["text"]) or
             (ABSTRACT.match(x["text"]) and not ABSTRACT.sub("",x["text"]).strip()))]
    if not before:return None
    previous=max(before,key=lambda x:x["bbox"][3])
    if ABSTRACT.match(previous["text"]):return None
    alignment=locate(previous["text"],native,region_boxes=previous["boxes"])
    return {"kind":"nonabstract_source_section","ref":previous["ref"],"label":previous["text"],
            "source_location":alignment["status"],"source_spans":alignment["spans"]}


def _collect(start: dict, ordered: list[dict], native: list[dict], explicit: bool) -> dict:
    if start["unlocated"]:
        return {"text": ABSTRACT.sub("", start["text"]), "boundary": None, "refs": [start["ref"]], "alignment_failure": "unlocated_ocr_paragraph"}
    column = start["bbox"]
    local = [x for x in ordered if x["bbox"] and x["bbox"][1] >= column[1]-1 and overlap(column, x["bbox"]) >= .5]
    local.sort(key=lambda x: (round(x["bbox"][1], 1), x["bbox"][0], x["tree_order"]))
    # Do not include earlier siblings sharing the same y position.
    index = next(i for i, x in enumerate(local) if x["ref"] == start["ref"])
    local = local[index:]
    initial_text=ABSTRACT.sub("",start["text"]).strip() if explicit else start["text"]
    if explicit and not initial_text:
        initial_text=next((x["text"] for x in local[1:] if x["text"].strip()),"")
    # A Methods/Results pair in the later body must not retroactively turn the
    # opening abstract into a structured abstract.
    structured = _structured(initial_text) if explicit else False
    pieces, refs, boundary, failure = [], [], None, None
    previous_style, previous_region = {}, None
    for x in local:
        text = x["text"]
        if x["ref"] == start["ref"] and explicit:
            text = ABSTRACT.sub("", text)
        if not text.strip():
            continue
        internal = normalize(text).lower().rstrip(": .") in INTERNAL and structured
        if pieces and not internal and (x["label"] == "section_header" or _header(text)):
            ambiguous = explicit and normalize(text).lower().rstrip(": .") in INTERNAL
            boundary = {"kind": "ambiguous_structured_or_body_section" if ambiguous else "body_section", "ref": x["ref"], "label": text[:120]}
            break
        if x["label"] in {"page_header", "page_footer", "footnote"}:
            continue
        if pieces and x["label"] in EXCLUDED:
            boundary = {"kind": "nontext_region_requires_source_review", "ref": x["ref"], "label": x["label"]}
            break
        if pieces and _role_rejected(text):
            boundary = {"kind": "metadata_or_nonabstract_region", "ref": x["ref"], "label": text[:120]}
            break
        if x["label"] in EXCLUDED or _role_rejected(text):
            failure = "nonabstract_start_region"
            break
        boxes = None if x["coordinate_source"] == "native_alignment_estimate" else x["boxes"]
        alignment = locate(text, native, region_boxes=boxes)
        if alignment["status"] != "located":
            # Keep the attempted text for inspection, but never trust its boxes.
            pieces.append(text)
            refs.append(x["ref"])
            failure = alignment.get("reason", "unlocated_source")
            break
        if alignment.get("column_change"):
            failure = "unverified_multi_column_continuation"
        source_text = alignment["text"]
        selected_lines = [s["line_id"] for s in alignment["spans"]]
        by_id = {str(n["id"]): n for n in native}
        first_style = style(by_id[str(selected_lines[0])]) if selected_lines else {}
        if pieces and previous_region and previous_style and first_style:
            color_change = first_style["color"] != previous_style["color"]
            if color_change and first_style.get("fraction", 0) >= .8 and SENTENCE_END.search("\n".join(pieces)):
                boundary = {"kind": "separate_source_style_region", "ref": x["ref"],
                            "before_style": previous_style, "after_style": first_style}
                break
        source_text, semantic = _cut(source_text, structured)
        styled_text, styled = _style_cut(alignment, native) if not structured else (alignment["text"], None)
        if styled and (not semantic or len(styled_text) < len(source_text)):
            source_text, semantic = styled_text, styled
        if source_text.strip():
            pieces.append(source_text)
            refs.append(x["ref"])
        if semantic:
            boundary = {**semantic, "ref": x["ref"]}
            break
        previous_region = x
        if selected_lines:
            previous_style = style(by_id[str(selected_lines[-1])])
    return {"text": "\n".join(pieces), "boundary": boundary, "refs": refs,
            "alignment_failure": failure, "structured": structured}


def seal(result: dict) -> dict:
    result.pop("assessment_sha256", None)
    result["text_sha256"] = hashlib.sha256(result["text"].encode()).hexdigest()
    result["evidence_sha256"] = digest_value({k: result.get(k) for k in (
        "source_sha256", "page_sha256", "physical_page", "text_sha256", "spans", "closing_boundary")})
    result["assessment_sha256"] = digest_value(result)
    return result


def verify_assessment(result: dict) -> None:
    copy = dict(result)
    actual = copy.pop("assessment_sha256", None)
    if digest_value(copy) != actual:
        raise ValueError("assessment_digest_mismatch")
    resealed = seal(copy)
    for key in ("text_sha256", "evidence_sha256", "assessment_sha256"):
        if resealed[key] != result.get(key):
            raise ValueError(key+"_mismatch")
    if result.get("eligible_for_jev") or result.get("verified_admission"):
        raise ValueError("selector_is_not_publication_authority")


def assess_document(document: dict, *, page_size, source_sha256, page_sha256,
                    native_lines=None, scholarly_abstract="", max_input_chars=4000,
                    conversion_status="success") -> dict:
    result = {"schema_version": 3, "extractor_version": VERSION, "physical_page": 1,
              "source_sha256": source_sha256 if isinstance(source_sha256, str) else None,
              "page_sha256": page_sha256 if isinstance(page_sha256, str) else None,
              "page_size": [x if isinstance(x, (int, float)) and math.isfinite(x) else None for x in page_size] if isinstance(page_size, (list, tuple)) else None,
              "status": "uncertain", "text": "", "proposal": False, "complete_candidate": False,
              "eligible_for_jev": False, "verified_admission": False,
              "admission": "source_review_required", "reasons": [], "spans": [], "closing_boundary": None,
              "conversion_status": str(conversion_status).lower().split(".")[-1],
              "source_hash_verification": "caller_must_verify_bytes"}
    try:
        if len(page_size) != 2 or any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or x <= 0 for x in page_size):
            raise ValueError("invalid_page_size")
        if not isinstance(max_input_chars, int) or isinstance(max_input_chars, bool) or max_input_chars <= 0:
            raise ValueError("invalid_request_character_budget")
        if any(not isinstance(h, str) or not re.fullmatch(r"[a-f0-9]{64}", h) for h in (source_sha256, page_sha256)):
            raise ValueError("invalid_source_sha256")
        status = result["conversion_status"]
        if status in {"truncated", "length", "max_tokens"}:
            result.update(status="truncated", reasons=["generation_token_limit_reached"])
            return seal(result)
        if status != "success":
            result.update(status="error", reasons=["isolated_conversion_error"])
            return seal(result)
        native = validate_lines(native_lines or [], page_size)
        ordered = regions(document, list(page_size))
        candidates = []
        for x in ordered:
            if x["label"] in EXCLUDED:
                continue
            if ABSTRACT.match(x["text"]):
                candidates.append((3, x, True, "explicit_abstract_heading"))
            elif not _role_rejected(x["text"]) and len(canonical(x["text"])) >= 100 and NARRATIVE.search(x["text"]):
                context=_field_context(x,ordered,native)
                if context:
                    result.setdefault("rejected_candidate_contexts",[]).append({"candidate_ref":x["ref"],**context})
                    continue
                field = compare(x["text"], scholarly_abstract) if scholarly_abstract else {}
                if _source_bold(x, native):
                    candidates.append((2, x, False, "source_bold_narrative_region"))
                elif field.get("text_match_98"):
                    candidates.append((1, x, False, "scholarly_candidate_source_region"))
        if not candidates:
            has_rejected_field = bool(scholarly_abstract and _role_rejected(scholarly_abstract))
            status = "absent" if native and (not scholarly_abstract or has_rejected_field) else "uncertain"
            result.update(status=status, reasons=["no_identified_first_page_abstract" if native else "no_native_source_text_review_image"])
            return seal(result)
        best = max(c[0] for c in candidates)
        candidates = [c for c in candidates if c[0] == best]
        # Collapse pure repeated headings only when adjacent in the same column.
        if len(candidates) > 1:
            substantive = [c for c in candidates if ABSTRACT.sub("", c[1]["text"]).strip()]
            if len(substantive) == 1 and all(overlap(c[1]["bbox"], substantive[0][1]["bbox"]) >= .8 for c in candidates if c[1]["bbox"]):
                candidates = substantive
        if len(candidates) != 1:
            result["reasons"] = ["multiple_plausible_abstract_regions"]
            result["candidate_refs"] = [c[1]["ref"] for c in candidates]
            return seal(result)
        _, start, explicit, basis = candidates[0]
        selected = _collect(start, ordered, native, explicit)
        text = selected["text"]
        result.update(text=text, closing_boundary=selected["boundary"], region_refs=selected["refs"],
                      explicit_heading=explicit, proposal_basis=basis, structured=selected.get("structured", False))
        if not text:
            result.update(status="absent", reasons=["heading_without_abstract_prose"])
            return seal(result)
        alignment = locate(text, native)
        result["source_alignment"] = {k: v for k, v in alignment.items() if k not in {"text", "spans"}}
        if selected["alignment_failure"] or alignment["status"] != "located":
            result.update(status="uncertain", reasons=[selected["alignment_failure"] or alignment.get("reason", "source_alignment_failure")])
        else:
            validate_source_spans(alignment["spans"], native)
            result.update(text=alignment["text"], spans=alignment["spans"], transcription="native_pdf")
            bottom = max(s["bbox"][3] for s in result["spans"])
            if alignment.get("column_change"):
                result.update(status="uncertain", reasons=["unverified_multi_column_continuation"])
            elif not selected["boundary"]:
                partial = bottom >= page_size[1]*.9 and not SENTENCE_END.search(result["text"])
                result.update(status="partial" if partial else "uncertain", reasons=["page_one_continues_without_closure" if partial else "no_explainable_closing_boundary"])
            elif selected["boundary"]["kind"] == "ambiguous_structured_or_body_section":
                result.update(status="uncertain", reasons=["structured_abstract_boundary_requires_review"])
            elif (selected["boundary"]["kind"] == "embedded_body_section" and explicit and
                  not selected["structured"] and
                  normalize(selected["boundary"].get("label", "")).lower().rstrip(": .") in INTERNAL):
                # An inline Methods/Results label can be an abstract subsection.
                # Without a witnessed closing section, the prefix is not safe.
                result.update(status="uncertain", reasons=["embedded_structured_section_requires_review"])
            elif selected["boundary"]["kind"] in {"separate_source_style_region", "nontext_region_requires_source_review"}:
                reason="style_transition_requires_source_review" if selected["boundary"]["kind"] == "separate_source_style_region" else "nontext_boundary_requires_source_review"
                result.update(status="uncertain", reasons=[reason])
            elif not SENTENCE_END.search(result["text"]):
                # A formula or unusual punctuation can be complete: hold, do not
                # claim a page break based on punctuation alone.
                result.update(status="uncertain", reasons=["closing_boundary_with_unresolved_terminal_notation"])
            else:
                result.update(status="complete", complete_candidate=True, reasons=["bounded_source_located_proposal"])
        text = result["text"]
        within_budget = len(text) <= max_input_chars
        result["request_budget"] = {"limit_characters": max_input_chars, "characters": len(text),
                                    "status": "within_budget" if within_budget else "exceeded", "text_truncated": False}
        if not within_budget:
            result["reasons"].append("exceeds_request_character_budget")
        result["proposal"] = result["status"] == "complete" and within_budget
        result["math_review_required"] = bool(re.search(r"[√∫∑∏≤≥∞]|\\(?:frac|sqrt|sum)|\$", text) or
            any(x["label"] == "formula" and x["ref"] in selected["refs"] for x in ordered))
        result["scholarly_alignment"] = compare(text, scholarly_abstract) if scholarly_abstract else None
    except (KeyError, ValueError, TypeError, OverflowError, IndexError) as exc:
        # Do not echo arbitrary upstream exception strings containing private paths.
        result.update(status="error", proposal=False, complete_candidate=False, reasons=["invalid_evidence:"+type(exc).__name__], error_code=str(exc) if isinstance(exc, ValueError) else type(exc).__name__)
    return seal(result)
