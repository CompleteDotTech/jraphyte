"""Local field preparation and query-blind candidate/rerank receipt evaluation."""
from __future__ import annotations

import argparse
import json
import hashlib
import time
from pathlib import Path
from typing import Any

from trace_gc.pdf_source_v3 import digest
from .adapters import read_native_page
from .common import data_root, external_output, file_digest, read, resolve_source, write_once, safe_id
from .retrieval import title_fields, candidate_pool, bm25, ranking_metrics, rerank


def prepare_fields(rows: list[dict], source_map: dict[str, str], root: Path,
                   out: Path, image_reviews: dict[str, dict] | None = None) -> dict:
    fields, holds = {}, []
    for row in rows:
        sid = safe_id(row["sample_id"])
        if sid in fields:
            raise ValueError("duplicate_document_identity")
        source_hash = row["source_sha256"]
        path = resolve_source(root, source_map[source_hash])
        page = read_native_page(path)
        if page["source_sha256"] != source_hash:
            raise ValueError("retrieval_source_hash_mismatch")
        review = (image_reviews or {}).get(source_hash)
        if review:
            # A fresh image receipt must bind to the exact page serialization
            # and image bytes; no arbitrary caller-supplied title replacements.
            image_path = resolve_source(root, review["image_path"])
            image_hash = file_digest(image_path)
            import fitz
            source_bytes = path.read_bytes()
            if hashlib.sha256(source_bytes).hexdigest() != source_hash:
                raise ValueError("retrieval_source_changed_during_image_verification")
            with fitz.open(stream=source_bytes, filetype="pdf") as source_pdf:
                rendered = source_pdf[0].get_pixmap(dpi=review.get("render_dpi", 120)).tobytes("png")
            if hashlib.sha256(rendered).hexdigest() != image_hash:
                raise ValueError("retrieval_image_is_not_source_physical_page_one")
            review = review["review"]
        else:
            image_hash = None
        value = title_fields(page["native_lines"], tuple(page["page_size"]), source_sha256=source_hash,
                             page_sha256=page["page_sha256"], image_review=review, image_sha256=image_hash)
        fields[sid] = {"id": sid, **value}
        if not value["indexable"]:
            holds.append({"id": sid, "hold": "image_transcription_review_queue"})
    result = {"fields": fields, "fields_sha256": digest(fields), "documents": len(fields),
              "error_ledger": holds, "field_generation_query_independent": True,
              "api_calls": 0, "graph_writes": 0}
    write_once(out / "fields.json", result)
    return result


def evaluate(fields_receipt: dict, queries: list[dict], out: Path, *,
             semantic_receipt: dict | None = None, rerank_receipts: dict | None = None, local_scorer: Any = None) -> dict:
    started = time.perf_counter()
    fields = fields_receipt["fields"]
    fields_hash = digest(fields)
    if fields_hash != fields_receipt["fields_sha256"]:
        raise ValueError("retrieval_fields_changed")
    if len({q["query_id"] for q in queries}) != len(queries):
        raise ValueError("duplicate_query_identity")
    if any(q["target_id"] not in fields for q in queries):
        raise ValueError("query_target_not_in_frozen_document_catalog")
    queries_hash = digest(queries)
    if semantic_receipt is not None:
        if (semantic_receipt.get("fields_sha256") != fields_hash or
                semantic_receipt.get("queries_sha256") != queries_hash or
                semantic_receipt.get("channel") != "specter2" or not semantic_receipt.get("model_revision")):
            raise ValueError("stale_or_unbound_semantic_rankings")
    details, reranked, holds = [], [], []
    for q in queries:
        safe_id(q["query_id"])
        # Title/abstract weighting plus a separate full-page BM25 channel. This
        # lexical reference is labelled separately from historical BM25F tuning.
        full = {sid: f["body"] for sid, f in fields.items()}
        weighted = {sid: (f["title"]+" ")*3 + (f.get("abstract", "")+" ")*2 + f["body"] for sid, f in fields.items()}
        rankings = {name: [{"id": sid, "score": score} for sid, score in bm25(q["text"], texts).items()]
                    for name, texts in (("bm25f", weighted), ("bm25_page", full))}
        if semantic_receipt:
            rows = semantic_receipt["rankings"][q["query_id"]]
            if any(r["id"] not in fields for r in rows):
                raise ValueError("semantic_document_not_in_catalog")
            rankings["specter2"] = [r for r in rows if fields[r["id"]].get("indexable", True)]
        pool = candidate_pool(rankings)
        write_once(out / "candidates" / (q["query_id"]+".json"), {"query_sha256": digest(q["text"]), "fields_sha256": fields_hash, **pool})
        details.append({"id": q["query_id"], "target_id": q["target_id"], "candidate_ids": pool["document_ids"], "ranking": pool["document_ids"]})
        receipt = (rerank_receipts or {}).get(q["query_id"])
        pairs = [[q["text"], fields[sid]["title"]+" "+fields[sid]["body"]] for sid in pool["document_ids"]]
        if receipt is None and local_scorer is not None:
            measured = local_scorer.score(q["text"], [pair[1] for pair in pairs])
            receipt = {**measured, "candidate_receipt_sha256": pool["candidate_receipt_sha256"], "pairs_sha256": digest(pairs)}
            write_once(out / "local_scores" / (q["query_id"]+".json"), receipt)
        if receipt is None:
            holds.append({"id": q["query_id"], "hold": "local_reranker_receipt_unavailable"})
            continue
        if (receipt.get("candidate_receipt_sha256") != pool["candidate_receipt_sha256"] or
                receipt.get("pairs_sha256") != digest(pairs) or not receipt.get("model_revision")):
            raise ValueError("stale_or_unbound_reranker_receipt")
        result = rerank(pool, {sid: f["title"]+" "+f["body"] for sid, f in fields.items()}, q["text"],
                        lambda _query, _docs: receipt["scores"])
        write_once(out / "reranked" / (q["query_id"]+".json"), result)
        reranked.append({"id": q["query_id"], "target_id": q["target_id"], "candidate_ids": pool["document_ids"], "ranking": result["ranking"]})
    result = {"status": "COMPLETE" if not holds else "CANDIDATE_ONLY_RERANK_GATE_OUTSTANDING",
              "documents": len(fields), "queries": len(queries), "fields_sha256": fields_hash,
              "queries_sha256": queries_hash, "candidate_metrics": ranking_metrics(details),
              "reranker_metrics": ranking_metrics(reranked) if len(reranked) == len(queries) else None,
              "details": details, "reranker_details": reranked, "error_ledger": holds,
              "lexical_definition": "BM25 with repeated title/abstract weighting; distinct from frozen v2 BM25F",
              "semantic_channel": "source_bound_cached_SPECTER2" if semantic_receipt else "NOT_RUN",
              "competing_results_relevance": "not exhaustively judged; labelled target rank is not an irrelevance judgement",
              "runtime_seconds": time.perf_counter()-started, "api_calls": 0, "api_spend_usd": 0, "graph_writes": 0}
    write_once(out / "results.json", result)
    return result


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("stage", choices=("fields", "evaluate"))
    p.add_argument("--data-root", type=Path)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--manifest", type=Path)
    p.add_argument("--source-map", type=Path)
    p.add_argument("--image-reviews", type=Path)
    p.add_argument("--fields", type=Path)
    p.add_argument("--queries", type=Path)
    p.add_argument("--semantic-receipt", type=Path)
    p.add_argument("--rerank-receipts", type=Path)
    p.add_argument("--local-model-dir", type=Path, help="authorized external scalar cross-encoder snapshot; never downloaded")
    p.add_argument("--local-model-manifest", type=Path, help="external JSON with pinned model_revision and exact files hashes")
    a = p.parse_args(); out = external_output(a.out)
    if a.stage == "fields":
        if not a.manifest or not a.source_map:
            p.error("fields requires --manifest and --source-map")
        result = prepare_fields(read(a.manifest)["pdfs"], read(a.source_map), data_root(a.data_root), out,
                                read(a.image_reviews) if a.image_reviews else None)
        print(json.dumps({"documents": result["documents"], "unindexable": len(result["error_ledger"])}))
    else:
        if not a.fields or not a.queries:
            p.error("evaluate requires --fields and --queries")
        queries = read(a.queries)
        queries = queries["queries"] if isinstance(queries, dict) else queries
        scorer = None
        if a.local_model_dir:
            if not a.local_model_manifest or a.rerank_receipts:
                p.error("local model requires its byte manifest and cannot be combined with cached score receipts")
            from .local_reranker import LocalReranker
            scorer = LocalReranker(a.local_model_dir, read(a.local_model_manifest))
        result = evaluate(read(a.fields), queries, out,
                          semantic_receipt=read(a.semantic_receipt) if a.semantic_receipt else None,
                          rerank_receipts=read(a.rerank_receipts) if a.rerank_receipts else None, local_scorer=scorer)
        print(json.dumps({"status": result["status"], "candidate_metrics": result["candidate_metrics"], "reranker_metrics": result["reranker_metrics"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
