"""Draft and review cited answers from current, authorized GraphRAG context.

The application supplies a pinned model and its current access policy. Citation
identity is checked mechanically; claim support still requires attributed review.
"""
from __future__ import annotations

import base64
import binascii
import json
from typing import Callable

from .canonical import bytes_digest, digest, loads
from .errors import boundary, require
from .schema import validate

INSTRUCTION = ("Answer only from the listed evidence. Return JSON with claims, each "
               "naming evidence_ids. If unsupported, return abstain=true and claims=[].")


def _sealed(value: dict) -> dict:
    return {**value, "sha256": digest(value)}


def _current(catalog, backend, context_id: str, current_access: dict) -> tuple[dict, dict, int, str]:
    """Reconstruct canonical context and bind live graph/source state."""
    from .retrieval.integration import validate_record
    from .retrieval.service import validate_context
    require(type(current_access) is dict and bool(current_access),
            "ANSWER_ACCESS", "application current access policy required")
    validate("graph-access", current_access)
    record = catalog.record(context_id, "graphrag-answer")
    validate_record(catalog, record)
    context = record["body"]
    require(context["answer_status"] == "CONTEXT_ONLY", "ANSWER_CONTEXT", "context-only record required")
    graph_context_id = context["graph_context_id"]
    with backend._lock:
        statuses = backend.statuses()
        version = backend.state()["graph_version"]
    graph_context = catalog.get(graph_context_id, "graph-context")
    require(graph_context["graph_version"] == version, "STALE_GRAPH_CONTEXT", "graph changed after retrieval")
    validate_context(catalog, graph_context_id, current_access=current_access, current_status=statuses)
    citations = {row["evidence_id"]: row for row in context["citations"]}
    require(len(citations) == len(context["citations"]), "ANSWER_CITATION", "duplicate evidence citation")
    for evidence_id, citation in citations.items():
        catalog.verify_evidence(evidence_id)
        source_status = statuses.get(citation["source_snapshot_id"])
        require(source_status is not None and source_status["active"] and
                source_status["permission"] == "READ" and not source_status["tombstone"],
                "ANSWER_SOURCE_WITHDRAWN", "cited source is not currently readable")
    with backend._lock:
        final_statuses = backend.statuses()
        final_version = backend.state()["graph_version"]
    require((final_version, final_statuses) == (version, statuses),
            "ANSWER_SOURCE_CHANGED", "graph or source changed during validation")
    return context, citations, version, digest(statuses)


def _prompt(question: str, citations: dict[str, dict]) -> bytes:
    request = {"instruction": INSTRUCTION, "question": question,
               "evidence": [{"evidence_id": row["evidence_id"], "quote": row["quote"]}
                            for row in sorted(citations.values(), key=lambda x: x["evidence_id"])]}
    return json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _response(response: bytes, citations: dict[str, dict]) -> dict:
    parsed = loads(response)  # rejects duplicate keys, nonfinite numbers and malformed UTF-8
    require(type(parsed) is dict and set(parsed) == {"abstain", "claims"} and
            type(parsed["abstain"]) is bool and type(parsed["claims"]) is list,
            "ANSWER_FORMAT", "response shape differs")
    require((not parsed["claims"]) if parsed["abstain"] else bool(parsed["claims"]),
            "ANSWER_FORMAT", "abstention and claims disagree")
    for claim in parsed["claims"]:
        require(type(claim) is dict and set(claim) == {"text", "evidence_ids"} and
                type(claim["text"]) is str and bool(claim["text"].strip()) and
                type(claim["evidence_ids"]) is list and bool(claim["evidence_ids"]) and
                len(claim["evidence_ids"]) == len(set(claim["evidence_ids"])) and
                all(type(x) is str and x in citations for x in claim["evidence_ids"]),
                "ANSWER_CITATION", "claim cites missing or invalid evidence")
    return parsed


@boundary
def draft_answer(catalog, backend, *, context_id: str, current_access: dict, question: str,
                 model_id: str, model_revision: str, tokenizer_id: str,
                 generate: Callable[[bytes], bytes], maximum_prompt_bytes: int = 16000,
                 maximum_response_bytes: int = 4000) -> dict:
    """Call a pinned adapter once; return a held draft, never a verified answer."""
    require(type(question) is str and bool(question.strip()), "ANSWER_CONTEXT", "question required")
    require(model_id and model_revision and tokenizer_id, "ANSWER_MODEL", "pinned model identity required")
    _, citations, graph_version, source_status_hash = _current(catalog, backend, context_id, current_access)
    if not citations:
        return _sealed({"status": "ABSTAIN_NO_AUTHORIZED_EVIDENCE", "context_id": context_id,
                        "context_sha256": catalog.hash(context_id), "question": question,
                        "model_id": model_id, "model_revision": model_revision,
                        "tokenizer_id": tokenizer_id, "provider_calls": 0,
                        "claims": [], "review_required": False,
                        "graph_version": graph_version, "source_status_sha256": source_status_hash})
    prompt = _prompt(question, citations)
    require(len(prompt) <= maximum_prompt_bytes, "ANSWER_BUDGET", "prompt exceeds byte budget")
    response = generate(prompt)
    require(type(response) is bytes and len(response) <= maximum_response_bytes,
            "ANSWER_BUDGET", "model response exceeds byte budget")
    parsed = _response(response, citations)
    _, _, final_version, final_status_hash = _current(catalog, backend, context_id, current_access)
    require((final_version, final_status_hash) == (graph_version, source_status_hash),
            "ANSWER_SOURCE_CHANGED", "graph or source status changed during generation")
    return _sealed({"status": "ABSTAIN_MODEL" if parsed["abstain"] else "REVIEW_REQUIRED",
                    "context_id": context_id, "context_sha256": catalog.hash(context_id),
                    "question": question, "model_id": model_id,
                    "model_revision": model_revision, "tokenizer_id": tokenizer_id,
                    "prompt_sha256": bytes_digest(prompt), "response_sha256": bytes_digest(response),
                    "prompt_base64": base64.b64encode(prompt).decode("ascii"),
                    "response_base64": base64.b64encode(response).decode("ascii"),
                    "provider_calls": 1, "claims": parsed["claims"],
                    "review_required": bool(parsed["claims"]),
                    "graph_version": graph_version, "source_status_sha256": source_status_hash})


@boundary
def review_answer(catalog, backend, *, draft: dict, expected_draft_sha256: str,
                  current_access: dict, reviewer: str, reviewer_kind: str,
                  reviewed_at: str, claim_support: list[bool]) -> dict:
    """Record source-first support judgments after revalidating current access."""
    body = {k: v for k, v in draft.items() if k != "sha256"}
    require(draft.get("sha256") == expected_draft_sha256 == digest(body),
            "ANSWER_DRAFT_CHANGED", "draft differs from durable checkpoint")
    require(body["status"] == "REVIEW_REQUIRED" and body["review_required"],
            "ANSWER_REVIEW", "draft has no reviewable claims")
    require(reviewer and reviewer_kind in {"assistant", "human"} and reviewed_at,
            "ANSWER_REVIEW", "attributed review required")
    try:
        prompt = base64.b64decode(body["prompt_base64"], validate=True)
        response = base64.b64decode(body["response_base64"], validate=True)
    except (binascii.Error, ValueError):
        require(False, "ANSWER_DRAFT_CHANGED", "prompt or response encoding changed")
    require(bytes_digest(prompt) == body["prompt_sha256"] and
            bytes_digest(response) == body["response_sha256"],
            "ANSWER_DRAFT_CHANGED", "prompt or response changed")
    _, citations, graph_version, source_status_hash = _current(
        catalog, backend, body["context_id"], current_access)
    require(catalog.hash(body["context_id"]) == body["context_sha256"] and
            (graph_version, source_status_hash) ==
            (body["graph_version"], body["source_status_sha256"]),
            "ANSWER_CONTEXT_CHANGED", "context, graph or source status changed")
    parsed = _response(response, citations)
    require(not parsed["abstain"] and parsed["claims"] == body["claims"] and
            prompt == _prompt(body["question"], citations),
            "ANSWER_DRAFT_CHANGED", "draft does not match original model exchange")
    require(len(claim_support) == len(parsed["claims"]) and
            all(type(value) is bool for value in claim_support),
            "ANSWER_REVIEW", "one support judgment per claim required")
    _, _, final_version, final_status_hash = _current(catalog, backend, body["context_id"], current_access)
    require((final_version, final_status_hash) == (graph_version, source_status_hash),
            "ANSWER_SOURCE_CHANGED", "graph or source status changed during review")
    return _sealed({"draft_sha256": draft["sha256"], "context_id": body["context_id"],
                    "status": "SUPPORTED" if all(claim_support) else "REJECTED_UNSUPPORTED_CLAIM",
                    "claim_support": claim_support, "reviewer": reviewer,
                    "reviewer_kind": reviewer_kind, "reviewed_at": reviewed_at,
                    "independent_review": False, "graph_version": graph_version,
                    "source_status_sha256": source_status_hash})
