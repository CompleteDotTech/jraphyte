"""Native first-page alignment with character-level provenance (no model calls).

Canonical agreement is a location aid, not proof of scientific notation fidelity.
No OCR coordinate is invented. Source text, offsets and boxes remain inspectable.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import math
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence
from .pdf_geometry_parallel_v4 import (logical_rows, transition_evidence, _horizontal,
                                     _exact_runs, _gutter, _same_row, _similar_extent)

VERSION = "page-one-parallel-source-v4"
SLICE_VERSION = "native-requested-leading-prefix-v1"
CHAIN_VERSION = "native-terminal-wrap-chain-v1"
FRACTION_VERSION = "source-vector-fraction-seam-v1"


def canonical(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text).casefold() if c.isalnum())


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest_value(value: object) -> str:
    return hashlib.sha256(json_bytes(value)).hexdigest()


def compare(predicted: str, reference: str) -> dict:
    """Exactly the ordered-character/boundary definition of the frozen report."""
    a, b = canonical(predicted), canonical(reference)
    matches = sum(m.size for m in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks())
    precision = matches / len(a) if a else float(not b)
    recall = matches / len(b) if b else 1.0
    boundary = a.startswith(b[:48]) and a.endswith(b[-48:]) if b else not bool(a)
    return {"precision": precision, "recall": recall, "boundary_match": boundary,
            "text_match_98": precision >= .98 and recall >= .98,
            "boundary_and_98_match": precision >= .98 and recall >= .98 and boundary}


def overlap(a: Sequence[float], b: Sequence[float]) -> float:
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0])) / max(1.0, min(a[2]-a[0], b[2]-b[0]))


def validate_box(box: Sequence[float], page_size: Sequence[float]) -> list[float]:
    if len(box) != 4 or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in box):
        raise ValueError("invalid_source_box")
    x0, y0, x1, y1 = box
    w, h = page_size
    if not 0 <= x0 < x1 <= w + 1 or not 0 <= y0 < y1 <= h + 1:
        raise ValueError("source_box_outside_first_page")
    return list(box)


def validate_lines(lines: Iterable[Mapping], page_size: Sequence[float]) -> list[dict]:
    result, seen = [], set()
    for raw in lines:
        line = dict(raw)
        key = str(line["id"])
        if key in seen:
            raise ValueError("duplicate_native_line_id")
        seen.add(key)
        if line.get("page_no", 1) != 1:
            raise ValueError("native_line_outside_first_physical_page")
        if not isinstance(line["text"], str):
            raise ValueError("native_text_not_string")
        line["bbox"] = validate_box(line["bbox"], page_size)
        for span in line.get("spans", []):
            start, end = span["start"], span["end"]
            if not isinstance(start, int) or not isinstance(end, int) or not 0 <= start <= end <= len(line["text"]):
                raise ValueError("invalid_native_span_offsets")
            if span.get("text", line["text"][start:end]) != line["text"][start:end]:
                raise ValueError("native_span_text_mismatch")
            if "size" in span and (not isinstance(span["size"], (int,float)) or not math.isfinite(span["size"]) or span["size"] < 0):
                raise ValueError("invalid_native_font_size")
            for field in ("flags", "color"):
                if field in span and (isinstance(span[field],bool) or not isinstance(span[field],int) or span[field] < 0):
                    raise ValueError("invalid_native_style")
        result.append(line)
    return result


def source_lines(page) -> list[dict]:
    """Read native spans from a verified PyMuPDF first-page object, never OCR."""
    if page.number != 0:
        raise ValueError("only_first_physical_page_is_allowed")
    result = []
    for bi, block in enumerate(page.get_text("dict", sort=True)["blocks"]):
        if block.get("type") != 0:
            continue
        for li, line in enumerate(block.get("lines", [])):
            spans, chunks, offset = [], [], 0
            for span in line.get("spans", []):
                text = span.get("text", "")
                spans.append({"start": offset, "end": offset+len(text), "text": text,
                              "font": span.get("font"), "size": span.get("size"),
                              "flags": span.get("flags", 0), "color": span.get("color", 0),
                              "bbox": list(span["bbox"])})
                chunks.append(text)
                offset += len(text)
            result.append({"id": len(result), "block_id": bi, "line_in_block": li, "page_no": 1,
                           "bbox": list(line["bbox"]), "text": "".join(chunks), "spans": spans})
    return validate_lines(result, (page.rect.width, page.rect.height))


@dataclass(frozen=True, init=False)
class SourceGeometry:
    """Owned, PDF-derived geometry for an explicit source locator opt-in.

    Construct through ``from_pdf``. A serialized dictionary is not a verified
    context. Native JSON is unchanged; this object supplies no text correction,
    section ownership, scientific-fidelity approval or graph authority.
    """
    _evidence: bytes

    def __init__(self):
        raise ValueError("source_geometry_use_verified_pdf_factory")

    @classmethod
    def from_pdf(cls, pdf_bytes: bytes, native_lines: list[dict], *, expected_source_sha256: str):
        if not isinstance(pdf_bytes, (bytes, bytearray, memoryview)):
            raise ValueError("source_geometry_requires_pdf_bytes")
        owned = bytes(pdf_bytes)
        source_sha = hashlib.sha256(owned).hexdigest()
        if not isinstance(expected_source_sha256, str) or source_sha != expected_source_sha256:
            raise ValueError("source_geometry_pdf_hash_mismatch")
        native = json.loads(json_bytes(native_lines))
        import fitz
        with fitz.open(stream=owned, filetype="pdf") as document:
            if not len(document):
                raise ValueError("source_geometry_empty_pdf")
            page = document[0]
            if digest_value(source_lines(page)) != digest_value(native):
                raise ValueError("source_geometry_native_mismatch")
            directions = []
            for block in page.get_text("dict", sort=True)["blocks"]:
                if block.get("type") == 0:
                    directions.extend(list(line.get("dir", ())) for line in block.get("lines", []))
            drawings = page.get_drawings(extended=True)
            paint = page.get_bboxlog()
            trace = page.get_texttrace()
            # A clipped vector plot supplies a bounded, PDF-owned figure
            # footprint.  The selector still has to prove caption and text
            # ownership; this evidence alone never closes an abstract.
            figure_regions = []
            if page.first_annot is None and page.first_widget is None:
                for drawing in drawings:
                    framed = (drawing.get("type") == "s" and len(drawing.get("items", [])) == 1
                              and drawing["items"][0][0] == "re")
                    if drawing.get("type") != "clip" and not framed:
                        continue
                    box = drawing.get("scissor") if drawing.get("type") == "clip" else drawing.get("rect")
                    if box is None:
                        continue
                    if (box.width < page.rect.width * .3 or box.height < page.rect.height * .1
                            or box.y0 < 0 or box.y1 > page.rect.height):
                        continue
                    bars = [path for path in drawings if path.get("type") in {"f", "fs"}
                            and path.get("rect") and path.get("fill") is not None
                            and 5 <= path["rect"].width <= 40
                            and box.x0 <= path["rect"].x0 <= path["rect"].x1 <= box.x1
                            and box.y0 <= path["rect"].y0 < box.y1]
                    if len({round(path["rect"].x0, 1) for path in bars}) >= 8:
                        entry = list(box)
                        if entry not in figure_regions:
                            figure_regions.append(entry)
            next_page_opening = None
            if len(document) > 1:
                following = document[1]
                lines = []
                for block in following.get_text("dict", sort=True)["blocks"]:
                    if block.get("type") == 0:
                        for line in block.get("lines", []):
                            value = "".join(span.get("text", "") for span in line.get("spans", [])).strip()
                            if value:
                                lines.append((list(line["bbox"]), value))
                lines.sort(key=lambda row: (row[0][1], row[0][0]))
                if lines and lines[0][0][1] < following.rect.height * .2:
                    first_box, first_text = lines[0]
                    preceding_header = None
                    preceding_bibliography = None
                    # A title-page PDF may repeat its title above a contents
                    # page. Keep that header as evidence; the selector must
                    # match it to the located first-page title before using
                    # Contents as a closing witness.
                    if (len(lines) > 1 and re.fullmatch(r"contents", lines[1][1], re.I)
                            and lines[1][0][1] < following.rect.height * .2
                            and .04 * following.rect.height <= first_box[1] < lines[1][0][1] - 8
                            and 20 <= len(first_text) <= 180
                            and abs((first_box[0] + first_box[2])/2 - following.rect.width/2)
                            <= following.rect.width * .12):
                        preceding_header = {"text": first_text,
                                            "text_sha256": hashlib.sha256(first_text.encode()).hexdigest(),
                                            "box": first_box}
                        first_box, first_text = lines[1]
                    # Some proceedings put the running title and author on
                    # opposite ends of one header row, then begin the body
                    # with a numbered Introduction. Retain the exact pair for
                    # first-page title/author verification by the selector.
                    elif (len(lines) > 2 and abs(lines[0][0][1] - lines[1][0][1]) < 3
                          and max(lines[0][0][3], lines[1][0][3]) + 12 < lines[2][0][1]
                          and lines[2][0][1] < following.rect.height * .2):
                        left, right = sorted(lines[:2], key=lambda row: row[0][0])
                        if (left[0][0] < following.rect.width * .4
                                and right[0][0] > following.rect.width * .55
                                and 8 <= len(left[1]) <= 180 and 8 <= len(right[1]) <= 180
                                and re.fullmatch(r"(?:[IVX]+|\d+)[.)]?\s+introduction", lines[2][1], re.I)):
                            preceding_bibliography = {
                                "running_title": {"text": left[1], "box": left[0],
                                                  "text_sha256": hashlib.sha256(left[1].encode()).hexdigest()},
                                "running_author": {"text": right[1], "box": right[0],
                                                   "text_sha256": hashlib.sha256(right[1].encode()).hexdigest()}}
                            first_box, first_text = lines[2]
                    opening = first_text
                    boxes = [first_box]
                    if (re.fullmatch(r"(?:[IVX]+|\d+)[.)]?", first_text, re.I)
                            and len(lines) > 1 and abs(lines[1][0][1] - first_box[1]) < 3):
                        opening += " " + lines[1][1]
                        boxes.append(lines[1][0])
                    kind = ("contents" if re.fullmatch(r"contents", opening, re.I) else
                            "body_section" if re.fullmatch(r"(?:[IVX]+|\d+)[.)]?\s+introduction", opening, re.I)
                            else None)
                    if kind:
                        next_page_opening = {"version": "source-next-page-opening-v1", "kind": kind,
                                             "physical_page": 2, "text": opening,
                                             "text_sha256": hashlib.sha256(opening.encode()).hexdigest(),
                                             "boxes": boxes, "page_size": [following.rect.width, following.rect.height]}
                        if preceding_header is not None:
                            next_page_opening["preceding_header"] = preceding_header
                        if preceding_bibliography is not None:
                            next_page_opening["preceding_bibliography"] = preceding_bibliography
            # Vector extraction is not a visibility guarantee. Unsupported
            # clipping/group compositing and annotation overlays stay held.
            unsupported_compositing = (any(path.get("type") in {"clip", "group"} for path in drawings)
                                       or page.first_annot is not None or page.first_widget is not None)
            rules = []
            for index, drawing in enumerate(drawings):
                items = drawing.get("items", [])
                # A standalone visible stroke is the supported producer shape.
                # Multi-segment paths and rectangle/table borders stay unresolved.
                if (unsupported_compositing or drawing.get("layer") or len(items) != 1
                        or items[0][0] != "l" or drawing.get("type") != "s"
                        or drawing.get("stroke_opacity", 0) < .99 or not drawing.get("color")
                        or min(drawing["color"]) >= .99):
                    continue
                _, a, b = items[0]
                values = [a.x, a.y, b.x, b.y, drawing.get("width", 0)]
                if any(type(value) not in (int, float) or not math.isfinite(value) for value in values):
                    continue
                x0, x1 = sorted((a.x, b.x))
                if abs(a.y-b.y) > .01 or x0 >= x1 or drawing["width"] <= 0:
                    continue
                sequence = drawing.get("seqno")
                if type(sequence) is not int or not 0 <= sequence < len(paint) or paint[sequence][0] != "stroke-path":
                    continue
                radius = drawing["width"]/2
                stroke_box = fitz.Rect(x0-radius, min(a.y, b.y)-radius, x1+radius, max(a.y, b.y)+radius)
                # Images, shading and path bounds conservatively cover their
                # whole paint extent. Text batches can span a full page, so use
                # individual painted glyph boxes rather than their union box.
                if (any(index != sequence and kind == "stroke-path" and fitz.Rect(box).intersects(stroke_box)
                        for index, (kind, box) in enumerate(paint))
                        or any(kind not in {"fill-text", "stroke-text", "ignore-text"}
                        and fitz.Rect(box).intersects(stroke_box) for kind, box in paint[sequence+1:])
                        or any(span.get("seqno", -1) > sequence and span.get("type") != 3
                               and span.get("opacity", 1) > 0 and any(not chr(char[0]).isspace()
                                   and fitz.Rect(char[3]).intersects(stroke_box) for char in span["chars"])
                               for span in trace)):
                    continue
                rules.append({"drawing_index": index, "seqno": drawing.get("seqno"),
                              "x0": x0, "x1": x1, "y": (a.y+b.y)/2,
                              "stroke_width": drawing["width"], "opacity": drawing["stroke_opacity"],
                              "color": list(drawing["color"]),
                              "visibility_check": "no_later_overlapping_paint_v1"})
            evidence = {"version": FRACTION_VERSION, "source_sha256": source_sha,
                        "native_sha256": digest_value(native), "physical_page": 1,
                        "rotation": page.rotation, "directions": directions, "rules": rules,
                        "next_page_opening": next_page_opening,
                        "unsupported_compositing": unsupported_compositing,
                        "painted_glyphs": _painted_glyphs(page, native, trace, paint) if rules else {}}
            if figure_regions:
                evidence["vector_figure_regions"] = figure_regions
        instance = object.__new__(cls)
        object.__setattr__(instance, "_evidence", json_bytes(evidence))
        return instance

    def descriptor(self) -> dict:
        """Return a detached inspectable receipt, never an importable authority."""
        return json.loads(self._evidence)


def verify_source_geometry_policy(policy: dict | None, context: SourceGeometry | None,
                                  *, source_sha256: str, native_sha256: str) -> None:
    """Require exact source/native/version replay for an enabled assessment."""
    if policy is None:
        if context is not None:
            raise ValueError("source_geometry_context_not_declared_by_assessment")
        return
    if type(context) is not SourceGeometry or not isinstance(policy, dict):
        raise ValueError("source_geometry_verified_context_required")
    descriptor = context.descriptor()
    if (policy.get("enabled") is not True or policy.get("version") != descriptor.get("version") or
            policy.get("source_sha256") != source_sha256 or
            policy.get("native_sha256") != native_sha256 or
            policy.get("descriptor_sha256") != digest_value(descriptor) or
            descriptor.get("source_sha256") != source_sha256 or
            descriptor.get("native_sha256") != native_sha256 or
            descriptor.get("physical_page") != 1):
        raise ValueError("source_geometry_assessment_identity_mismatch")


def _painted_glyphs(page, native: list[dict], trace: list[dict], paint: list) -> dict:
    """Exact RAWDICT-to-trace visibility witnesses; uncertain mappings omitted.

    In particular a ligature continuation with glyph_id=-1 is not invented as
    an independently painted glyph. Later paint is retained for the seam to
    reject, except its own independently checked fraction rule.
    """
    import fitz
    key = lambda text, origin, font, size: (text, tuple(round(v, 4) for v in origin), font, round(size, 4))
    index = defaultdict(list)
    for span in trace:
        for char in span["chars"]:
            index[key(chr(char[0]), char[2], span["font"], span["size"])].append((span, char))
    raw_lines = [line for block in page.get_text("rawdict", sort=True)["blocks"] if block.get("type") == 0
                 for line in block.get("lines", [])]
    if len(raw_lines) != len(native):
        return {}
    result = {}
    for line, raw in zip(native, raw_lines):
        if line["text"] != "".join(char["c"] for span in raw["spans"] for char in span["chars"]):
            continue
        glyphs, offset = {}, 0
        for run in raw["spans"]:
            for char in run["chars"]:
                start = offset
                offset += len(char["c"])
                if len(char["c"]) != 1 or char["c"].isspace():
                    continue
                matches = index[key(char["c"], char["origin"], run["font"], run["size"])]
                if len(matches) != 1:
                    continue
                span, traced = matches[0]
                box = fitz.Rect(traced[3])
                if (span.get("type") not in {0, 1} or span.get("opacity", 0) < .99 or span.get("layer")
                        or not span.get("color") or min(span["color"]) >= .99 or traced[1] < 0
                        or box.is_empty or not box.intersects(fitz.Rect(char["bbox"]))):
                    continue
                sequence = span["seqno"]
                if any(other["seqno"] > sequence and other.get("type") != 3 and other.get("opacity", 1) > 0
                       and fitz.Rect(other["bbox"]).intersects(box)
                       and any(not chr(value[0]).isspace() and fitz.Rect(value[3]).intersects(box)
                               for value in other["chars"]) for other in trace):
                    continue
                occluders = [i for i, (kind, bounds) in enumerate(paint) if i > sequence
                             and kind not in {"fill-text", "stroke-text", "ignore-text"}
                             and fitz.Rect(bounds).intersects(box)]
                glyphs[str(start)] = {"offset": start, "character": char["c"], "origin": list(char["origin"]),
                                     "source_bbox": list(char["bbox"]), "trace_bbox": list(traced[3]),
                                     "font": span["font"], "size": span["size"], "seqno": sequence,
                                     "glyph_id": traced[1], "paint_type": span["type"], "opacity": span["opacity"],
                                     "later_paint_seqnos": occluders}
        result[str(line["id"])] = glyphs
    return result


def _fraction_rows(native: list[dict], rows: list[dict], context: SourceGeometry) -> list[dict]:
    if type(context) is not SourceGeometry:
        raise ValueError("source_geometry_verified_context_required")
    evidence = context.descriptor()
    if digest_value(native) != evidence["native_sha256"]:
        raise ValueError("source_geometry_native_changed")
    if evidence["rotation"] != 0:
        return rows
    directions = {str(line["id"]): direction for line, direction in zip(native, evidence["directions"])}
    horizontal = lambda line: directions.get(str(line["id"])) == [1.0, 0.0] and _horizontal(line)
    by_block = defaultdict(list)
    for line in native:
        by_block[line.get("block_id")].append(line)
    singletons = [row for row in rows if len(row["lines"]) == 1]
    proposals = []
    for left_row in singletons:
        left = left_row["lines"][0]
        if (not horizontal(left) or type(left.get("block_id")) is not int
                or left.get("line_in_block") != 0 or len(by_block[left["block_id"]]) != 1):
            continue
        lr = _exact_runs(left)
        visible = [run for run in lr if run["text"].strip()]
        if len(visible) < 2:
            continue
        flank, upper = visible[-2:]
        if (upper is not lr[-1] or not re.fullmatch(r"[0-9]", upper["text"])
                or len(canonical(flank["text"])) < 3):
            continue
        for right_row in singletons:
            right = right_row["lines"][0]
            if (left is right or not horizontal(right) or not _same_row(left, right)
                    or type(right.get("block_id")) is not int or right["block_id"] == left["block_id"]
                    or right.get("line_in_block") != 0):
                continue
            owner = by_block[right["block_id"]]
            # This bounded rule handles a two-line paragraph split at a fraction.
            # Duplicate indices or hidden later owner lines invalidate the proof.
            if len(owner) != 2 or sorted(line.get("line_in_block", -1) for line in owner) != [0, 1]:
                continue
            following = next(line for line in owner if line["line_in_block"] == 1)
            if not horizontal(following) or not any(row["lines"][0] is following for row in singletons):
                continue
            rr = _exact_runs(right)
            visible_right = [run for run in rr if run["text"].strip()]
            if (len(visible_right) != 2 or visible_right[0] is not rr[0]
                    or not re.fullmatch(r"[1-9]", visible_right[0]["text"])
                    or not re.fullmatch(r"[A-Za-z]{3,}[.,;:]?", visible_right[1]["text"])):
                continue
            lower, tail = visible_right
            em = flank["size"]
            signature = lambda run: (run.get("font"), run["size"], run["flags"] & 18, run.get("color"))
            if (not flank.get("font") or signature(flank) != signature(tail)
                    or _paragraph_font(following) != signature(flank)
                    or not .5*em <= upper["size"] <= .8*em or upper["size"] != lower["size"]
                    or upper.get("font") != lower.get("font") or upper.get("color") != lower.get("color")):
                continue
            b, u, lo, t = (run["bbox"] for run in (flank, upper, lower, tail))
            mid = lambda box: (box[1]+box[3])/2
            if (left["bbox"][2]-left["bbox"][0] < 8*em
                    or not 2*em <= right["bbox"][2]-right["bbox"][0] <= 8*em
                    or abs(b[2]-u[0]) > .25*em or abs(u[0]-lo[0]) > .08*em
                    or abs(u[2]-lo[2]) > .08*em or u[2]-u[0] > em
                    or not 0 <= t[0]-max(u[2], lo[2]) <= .6*em
                    or abs(mid(b)-mid(t)) > .08*em
                    or not .2*em <= mid(b)-mid(u) <= .65*em
                    or not .15*em <= mid(lo)-mid(b) <= .65*em):
                continue
            matches = [rule for rule in evidence["rules"] if abs(rule["x0"]-u[0]) <= .08*em
                       and abs(rule["x1"]-u[2]) <= .08*em and u[3] <= rule["y"] <= lo[1]
                       and rule["stroke_width"] <= .1*em]
            if len(matches) != 1:
                continue
            extent = {"bbox": [left["bbox"][0], min(left["bbox"][1], right["bbox"][1]),
                               right["bbox"][2], max(left["bbox"][3], right["bbox"][3])]}
            step = mid(following["bbox"])-mid(b)
            nearby = [line for line in native if line is not left and line is not right
                      and abs(mid(line["bbox"])-mid(b)) <= 3.2*em]
            if (not .8*em <= step <= 1.8*em or not _similar_extent(following, extent)
                    or abs(following["bbox"][0]-left["bbox"][0]) > 1.25*em
                    or _gutter(left, right, nearby, em)
                    or any(line is not following and overlap(extent["bbox"], line["bbox"]) > .1
                           and min(b[1], u[1]) <= mid(line["bbox"]) <= following["bbox"][3]
                           for line in nearby)):
                continue
            rule_sequence = matches[0]["seqno"]

            def painted(line, offsets):
                values = evidence["painted_glyphs"].get(str(line["id"]), {})
                selected = [values.get(str(offset)) for offset in offsets]
                if not selected or any(value is None or any(seq != rule_sequence for seq in value["later_paint_seqnos"])
                                       for value in selected):
                    return None
                return selected

            run_proofs = []
            for role, line, run in (("left_prose", left, flank), ("upper", left, upper),
                                    ("lower", right, lower), ("right_prose", right, tail)):
                glyphs = painted(line, [i for i in range(run["start"], run["end"]) if not line["text"][i].isspace()])
                if glyphs is None:
                    break
                run_proofs.append({"role": role, "line_id": line["id"], "start": run["start"], "end": run["end"],
                                   "bbox": list(run["bbox"]), "painted_glyphs": glyphs})
            if len(run_proofs) != 4:
                continue
            # Endpoint witnesses establish geometry support only. They must be
            # in one visible paint operation; an unpainted interior ligature is
            # not asserted to have a one-to-one trace mapping or full fidelity.
            following_runs = [run for run in _exact_runs(following) if run["text"].strip()]
            if not following_runs or any(signature(run) != signature(flank) for run in following_runs):
                continue
            nonspace = [i for i, char in enumerate(following["text"]) if not char.isspace()]
            endpoints = painted(following, [nonspace[0], nonspace[-1]]) if nonspace else None
            if endpoints is None or endpoints[0]["seqno"] != endpoints[1]["seqno"]:
                continue
            proof = {"version": FRACTION_VERSION, "reason": "source_vector_fraction_seam",
                     "scope": "raw_reading_order_only", "notation_review_required": True,
                     "source_sha256": evidence["source_sha256"], "native_sha256": evidence["native_sha256"],
                     "physical_page": 1, "native_line_ids": [left["id"], right["id"]],
                     "support_native_line_id": following["id"], "rule": matches[0],
                     "native_runs": run_proofs,
                     "support_visibility": {"scope": "source_line_endpoints_geometry_only", "glyphs": endpoints}}
            proposals.append((left_row, right_row, {**extent, "lines": [left, right], "joins": [proof]}))
    # No greedy resolution of competing partners or reused vector strokes.
    counts = defaultdict(int)
    for a, b, merged in proposals:
        for key in (("line", str(a["lines"][0]["id"])), ("line", str(b["lines"][0]["id"])),
                    ("rule", merged["joins"][0]["rule"]["drawing_index"])):
            counts[key] += 1
    result = list(rows)
    for a, b, merged in proposals:
        if any(counts[key] != 1 for key in (("line", str(a["lines"][0]["id"])),
               ("line", str(b["lines"][0]["id"])), ("rule", merged["joins"][0]["rule"]["drawing_index"]))):
            continue
        result.remove(a)
        result.remove(b)
        result.append(merged)
    result.sort(key=lambda row: (round(row["bbox"][1], 1), row["bbox"][0], str(row["lines"][0]["id"])))
    return [{**row, "id": index} for index, row in enumerate(result)]


def style(line: Mapping) -> dict:
    """Dominant visible text style, weighted by characters, not equation glyphs."""
    weights = defaultdict(int)
    for span in line.get("spans", []):
        text = span.get("text", line["text"][span["start"]:span["end"]])
        weight = len(canonical(text))
        if weight:
            bold = bool(span.get("flags", 0) & 16 or "bold" in str(span.get("font", "")).lower())
            weights[(span.get("color", 0), bold, round(float(span.get("size") or 0), 1))] += weight
    if not weights:
        return {}
    (color, bold, size), weight = max(weights.items(), key=lambda kv: kv[1])
    return {"color": color, "bold": bold, "size": size, "fraction": weight/sum(weights.values())}


def _paragraph_font(line: dict) -> tuple | None:
    weights = defaultdict(int)
    for run in line.get("spans", []):
        if (not isinstance(run.get("font"), str) or not run["font"]
                or type(run.get("size")) not in (int, float) or not math.isfinite(run["size"])
                or run["size"] <= 0 or type(run.get("flags")) is not int or type(run.get("color")) is not int):
            return None
        weights[(run["font"], float(run["size"]), run["flags"] & 18, run["color"])] += len(canonical(run.get("text", "")))
    if not weights or not sum(weights.values()):
        return None
    signature, weight = max(weights.items(), key=lambda item: item[1])
    return signature if weight/sum(weights.values()) >= .8 else None


def _terminal_wraps(source_rows: list[dict]) -> list[tuple[dict, dict]]:
    """Corroborate only a native block's short final sentence row.

    Two immediate full-width predecessors must agree on paragraph typography,
    native ownership, left edge and line spacing. Full-page context prevents a
    model crop from hiding a later owner line or a competing adjacent lane.
    """
    by_block = defaultdict(list)
    by_line = {}
    for row in source_rows:
        for line in row["lines"]:
            by_line[str(line["id"])] = row
            if type(line.get("block_id")) is int and type(line.get("line_in_block")) is int:
                by_block[line["block_id"]].append(line)
    candidates = []
    for owner, lines in by_block.items():
        indices = {line["line_in_block"]: line for line in lines}
        if len(indices) != len(lines) or len(indices) < 3:
            continue
        final_index = max(indices)
        if final_index-1 not in indices or final_index-2 not in indices:
            continue
        before, prior, final = (indices[i] for i in (final_index-2, final_index-1, final_index))
        rows = [by_line[str(line["id"])] for line in (before, prior, final)]
        if (any(len(row["lines"]) != 1 for row in rows) or not all(_horizontal(line) for line in (before, prior, final))
                or len(canonical(final["text"])) < 4 or not re.search(r"[.!?][\s\)\]\}’\"']*$", final["text"])):
            continue
        fonts = [_paragraph_font(line) for line in (before, prior, final)]
        if not fonts[0] or any(font != fonts[0] for font in fonts[1:]):
            continue
        em = fonts[0][1]
        a, b, c = (line["bbox"] for line in (before, prior, final))
        widths = [box[2]-box[0] for box in (a, b, c)]
        centers = [(box[1]+box[3])/2 for box in (a, b, c)]
        steps = [centers[1]-centers[0], centers[2]-centers[1]]
        if (min(widths[:2]) < 10*em or not 2*em <= widths[2] < min(widths[:2])/1.65
                or abs(a[0]-b[0]) > .25*em or abs(b[0]-c[0]) > .25*em
                or abs(a[2]-b[2]) > .5*em or any(not .8*em <= step <= 1.8*em for step in steps)
                or abs(steps[0]-steps[1]) > .25*em):
            continue
        # An intervening row or simultaneous neighboring column contradicts a
        # terminal wrap, even if the native extractor reused one block ID.
        if any(row not in rows and overlap(b, row["bbox"]) >= .1
               and centers[1] < (row["bbox"][1]+row["bbox"][3])/2 <= c[3]
               for row in source_rows):
            continue
        proof = {"version": CHAIN_VERSION, "reason": "source_owned_short_final_wrap",
                 "block_id": owner, "final_native_line_id": final["id"],
                 "support_native_line_ids": [before["id"], prior["id"]],
                 "native_line_indices": [final_index-2, final_index-1, final_index],
                 "source_boxes": [list(box) for box in (a, b, c)],
                 "dominant_font": {"font": fonts[0][0], "size": em, "flags": fonts[0][2], "color": fonts[0][3]},
                 "scope": "raw_reading_order_only"}
        candidates.append((rows[-1], proof))
    return candidates


def _chains(lines: list[dict], rows: list[dict] | None = None, *, source_rows=None,
            evidence: dict | None = None) -> list[list[dict]]:
    """Column-local order plus original order; never a global y-sort only.

    Requiring high horizontal overlap prevents the wrong-column projection.
    Full-width lines are not used to connect two narrow columns transitively.
    """
    rows = logical_rows(lines) if rows is None else rows
    wraps = _terminal_wraps(rows if source_rows is None else source_rows)
    eligible = {str(line["id"]) for line in lines}
    result = []
    for anchor in rows:
        a = anchor["bbox"]
        local = [x for x in rows if overlap(a, x["bbox"]) >= .8 and
                 max(a[2]-a[0], x["bbox"][2]-x["bbox"][0]) <= 1.65*max(1, min(a[2]-a[0], x["bbox"][2]-x["bbox"][0]))]
        local.sort(key=lambda x: (round(x["bbox"][1], 1), x["bbox"][0], str(x["id"])))
        local_ids = {str(line["id"]) for row in local for line in row["lines"]}
        added = [(row, proof) for row, proof in wraps if str(proof["final_native_line_id"]) in eligible-local_ids
                 and all(str(sid) in local_ids for sid in proof["support_native_line_ids"])]
        if added:
            extended = sorted(local+[row for row, _ in added], key=lambda x: (round(x["bbox"][1], 1), x["bbox"][0], str(x["id"])))
            chain = [line for row in extended for line in row["lines"]]
            result.append(chain)
            if evidence is not None:
                evidence[tuple(str(line["id"]) for line in chain)] = [proof for _, proof in added]
        result.append([line for row in local for line in row["lines"]])
    # Native original order can encode legitimate multi-column continuation.
    # Such a match is returned but held by the caller unless layout corroborates it.
    result.append(lines)
    unique, seen = [], set()
    for chain in result:
        key = tuple(str(x["id"]) for x in chain)
        if key and key not in seen:
            seen.add(key)
            unique.append(chain)
    return unique


def _mapped(chain: list[dict]) -> tuple[str, list[tuple[int, int]]]:
    chars, mapping = [], []
    for li, line in enumerate(chain):
        for ci, char in enumerate(line["text"]):
            for c in unicodedata.normalize("NFKD", char).casefold():
                if c.isalnum():
                    chars.append(c)
                    mapping.append((li, ci))
    return "".join(chars), mapping


def _slices(chain: list[dict], mapping: list[tuple[int, int]], start: int, end: int) -> list[dict]:
    first_line, first_char = mapping[start]
    last_line, last_char = mapping[end-1]
    output = []
    for i in range(first_line, last_line+1):
        line = chain[i]
        a = first_char if i == first_line else 0
        b = last_char+1 if i == last_line else len(line["text"])
        # Include source punctuation immediately adjacent to the selected range,
        # but not following alphanumeric metadata or a new sentence.
        if i == last_line:
            while b < len(line["text"]) and line["text"][b] in ".!?;,:)]}’\"'†‡*":
                b += 1
        output.append({"line_id": line["id"], "start": a, "end": b,
                       "text": line["text"][a:b], "bbox": list(line["bbox"]),
                       "box_scope": "native_line_not_character_box", "page_no": 1})
    return output


def _bind_leading_prefix(text: str, match: dict, native_lines: list[dict]) -> dict:
    """Bind a requested prefix after canonical occurrence ambiguity is resolved.

    This changes raw offsets only. It does not infer glyph mappings, attach a
    separate native line, or certify internal/trailing scientific notation.
    """
    requested = text.lstrip()
    anchor = next(i for i, char in enumerate(requested) if canonical(char))
    prefix = requested[:anchor]
    if not prefix:
        return match
    evidence = {"version": SLICE_VERSION, "scope": "requested_leading_prefix_only",
                "requested_prefix_sha256": hashlib.sha256(prefix.encode("utf-8")).hexdigest(),
                "requested_prefix_characters": len(prefix)}

    def held(reason: str) -> dict:
        return {"status": "unlocated", "reason": "requested_leading_prefix_not_source_bound", "spans": [],
                "slice_evidence": {**evidence, "status": "unresolved", "reason": reason},
                "candidate_native_extent": {"status": "canonical_extent_only", "accepted": False,
                    "spans": match["spans"], "column_change": match["column_change"],
                    "precision": match["precision"], "recall": match["recall"]}}

    # Only visible punctuation/symbols and horizontal spaces belong to this
    # repair. Controls, line breaks and combining glyph mappings need separate
    # representation evidence, even if identical raw bytes appear nearby.
    if any(unicodedata.category(char)[0] not in "PS" and unicodedata.category(char) != "Zs"
           for char in prefix):
        return held("unsupported_prefix_character")
    first = match["spans"][0]
    line = next(line for line in native_lines if str(line["id"]) == str(first["line_id"]))
    start, end = first["start"], first["end"]
    if canonical(requested[anchor]) != canonical(line["text"][start]):
        return held("requested_anchor_not_selected_native_anchor")
    extended_start = start - len(prefix)
    if extended_start < 0 or line["text"][extended_start:start] != prefix:
        return held("prefix_not_contiguous_on_selected_native_line")
    spans = [{**first, "start": extended_start, "text": line["text"][extended_start:end]},
             *match["spans"][1:]]
    return {**match, "spans": spans, "text": "\n".join(span["text"] for span in spans),
            "slice_evidence": {**evidence, "status": "exact_raw_prefix",
                               "line_id": first["line_id"], "start": extended_start,
                               "canonical_start": start, "end": end}}


def locate(text: str, native_lines: list[dict], *, region_boxes: list[list[float]] | None = None,
           threshold: float = .98, source_geometry: SourceGeometry | None = None) -> dict:
    """Find a unique contiguous source transcription; never relax the 98% gate.

    Geometry restricts a genuine layout region. OCR callers omit region_boxes:
    their estimated boxes must not be used as independent corroboration.
    A SourceGeometry context is optional, PDF-derived geometry only. Its
    fraction seam never inserts a slash or approves notation/section scope.
    """
    if threshold < .98 or threshold > 1:
        raise ValueError("alignment_threshold_must_not_weaken_frozen_gate")
    if source_geometry is not None:
        # Bind verification and all subsequent traversal to one owned snapshot,
        # even if an application mutates its original native records meanwhile.
        native_lines = json.loads(json_bytes(native_lines))
    target = canonical(text)
    if not target:
        return {"status": "unlocated", "reason": "empty_candidate", "spans": []}
    eligible = native_lines
    if region_boxes is not None:
        eligible = [line for line in native_lines if any(
            box[1]-2 <= (line["bbox"][1]+line["bbox"][3])/2 <= box[3]+2 and
            overlap(box, line["bbox"]) >= .8 for box in region_boxes)]
    # Derive against the full native page: restricting to a model region first
    # would remove neighboring-row evidence and make geometry model-dependent.
    rows = logical_rows(native_lines)
    if source_geometry is not None:
        rows = _fraction_rows(native_lines, rows, source_geometry)
    eligible_ids = {str(line["id"]) for line in eligible}
    eligible_rows = [{**row, "lines": [line for line in row["lines"] if str(line["id"]) in eligible_ids]}
                     for row in rows if any(str(line["id"]) in eligible_ids for line in row["lines"])]
    matches, chain_proofs = {}, {}
    for chain in _chains(eligible, eligible_rows, source_rows=rows, evidence=chain_proofs):
        haystack, mapping = _mapped(chain)
        if not haystack:
            continue
        intervals = []
        pos = haystack.find(target)
        while pos >= 0:
            intervals.append((pos, pos+len(target)))
            pos = haystack.find(target, pos+1)
        # Exact occurrences partition the source. Search other disjoint regions
        # as well: otherwise a near-duplicate elsewhere could be hidden. Avoid
        # expensive fuzzy windows over already-exact long/repetitive paragraphs.
        ranges = []
        cursor = 0
        for a, b in intervals:
            if a-cursor >= len(target)*threshold:
                ranges.append((cursor, a))
            cursor = max(cursor, b)
        if len(haystack)-cursor >= len(target)*threshold:
            ranges.append((cursor, len(haystack)))
        seed_size = min(24, max(4, len(target)//4))
        stride = max(seed_size, len(target)//8)
        slack = max(3, math.ceil(len(target)*.025))
        windows = set(ranges)
        for left, right in ranges:
            for offset in sorted(set(range(0, len(target)-seed_size+1, stride)) | {len(target)-seed_size}):
                seed = target[offset:offset+seed_size]
                pos = haystack.find(seed, left, right)
                while pos >= 0:
                    estimate = pos-offset
                    windows.add((max(left, estimate-slack), min(right, estimate+len(target)+slack)))
                    if len(windows) > 256:
                        return {"status": "unlocated", "reason": "alignment_search_budget_exceeded", "spans": []}
                    pos = haystack.find(seed, pos+1, right)
        for left, right in windows:
            blocks = [m for m in difflib.SequenceMatcher(None, target, haystack[left:right], autojunk=False).get_matching_blocks() if m.size]
            if blocks:
                intervals.append((left+blocks[0].b, left+blocks[-1].b+blocks[-1].size))
        for a, b in intervals:
            source = haystack[a:b]
            score = compare(target, source)
            if min(score["precision"], score["recall"]) < threshold:
                continue
            spans = _slices(chain, mapping, a, b)
            key = tuple((str(s["line_id"]), s["start"], s["end"]) for s in spans)
            source_text = "\n".join(s["text"] for s in spans)
            geometry = transition_evidence(spans, rows)
            column_change = bool(geometry["unsupported_transitions"])
            matches[key] = {"status": "located", "spans": spans, "text": source_text,
                            "precision": score["precision"], "recall": score["recall"],
                            "column_change": column_change, "coordinate_source": "native_pdf_lines",
                            "logical_geometry": geometry}
            selected_ids = {str(span["line_id"]) for span in spans}
            proof = [value for value in chain_proofs.get(tuple(str(line["id"]) for line in chain), [])
                     if str(value["final_native_line_id"]) in selected_ids]
            if proof:
                matches[key]["chain_evidence"] = proof
    if not matches:
        return {"status": "unlocated", "reason": "no_98_percent_source_alignment", "spans": []}
    occurrences = []
    for value in sorted(matches.values(), key=lambda v: (-min(v["precision"], v["recall"]), -len(canonical(v["text"])))):
        positions = {(str(span["line_id"]), i) for span in value["spans"] for i in range(span["start"], span["end"])}
        if not any(len(positions & prior)/max(1, min(len(positions), len(prior))) >= .9 for _, prior in occurrences):
            occurrences.append((value, positions))
    if len(occurrences) != 1:
        return {"status": "ambiguous", "reason": "multiple_source_occurrences", "spans": [], "matches": len(occurrences)}
    # Prefix punctuation must never silently select one canonical occurrence
    # over another. It is bound only after the existing ambiguity gate passes.
    return _bind_leading_prefix(text, occurrences[0][0], native_lines)


def validate_source_spans(spans: list[dict], native_lines: list[dict]) -> None:
    by_id = {str(x["id"]): x for x in native_lines}
    seen = set()
    for s in spans:
        key = (str(s["line_id"]), s["start"], s["end"])
        if key in seen:
            raise ValueError("duplicate_selected_span")
        seen.add(key)
        line = by_id[str(s["line_id"])]
        if s.get("page_no") != 1 or not 0 <= s["start"] < s["end"] <= len(line["text"]):
            raise ValueError("invalid_selected_span")
        if line["text"][s["start"]:s["end"]] != s["text"] or list(line["bbox"]) != s["bbox"]:
            raise ValueError("selected_span_does_not_match_source")
