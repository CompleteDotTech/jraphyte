"""Read-only replay of the 200-page regression and versioned v3 comparisons.

All original PDFs, renders, cached conversions, labels and source maps stay in
an authorized external root. This command never imports the corpus worker,
loads a model, calls an API, or connects to a graph. It will not manufacture
measurements when any required evidence is missing.
"""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

from trace_gc.pdf_source_v3 import assess_document, compare, digest, seal, verify_scholarly_field
from .adapters import read_native_page, mineru_assess, olmocr_assess
from .common import REPO, code_hashes, data_root, external_output, file_digest, read, resolve_source, write_once, safe_id

METHODS = ("source_v3", "grobid_verified_v3", "mineru_v3", "olmocr_v3")
OLD_METHODS = ("current", "geometry_v1", "grobid", "structure_v2", "mineru", "olmocr")
MATH_HOLDS = {"f026", "f033", "f103", "f111", "f122", "f125", "f131", "f142", "f146", "f153", "f154", "f158", "f166", "f189"}


def summary(details: list[dict[str, Any]]) -> dict[str, Any]:
    complete = [d for d in details if d["gold"] == "complete"]
    proposed = [d for d in details if d["proposed"]]
    good = [d for d in proposed if d["gold"] == "complete" and d["text_match_98"]]
    return {"pages": len(details), "complete_available": len(complete),
            "text_recovered_98": sum(d["text_match_98"] for d in complete),
            "proposed": len(proposed), "correct_proposals_98": len(good),
            "proposal_precision_98": len(good)/len(proposed) if proposed else None,
            "correct_proposal_recall_98": len(good)/len(complete) if complete else None,
            "false_proposals": [d["id"] for d in proposed if d not in good],
            "withheld_complete": [d["id"] for d in complete if not d["proposed"]],
            "matching_text_withheld": [d["id"] for d in complete if d["text_match_98"] and not d["proposed"]],
            "partial_false_proposals": [d["id"] for d in proposed if d["gold"] == "partial_on_page_one"],
            "absent_false_proposals": [d["id"] for d in proposed if d["gold"] == "no_abstract_text"],
            "boundary_and_98_correct_proposals": sum(d["boundary_and_98_match"] for d in good),
            "states": dict(Counter(d["predicted"] for d in details)),
            "conversion_states": dict(Counter(d.get("conversion_status", "not_recorded") for d in details)),
            "request_budget_states": dict(Counter(d.get("request_budget_status", "not_recorded") for d in details)),
            "verified_admissions": 0}


def paired_fallback(primary: list[dict[str, Any]], fallback: list[dict[str, Any]]) -> dict[str, Any]:
    left, right = {d["id"]: d for d in primary}, {d["id"]: d for d in fallback}
    if set(left) != set(right):
        raise ValueError("unpaired_fallback_cohort")
    selected = [right[sid] for sid in left if not left[sid]["proposed"] and right[sid]["proposed"]]
    return {"primary_abstentions": sum(not d["proposed"] for d in primary),
            "new_correct": [d["id"] for d in selected if d["gold"] == "complete" and d["text_match_98"]],
            "new_wrong": [d["id"] for d in selected if not (d["gold"] == "complete" and d["text_match_98"])],
            "automatic_use_enabled": False, "reason": "no_approved_independent_risk_coverage_policy"}


class RegressionInputs:
    def __init__(self, root: Path, source_map: dict[str, str]):
        self.root, self.source_map = root, source_map
        self.old = root / "validation_v2"
        self.expanded = root / "validation_expanded200"

    def page(self, sid: str) -> Path:
        # This is historical cache routing, not a selector rule or a label hint.
        return (self.old if int(sid[1:]) <= 100 else self.expanded) / "pages" / sid

    def cache(self, method: str, sid: str, suffix: str = ".json") -> Path:
        old = self.old / method / (sid + suffix)
        return old if int(sid[1:]) <= 100 and old.exists() else self.expanded / method / (sid + suffix)

    def verify_page(self, sid: str, public: dict[str, Any]) -> tuple[dict, list]:
        folder = self.page(sid)
        receipt = read(folder / "receipt.json")
        if receipt.get("physical_page") != 1:
            raise ValueError("wrong_physical_page")
        for name, field in (("page.pdf", "page_pdf_sha256"), ("page.png", "image_sha256"),
                            ("reference_blocks.json", "reference_blocks_sha256")):
            expected = public[field]
            if file_digest(folder / name) != expected:
                raise ValueError("retained_source_artifact_hash_mismatch")
            if field in receipt and receipt[field] != expected:
                raise ValueError("receipt_binding_mismatch")
        source_hash = public["source_sha256"]
        if receipt["source_sha256"] != source_hash or source_hash not in self.source_map:
            raise ValueError("authorized_original_source_mapping_required")
        source = resolve_source(self.root, self.source_map[source_hash])
        if file_digest(source) != source_hash:
            raise ValueError("original_source_hash_mismatch")
        # Native typography is recovered from the actual physical page, rather
        # than inferred from paragraph labels or synthesized OCR rectangles.
        native = read_native_page(source)
        retained = read_native_page(folder / "page.pdf")
        a = " ".join(l["text"] for l in native["native_lines"])
        b = " ".join(l["text"] for l in retained["native_lines"])
        if not compare(a, b)["text_match_98"]:
            raise ValueError("retained_page_native_text_not_reproduced")
        return receipt, native["native_lines"]

    def frozen_prediction(self, method: str, sid: str, receipt: dict) -> dict:
        # Imports are of the frozen offline selectors only, never paid adapters
        # or the active run_jev_corpus worker.
        from trace_gc.pdf_evidence import assess_first_page
        from trace_gc.pdf_structure import assess_document as v2
        from src.abstract_validation_v2.adapters import mineru_document, olmocr_assess as old_ocr
        kwargs = {"page_size": receipt["page_size"], "source_sha256": receipt["source_sha256"],
                  "page_sha256": receipt["page_pdf_sha256"], "native_lines": read(self.page(sid) / "lines.json")}
        if method == "current":
            return read(self.cache("baselines/current", sid))
        grobid = read(self.cache("grobid", sid))
        text = grobid.get("text", "")
        if method == "grobid":
            return {**grobid, "text": text.strip(), "status": "complete" if text.strip() else ("error" if grobid["status"] == "error" else "absent"), "eligible_for_jev": bool(text.strip())}
        source = "docling" if method in {"geometry_v1", "structure_v2"} else method
        raw = read(self.cache(source, sid))
        if raw.get("page_sha256") and raw["page_sha256"] != kwargs["page_sha256"]:
            raise ValueError("cached_conversion_page_mismatch")
        if raw["status"] == "error":
            return {"status": "error", "text": "", "eligible_for_jev": False, "reasons": [raw.get("error", "Conversion error")]}
        if source == "docling":
            document = read(self.cache("docling", sid, ".document.json"))
            if method == "geometry_v1":
                return assess_first_page(document["texts"], **kwargs, conversion_status=raw["status"])
            return v2(document, **kwargs, scholarly_abstract=text, conversion_status=raw["status"])
        if method == "mineru":
            return v2(mineru_document(raw, kwargs["page_size"]), **kwargs, scholarly_abstract=text, conversion_status=raw["status"])
        return old_ocr(raw, **kwargs, scholarly_abstract=text)


def _detail(sid: str, prediction: dict, gold: dict) -> dict:
    return {"id": sid, "gold": gold["status"], "predicted": prediction["status"],
            "proposed": prediction.get("proposed", prediction.get("eligible_for_jev", False)),
            "conversion_status": prediction.get("conversion_status", "not_recorded"),
            "request_budget_status": prediction.get("request_budget_status", "not_recorded"),
            "reasons": prediction.get("reasons", []),
            "math_review_required": gold.get("math_review_required", False) or sid in MATH_HOLDS,
            **compare(prediction.get("text", ""), gold["text"])}


def run_regression(root: Path, out: Path, source_map: dict[str, str]) -> dict:
    started = time.perf_counter()
    inputs = RegressionInputs(root, source_map)
    required = [inputs.expanded / f for f in ("manifest.json", "labels.json", "protocol.json", "reference_freeze.json")]
    portable = REPO / "review/first_page_expanded200/source_hashes.json"
    if any(not p.is_file() for p in required + [portable]):
        receipt = {"status": "BLOCKED", "gate": "regression_source_inputs_unavailable", "cohort": "known_regression200",
                   "pages_evaluated": 0, "newly_unseen_pages": 0, "precision": None, "recall": None,
                   "source_hash_verification": "NOT_RUN", "required_artifacts": ["authorized source PDFs", "retained page PDFs/renders/native spans", "cached conversions and saved assessments", "frozen labels/protocol/source hashes"],
                   "api_calls": 0, "api_spend_usd": 0, "graph_writes": 0,
                   "runtime_seconds": time.perf_counter()-started}
        write_once(out / "blocked.json", receipt)
        return receipt
    manifest, labels = read(required[0]), read(required[1])
    old_protocol = read(required[2])
    reference_freeze = read(required[3])
    for rel, expected in old_protocol["method_hashes"].items():
        if file_digest(REPO / rel) != expected:
            raise ValueError("frozen_method_changed; preserve_original_protocol_and_bytes")
    if file_digest(required[0]) != old_protocol["manifest_sha256"]:
        raise ValueError("frozen_manifest_changed")
    if reference_freeze.get("files", {}).get("labels.json") != file_digest(required[1]):
        raise ValueError("frozen_labels_changed")
    rows = manifest["pdfs"]
    if len(rows) != 200 or len({r["sample_id"] for r in rows}) != 200:
        raise ValueError("not_the_frozen_200_page_regression")
    public = read(portable)
    protocol = {"cohort": "known_regression200", "not_unseen": True, "code_hashes": code_hashes(),
                "legacy_protocol_sha256": file_digest(required[2]), "labels_sha256": file_digest(required[1]),
                "portable_source_hashes_sha256": file_digest(portable),
                "scoring": "ordered canonical precision and recall >= .98; boundary first/last 48; gold complete",
                "automatic_fallback_enabled": False, "publication": "source_review_required",
                "model_loading": False, "api_calls": 0, "graph_writes": 0}
    write_once(out / "protocol.json", protocol)
    details = {method: [] for method in OLD_METHODS + METHODS}
    holds, replayed, verified = [], 0, 0
    for row in rows:
        sid = safe_id(row["sample_id"])
        try:
            receipt, native = inputs.verify_page(sid, public[sid])
            verified += 1
            for method in OLD_METHODS:
                pred = inputs.frozen_prediction(method, sid, receipt)
                saved = read(inputs.expanded / "assessments" / method / (sid + ".json"))
                if digest(pred) != digest(saved):
                    raise ValueError("saved_assessment_replay_mismatch_"+method)
                replayed += 1
                details[method].append(_detail(sid, pred, labels[sid]))
                write_once(out / "replay" / method / (sid + ".json"), {"id": sid, "saved_sha256": digest(saved), "reproduced_sha256": digest(pred)})
            kwargs = {"page_size": receipt["page_size"], "source_sha256": receipt["source_sha256"],
                      "page_sha256": receipt["page_pdf_sha256"], "native_lines": native}
            grobid = read(inputs.cache("grobid", sid))
            scholarly = grobid.get("text", "") if grobid.get("status") == "success" else ""
            docling = read(inputs.cache("docling", sid))
            document = read(inputs.cache("docling", sid, ".document.json"))
            predictions = {
                "source_v3": assess_document(document, **kwargs, scholarly_abstract=scholarly, conversion_status=docling["status"]),
                "grobid_verified_v3": verify_scholarly_field(grobid.get("text", ""), document, **kwargs,
                                                           conversion_status=grobid.get("status", "error"), conversion_http_status=grobid.get("http_status")),
                "mineru_v3": mineru_assess(read(inputs.cache("mineru", sid)), **kwargs, scholarly_abstract=scholarly),
                "olmocr_v3": olmocr_assess(read(inputs.cache("olmocr", sid)), **kwargs, scholarly_abstract=scholarly)}
            for method, pred in predictions.items():
                pred["source_bytes_verified"] = True
                pred["verified_input_hashes"] = public[sid]
                pred["math_review_required"] = labels[sid].get("math_review_required", False) or sid in MATH_HOLDS
                pred = seal(pred)
                write_once(out / "assessments" / method / (sid + ".json"), pred)
                details[method].append(_detail(sid, pred, labels[sid]))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            # No private filenames, paper text, tokens, or raw parser errors in
            # the compact report. Full sources stay available for local review.
            holds.append({"id": sid, "hold": "source_or_replay_verification_failed", "error_type": type(exc).__name__})
    complete_run = not holds and all(len(v) == 200 for v in details.values())
    # Partial cohorts are diagnostics, never substituted for the 200-page result.
    metrics = {m: summary(v) for m, v in details.items()} if complete_run else None
    old_good = {d["id"] for d in details["structure_v2"] if d["proposed"] and d["gold"] == "complete" and d["text_match_98"]}
    new_good = {d["id"] for d in details["source_v3"] if d["proposed"] and d["gold"] == "complete" and d["text_match_98"]}
    preservation = {"expected_prior_correct": 91, "replayed_prior_correct": len(old_good),
                    "lost_prior_correct": sorted(old_good-new_good),
                    "status": "PASS" if complete_run and len(old_good) == 91 and old_good <= new_good else "FAIL_OR_UNAVAILABLE"}
    result = {"status": "COMPLETE_REGRESSION" if complete_run else "INCOMPLETE_NO_AGGREGATE_CLAIM",
              "cohort": "known_regression200", "metrics": metrics, "details": details,
              "source_hashes_verified": verified, "saved_assessments_reproduced": replayed,
              "preserve_91_gate": preservation, "error_ledger": holds,
              "unseen_cohort": {"pages": 0, "status": "NOT_RUN", "metrics": None},
              "fallback": {m: paired_fallback(details["source_v3"], details[m]) for m in ("mineru_v3", "olmocr_v3")} if complete_run else None,
              "retrieval_metrics": None, "retrieval_gate": "run_separate_candidate_and_rerank_evaluation",
              "independent_human_validation": "outstanding", "math_review_holds": sorted(MATH_HOLDS),
              "boundary_sensitive_reference": "f151 Executive Summary remains no separate abstract",
              "api_calls": 0, "api_spend_usd": 0, "graph_writes": 0, "automatic_promotion": False,
              "runtime_seconds": time.perf_counter()-started}
    write_once(out / "results.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--out", type=Path, required=True, help="new external versioned receipt directory")
    parser.add_argument("--source-map", type=Path, help="external JSON: source SHA-256 -> relative PDF path beneath data root")
    args = parser.parse_args()
    root, out = data_root(args.data_root), external_output(args.out)
    source_map = read(args.source_map) if args.source_map else {}
    try:
        result = run_regression(root, out, source_map)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result = {"status": "BLOCKED", "gate": "frozen_input_verification", "error_type": type(exc).__name__,
                  "api_calls": 0, "api_spend_usd": 0, "graph_writes": 0}
        write_once(out / "failure.json", result)
    print(json.dumps({k: result[k] for k in ("status", "api_calls", "api_spend_usd", "graph_writes")}, indent=2))
    return 0 if result["status"] == "COMPLETE_REGRESSION" and result["preserve_91_gate"]["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
