"""Bounded retrieval work and context accounting; costs are work units, not USD."""
from __future__ import annotations
import time
from typing import Any, Callable
from ..canonical import dumps
from ..errors import ContractError, require
from .contracts import RetrievalBudget


def conservative_tokens(value: Any) -> int:
    """UTF-8 byte upper-bound estimate, not a provider-qualified tokenizer."""
    return len(dumps(value).encode("utf-8"))


class BudgetMeter:
    def __init__(self, limits: RetrievalBudget, *, clock: Callable[[], float] = time.monotonic):
        self.limits, self.clock, self.started = limits, clock, clock()
        self.used = {"cost_units": 0, "candidates": 0, "nodes": 0, "edges": 0, "paths": 0,
                     "communities": 0, "decisions": 0, "source_spans": 0, "tokens": 0,
                     "graph_queries": 0, "vector_queries": 0}
        self.exhausted: str | None = None

    def check(self) -> None:
        if self.elapsed_ms >= self.limits.maximum_latency_ms:
            self.exhausted = "latency"
            raise ContractError("RETRIEVAL_BUDGET_EXHAUSTED", "latency deadline")

    @property
    def elapsed_ms(self) -> float:
        return max(0.0, (self.clock() - self.started) * 1000)

    def work(self, amount: int = 1, *, candidate: bool = False) -> None:
        self.check()
        require(type(amount) is int and amount >= 0, "RETRIEVAL_BUDGET", "invalid work charge")
        if self.used["cost_units"] + amount > self.limits.maximum_cost_units:
            self.exhausted = "cost_units"
            raise ContractError("RETRIEVAL_BUDGET_EXHAUSTED", "cost limit")
        if candidate and self.used["candidates"] >= self.limits.maximum_candidates:
            self.exhausted = "candidates"
            raise ContractError("RETRIEVAL_BUDGET_EXHAUSTED", "candidate limit")
        self.used["cost_units"] += amount
        self.used["candidates"] += int(candidate)

    def accept(self, item: dict[str, Any], tokens: int, seen: dict[str, set[str]]) -> tuple[bool, str]:
        """Count unique underlying nodes/edges/spans, including path/summary members."""
        groups = {"nodes": set(item["entity_ids"]), "edges": set(item["assertion_ids"]),
                  "source_spans": set(item["evidence_ids"]), "decisions": set(item["decision_ids"]),
                  "paths": {item["id"]} if item["kind"] == "PATH" else set(),
                  "communities": {item["id"]} if item["kind"] == "COMMUNITY" else set()}
        for resource, values in groups.items():
            if len(seen[resource] | values) > getattr(self.limits, "maximum_" + resource):
                return False, resource + "_budget"
        if self.used["tokens"] + tokens > self.limits.maximum_tokens:
            return False, "token_budget"
        for resource, values in groups.items():
            seen[resource].update(values)
            self.used[resource] = len(seen[resource])
        self.used["tokens"] += tokens
        return True, "selected_by_bounded_utility"
