"""Query-independent fields and candidate generation, separate from reranking.

No target IDs are accepted by the candidate generator. Source-reviewed image
transcriptions are retrieval metadata only and never become abstract evidence.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Callable

from trace_gc.pdf_source_v3 import (ABSTRACT, METADATA, NON_ABSTRACT, _author_list,
                                  _style, canonical, digest, normalize, validate_lines)

PAGE_LABEL = re.compile(r"^(?:graphical\s+abstract|highlights?|key\s+points?|contents|table\s+of\s+contents|cover|author\s+(?:list|details|information)|executive\s+summary|abstract)\s*[:.—-]?\s*$", re.I)
NO_TITLE = re.compile(r"(?:arXiv:|@|https?://|^\s*(?:preprint|prepared\s+for|draft\s+version|running\s+title|keywords?|doi\s*:|received\s+|accepted\s+))", re.I)


def title_fields(lines: list[dict[str, Any]], page_size: tuple[float, float], *,
                 source_sha256: str, page_sha256: str,
                 image_review: dict[str, Any] | None = None,
                 image_sha256: str | None = None) -> dict[str, Any]:
    """Avoid page-type labels; retain all body text and title source intervals.

    A cover with no native text stays unindexable until an image transcription
    bound to the exact source/page/image has actually been reviewed. A filename
    or known evaluation target is never used as a title.
    """
    lines = validate_lines(lines, page_size)
    result = {"title": "", "abstract": "", "body": normalize(" ".join(l["text"] for l in lines)),
              "title_spans": [], "field_source": "native_first_page", "source_sha256": source_sha256,
              "page_sha256": page_sha256, "source_review_required": True, "graph_evidence": False}
    candidates = []
    for line in lines:
        text = normalize(line["text"])
        if len(text) < 12 or PAGE_LABEL.fullmatch(text) or NO_TITLE.search(text) or METADATA.match(text) or _author_list(text):
            continue
        if ABSTRACT.match(text) or NON_ABSTRACT.match(text):
            continue
        if line["bbox"][1] > .80*page_size[1]:
            continue
        style = _style(line)
        size = style.get("size")
        if size is not None and math.isfinite(size):
            candidates.append((float(size), -line["bbox"][1], line))
    if candidates:
        _, _, first = max(candidates, key=lambda x: (x[0], x[1]))
        max_size = _style(first)["size"]
        # Same native block or adjacent same-font lines, not all large text on page.
        selected = [first]
        rest = sorted([c[2] for c in candidates if c[2]["id"] != first["id"] and c[0] >= .92*max_size], key=lambda l: l["bbox"][1])
        for line in rest:
            last = selected[-1]
            same_block = first.get("block_id") is not None and line.get("block_id") == first["block_id"]
            close = 0 <= line["bbox"][1]-last["bbox"][3] <= 12 and abs(line["bbox"][0]-last["bbox"][0]) <= 32
            if line["bbox"][1] >= first["bbox"][1] and (same_block or close):
                selected.append(line)
        result["title"] = normalize(" ".join(l["text"] for l in selected))
        result["title_spans"] = [{"line_id": l["id"], "start": 0, "end": len(l["text"]), "bbox": l["bbox"]} for l in selected]
    if not result["body"] and image_review is not None:
        value = dict(image_review)
        supplied = value.pop("review_sha256", None)
        bindings = {"source_sha256": source_sha256, "page_sha256": page_sha256, "image_sha256": image_sha256}
        valid = (supplied == digest(value) and image_sha256 is not None and
                 all(value.get(k) == v for k, v in bindings.items()) and value.get("physical_page") == 1 and
                 value.get("reviewer_kind") in {"assistant", "human"} and bool(value.get("reviewer")) and
                 bool(value.get("reviewed_at")) and value.get("source_image_reviewed") is True)
        if not valid:
            raise ValueError("unbound_image_transcription")
        title, body = value.get("title", ""), value.get("text", "")
        if not isinstance(title, str) or not isinstance(body, str) or PAGE_LABEL.fullmatch(title):
            raise ValueError("invalid_image_title")
        result.update(title=title, body=body, field_source="reviewed_first_page_image_transcription",
                      image_review_sha256=supplied, independent_human_validation=False)
    result["candidate_path"] = "native_fields_and_full_page_lexical" if result["body"] else "image_transcription_review_queue"
    result["indexable"] = bool(result["title"] or result["body"])
    result["fields_sha256"] = digest(result)
    return result


def tokens(text: str) -> list[str]:
    return re.findall(r"\w+", text.casefold())


def bm25(query: str, texts: dict[str, str], *, k1: float = 1.2, b: float = .75) -> dict[str, float]:
    """Small dependency-free BM25 reference channel, with no target-dependent ties."""
    bags = {ident: Counter(tokens(text)) for ident, text in texts.items()}
    n = len(bags)
    average = sum(sum(v.values()) for v in bags.values()) / n if n else 1
    average = average or 1
    terms = set(tokens(query))
    df = {t: sum(t in bag for bag in bags.values()) for t in terms}
    scores = {}
    for ident, bag in bags.items():
        length = sum(bag.values())
        scores[ident] = sum(math.log(1+(n-df[t]+.5)/(df[t]+.5)) * bag[t]*(k1+1) /
                            (bag[t]+k1*(1-b+b*length/average)) for t in terms if bag[t])
    return scores


def candidate_pool(rankings: dict[str, list[dict[str, Any]]], *, per_channel: int = 50) -> dict[str, Any]:
    """Union BM25F/SPECTER2/full-page BM25; IDs, ties and order are deterministic."""
    if not isinstance(per_channel, int) or isinstance(per_channel, bool) or per_channel < 1:
        raise ValueError("invalid_candidate_limit")
    allowed = {"bm25f", "specter2", "bm25_page"}
    if set(rankings) - allowed:
        raise ValueError("unknown_or_nonlocal_candidate_channel")
    sources: dict[str, dict[str, int]] = {}
    for name in sorted(rankings):
        rows = rankings[name]
        if len({r["id"] for r in rows}) != len(rows):
            raise ValueError("duplicate_channel_document")
        if any(not isinstance(r["id"], str) or not isinstance(r["score"], (int, float)) or not math.isfinite(r["score"]) for r in rows):
            raise ValueError("invalid_channel_ranking")
        ordered = sorted(rows, key=lambda r: (-r["score"], r["id"]))[:per_channel]
        for rank, row in enumerate(ordered, 1):
            # Empty/zero lexical fields have no query evidence. Do not smuggle
            # image-only targets into a zero-score arbitrary top-k tie.
            if name.startswith("bm25") and row["score"] <= 0:
                continue
            sources.setdefault(row["id"], {})[name] = rank
    ids = sorted(sources, key=lambda ident: (-sum(1/(60+r) for r in sources[ident].values()), ident))
    result = {"document_ids": ids, "channels": sources, "per_channel": per_channel,
              "target_insertion": False, "policy": "local_union_bm25f_specter2_bm25_page_v3"}
    result["candidate_receipt_sha256"] = digest(result)
    return result


def rerank(pool: dict[str, Any], documents: dict[str, str], query: str,
           scorer: Callable[[str, list[str]], list[float]]) -> dict[str, Any]:
    """Invoke an explicitly supplied local scorer only on the frozen candidates."""
    ids = pool["document_ids"]
    scores = scorer(query, [documents[ident] for ident in ids]) if ids else []
    if len(scores) != len(ids) or not all(math.isfinite(s) for s in scores):
        raise ValueError("invalid_reranker_scores")
    order = sorted(zip(ids, scores), key=lambda r: (-r[1], r[0]))
    return {"ranking": [ident for ident, score in order],
            "scores": dict(order), "candidate_receipt_sha256": pool["candidate_receipt_sha256"]}


def ranking_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Targets are used only here, after both candidate generation and reranking."""
    ranks = []
    covered = 0
    for row in rows:
        pool, order = row["candidate_ids"], row["ranking"]
        if len(set(pool)) != len(pool) or len(set(order)) != len(order) or set(order) != set(pool):
            raise ValueError("reranking_must_be_a_permutation_of_candidates")
        target = row["target_id"]
        covered += target in pool
        ranks.append(order.index(target)+1 if target in order else None)
    n = len(rows)
    return {"queries": n, "candidate_coverage_count": covered,
            "candidate_coverage": covered/n if n else None,
            "top_1": sum(r == 1 for r in ranks), "top_10": sum(r is not None and r <= 10 for r in ranks),
            "recall_at_1": sum(r == 1 for r in ranks)/n if n else None,
            "recall_at_10": sum(r is not None and r <= 10 for r in ranks)/n if n else None,
            "mrr": sum(1/r for r in ranks if r)/n if n else None,
            "ranks": ranks, "competing_results_judged": False}
