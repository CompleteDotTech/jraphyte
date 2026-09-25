"""Bounded exact global resolution with independently recheckable certificates."""
from __future__ import annotations
from copy import deepcopy
from typing import Any
from .adapter import validate_observation
from .budget import RunBudget
from .canonical import digest
from .catalog import Catalog
from .compiler import now
from .constraints import add_candidates_to_facts, validate_graph, impact
from .errors import ContractError, boundary, require

SOLVER="exact-subset-v1"

def primary_observation(catalog: Catalog, candidate_id: str, observation_ids: list[str]) -> dict[str,Any] | None:
    candidate=catalog.get(candidate_id,"candidate")
    task="IDENTITY" if candidate["candidate_kind"]=="IDENTITY" else "SUPPORT"
    matches=[]
    for ref in observation_ids:
        o=catalog.get(ref,"observation")
        if o["candidate_id"]!=candidate_id:continue
        p=catalog.get(o["pack_id"],"pack")
        q=next(x for x in p["questions"] if x["id"]==o["question_id"])
        if q["task"]==task and q["primitive"]=="CHOICE":matches.append(o)
    require(len(matches)<=1,"AMBIGUOUS_PRIMARY_OBSERVATION","choose an explicit immutable retry/replay branch")
    return matches[0] if matches and matches[0]["status"]=="OK" else None

def acceptance_label(candidate: dict[str,Any]) -> str:
    predicate=candidate["assertion"]["predicate"]
    if candidate["candidate_kind"]=="IDENTITY":return "MATCH"
    require(predicate in {"supports","refutes"},"UNSUPPORTED_TASK","fixed-question pipeline supports supports/refutes/identity")
    return "SUPPORTS" if predicate=="supports" else "CONTRADICTS"

def accepted_probability(catalog: Catalog, candidate_id: str, observation_ids: list[str]) -> float | None:
    primary=primary_observation(catalog,candidate_id,observation_ids)
    if primary is None:return None
    label=acceptance_label(catalog.get(candidate_id,"candidate"))
    require(label in primary["probabilities"],"DISTRIBUTION_LABELS","missing accepted-label contract")
    return primary["probabilities"][label]

def build_problem(catalog: Catalog, candidate_ids: list[str], observation_ids: list[str], snapshot_id: str,
                  exclusive_groups: list[list[str]] | None = None) -> dict[str,Any]:
    snap=catalog.get(snapshot_id,"graph-snapshot")
    pairs,cannot=[],[]; dependents={node:[] for node in snap["nodes"]}
    for ref,fact in snap["assertions"].items():
        if not fact["active"]:continue
        a=fact["assertion"]
        if a["predicate"]=="same_as":pairs.append([a["subject"],a["object"]])
        elif a["predicate"]=="different_from":cannot.append([a["subject"],a["object"]])
        for node in (a["subject"],a["object"]):dependents[node].append(ref)
    # Include transitive assertion dependents in the impact certificate.
    children={ref:set() for ref in snap["assertions"]}
    for ref,fact in snap["assertions"].items():
        for parent in fact["prerequisites"]:
            if parent in children:children[parent].add(ref)
    for node,refs in dependents.items():
        todo=list(refs);seen=set(refs)
        while todo:
            for child in children[todo.pop()]:
                if child not in seen:seen.add(child);todo.append(child)
        dependents[node]=sorted(seen)
    weights={}
    for ref in candidate_ids:
        p=accepted_probability(catalog,ref,observation_ids)
        weights[ref]=round(1_000_000*(2*p-1)) if p is not None else -1_000_001
    groups=sorted(sorted(group) for group in (exclusive_groups or []))
    require(all(len(g)>1 and len(g)==len(set(g)) and set(g)<=set(candidate_ids) for g in groups),"EXCLUSIVE_GROUP","invalid alternative set")
    return {"nodes":snap["nodes"],"existing_identity_pairs":sorted(pairs),"cannot_links":sorted(cannot),
            "exclusive_groups":groups,"weights":weights,"dependent_assertions":dependents}

@boundary
def solve(catalog: Catalog, *, run_id: str, candidate_ids: list[str], observation_ids: list[str], snapshot_id: str,
          budget: RunBudget, max_expansions: int = 65536, exclusive_groups: list[list[str]] | None = None,
          created_at: str | None = None) -> str:
    require(budget.run_id==run_id,"BUDGET_SCOPE","solver run mismatch")
    require(type(max_expansions) is int and max_expansions>0,"SOLVER_BUDGET","positive cap required")
    ids=sorted(candidate_ids)
    require(len(ids)==len(set(ids)) and len(observation_ids)==len(set(observation_ids)),"DUPLICATE_ID","solver inputs")
    candidates={ref:catalog.get(ref,"candidate") for ref in ids}
    require(all(c["run_id"]==run_id for c in candidates.values()),"MODE_MISMATCH","solver candidate run")
    for ref in observation_ids:
        validate_observation(catalog,ref)
        require(catalog.get(ref,"observation")["candidate_id"] in candidates,"CANDIDATE_BINDING",ref)
    snapshot=catalog.get(snapshot_id,"graph-snapshot")
    schema=catalog.get(snapshot["schema_id"],"schema")
    problem=build_problem(catalog,ids,observation_ids,snapshot_id,exclusive_groups)
    status="OPTIMAL"; best: list[str]=[]; best_value=None; expansions=0
    try:validate_graph(snapshot["nodes"],snapshot["assertions"],schema["relations"])
    except ContractError:status="INFEASIBLE"
    if status!="INFEASIBLE":
        # Never construct an unbounded search range for a large problem.
        if len(ids)>24:status="BUDGET_EXHAUSTED"
        else:
            for mask in range(1<<len(ids)):
                if expansions>=max_expansions:status="BUDGET_EXHAUSTED";break
                try:budget.consume("solver_expansions")
                except ContractError as exc:
                    if exc.code!="RUN_BUDGET_EXHAUSTED":raise
                    status="BUDGET_EXHAUSTED";break
                expansions+=1
                chosen=[ref for j,ref in enumerate(ids) if mask&(1<<j)]
                if any(sum(ref in chosen for ref in group)>1 for group in problem["exclusive_groups"]):continue
                if any(primary_observation(catalog,ref,observation_ids) is None for ref in chosen):continue
                try:
                    facts=add_candidates_to_facts(snapshot,candidates,chosen)
                    validate_graph(snapshot["nodes"],facts,schema["relations"])
                except ContractError:continue
                value=sum(problem["weights"][ref] for ref in chosen)
                if best_value is None or value>best_value or (value==best_value and tuple(chosen)<tuple(best)):
                    best,best_value=chosen,value
        if status=="OPTIMAL" and best_value is None:status="INFEASIBLE"
    if status!="OPTIMAL":best=[];best_value=None
    new_pairs=[[candidates[ref]["assertion"]["subject"],candidates[ref]["assertion"]["object"]]
               for ref in best if candidates[ref]["candidate_kind"]=="IDENTITY"]
    body={"run_id":run_id,"candidate_ids":ids,"candidate_hashes":{ref:catalog.hash(ref) for ref in ids},
          "observation_ids":sorted(observation_ids),"observation_hashes":{ref:catalog.hash(ref) for ref in observation_ids},"snapshot_id":snapshot_id,
          "snapshot":{"graph_version":snapshot["graph_version"],"schema_hash":snapshot["schema_hash"]},
          "problem":problem,"problem_hash":digest(problem),"solver_version":SOLVER,
          "objective":"MAX_INTEGER_UTILITY_THEN_LEXICOGRAPHIC","status":status,"selected_ids":best,
          "expansions":expansions,"objective_value":best_value,
          "impact":impact(problem["nodes"],problem["existing_identity_pairs"],new_pairs,problem["dependent_assertions"]),
          "created_at":created_at or now()}
    return catalog.put("resolution-batch",body)

@boundary
def verify_certificate(catalog: Catalog, batch_id: str, snapshot_id: str) -> None:
    b=catalog.get(batch_id,"resolution-batch");snap=catalog.get(snapshot_id,"graph-snapshot")
    require(b["snapshot_id"]==snapshot_id,"CERTIFICATE_SNAPSHOT","exact snapshot identity differs")
    require(b["snapshot"]=={"graph_version":snap["graph_version"],"schema_hash":snap["schema_hash"]},"CERTIFICATE_SNAPSHOT",batch_id)
    require(b["candidate_hashes"]=={r:catalog.hash(r) for r in b["candidate_ids"]} and
            b["observation_hashes"]=={r:catalog.hash(r) for r in b["observation_ids"]},"CERTIFICATE_INPUT",batch_id)
    expected=build_problem(catalog,b["candidate_ids"],b["observation_ids"],snapshot_id,b["problem"]["exclusive_groups"])
    require(b["problem"]==expected and b["problem_hash"]==digest(expected),"CERTIFICATE_INPUT","problem not derived from snapshot/observations")
    if b["status"]!="OPTIMAL":
        require(b["selected_ids"]==[] and b["objective_value"] is None,"SOLVER_UNRESOLVED","incomplete search cannot claim selection")
        return
    require(set(b["selected_ids"])<=set(b["candidate_ids"]),"CANDIDATE_BINDING",batch_id)
    require(all(sum(ref in b["selected_ids"] for ref in group)<=1 for group in expected["exclusive_groups"]),"EXCLUSIVE_GROUP",batch_id)
    candidates={ref:catalog.get(ref,"candidate") for ref in b["candidate_ids"]}
    facts=add_candidates_to_facts(snap,candidates,b["selected_ids"])
    validate_graph(snap["nodes"],facts,catalog.get(snap["schema_id"],"schema")["relations"])
    require(b["objective_value"]==sum(expected["weights"][ref] for ref in b["selected_ids"]),"CERTIFICATE_OBJECTIVE",batch_id)
    new_pairs=[[candidates[ref]["assertion"]["subject"],candidates[ref]["assertion"]["object"]]
               for ref in b["selected_ids"] if candidates[ref]["candidate_kind"]=="IDENTITY"]
    require(b["impact"]==impact(expected["nodes"],expected["existing_identity_pairs"],new_pairs,expected["dependent_assertions"]),
            "CERTIFICATE_IMPACT",batch_id)
    # Feasibility is independently checked. Global optimality is not used as
    # write authority; exact solver generation and its termination count are audited.
    require(b["expansions"]==1<<len(b["candidate_ids"]),"SOLVER_INCOMPLETE","exact enumerator did not complete")

def effective_risk(operation: str, batch: dict[str,Any] | None = None) -> str:
    floor={"ATTACH_CANDIDATE_METADATA":1,"ADD_ASSERTION":2,"RETRACT_ASSERTION":3,
           "ADD_IDENTITY_ASSERTION":4,"PROPOSE_SCHEMA_MIGRATION":5,"APPLY_SCHEMA_MIGRATION":5}[operation]
    # Conservative structural classification, not an empirical error threshold.
    if operation=="ADD_IDENTITY_ASSERTION" and batch and (batch["impact"]["implied_equivalences"]>1 or batch["impact"]["dependent_assertions"]>0):floor=5
    return f"R{floor}"

def project_resolutions(catalog: Catalog, batch_id: str) -> list[str]:
    batch=catalog.get(batch_id,"resolution-batch");result=[]
    for ref in batch["candidate_ids"]:
        candidate=catalog.get(ref,"candidate")
        outcome="UNRESOLVED" if batch["status"]!="OPTIMAL" else "SELECTED" if ref in batch["selected_ids"] else "NOT_SELECTED"
        operation="ADD_IDENTITY_ASSERTION" if candidate["candidate_kind"]=="IDENTITY" else "ADD_ASSERTION"
        body = {"candidate_id":ref,"batch_id":batch_id,"outcome":outcome,
                "evidence_ids":candidate["evidence_ids"],"observation_ids":[x for x in batch["observation_ids"] if catalog.get(x,"observation")["candidate_id"]==ref],
                "risk_class":effective_risk(operation,batch)}
        from .retrieval.integration import resolution_lineage
        body.update(resolution_lineage(catalog, body["observation_ids"]))
        result.append(catalog.put("resolution", body))
    return result
