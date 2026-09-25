"""Typed references and linear-time causal ordering; ordinary links are not DAG edges."""
from __future__ import annotations
from collections import deque
from typing import Any, Iterable, Mapping
from .errors import require

def topological_order(dependencies: Mapping[str, Iterable[str]], *, code: str = "DEPENDENCY_CYCLE") -> list[str]:
    edges = {key: set(value) for key, value in dependencies.items()}
    keys = set(edges)
    require(all(values <= keys for values in edges.values()), "MISSING_REFERENCE", "unresolved causal prerequisite")
    remaining = {key: len(value) for key, value in edges.items()}
    consumers: dict[str, list[str]] = {key: [] for key in edges}
    for key, prerequisites in edges.items():
        for ref in prerequisites:
            consumers[ref].append(key)
    queue = deque(key for key in edges if remaining[key] == 0)
    result: list[str] = []
    while queue:
        key = queue.popleft()
        result.append(key)
        for child in consumers[key]:
            remaining[child] -= 1
            if not remaining[child]:
                queue.append(child)
    require(len(result) == len(edges), code, "causal graph has a cycle")
    return result

def scoped_question(run_id: str, pack_id: str, question_id: str) -> str:
    # Length-prefixing prevents ambiguity when identifiers contain separators.
    return "".join(f"{len(x)}:{x}" for x in (run_id, pack_id, question_id))

def check_question_dependencies(packs: list[dict[str, Any]], observations: list[dict[str, Any]]) -> None:
    questions, owner, obs_by_question = {}, {}, {}
    for pack in packs:
        for q in pack["questions"]:
            key = scoped_question(pack["run_id"], pack["id"], q["id"])
            require(key not in questions, "DUPLICATE_ID", key)
            questions[key], owner[key] = q, pack
    for observation in observations:
        key = scoped_question(observation["run_id"], observation["pack_id"], observation["question_id"])
        require(key in questions, "MISSING_REFERENCE", key)
        obs_by_question.setdefault(key, []).append(observation)
    deps: dict[str, set[str]] = {}
    for key, question in questions.items():
        pack = owner[key]
        deps[key] = set()
        for ref in question["depends_on"]:
            target = scoped_question(ref["run_id"], ref["pack_id"], ref["question_id"])
            require(target in questions, "MISSING_REFERENCE", target)
            require(ref["run_id"] == pack["run_id"] and ref["pack_id"] != pack["id"],
                    "PACK_DEPENDENCY_VIOLATION", "prerequisites must precede this pack in this run")
            deps[key].add(target)
    topological_order(deps)
    for key, targets in deps.items():
        pack = owner[key]
        for target in targets:
            usable = [o for o in obs_by_question.get(target, []) if o["status"] == "OK"
                      and o["id"] in pack["prior_observation_ids"]]
            require(bool(usable), "PREREQUISITE_NOT_COMPLETED", target)
            from .compiler import timestamp
            require(all(timestamp(o["completed_at"]) <= timestamp(pack["created_at"]) for o in usable),
                    "TEMPORAL_ORDER", "upstream completion is later than pack creation")
