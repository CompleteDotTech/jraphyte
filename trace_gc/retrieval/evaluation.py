"""Retrieval/synthesis metrics and held-out research gates. No fabricated qualification."""
from __future__ import annotations
import math
from copy import deepcopy
from typing import Any
from ..canonical import digest
from ..compiler import now
from ..errors import require
from .contracts import VERSION, FAILURES

UPSTREAM_ABLATIONS = {
    "no_graph": {"retrieval_strategy": ["SOURCE", "EVIDENCE"], "include_conflicts": False},
    "one_hop": {"retrieval_strategy": ["ENTITY", "NEIGHBORHOOD"], "hop_limit": 1, "include_conflicts": False},
    "vector_only": {"retrieval_strategy": ["VECTOR"], "include_conflicts": False},
    "paths_only": {"retrieval_strategy": ["PATH"], "hop_limit": 2, "include_conflicts": False},
    "graph_only": {"retrieval_strategy": ["ENTITY", "NEIGHBORHOOD", "PATH", "CONFLICT"], "hop_limit": 2},
    "hybrid": {"retrieval_strategy": ["LEXICAL", "VECTOR", "NEIGHBORHOOD", "PATH", "CONFLICT"], "hop_limit": 2},
    "hybrid_semantic": {"retrieval_strategy": ["LEXICAL", "VECTOR", "NEIGHBORHOOD", "PATH", "CONFLICT"], "hop_limit": 2},
    "adaptive": {"retrieval_strategy": ["ENTITY", "SOURCE"], "hop_limit": 0},
}
DOWNSTREAM_ABLATIONS = {
    "vector_rag": {"retrieval_strategy": ["VECTOR"], "include_conflicts": False, "include_provenance": False},
    "plain_graph": {"retrieval_strategy": ["NEIGHBORHOOD"], "include_conflicts": False, "include_provenance": False},
    "graphrag": {"retrieval_strategy": ["NEIGHBORHOOD", "PATH", "COMMUNITY"], "include_conflicts": False, "include_provenance": False},
    "trace_provenance": {"retrieval_strategy": ["NEIGHBORHOOD", "PATH", "PROVENANCE"], "include_conflicts": False, "include_provenance": True},
    "trace_contradiction": {"retrieval_strategy": ["NEIGHBORHOOD", "PATH", "PROVENANCE", "CONFLICT"], "include_conflicts": True, "include_provenance": True},
}


def _ratio(numerator: int | float, denominator: int | float) -> float | None:
    return numerator / denominator if denominator else None


def retrieval_metrics(ranked_ids: list[str], relevance: dict[str, float], *, k: int,
                      items: list[dict[str, Any]] | None = None, expected: dict[str, list[str]] | None = None,
                      previous_ids: list[str] | None = None) -> dict[str, Any]:
    require(type(k) is int and k > 0 and all(type(v) in (int, float) and math.isfinite(v) and v >= 0 for v in relevance.values()),
            "EVALUATION_INPUT", "positive k and finite nonnegative relevance grades")
    unique = list(dict.fromkeys(ranked_ids))
    top = unique[:k]
    relevant = {key for key, grade in relevance.items() if grade > 0}
    hits = sum(key in relevant for key in top)
    dcg = sum((2**relevance.get(key, 0)-1)/math.log2(i+2) for i, key in enumerate(top))
    ideal = sum((2**grade-1)/math.log2(i+2) for i, grade in enumerate(sorted(relevance.values(), reverse=True)[:k]))
    novelty = set(unique)-set(previous_ids or [])
    result = {"precision_at_k": hits/k, "recall_at_k": _ratio(hits, len(relevant)),
              "mrr": next((1/(i+1) for i, key in enumerate(unique) if key in relevant), 0.0),
              "ndcg_at_k": _ratio(dcg, ideal), "k": k,
              "context_redundancy": 1-len(unique)/len(ranked_ids) if ranked_ids else 0.0,
              "context_novelty": _ratio(len(novelty), len(unique)),
              "retrieval_saturation": not novelty, "new_relevant_information_per_round": len(novelty & relevant)}
    for target, field in (("path", "id"), ("entity", "entity_ids"), ("evidence", "evidence_ids"),
                          ("contradiction", "id"), ("provenance", "record_refs")):
        wanted = set((expected or {}).get(target, []))
        found = set()
        for item in items or []:
            if target == "path" and item["kind"] != "PATH":
                continue
            if target == "contradiction" and item["kind"] != "CONFLICT":
                continue
            value = item[field]
            found.update([value] if isinstance(value, str) else value)
        result[target+"_recall"] = _ratio(len(wanted & found), len(wanted))
    # Redundant evidence across different paths/summary IDs is measured separately.
    evidence_refs = [e for item in items or [] for e in item["evidence_ids"]]
    result["evidence_context_redundancy"] = 1-len(set(evidence_refs))/len(evidence_refs) if evidence_refs else 0.0
    return result


def synthesis_metrics(*, predicted_edges: list[str], expected_edges: list[str], entity_decisions: list[dict[str, Any]] | None = None,
                      assertion_labels: list[dict[str, Any]] | None = None, decisions: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    predicted, expected = set(predicted_edges), set(expected_edges)
    tp = len(predicted & expected)
    precision, recall = _ratio(tp, len(predicted)), _ratio(tp, len(expected))
    pairs, labels, outcomes = entity_decisions or [], assertion_labels or [], decisions or []
    return {"graph_precision": precision, "graph_recall": recall,
            "edge_f1": 2*tp/(len(predicted)+len(expected)) if predicted or expected else None,
            "entity_resolution_accuracy": _ratio(sum(x["same_entity"] == x["predicted_same"] for x in pairs), len(pairs)),
            "false_merge_rate": _ratio(sum(x["predicted_same"] and not x["same_entity"] for x in pairs), sum(x["predicted_same"] for x in pairs)),
            "false_split_rate": _ratio(sum(x["same_entity"] and not x["predicted_same"] for x in pairs), sum(x["same_entity"] for x in pairs)),
            "unsupported_assertion_rate": _ratio(sum(not x["supported"] for x in labels), len(labels)),
            "contradiction_handling": _ratio(sum(x["conflict_handled"] for x in outcomes if x.get("has_conflict")), sum(x.get("has_conflict", False) for x in outcomes)),
            "abstention_quality": _ratio(sum(x["ambiguous"] for x in outcomes if x["decision"] == "ABSTAIN"), sum(x["decision"] == "ABSTAIN" for x in outcomes)),
            "human_review_volume": sum(x["decision"] == "HUMAN_REVIEW" for x in outcomes)}


def efficiency_metrics(lineages: list[dict[str, Any]], *, jev_latency_ms: float = 0.0,
                       total_synthesis_latency_ms: float | None = None, tokens_supplied_to_jev: int = 0,
                       accepted_assertions: int = 0, resolved_candidates: int = 0) -> dict[str, Any]:
    units = sum(x["cost_units"] for x in lineages)
    return {"retrieval_latency_ms": sum(x["latency_ms"] for x in lineages), "jev_latency_ms": jev_latency_ms,
            "total_synthesis_latency_ms": total_synthesis_latency_ms,
            "graph_query_count": sum(x["usage"]["graph_queries"] for x in lineages),
            "vector_query_count": sum(x["usage"]["vector_queries"] for x in lineages),
            "tokens_supplied_to_jev": tokens_supplied_to_jev, "retrieval_cost_units": units,
            "cost_units_per_accepted_assertion": _ratio(units, accepted_assertions),
            "cost_units_per_resolved_candidate": _ratio(units, resolved_candidates),
            "retrieval_expansions": max(0, len(lineages)-1),
            "average_graph_context_size": _ratio(sum(len(x["selected"]) for x in lineages), len(lineages)),
            "currency_cost": None, "cost_note": "Offline work units; monetary costs require a metered external provider."}


def propose_retrieval_changes(failures: list[str]) -> list[dict[str, Any]]:
    require(set(failures) <= set(FAILURES), "RESEARCH_FAILURE_CODE", "unknown error taxonomy member")
    mapping = {"ENTITY_NOT_RETRIEVED": ["ENTITY", "NEIGHBORHOOD"], "VECTOR_RETRIEVAL_MISS": ["LEXICAL", "VECTOR"],
               "RELEVANT_PATH_NOT_RETRIEVED": ["PATH"], "CONTRADICTION_NOT_RETRIEVED": ["CONFLICT", "TEMPORAL"],
               "ONTOLOGY_CONTEXT_MISSING": ["ONTOLOGY", "SCHEMA"], "PROVENANCE_CONTEXT_MISSING": ["PROVENANCE"],
               "HISTORICAL_CONTEXT_MISSING": ["DECISION", "TEMPORAL"]}
    return [{"failure": f, "proposed_channels": mapping.get(f, []), "review_required": True,
             "experiment": "Compare bounded policy on development set, then a locked disjoint holdout."} for f in failures]


def heldout_policy_gate(*, baseline: str, development_scores: dict[str, float], heldout_scores: dict[str, float],
                        development_groups: list[str], heldout_groups: list[str], locked_candidate: str,
                        minimum_gain: float = 0.0, safety_passed: bool = True) -> dict[str, Any]:
    """One locked development-selected proposal may advance on held-out improvement.

    This returns a review artifact, not a qualification or automatic code rewrite.
    Representative independent labeling remains a separate deployment requirement.
    """
    require(bool(development_groups) and bool(heldout_groups) and not set(development_groups) & set(heldout_groups),
            "EVALUATION_LEAKAGE", "development and held-out groups must be disjoint")
    require(baseline in development_scores and baseline in heldout_scores and bool(development_scores), "RESEARCH_BASELINE", "baseline missing")
    require(all(type(x) in (int, float) and math.isfinite(x) for x in list(development_scores.values())+list(heldout_scores.values())),
            "EVALUATION_INPUT", "finite metric values required")
    winner = min(development_scores, key=lambda key: (-development_scores[key], key))
    require(locked_candidate == winner and winner in heldout_scores, "EVALUATION_PROTOCOL", "candidate must be selected before seeing holdout")
    gain = heldout_scores[winner]-heldout_scores[baseline]
    retain = winner != baseline and gain > minimum_gain and safety_passed
    return {"version": VERSION, "baseline": baseline, "development_selected": winner,
            "retained_policy": winner if retain else baseline, "heldout_gain": gain, "retained_change": retain,
            "safety_passed": safety_passed, "production_qualified": False, "created_at": now(),
            "protocol_hash": digest({"baseline": baseline, "candidate": locked_candidate,
                "development_groups": sorted(development_groups), "heldout_groups": sorted(heldout_groups), "minimum_gain": minimum_gain})}
