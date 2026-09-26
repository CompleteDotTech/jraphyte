"""Source-first experimental proposals. No API requests or publication authority.

Coordinates below come from the physical first page, never an OCR model. A
proposal and its source locations are separate from a reviewed abstract. The
frozen v1/v2 implementations are intentionally not imported or modified.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import math
import re
import unicodedata
from collections import Counter
from typing import Any, Iterable

VERSION = "page-one-source-v3"
ABSTRACT = re.compile(r"^\s*a\s*b\s*s\s*t\s*r\s*a\s*c\s*t\b\s*[.:—–-]?\s*", re.I)
SECTION = re.compile(r"^(?:(?:\d+(?:\.\d+)*|[IVX]+)[.)]?\s+)?(?:overview|introduction|background|preliminaries|related\s+work|methods?|results|discussion|conclusions?|references|appendix)\b(?:\s*[:.—–-]\s*|\s*$)", re.I)
NUMBERED_SECTION = re.compile(r"^(?:\d+(?:\.\d+)*|[IVX]+)[.)]?\s+[A-Z][^.!?\n]{0,70}(?:\n|$)")
INTERNAL = {"background", "objective", "objectives", "methods", "method", "results", "discussion", "conclusion", "conclusions", "purpose", "findings", "interpretation"}
NON_ABSTRACT = re.compile(r"^(?:graphical\s+abstract|highlights?|key\s+points?|executive\s+summary|table\s+of\s+contents|contents|author\s+(?:list|details|notes?|contributions?)|affiliations?|dedication)\b", re.I)
METADATA = re.compile(r"^(?:(?:[\d,*†‡]+\s*)?(?:department|university|institute|school|faculty|laboratory|college|centre|center)\b|key\s*words?\b|index\s+terms\b|CCS\s+concepts\b|PACS\b|funding\b|acknowledg\w*\b|correspond(?:ence|ing\s+author)\b|author\s+(?:notes?|contributions?|information|details)\b|(?:these\s+)?authors?\s+contributed\b|(?:all\s+)?authors?\s+(?:are|were)\s+with\b|data\s+availability\b|dedicated\s+to\b|in\s+(?:loving\s+)?memory\s+of\b|©|copyright\b)", re.I)
RESEARCH = re.compile(r"\b(?:we\s+(?:study|show|present|propose|investigate|introduce|derive|prove|find|demonstrate|develop)|this\s+(?:paper|study|work|article)|results?\s+(?:show|suggest|demonstrate)|investigat\w*|propos\w*|demonstrat\w*|measur\w*|evaluat\w*|establish\w*|analys\w*|analyz\w*|observ\w*)\b", re.I)
SENTENCE_END = re.compile(r"[.!?][\s\"”’')\]}]*$")
# A heading must start a source line/run, or follow a sentence delimiter. Bare
# occurrences of 'overview', 'authors', etc. in scientific prose are not cut.
EMBEDDED = re.compile(r"(?<=[.!?])\s+(?=(?:(?:\d+(?:\.\d+)*|[IVX]+)[.)]?\s+)?(?:Overview|Introduction|Related\s+Work|References)\s*[:.—–-]|(?:Dedicated\s+to|In\s+memory\s+of|Keywords?\s*:|Author\s+(?:notes?|contributions?)\s*:))")
EXCLUDED_LABELS = {"page_header", "page_footer", "footnote", "caption", "picture", "table", "document_index", "title"}


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def canonical(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text).casefold() if c.isalnum())


def compare(predicted: str, reference: str) -> dict[str, Any]:
    """The exact ordered canonical/48-character boundary scoring used in doc 25."""
    a, b = canonical(predicted), canonical(reference)
    matches = sum(m.size for m in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks())
    precision = matches / len(a) if a else float(not b)
    recall = matches / len(b) if b else 1.0
    boundary = (a.startswith(b[:48]) and a.endswith(b[-48:])) if b else not bool(a)
    return {"precision": precision, "recall": recall, "boundary_match": boundary,
            "text_match_98": precision >= .98 and recall >= .98,
            "boundary_and_98_match": precision >= .98 and recall >= .98 and boundary}


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def seal(result: dict[str, Any]) -> dict[str, Any]:
    result.pop("assessment_sha256", None)
    result["text_sha256"] = hashlib.sha256(result["text"].encode()).hexdigest()
    result["evidence_sha256"] = digest({k: result.get(k) for k in
        ("source_sha256", "page_sha256", "physical_page", "text_sha256", "spans", "closing_boundary")})
    result["assessment_sha256"] = digest(result)
    return result


def _box(box: Iterable[float], size: tuple[float, float]) -> list[float]:
    value = list(box)
    if len(value) != 4 or not all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in value):
        raise ValueError("invalid_source_box")
    x0, y0, x1, y1 = value
    if not (0 <= x0 < x1 <= size[0] + 1 and 0 <= y0 < y1 <= size[1] + 1):
        raise ValueError("invalid_source_box")
    return value


def validate_lines(lines: Iterable[dict[str, Any]], size: tuple[float, float]) -> list[dict[str, Any]]:
    result, seen = [], set()
    for line in lines:
        if line.get("page_no", 1) != 1:
            raise ValueError("native_span_outside_first_physical_page")
        ident = line["id"]
        if not isinstance(ident, (str, int)) or isinstance(ident, bool) or ident in seen:
            raise ValueError("invalid_or_duplicate_native_line_id")
        seen.add(ident)
        text = line["text"]
        if not isinstance(text, str):
            raise ValueError("invalid_native_text")
        value = dict(line, bbox=_box(line["bbox"], size), page_no=1)
        previous = 0
        for span in line.get("runs", []):
            start, end = span["start"], span["end"]
            if not isinstance(start, int) or not isinstance(end, int) or not previous <= start < end <= len(text):
                raise ValueError("invalid_native_run_offsets")
            if span.get("text", text[start:end]) != text[start:end]:
                raise ValueError("native_run_text_mismatch")
            run_box = span.get("bbox", value["bbox"])
            if (run_box[0] == run_box[2]
                    and all(unicodedata.combining(char) for char in text[start:end])):
                # Some PDFs position a combining accent on a zero-width glyph.
                # It belongs to a valid native line, but is not a spatial span.
                if (len(run_box) != 4 or not all(isinstance(x, (int, float)) and
                        not isinstance(x, bool) and math.isfinite(x) for x in run_box)
                        or not (value["bbox"][0] <= run_box[0] <= value["bbox"][2]
                                and 0 <= run_box[1] < run_box[3] <= size[1] + 1)):
                    raise ValueError("invalid_source_box")
            else:
                _box(run_box, size)
            previous = end
        result.append(value)
    return result


def _span(line: dict[str, Any], start: int = 0, end: int | None = None) -> dict[str, Any]:
    end = len(line["text"]) if end is None else end
    return {"line_id": line["id"], "physical_page": 1, "start": start, "end": end,
            "text": line["text"][start:end], "bbox": list(line["bbox"]),
            "box_precision": "containing_native_line; character offsets are exact"}


def reconstruct(spans: list[dict[str, Any]], lines: list[dict[str, Any]]) -> str:
    lookup = {line["id"]: line for line in lines}
    parts = []
    for span in spans:
        line = lookup[span["line_id"]]
        if span.get("physical_page") != 1 or not 0 <= span["start"] < span["end"] <= len(line["text"]):
            raise ValueError("invalid_evidence_interval")
        text = line["text"][span["start"]:span["end"]]
        if text != span["text"] or list(line["bbox"]) != span["bbox"]:
            raise ValueError("evidence_interval_changed")
        parts.append(text)
    return normalize(" ".join(parts))


def _overlap(a: list[float], b: list[float]) -> float:
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0])) / max(1, min(a[2]-a[0], b[2]-b[0]))


def _streams(lines: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Actual order plus geometric columns; no permutation of individual words."""
    ordered = sorted(lines, key=lambda x: (x["bbox"][1], x["bbox"][0], str(x["id"])))
    streams = [lines, ordered]
    for anchor in ordered:
        lane = [x for x in ordered if _overlap(anchor["bbox"], x["bbox"]) >= .75
                and abs(x["bbox"][0]-anchor["bbox"][0]) <= 36]
        if lane:
            streams.append(lane)
    unique = {}
    for stream in streams:
        unique[tuple(x["id"] for x in stream)] = stream
    return list(unique.values())


def align_text(text: str, native_lines: list[dict[str, Any]], page_size: tuple[float, float]) -> dict[str, Any]:
    """Locate a unique, contiguous canonical interval, including split native lines.

    No full-page placeholder boxes or unlocated string-similarity admissions.
    Normalization permits ligatures, whitespace and hyphenation, not missing
    words. Approximate-only matches remain review-only. Duplicate source
    locations are ambiguous even when their text is identical.
    """
    lines = validate_lines(native_lines, page_size)
    target = canonical(text)
    if not target:
        return {"status": "empty", "spans": [], "coordinate_source": "none"}
    locations = {}
    for stream in _streams(lines):
        chars, offsets = [], []
        for line in stream:
            for offset, char in enumerate(line["text"]):
                for c in canonical(char):
                    chars.append(c); offsets.append((line["id"], offset))
        source = "".join(chars)
        pos = source.find(target)
        lookup = {line["id"]: line for line in stream}
        while pos >= 0:
            mapped = offsets[pos:pos+len(target)]
            spans = []
            for ident, offset in mapped:
                if spans and spans[-1]["line_id"] == ident:
                    spans[-1]["end"] = offset + 1
                    spans[-1]["text"] = lookup[ident]["text"][spans[-1]["start"]:offset+1]
                else:
                    spans.append(_span(lookup[ident], offset, offset+1))
            # Restore adjacent punctuation only when present in the candidate.
            first, last = spans[0], spans[-1]
            first_line, last_line = lookup[first["line_id"]], lookup[last["line_id"]]
            leading = re.match(r"^\W*", text).group()
            trailing = re.search(r"\W*$", text).group()
            if leading and first["start"] >= len(leading) and first_line["text"][first["start"]-len(leading):first["start"]] == leading:
                first["start"] -= len(leading)
                first["text"] = first_line["text"][first["start"]:first["end"]]
            if trailing and last_line["text"][last["end"]:last["end"]+len(trailing)] == trailing:
                last["end"] += len(trailing)
                last["text"] = last_line["text"][last["start"]:last["end"]]
            # Intermediate line punctuation is part of the located source interval.
            for i, span in enumerate(spans):
                line = lookup[span["line_id"]]
                if i > 0:
                    span["start"] = 0
                if i < len(spans)-1:
                    span["end"] = len(line["text"])
                span["text"] = line["text"][span["start"]:span["end"]]
            key = tuple((s["line_id"], s["start"], s["end"]) for s in spans)
            locations[key] = spans
            pos = source.find(target, pos+1)
    if len(locations) != 1:
        return {"status": "ambiguous" if locations else "unlocated", "spans": [],
                "locations": len(locations), "coordinate_source": "none"}
    spans = next(iter(locations.values()))
    return {"status": "located", "spans": spans, "text": reconstruct(spans, lines),
            "coordinate_source": "native_pdf_character_intervals", "agreement": 1.0}


def _document_items(document: dict[str, Any], size: tuple[float, float]) -> list[dict[str, Any]]:
    objects = {}
    for group in ("texts", "groups", "pictures", "tables"):
        for item in document.get(group, []):
            ref = item["self_ref"]
            if ref in objects:
                raise ValueError("duplicate_document_reference")
            objects[ref] = item
    ordered, seen = [], set()
    stack = [document.get("body", {"self_ref": "#/body", "children": []})]
    while stack:
        item = stack.pop()
        ref = item["self_ref"]
        if ref in seen:
            raise ValueError("duplicate_or_cyclic_reading_order")
        seen.add(ref)
        if item.get("text"):
            boxes = []
            for prov in item.get("prov", []):
                if prov.get("page_no") != 1:
                    raise ValueError("model_region_outside_first_physical_page")
                b = prov["bbox"]
                if b.get("coord_origin") == "TOPLEFT":
                    coords = [b["l"], b["t"], b["r"], b["b"]]
                elif b.get("coord_origin") == "BOTTOMLEFT":
                    coords = [b["l"], size[1]-b["t"], b["r"], size[1]-b["b"]]
                else:
                    raise ValueError("unknown_model_coordinate_origin")
                boxes.append(_box(coords, size))
            ordered.append({**item, "boxes": boxes})
        for child in reversed(item.get("children", [])):
            stack.append(objects[child.get("cref", child.get("$ref"))])
    return ordered


def _style(line: dict[str, Any]) -> dict[str, Any]:
    runs = line.get("runs", [])
    if runs:
        longest = max(runs, key=lambda x: x["end"]-x["start"])
        return {**{k: longest.get(k) for k in ("font", "size", "flags", "color")}, "background": line.get("background")}
    return {k: line.get(k) for k in ("font", "size", "flags", "color", "background")}


def _bold(style: dict[str, Any]) -> bool:
    return bool((style.get("flags") or 0) & 16 or re.search(r"bold|black|heavy", style.get("font") or "", re.I))


def _role(text: str, *, structured: bool = False) -> str | None:
    t = normalize(text)
    footnote = re.sub(r"^[*†‡§∗\s]+", "", t)
    if footnote != t and re.match(r"(?:(?:both|these|all)\s+)?authors?\s+contributed\b|work\s+done\s+while\b", footnote, re.I):
        return "metadata_or_non_abstract"
    if NON_ABSTRACT.match(t) or METADATA.match(t) or re.match(r"^(?:Fig\.?|Figure|Table)\s*\d+\b", t, re.I) or _author_list(t):
        return "metadata_or_non_abstract"
    section = re.sub(r"^(?:\d+(?:\.\d+)*|[IVX]+)[.)]?\s+", "", t).split(":", 1)[0].strip(" .:").lower()
    if structured and section in INTERNAL and not re.match(r"^(?:\d+|[IVX]+)[.)]?\s+", t):
        return None
    if SECTION.match(t) or NUMBERED_SECTION.match(t):
        return "body_section"
    return None


def _author_list(text: str) -> bool:
    words = re.findall(r"[^\W\d_]+", text, flags=re.U)
    capitals = sum(w[0].isupper() for w in words)
    return bool(words and not RESEARCH.search(text) and
                (text.count(",") >= 2 or len(re.findall(r"\b[A-Z]\.", text)) >= 3) and
                capitals / len(words) > .55)


def _fragments(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for line in lines:
        cuts = {0, len(line["text"])}
        cuts.update(m.end() for m in EMBEDDED.finditer(line["text"]))
        for m in re.finditer(r"\n\s*", line["text"]):
            cuts.add(m.end())
        # Retain a style-supported inline heading even when native PDF grouping
        # placed it in the same line/region as abstract prose.
        for run in line.get("runs", []):
            suffix = line["text"][run["start"]:]
            if run["start"] > 0 and _bold(run) and (_role(suffix) or _role(line["text"][run["start"]:run["end"]])):
                cuts.add(run["start"])
                if _role(line["text"][run["start"]:run["end"]]):
                    cuts.add(run["end"])
        points = sorted(cuts)
        for a, b in zip(points, points[1:]):
            while a < b and line["text"][a].isspace(): a += 1
            while b > a and line["text"][b-1].isspace(): b -= 1
            if a < b:
                out.append({"line": line, "start": a, "end": b,
                            "text": line["text"][a:b], "bbox": line["bbox"], "style": _style(line)})
    return sorted(out, key=lambda x: (x["bbox"][1], x["bbox"][0], x["start"]))


def _is_same_lane(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return _overlap(a["bbox"], b["bbox"]) >= .65 and abs(a["bbox"][0]-b["bbox"][0]) <= 48


def _boundary(fragment: dict[str, Any], kind: str, trusted: bool) -> dict[str, Any]:
    return {"kind": kind, "trusted_for_proposal": trusted,
            "source_span": _span(fragment["line"], fragment["start"], fragment["end"]),
            "style": fragment["style"]}


def _candidate(anchor: dict[str, Any], fragments: list[dict[str, Any]], *, explicit: bool,
               model_items: list[dict[str, Any]]) -> dict[str, Any]:
    text_start = anchor["start"]
    if explicit:
        text_start += ABSTRACT.match(anchor["text"]).end()
    inline = text_start < anchor["end"]
    if inline:
        first = anchor
    else:
        following = [f for f in fragments if f is not anchor and f["bbox"][1] >= anchor["bbox"][3]-2
                     and _is_same_lane(anchor, f)]
        if not following:
            return {"text": "", "spans": [], "status": "absent", "reasons": ["heading_without_prose"], "closing_boundary": None}
        first = following[0]
    lane = [f for f in fragments if _is_same_lane(first, f)
            and (f["bbox"][1], f["start"]) >= (first["bbox"][1], first["start"])]
    internal_headers = {normalize(f["text"]).split(":", 1)[0].lower() for f in lane
                        if re.match(r"^(?:Methods?|Results)\s*:", f["text"], re.I)}
    structured = len(internal_headers) >= 2
    selected, boundary = [], None
    previous = None
    for f in lane:
        # Another explicit Abstract heading is not a continuation in this lane.
        if f is not anchor and ABSTRACT.match(f["text"]):
            boundary = _boundary(f, "another_abstract_region", False); break
        role = _role(f["text"], structured=structured)
        if role:
            boundary = _boundary(f, role, True); break
        if selected:
            # A model label is usable only when its text is actually represented
            # by this native fragment; a broad estimated box is not role evidence.
            excluded = next((m for m in model_items if m.get("label") in EXCLUDED_LABELS
                             and canonical(f["text"]) and canonical(f["text"]) in canonical(m["text"])
                             and any(_overlap(f["bbox"], b) >= .8 and b[1]-2 <= f["bbox"][1] <= b[3]+2 for b in m["boxes"])), None)
            if excluded:
                boundary = _boundary(f, "located_" + excluded["label"], True); break
            before = previous["style"]
            after = f["style"]
            new_paragraph = (f["line"].get("block_id") != previous["line"].get("block_id")
                             or f["bbox"][1]-previous["bbox"][3] > max(3, .35*(f["bbox"][3]-f["bbox"][1])))
            changed_color = before.get("color") is not None and after.get("color") is not None and before["color"] != after["color"]
            changed_weight = _bold(before) and not _bold(after) and after.get("font") is not None
            changed_panel = before.get("background") != after.get("background")
            if new_paragraph and (changed_color or changed_weight or changed_panel) and len(f["text"]) > 25:
                # Typography alone does not certify semantics. Expose the safe
                # prefix and hold it; source review can adjudicate a synopsis.
                boundary = _boundary(f, "separate_styled_region", False); break
            if f["bbox"][1]-previous["bbox"][3] > 42:
                boundary = _boundary(f, "layout_gap", False); break
        start = text_start if f is anchor and explicit else f["start"]
        if start < f["end"]:
            selected.append(_span(f["line"], start, f["end"]))
            previous = f
    text = normalize(" ".join(s["text"] for s in selected))
    reasons = []
    if not text:
        status = "absent"; reasons.append("heading_without_prose")
    elif not canonical(text):
        status = "uncertain"; reasons.append("insufficient_abstract_prose")
    elif _author_list(text):
        status = "absent"; reasons.append("author_list_not_abstract")
    elif not SENTENCE_END.search(text):
        status = "partial"; reasons.append("unfinished_final_sentence")
    elif not boundary or not boundary["trusted_for_proposal"]:
        status = "uncertain"; reasons.append("closing_boundary_requires_source_review")
    else:
        status = "complete"; reasons.append("located_source_with_structural_closing_boundary")
    return {"text": text, "spans": selected, "status": status, "reasons": reasons,
            "closing_boundary": boundary, "structured": structured, "explicit_heading": explicit}



def _column_continuation(candidate: dict[str, Any], fragments: list[dict[str, Any]],
                         model_items: list[dict[str, Any]], size: tuple[float, float],
                         scholarly_abstract: str) -> dict[str, Any]:
    """Allow a constrained, witnessed column wrap; never join by proximity alone.

    A bottom-of-column prefix must be contiguous with the next source region in
    the reading-order tree (excluding located notes). The continuation must be
    above a structural closing boundary in a different column. An unfinished
    sentence needs a lower-case continuation; a sentence-ended prefix additionally
    needs a source-located scholarly field covering the entire concatenation.
    Ambiguous possible wraps remain held, and no model text is substituted.
    """
    if (not candidate["spans"] or candidate["status"] not in {"partial", "uncertain"}
            or candidate["closing_boundary"] is not None):
        return candidate
    last = candidate["spans"][-1]
    if last["bbox"][3] < .75*size[1]:
        return candidate
    tree = canonical(" ".join(m["text"] for m in model_items if m.get("label") not in EXCLUDED_LABELS))
    options = []
    for f in fragments:
        if (_overlap(last["bbox"], f["bbox"]) > .15 or f["bbox"][1] > .35*size[1]
                or _role(f["text"]) or ABSTRACT.match(f["text"])):
            continue
        # Do not start halfway down a source column or after its body heading.
        earlier = [x for x in fragments if _is_same_lane(f, x) and x["bbox"][1] < f["bbox"][1]]
        if any(_role(x["text"]) == "body_section" for x in earlier):
            continue
        tail = _candidate(f, fragments, explicit=False, model_items=model_items)
        if tail["status"] != "complete" or not tail["closing_boundary"]["trusted_for_proposal"]:
            continue
        joined = normalize(candidate["text"]+" "+tail["text"])
        target = canonical(joined)
        if not target or tree.count(target) != 1:
            continue
        if SENTENCE_END.search(candidate["text"]):
            if not scholarly_abstract or not compare(joined, scholarly_abstract)["text_match_98"]:
                continue
        elif not f["text"][:1].islower():
            continue
        options.append({**candidate, "text": joined, "spans": candidate["spans"]+tail["spans"],
                        "status": "complete", "closing_boundary": tail["closing_boundary"],
                        "reasons": ["source_column_wrap_with_reading_order_and_closing_boundary"],
                        "column_continuation": {"from_line_id": last["line_id"],
                            "to_line_id": f["line"]["id"], "reading_order_unique_match": True,
                            "sentence_ended_prefix": bool(SENTENCE_END.search(candidate["text"]))}})
    return options[0] if len(options) == 1 else candidate


def assess_document(document: dict[str, Any], *, page_size: Iterable[float], source_sha256: str,
                    page_sha256: str, native_lines: list[dict[str, Any]] | None = None,
                    scholarly_abstract: str = "", max_input_chars: int = 4000,
                    conversion_status: str = "success", conversion_http_status: int | None = None,
                    generation_tokens: int | None = None, generation_limit: int = 4096,
                    finish_reason: str | None = None) -> dict[str, Any]:
    """Produce an experimental, source-bound proposal; always require review.

    Supplied hashes are bindings, not proof that this function read the files.
    The offline harness separately verifies actual source/page/image bytes.
    """
    result = {"schema_version": 3, "extractor_version": VERSION, "physical_page": 1,
              "source_sha256": source_sha256 if isinstance(source_sha256, str) and re.fullmatch("[a-f0-9]{64}", source_sha256) else None,
              "page_sha256": page_sha256 if isinstance(page_sha256, str) and re.fullmatch("[a-f0-9]{64}", page_sha256) else None,
              "status": "uncertain", "text": "", "spans": [], "reasons": [],
              "conversion_status": conversion_status, "conversion_http_status": conversion_http_status,
              "selector_proposal": False, "proposed": False, "eligible_for_jev": False,
              "verified_admission": False, "publication_gate": "source_review_required",
              "automatic_fallback_enabled": False, "request_budget_status": "not_assessed",
              "source_bytes_verified": False, "coordinate_source": "native_pdf_not_model_prediction"}
    try:
        size = tuple(page_size)
        if len(size) != 2 or not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v > 0 for v in size):
            raise ValueError("invalid_page_size")
        result["page_size"] = list(size)
        if any(not isinstance(h, str) or not re.fullmatch("[a-f0-9]{64}", h) for h in (source_sha256, page_sha256)):
            raise ValueError("invalid_source_hash")
        if isinstance(max_input_chars, bool) or not isinstance(max_input_chars, int) or max_input_chars < 1:
            raise ValueError("invalid_request_budget")
        if not isinstance(generation_limit, int) or isinstance(generation_limit, bool) or generation_limit < 1:
            raise ValueError("invalid_generation_limit")
        if generation_tokens is not None and (not isinstance(generation_tokens, int) or isinstance(generation_tokens, bool) or generation_tokens < 0):
            raise ValueError("invalid_generation_token_count")
        if conversion_status == "truncated" or finish_reason in {"length", "max_tokens"} or (
                generation_tokens is not None and generation_tokens >= generation_limit and finish_reason not in {"stop", "eos"}):
            result.update(status="truncated", reasons=["generation_token_limit"],
                          generation_tokens=generation_tokens, generation_limit=generation_limit)
            return seal(result)
        if conversion_status.lower().split(".")[-1] != "success" or (conversion_http_status is not None and conversion_http_status >= 400):
            result.update(status="error", reasons=["isolated_conversion_error"])
            return seal(result)
        lines = validate_lines(native_lines or [], size)
        model_items = _document_items(document, size)
        result["reading_order_refs"] = [m["self_ref"] for m in model_items]
        result["model_document_sha256"] = digest(document)
        if not lines:
            result.update(reasons=["no_locatable_native_source; source_image_review_required"])
            return seal(result)
        fragments = _fragments(lines)
        def excluded_anchor(f):
            return any(m.get("label") in EXCLUDED_LABELS and canonical(f["text"]) in canonical(m["text"])
                       and any(_overlap(f["bbox"], b) >= .8 and b[1]-2 <= f["bbox"][1] <= b[3]+2 for b in m["boxes"])
                       for m in model_items)
        anchors = [f for f in fragments if ABSTRACT.match(f["text"]) and not excluded_anchor(f)]
        if len(anchors) > 1:
            result.update(reasons=["multiple_native_abstract_regions"])
            return seal(result)
        field = align_text(scholarly_abstract, lines, size) if scholarly_abstract.strip() else {"status": "empty", "spans": []}
        result["scholarly_field_location"] = field
        candidates = []
        if anchors:
            initial = _candidate(anchors[0], fragments, explicit=True, model_items=model_items)
            candidates.append(_column_continuation(initial, fragments, model_items, size,
                                                  scholarly_abstract if field["status"] == "located" else ""))
        else:
            # A forbidden cover-page role vetoes unlabelled guessing. It does not
            # veto a separately labelled real abstract elsewhere on that page.
            forbidden = [f for f in fragments if NON_ABSTRACT.match(normalize(f["text"]))]
            if forbidden:
                result.update(status="absent", reasons=["non_abstract_page_role"],
                              page_role_evidence=[_span(f["line"], f["start"], f["end"]) for f in forbidden])
                return seal(result)
            for f in fragments:
                if _role(f["text"]) or _author_list(f["text"]) or excluded_anchor(f):
                    continue
                prior_body = any(x["bbox"][1] <= f["bbox"][1] and _is_same_lane(f, x)
                                 and _role(x["text"]) == "body_section" for x in fragments if x is not f)
                if prior_body:
                    continue
                starts_field = field["status"] == "located" and field["spans"][0]["line_id"] == f["line"]["id"] and field["spans"][0]["start"] >= f["start"]
                if not starts_field and not (_bold(f["style"]) and RESEARCH.search(f["text"])):
                    continue
                candidate = _candidate(f, fragments, explicit=False, model_items=model_items)
                if len(candidate["text"]) < 100 or not RESEARCH.search(candidate["text"]):
                    continue
                if starts_field and not compare(candidate["text"], scholarly_abstract)["text_match_98"]:
                    candidate["status"] = "uncertain"
                    candidate["reasons"].append("scholarly_field_does_not_match_bounded_source")
                candidates.append(candidate)
        if not candidates:
            result.update(status="absent" if not scholarly_abstract else "uncertain",
                          reasons=["no_identified_page_one_abstract"])
            return seal(result)
        # Multiple physically distinct candidates are not resolved by tree order
        # or by blindly preferring the left column.
        unique = {tuple((s["line_id"], s["start"], s["end"]) for s in c["spans"]): c for c in candidates}
        if len(unique) != 1:
            result.update(reasons=["ambiguous_native_candidates"], candidate_count=len(unique))
            return seal(result)
        candidate = next(iter(unique.values()))
        result.update(candidate)
        if reconstruct(result["spans"], lines) != result["text"]:
            raise ValueError("source_reconstruction_mismatch")
        result["native_alignment"] = 1.0
        result["native_alignment_basis"] = "exact reconstruction from returned source intervals; not a model accuracy score"
        model_text = canonical(" ".join(m["text"] for m in model_items))
        target = canonical(result["text"])
        result["selected_text_in_layout_tree"] = bool(target) and model_text.count(target) == 1
        result["transcription"] = "native_pdf"
        result["request_budget_status"] = "within_budget" if len(result["text"]) <= max_input_chars else "exceeds_character_budget"
        result["selector_proposal"] = result["status"] == "complete"
        # 'proposed' uses the historical request-budget scoring convention.
        result["proposed"] = result["selector_proposal"] and result["request_budget_status"] == "within_budget"
        if result["request_budget_status"] != "within_budget":
            result["reasons"].append("complete_text_retained; request_character_budget_exceeded")
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        # Do not echo parser text, paths, source paper names or credentials.
        result.update(status="error", selector_proposal=False, proposed=False,
                      reasons=["invalid_source_or_layout_input", type(exc).__name__])
    return seal(result)


def verify_scholarly_field(field: str, document: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """A header field is corroboration only, never evidence of first-page scope."""
    result = assess_document(document, scholarly_abstract=field, **kwargs)
    match = bool(field.strip()) and compare(result["text"], field)["text_match_98"]
    location = result.get("scholarly_field_location", {}).get("status") == "located"
    result["scholarly_field_verified"] = bool(match and location and result["status"] == "complete")
    if not result["scholarly_field_verified"]:
        result["selector_proposal"] = result["proposed"] = False
        if result["status"] == "complete":
            result["status"] = "uncertain"
        result["reasons"].append("scholarly_field_requires_bounded_first_page_verification")
    return seal(result)
