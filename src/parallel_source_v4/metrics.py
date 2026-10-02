"""Disjoint proposal, abstention, conversion and admission measurements."""
from __future__ import annotations

from collections import Counter
from trace_gc.pdf_source_parallel_v4 import compare
from .fidelity import LEGACY_METRIC_VERSION, evaluate_fidelity, fidelity_summary

COMPLETE = "complete"
PARTIAL = {"partial", "partial_on_page_one"}
ABSENT = {"absent", "no_abstract_text"}


def score_case(case_id: str, prediction: dict, reference: dict, *, evaluated_at: str | None = None) -> dict:
    return {"id": case_id, "gold": reference["status"], "predicted": prediction["status"],
            "legacy_metric_version": LEGACY_METRIC_VERSION,
            "fidelity": evaluate_fidelity(prediction, reference, evaluated_at=evaluated_at),
            "proposed": bool(prediction.get("proposal", False)),
            "conversion_status": prediction.get("conversion_status", "unknown"),
            "verified_admission": bool(prediction.get("verified_admission", False)),
            "field_candidate": bool(prediction.get("field_candidate", False)),
            "request_budget": prediction.get("request_budget", {}).get("status", "not_assessed"),
            "math_review_required": bool(reference.get("math_review_required") or prediction.get("math_review_required")),
            "reasons": prediction.get("reasons", []), **compare(prediction.get("text", ""), reference["text"])}


def summary(details: list[dict]) -> dict:
    complete = [d for d in details if d["gold"] == COMPLETE]
    proposed = [d for d in details if d["proposed"]]
    good = [d for d in proposed if d["gold"] == COMPLETE and d["text_match_98"]]
    wrong = [d for d in proposed if not (d["gold"] == COMPLETE and d["text_match_98"])]
    withheld = [d for d in complete if not d["proposed"]]
    incorrect_complete = [d for d in complete if d["proposed"] and not d["text_match_98"]]
    # Never count a matching withheld candidate as a correct proposal.
    assert len(good)+len(withheld)+len(incorrect_complete) == len(complete)
    return {"legacy_metric_version": LEGACY_METRIC_VERSION, "fidelity": fidelity_summary(details),
            "pages": len(details), "complete_available": len(complete), "proposed": len(proposed),
            "correct_proposals_98": len(good), "false_proposals": len(wrong),
            "complete_abstracts_withheld": len(withheld), "complete_abstracts_proposed_incorrectly": len(incorrect_complete),
            "matching_complete_abstracts_withheld": sum(d["text_match_98"] for d in withheld),
            "proposal_precision_98": len(good)/len(proposed) if proposed else None,
            "correct_proposal_recall_98": len(good)/len(complete) if complete else None,
            "boundary_and_98_correct_proposals": sum(d["boundary_and_98_match"] for d in good),
            "boundary_accuracy_among_proposals": sum(d["gold"] == COMPLETE and d["boundary_and_98_match"] for d in proposed)/len(proposed) if proposed else None,
            "partial_false_proposals": sum(d["gold"] in PARTIAL for d in proposed),
            "absent_false_proposals": sum(d["gold"] in ABSENT for d in proposed),
            "wrong_proposal_ids": [d["id"] for d in wrong], "withheld_complete_ids": [d["id"] for d in withheld],
            "states": dict(Counter(d["predicted"] for d in details)),
            "conversion_states": dict(Counter(d["conversion_status"] for d in details)),
            "request_budget_states": dict(Counter(d["request_budget"] for d in details)),
            "verified_admissions": sum(d["verified_admission"] for d in details),
            "math_review_ids": [d["id"] for d in details if d["math_review_required"]]}


def fallback_increment(primary: list[dict], fallback: list[dict]) -> dict:
    a, b = {d["id"]: d for d in primary}, {d["id"]: d for d in fallback}
    if len(a) != len(primary) or len(b) != len(fallback) or set(a) != set(b):
        raise ValueError("fallback_requires_identical_unique_paired_cases")
    extra = [b[k] for k in a if not a[k]["proposed"] and b[k]["proposed"]]
    good = [d for d in extra if d["gold"] == COMPLETE and d["text_match_98"]]
    return {"additional_correct": len(good), "additional_wrong": len(extra)-len(good),
            "additional_ids": [d["id"] for d in extra], "automatic_fallback_enabled": False,
            "policy_status": "requires_separate_approval_independent_labels_and_risk_coverage_assessment"}


def ranking_metrics(rankings: dict[str, list[str]], pools: dict[str, list[str]], queries: list[dict]) -> dict:
    details = []
    for q in queries:
        key = str(q["id"])
        order, pool = rankings[key], pools[key]
        if len(order) != len(set(order)) or len(pool) != len(set(pool)):
            raise ValueError("duplicate_ranking_or_pool_ids")
        if set(order) != set(pool):
            raise ValueError("reranker_must_rank_exact_candidate_pool_without_insertion_or_drop")
        target = q["target_id"]
        rank = order.index(target)+1 if target in order else None
        details.append({"id": key, "target_id": target, "candidate_present": target in pool,
                        "rank": rank, "reciprocal_rank": 1/rank if rank else 0.0,
                        "top10": order[:10], "competing_results_relevance": "unjudged"})
    n = len(details)
    return {"queries": n, "top1": sum(d["rank"] == 1 for d in details),
            "top10": sum(d["rank"] is not None and d["rank"] <= 10 for d in details),
            "mrr": sum(d["reciprocal_rank"] for d in details)/n if n else None,
            "candidate_coverage": sum(d["candidate_present"] for d in details)/n if n else None,
            "details": details}
