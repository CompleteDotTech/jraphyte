"""Derived logical rows; native lines, offsets and rectangles are never rewritten.

The native DICT line is a text extraction unit, not necessarily a visual row.
This conservative view requires nearby owned-row support plus two-sided
continuation, block-start ownership, or a corroborated flanking script. It is
geometry evidence, not a semantic section boundary or a recovered text direction.
"""
from __future__ import annotations

VERSION = "native-logical-rows-v1"


def _size(line: dict) -> float:
    spans = line.get("spans", [])
    values = [(float(s.get("size") or 0), max(1, s.get("end", 0)-s.get("start", 0))) for s in spans]
    values = [(size, weight) for size, weight in values if size > 0]
    return max(values, key=lambda pair: pair[1])[0] if values else max(1., (line["bbox"][3]-line["bbox"][1])/1.2)


def _horizontal(line: dict) -> bool:
    direction = line.get("dir", (1, 0))
    return (len(direction) == 2 and direction[0] > .95 and abs(direction[1]) < .1
            and line["bbox"][3]-line["bbox"][1] <= 1.8*_size(line))


def _same_row(a: dict, b: dict) -> bool:
    if not _horizontal(a) or not _horizontal(b):
        return False
    x, y = a["bbox"], b["bbox"]
    em = max(_size(a), _size(b))
    vertical = min(x[3], y[3])-max(x[1], y[1])
    if vertical <= 0:
        return False
    ordinary = vertical/min(x[3]-x[1], y[3]-y[1]) >= .7 and abs((x[1]+x[3]-y[1]-y[3])/2) <= .45*em
    compact = min((a, b), key=lambda line: line["bbox"][2]-line["bbox"][0])
    script = (compact["bbox"][2]-compact["bbox"][0] <= 2*em and vertical >= .15*em
              and abs((x[1]+x[3]-y[1]-y[3])/2) >= .2*em)
    return ordinary or script


def _mid(line: dict) -> float:
    return (line["bbox"][1]+line["bbox"][3])/2


def _similar_extent(a: dict, b: dict) -> bool:
    x, y = a["bbox"], b["bbox"]
    widths = (x[2]-x[0], y[2]-y[0])
    return (max(0., min(x[2], y[2])-max(x[0], y[0])) >= .8*min(widths)
            and max(widths) <= 1.65*max(1., min(widths)))


def _source_evidence(lines: list[dict]) -> list[dict]:
    return [{"line_id": line["id"], "block_id": line.get("block_id"), "bbox": list(line["bbox"])}
            for line in lines]


def _script_flank(compact: dict, baseline: dict, lines: list[dict], em: float) -> dict | None:
    """Require another baseline fragment on the opposite side of a raised run.

    A small raised word is not inherently a script. Flanking text, comparable
    baseline typography and a shared owning block provide separate evidence.
    """
    c, base = compact["bbox"], baseline["bbox"]
    for other in lines:
        if other is compact or other is baseline or not _horizontal(other):
            continue
        box = other["bbox"]
        if (abs(_mid(baseline)-_mid(other)) > .3*em
                or min(_size(baseline), _size(other)) < .85*max(_size(baseline), _size(other))):
            continue
        left_flank = c[2] <= base[0]+.3*em and -.9*em <= c[0]-box[2] <= .3*em
        right_flank = c[0] >= base[2]-.3*em and -.9*em <= box[0]-c[2] <= .3*em
        if (left_flank or right_flank) and compact.get("block_id") is not None and compact.get("block_id") in {baseline.get("block_id"), other.get("block_id")}:
            return other
    return None


def _join_reason(a: dict, b: dict, lines: list[dict], *, context: list[dict] | tuple[dict, ...] = ()) -> dict | None:
    if not _same_row(a, b):
        return None
    left, right = sorted((a, b), key=lambda line: line["bbox"][0])
    x, y = left["bbox"], right["bbox"]
    em = max(_size(a), _size(b))
    gap = y[0]-x[2]
    # Large overlaps are separate overprints/occurrences, not inline fragments.
    if gap < -.9*em or gap > 1.25*em:
        return None
    center = (max(x[1], y[1])+min(x[3], y[3]))/2
    nearby = [line for line in lines if line is not a and line is not b and _horizontal(line)
              and .7*em < abs(_mid(line)-center) <= 3.2*em]
    # A nearby row spanning this small gap supports one continuous prose region.
    # Full-width titles far above two columns cannot supply this evidence.
    pair_owners = {a.get("block_id"), b.get("block_id")} - {None}
    # Already corroborated fragments of this same anchored visual row can
    # explain an overlapping font run at a native-block split. This evidence
    # cannot authorize a positive whitespace gap across two native blocks.
    owners = pair_owners | ({line.get("block_id") for line in context}-{None} if gap <= 0 else set())
    owner_context = [line["id"] for line in context] if owners != pair_owners else []
    bridges = [line for line in nearby if line.get("block_id") in owners
               and line["bbox"][0] <= x[2]-em and line["bbox"][2] >= y[0]+em]
    # Opposite sides of a repeated vertical gap are columns even when a broken
    # PDF puts them in the same block. One paired row is already counterevidence.
    left_rows = [line for line in nearby if line["bbox"][2] <= y[0] and line["bbox"][0] < x[2]-em]
    right_rows = [line for line in nearby if line["bbox"][0] >= x[2] and line["bbox"][2] > y[0]+em]
    paired = [line for line in left_rows if any(_same_row(line, other) for other in right_rows)]
    if gap >= 0 and paired:
        return None
    compact = min((a, b), key=lambda line: line["bbox"][2]-line["bbox"][0])
    baseline = b if compact is a else a
    displacement = abs((x[1]+x[3]-y[1]-y[3])/2)
    if (bridges and compact["bbox"][2]-compact["bbox"][0] <= 2*em
            and displacement >= .2*em and gap <= .3*em):
        flank = _script_flank(compact, baseline, lines, em)
        if flank:
            return {"reason": "attached_script", "ownership_cue": "flanking_baseline_fragments",
                    "support": _source_evidence(bridges), "flank": _source_evidence([flank])[0],
                    "corroborated_row_context": owner_context}
    if gap > 0 and (len(pair_owners) != 1 or a.get("block_id") is None or b.get("block_id") is None):
        return None
    # Neighboring paragraph-width rows can corroborate a short wrap as well as a
    # full-width row. An above-only header/abstract cannot establish continuation
    # into new columns, even when native extraction merges their block IDs.
    supporting = [line for line in nearby if line.get("block_id") in owners
                  and any(_similar_extent(line, bridge) for bridge in bridges)]
    above = [line for line in supporting if _mid(line) < center]
    below = [line for line in supporting if _mid(line) > center]
    if above and below:
        return {"reason": "nearby_continuous_row", "ownership_cue": "owned_rows_above_and_below",
                "support": _source_evidence(supporting), "corroborated_row_context": owner_context}
    # The first visual row of one native block may have no preceding prose row.
    # Require its real line_in_block=0 anchor and two following row levels.
    first = next((line for line in lines if len(owners) == 1 and line.get("block_id") in owners
                  and line.get("line_in_block") == 0 and _same_row(line, a) and _same_row(line, b)), None)
    levels = []
    for line in sorted(below, key=_mid):
        if not levels or _mid(line)-levels[-1] > .5*em:
            levels.append(_mid(line))
    if first and len(levels) >= 2:
        return {"reason": "nearby_continuous_row", "ownership_cue": "native_block_start_with_two_following_rows",
                "block_start": _source_evidence([first])[0], "support": _source_evidence(below)}
    return None


def logical_rows(lines: list[dict]) -> list[dict]:
    """Build a reversible geometry view without changing any source object.

    A wide anchor prevents a small script from joining consecutive text rows by
    transitivity. Physical x order is used only inside a corroborated visual row.
    """
    pending = sorted(lines, key=lambda line: (-(line["bbox"][2]-line["bbox"][0]), str(line["id"])))
    groups = []
    while pending:
        anchor = pending.pop(0)
        members, joins = [anchor], []
        changed = True
        while changed:
            changed = False
            for candidate in pending[:]:
                if not _same_row(anchor, candidate):
                    continue
                connected = next(((member, reason) for member in members
                                  if (reason := _join_reason(member, candidate, lines, context=members))), None)
                if connected:
                    member, reason = connected
                    members.append(candidate)
                    pending.remove(candidate)
                    joins.append({"native_line_ids": [member["id"], candidate["id"]], **reason})
                    changed = True
        members.sort(key=lambda line: (line["bbox"][0], str(line["id"])))
        boxes = [line["bbox"] for line in members]
        groups.append({"bbox": [min(b[0] for b in boxes), min(b[1] for b in boxes),
                                max(b[2] for b in boxes), max(b[3] for b in boxes)],
                       "lines": members, "joins": joins})
    groups.sort(key=lambda row: (round(row["bbox"][1], 1), row["bbox"][0], str(row["lines"][0]["id"])))
    for index, row in enumerate(groups):
        row["id"] = index
    return groups


def transition_evidence(spans: list[dict], rows: list[dict]) -> dict:
    """Explain unsupported jumps using whole logical rows, never glyph boxes."""
    by_line = {str(line["id"]): row for row in rows for line in row["lines"]}
    selected = []
    for span in spans:
        row = by_line[str(span["line_id"])]
        if not selected or selected[-1]["id"] != row["id"]:
            selected.append(row)
    jumps = []
    for a, b in zip(selected, selected[1:]):
        x, y = a["bbox"], b["bbox"]
        shared = max(0., min(x[2], y[2])-max(x[0], y[0])) / max(1., min(x[2]-x[0], y[2]-y[0]))
        if shared < .5:
            jumps.append({"from_row": a["id"], "to_row": b["id"], "reason": "unsupported_horizontal_transition"})
    return {"version": VERSION, "rows": [{"id": row["id"], "bbox": row["bbox"],
             "native_line_ids": [line["id"] for line in row["lines"]], "joins": row["joins"]}
            for row in selected], "unsupported_transitions": jumps}
