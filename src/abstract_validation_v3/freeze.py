"""Freeze a genuinely new source-reviewed cohort before opening predictions.

Review declarations are auditable attestations, not proof of independent human
review. The tool cannot establish what a reviewer has previously seen. It does
reject known work/source overlap and unbound or prediction-first references.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

from trace_gc.pdf_source_v3 import compare, digest, reconstruct
from .adapters import read_native_page, native_document
from .common import code_hashes, data_root, external_output, file_digest, read, resolve_source, write_once, safe_id


def freeze_cohort(rows: list[dict[str, Any]], reviews: dict[str, dict], *, root: Path, out: Path,
                  seen_source_hashes: set[str], seen_work_ids: set[str]) -> dict:
    if not rows or not seen_source_hashes or not seen_work_ids:
        raise ValueError("nonempty_cohort_and_seen_catalog_required")
    if len({r["id"] for r in rows}) != len(rows) or len({r["work_id"] for r in rows}) != len(rows):
        raise ValueError("duplicate_new_cohort_identity")
    if len({r["source_sha256"] for r in rows}) != len(rows):
        raise ValueError("duplicate_new_cohort_source")
    if set(reviews) != {r["id"] for r in rows}:
        raise ValueError("every_frozen_source_requires_review")
    hashes, labels, declared_reviewers = {}, {}, []
    for row in rows:
        safe_id(row["id"])
        if row["source_sha256"] in seen_source_hashes or row["work_id"] in seen_work_ids:
            raise ValueError("previously_exposed_work_or_source")
        r = reviews[row["id"]]
        if r.get("prediction_seen") is not False or r.get("image_reviewed") is not True or r.get("native_spans_reviewed") is not True:
            raise ValueError("source_first_review_required_before_predictions")
        if r.get("reviewer_kind") not in {"assistant", "human"} or not r.get("reviewer"):
            raise ValueError("reviewer_identity_required")
        reviewed = dt.datetime.fromisoformat(r["reviewed_at"])
        if reviewed.tzinfo is None or reviewed > dt.datetime.now(dt.timezone.utc):
            raise ValueError("invalid_review_timestamp")
        for name, field in (("source_path", "source_sha256"), ("page_path", "page_sha256"),
                            ("image_path", "image_sha256"), ("lines_path", "native_lines_sha256")):
            path = resolve_source(root, row[name])
            if file_digest(path) != row[field] or r.get(field) != row[field]:
                raise ValueError("reviewed_artifact_binding_mismatch")
        lines = read(resolve_source(root, row["lines_path"]))
        native = read_native_page(resolve_source(root, row["source_path"]))
        if native["page_sha256"] != row["page_sha256"]:
            raise ValueError("reviewed_page_is_not_source_physical_page_one")
        import fitz, hashlib
        with fitz.open(stream=resolve_source(root, row["source_path"]).read_bytes(), filetype="pdf") as source_pdf:
            image = source_pdf[0].get_pixmap(dpi=row.get("render_dpi", 120)).tobytes("png")
        if hashlib.sha256(image).hexdigest() != row["image_sha256"]:
            raise ValueError("reviewed_image_is_not_source_physical_page_one")
        if digest(native["native_lines"]) != digest(lines):
            raise ValueError("reviewed_native_spans_not_reproduced")
        reference = reconstruct(r.get("spans", []), lines)
        if reference != r["text"]:
            raise ValueError("reference_not_exact_source_intervals")
        status = r["status"]
        if status not in {"complete", "partial_on_page_one", "no_abstract_text", "uncertain"}:
            raise ValueError("invalid_reference_state")
        if status in {"complete", "partial_on_page_one"} and not reference:
            raise ValueError("reference_text_required")
        if status == "no_abstract_text" and reference:
            raise ValueError("absent_reference_must_be_empty")
        labels[row["id"]] = {"status": status, "text": reference, "spans": r.get("spans", []),
                              "review_sha256": digest(r), "math_review_required": bool(r.get("math_review_required"))}
        hashes[row["id"]] = {k: row[k] for k in ("source_sha256", "page_sha256", "image_sha256", "native_lines_sha256")}
        declared_reviewers.append({k: r[k] for k in ("reviewer", "reviewer_kind", "reviewed_at")})
    protocol = {"schema_version": 3, "cohort": "source_first_unseen", "frozen_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "method": "source_v3_native_only", "code_hashes": code_hashes(),
                "source_hashes": hashes, "labels_sha256": digest(labels), "manifest_sha256": digest(rows),
                "seen_catalog_sha256": digest({"sources": sorted(seen_source_hashes), "works": sorted(seen_work_ids)}),
                "seen_sources": len(seen_source_hashes), "seen_works": len(seen_work_ids),
                "reviews": declared_reviewers, "independent_human_validation": "not_certified",
                "review_declarations_are_attestations": True, "api_calls": 0, "graph_writes": 0}
    # Write private references first; an interrupted freeze cannot create a usable
    # protocol without all hash-bound source records and labels.
    write_once(out / "manifest.json", rows)
    write_once(out / "labels.json", labels)
    write_once(out / "reviews.json", reviews)
    write_once(out / "protocol.json", protocol)
    return protocol


def evaluate_frozen(frozen: Path, root: Path, out: Path) -> dict:
    from trace_gc.pdf_source_v3 import assess_document, seal
    from .evaluate import _detail, summary
    import time
    started = time.perf_counter()
    protocol, rows, labels = [read(frozen / name) for name in ("protocol.json", "manifest.json", "labels.json")]
    if protocol["code_hashes"] != code_hashes() or protocol["manifest_sha256"] != digest(rows) or protocol["labels_sha256"] != digest(labels):
        raise ValueError("frozen_method_or_reference_changed")
    details = []
    for row in rows:
        safe_id(row["id"])
        sid = row["id"]
        for name, field in (("source_path", "source_sha256"), ("page_path", "page_sha256"),
                            ("image_path", "image_sha256"), ("lines_path", "native_lines_sha256")):
            if file_digest(resolve_source(root, row[name])) != protocol["source_hashes"][sid][field]:
                raise ValueError("frozen_source_changed")
        source = read_native_page(resolve_source(root, row["source_path"]))
        lines = read(resolve_source(root, row["lines_path"]))
        if digest(source["native_lines"]) != digest(lines):
            raise ValueError("frozen_native_spans_changed")
        pred = assess_document(native_document(lines), page_size=source["page_size"], native_lines=lines,
                               source_sha256=row["source_sha256"], page_sha256=row["page_sha256"])
        pred["source_bytes_verified"] = True
        pred["math_review_required"] = labels[sid]["math_review_required"]
        pred = seal(pred)
        write_once(out / "assessments" / (sid + ".json"), pred)
        details.append(_detail(sid, pred, labels[sid]))
    result = {"status": "COMPLETE_UNSEEN_COHORT", "cohort": protocol["cohort"], "method": protocol["method"],
              "protocol_sha256": file_digest(frozen / "protocol.json"), "metrics": summary(details), "details": details,
              "source_hashes_verified": len(rows), "runtime_seconds": time.perf_counter()-started,
              "independent_human_validation": "not_certified", "api_calls": 0, "api_spend_usd": 0, "graph_writes": 0,
              "retrieval_metrics": None, "automatic_promotion": False}
    write_once(out / "results.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("freeze", "evaluate"))
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--reviews", type=Path)
    parser.add_argument("--seen-manifest", type=Path, help="original regression manifest with work_id and source_sha256")
    parser.add_argument("--seen-hashes", type=Path, help="public 200-page source_hashes.json")
    parser.add_argument("--frozen", type=Path)
    args = parser.parse_args()
    root, out = data_root(args.data_root), external_output(args.out)
    if args.stage == "freeze":
        if not all((args.manifest, args.reviews, args.seen_manifest, args.seen_hashes)):
            parser.error("freeze requires manifest, source-first reviews and the prior seen catalogs")
        seen = read(args.seen_manifest)["pdfs"]
        sources = {r["source_sha256"] for r in read(args.seen_hashes).values()}
        works = {r["work_id"] for r in seen}
        if len(sources) < 200 or len(works) < 200:
            parser.error("the complete known 200-paper catalog is required")
        result = freeze_cohort(read(args.manifest), read(args.reviews), root=root, out=out,
                               seen_source_hashes=sources, seen_work_ids=works)
        print(json.dumps({"status": "FROZEN", "pages": len(result["source_hashes"]), "independent_human_validation": "not_certified"}))
    else:
        if not args.frozen:
            parser.error("evaluate requires --frozen")
        result = evaluate_frozen(args.frozen, root, out)
        print(json.dumps({"status": result["status"], "metrics": result["metrics"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
