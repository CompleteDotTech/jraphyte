"""Deterministic graph constraints shared by the solver and transaction boundary."""
from __future__ import annotations
from collections import defaultdict
from copy import deepcopy
from typing import Any, Iterable
from .canonical import dumps
from .errors import require
from .references import topological_order

class UnionFind:
    def __init__(self, nodes: Iterable[str]):
        self.parent={node:node for node in nodes}
    def root(self, node: str) -> str:
        require(node in self.parent,"UNKNOWN_NODE",node)
        while self.parent[node]!=node:
            self.parent[node]=self.parent[self.parent[node]]
            node=self.parent[node]
        return node
    def union(self, left: str, right: str) -> None:
        a,b=self.root(left),self.root(right)
        self.parent[max(a,b)]=min(a,b)
    def groups(self) -> list[list[str]]:
        groups: dict[str,list[str]]=defaultdict(list)
        for node in sorted(self.parent):groups[self.root(node)].append(node)
        return sorted(groups.values())

def normalize(assertion: dict[str,Any], relations: dict[str,Any]) -> tuple[str,str,str]:
    s,p,o=assertion["subject"],assertion["predicate"],assertion["object"]
    require(p in relations,"UNKNOWN_PREDICATE",p)
    if relations[p]["inverse_of"]:
        s,p,o=o,relations[p]["inverse_of"],s
    if relations[p]["symmetric"] and s>o:s,o=o,s
    return s,p,o

def validate_schema_contract(relations: dict[str,Any]) -> None:
    require(bool(relations),"SCHEMA_EMPTY","relation schema required")
    for predicate,spec in relations.items():
        require(set(spec["incompatible"])<=set(relations),"MISSING_REFERENCE",predicate)
        if spec["symmetric"]:require(spec["domain"]==spec["range"],"SCHEMA_TYPE",predicate)
        inverse=spec["inverse_of"]
        if inverse:
            require(inverse in relations and not relations[inverse]["inverse_of"] and not spec["symmetric"],"SCHEMA_INVERSE",predicate)
            target=relations[inverse]
            require((spec["domain"],spec["range"])==(target["range"],target["domain"]),"SCHEMA_INVERSE",predicate)
    if "same_as" in relations:
        require(relations["same_as"]["symmetric"] and not relations["same_as"]["inverse_of"],"IDENTITY_SCHEMA","same_as must be canonical/symmetric")

def validate_graph(nodes: dict[str,str], facts: dict[str,Any], relations: dict[str,Any]) -> dict[str,str]:
    validate_schema_contract(relations)
    active={key:value for key,value in facts.items() if value["active"]}
    topological_order({key:value["prerequisites"] for key,value in active.items()})
    uf=UnionFind(nodes)
    for key,fact in active.items():
        s,p,o=normalize(fact["assertion"],relations)
        require(s in nodes and o in nodes,"UNKNOWN_NODE",key)
        spec=relations[p]
        for node,expected in ((s,spec["domain"]),(o,spec["range"])):
            require(expected=="*" or nodes[node]==expected,"ENDPOINT_TYPE",key)
        if p=="same_as":
            require(nodes[s]==nodes[o],"IDENTITY_TYPE",key)
            uf.union(s,o)
    conflicts: dict[tuple[str,str,str],set[str]]=defaultdict(set)
    for key,fact in active.items():
        a=fact["assertion"]; s,p,o=normalize(a,relations); spec=relations[p]
        if p=="different_from":require(uf.root(s)!=uf.root(o),"CANNOT_LINK",key)
        if p not in {"same_as","different_from"}:
            s,o=uf.root(s),uf.root(o)
            if spec["symmetric"] and s>o:s,o=o,s
        require(s!=o or spec["allow_self"],"SELF_RELATION",key)
        scope=dumps(a["qualifiers"]); previous=conflicts[(s,o,scope)]
        require(all(other not in spec["incompatible"] and p not in relations[other]["incompatible"] for other in previous),
                "INCOMPATIBLE_RELATION",key)
        previous.add(p)
    return {node:uf.root(node) for node in nodes}

def add_candidates_to_facts(snapshot: dict[str,Any], candidates: dict[str,dict[str,Any]], selected: list[str]) -> dict[str,Any]:
    result=deepcopy(snapshot["assertions"])
    for ref in selected:
        c=candidates[ref]
        require(ref not in result,"IMMUTABLE_ASSERTION",ref)
        result[ref]={"assertion":c["assertion"],"evidence_ids":c["evidence_ids"],"prerequisites":c["prerequisites"],"active":True,"revision":1}
    return result

def impact(nodes: dict[str,str], before_pairs: list[list[str]], after_pairs: list[list[str]], dependents: dict[str,list[str]]) -> dict[str,int]:
    before,after=UnionFind(nodes),UnionFind(nodes)
    for s,o in before_pairs:before.union(s,o);after.union(s,o)
    for s,o in after_pairs:after.union(s,o)
    old=sum(len(g)*(len(g)-1)//2 for g in before.groups())
    new=sum(len(g)*(len(g)-1)//2 for g in after.groups())
    affected=set()
    for group in after.groups():
        if len({before.root(n) for n in group})>1:affected.update(group)
    downstream={ref for node in affected for ref in dependents.get(node,[])}
    return {"implied_equivalences":new-old,"affected_nodes":len(affected),"dependent_assertions":len(downstream)}
