"""A complete isolated lifecycle using synthetic observations and ephemeral keys.

No provider call, deployed backend access, persistent private key, or real
qualification is involved. The test store is durably marked sandbox-only.
"""
from __future__ import annotations
import json
import tempfile
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from .adapter import record_response
from .backend import SQLiteReferenceBackend, CompilerService
from .budget import RunBudget
from .canonical import digest, dumps, write
from .catalog import Catalog
from .compiler import compile_pack, now
from .errors import require
from .ledger import make_bundle
from .plans import add_operation,create_plan,REQUIRED_CHECKS,Lifecycle
from .policy import create_policy
from .programs import question
from .qualification import evaluate_policy
from .resolver import solve,project_resolutions
from .trust import Signer,TrustStore,IssuerPolicy,authorize_plan
from .validation import validate_bundle

RUN="isolated-lifecycle-demo"
SCOPE="isolated-test"
POPULATION="fabricated-fixtures-not-qualified"
POLICY="reviewed-sandbox-v1"


def relation(domain: str, range_: str, **changes: Any) -> dict[str,Any]:
    return {"domain":domain,"range":range_,"symmetric":False,"inverse_of":None,
            "incompatible":[],"transitive":False,"allow_self":False,**changes}


def limits(**changes: int) -> dict[str,int]:
    return {"retrieval_requests":20,"model_calls":20,"retries":20,"solver_expansions":10000,
            "review_actions":20,"request_bytes":10_000_000,**changes}


def fixture_response(pack: dict[str,Any], probabilities: list[float] | None=None) -> bytes:
    answers={}
    for index,q in enumerate(pack["questions"]):
        if q["primitive"]=="CHOICE":
            p=(probabilities or [.95]*len(pack["questions"]))[index]
            labels=[v["label"] for v in q["criteria"]]
            values={labels[0]:p,labels[1]:.0,labels[2]:1-p}
            answers[q["id"]]={"type":"choice","choice":max(values,key=values.get),"probabilities":values,"confidence":.5}
        elif q["primitive"]=="NOUL":answers[q["id"]]={"type":"noul","noul":.8}
        else:
            answers[q["id"]]={"type":"score","score":1.5,"legend":{v["label"]:v["description"] for v in q["criteria"]},
                "probabilities":{"0":0.0,"1":.5,"2":.5},"confidence":.5}
    return json.dumps({"model":pack["model_version"],"answers":answers,
                       "usage":{"input_tokens":100,"output_tokens":20}},separators=(",",":")).encode()


@dataclass
class DemoFixture:
    root: Path
    catalog: Catalog
    backend: SQLiteReferenceBackend
    trust: TrustStore
    reviewer: Signer
    validator: Signer
    checkpoint: Signer
    budget: RunBudget
    policy_id: str
    schema_id: str
    claim_id: str
    source_ids: list[str]
    evidence_ids: list[str]
    candidate_ids: list[str]
    snapshot_id: str
    pack_id: str
    observation_ids: list[str]
    batch_id: str
    resolution_ids: list[str]
    evaluation_ids: list[str]
    plan_id: str
    service: CompilerService

    def approvals(self) -> tuple[dict[str,Any],dict[str,Any]]:
        self.budget.consume("review_actions")
        preflight=self.service.preflight(self.catalog,self.plan_id,reviewed=True)
        authorization=authorize_plan(self.reviewer,self.catalog.get(self.plan_id,"plan"),
                                     self.catalog.hash(self.plan_id),reviewed_by="isolated-test-reviewer")
        self.catalog.put("receipt",preflight);self.catalog.put("receipt",authorization)
        return preflight,authorization

    def publish(self, *, fault=None, approvals=None) -> dict[str,Any]:
        preflight,authorization=approvals or self.approvals()
        return self.service.publish(self.catalog,self.plan_id,preflight=preflight,authorization=authorization,fault=fault)

    def status_change(self, source_id: str, *, active: bool=False, permission: str="READ", tombstone: bool=False,
                      key: str | None=None) -> dict[str,Any]:
        status=self.backend.statuses()[source_id];version=self.backend.state()["graph_version"]
        action={"action":"ERASE" if tombstone else "STATUS_CHANGE","source_id":source_id,"source_hash":self.catalog.hash(source_id),
            "active":active,"permission":permission,"expected_epoch":status["epoch"],"expected_version":version,
            "security_scope":SCOPE,"reason":"isolated lifecycle test","tombstone":tombstone}
        receipt=self.reviewer.issue("SOURCE_STATUS",action)
        return self.backend.change_source_status(self.catalog,source_id,active=active,permission=permission,
            expected_epoch=status["epoch"],expected_version=version,key=key or f"status:{source_id}:{status['epoch']}",
            reason=action["reason"],authorization=receipt,trust=self.trust,tombstone=tombstone)

    def bundle(self, *, historical: bool=False, signed: bool=True) -> dict[str,Any]:
        snap=self.catalog.get(self.snapshot_id,"graph-snapshot")
        return make_bundle(self.catalog,run_id=RUN,execution_mode="SYNTHETIC",security_scope=SCOPE,
            graph_version=snap["graph_version"],schema_hash=snap["schema_hash"],source_status=self.backend.statuses(),
            policy_version=POLICY,profile="HISTORICAL_REPLAY" if historical else "FINALIZED_ANALYSIS",
            signer=self.checkpoint if signed else None)

    def close(self) -> None:
        self.backend.close();self.budget.close()


def build_fixture(root: Path, *, probabilities: list[float] | None=None, mode: str="SYNTHETIC",
                  make_plan: bool=True, candidate_count: int=2, primitives: list[str] | None=None,
                  sandbox: bool=True, policy_mode: str="REVIEWED", token_counter=None,
                  tokenizer_version: str="utf8-byte-estimate-v1", existing_schema=None, prerequisite_chain=False, backend_factory=None,
                  fixture_claim_text: str="Aster joined Meridian in 2024.", fixture_document_id: str="document-demo",
                  fixture_extra_nodes: dict[str,str] | None=None) -> DemoFixture:
    """Shared test fixture, never an automatically qualified production setup."""
    root.mkdir(parents=True,exist_ok=True)
    catalog=Catalog();claim=catalog.claim(fixture_claim_text)
    relations=existing_schema or {"supports":relation("Document","Claim",incompatible=["refutes"]),
               "refutes":relation("Document","Claim",incompatible=["supports"]),
               "same_as":relation("*","*",symmetric=True,transitive=True),
               "different_from":relation("*","*",symmetric=True)}
    schema_id=catalog.put("schema",{"version":"demo-schema-v1","relations":relations})
    policy_id=create_policy(catalog,version=POLICY,scope=SCOPE,population=POPULATION,mode=policy_mode,allowed_modes=[mode])
    reviewer,validator,checkpoint=(Signer.ephemeral(x) for x in ("ephemeral-reviewer","ephemeral-validator","ephemeral-checkpoint"))
    trust=TrustStore()
    all_ops=frozenset({"ADD_ASSERTION","ADD_IDENTITY_ASSERTION","RETRACT_ASSERTION","ATTACH_CANDIDATE_METADATA",
        "PROPOSE_SCHEMA_MIGRATION","APPLY_SCHEMA_MIGRATION","SOURCE_ADMIT","SOURCE_WITHDRAW","SOURCE_PERMISSION","SOURCE_ERASE"})
    trust.enroll(reviewer.issuer,IssuerPolicy(reviewer.public_key(),"isolated-test-reviewer",
        frozenset({"AUTHORIZATION","SOURCE_STATUS","QUALIFICATION","OBSERVATION"}),all_ops,frozenset({SCOPE}),frozenset({mode}),5,True))
    trust.enroll(validator.issuer,IssuerPolicy(validator.public_key(),"isolated-validator",frozenset({"PREFLIGHT"}),
        frozenset(),frozenset({SCOPE}),frozenset({mode})))
    trust.enroll(checkpoint.issuer,IssuerPolicy(checkpoint.public_key(),"isolated-checkpoint",frozenset({"RUN_CHECKPOINT"}),
        frozenset(),frozenset({SCOPE}),frozenset({mode})))
    backend=(backend_factory or SQLiteReferenceBackend)(root/"graph.sqlite3",catalog=catalog,schema_id=schema_id,
                                   nodes={fixture_document_id:"Document",claim:"Claim","person-a":"Person","person-b":"Person","person-c":"Person", **(fixture_extra_nodes or {})},sandbox=sandbox)
    budget=RunBudget(root/"budget.sqlite3",RUN,limits())
    sources=[catalog.source(fixture_document_id,str(i+1),f"{fixture_claim_text} Archival representation {i+1}.",scope=SCOPE) for i in range(candidate_count)]
    admission={"action":"ADMIT","source_hashes":{ref:catalog.hash(ref) for ref in sorted(sources)},
               "security_scope":SCOPE,"execution_mode":mode,"expected_version":0}
    backend.admit_sources(catalog,sources,trust=trust,authorization=reviewer.issue("SOURCE_STATUS",admission),
                          security_scope=SCOPE,execution_mode=mode,expected_version=0,key="admit-fixture-snapshots")
    snapshot=backend.snapshot(catalog)
    evidence=[catalog.evidence(s,0,len(fixture_claim_text)) for s in sources]
    candidates=[]
    for i,ev in enumerate(evidence):
        candidates.append(catalog.candidate(id_=f"candidate-{i+1}",run_id=RUN,
            assertion={"subject":fixture_document_id,"predicate":"supports","object":claim,"qualifiers":{}},
            claim_id=claim,evidence_ids=[ev],prerequisites=[candidates[-1]] if prerequisite_chain and candidates else [],mode=mode))
    questions=[question(ref,id_=f"q{i+1}") for i,ref in enumerate(candidates)]
    for prim in primitives or []:questions.append(question(candidates[0],id_=f"extra-{prim}",task="EVIDENCE_QUALITY",primitive=prim))
    pack_id=compile_pack(catalog,id_="pack-demo",run_id=RUN,candidate_ids=candidates,questions=questions,snapshot_id=snapshot,
                        security_scope=SCOPE,execution_mode=mode,token_counter=token_counter,tokenizer_version=tokenizer_version)
    observations=record_response(catalog,pack_id,fixture_response(catalog.get(pack_id,"pack"),probabilities))
    if mode!="SYNTHETIC":
        # Test importer attests only in this explicitly isolated fixture.
        from .trust import attest_observation
        for ref in observations:catalog.put("receipt",attest_observation(reviewer,catalog.record(ref,"observation")))
    batch=solve(catalog,run_id=RUN,candidate_ids=candidates,observation_ids=observations,snapshot_id=snapshot,budget=budget)
    resolutions=project_resolutions(catalog,batch)
    evaluations=[evaluate_policy(catalog,candidate_id=ref,batch_id=batch,policy_version=POLICY,population=POPULATION) for ref in candidates]
    selected=set(catalog.get(batch,"resolution-batch")["selected_ids"])
    ops=[add_operation(catalog,r,e,operation_id=f"add:{c}") for c,r,e in zip(candidates,resolutions,evaluations) if c in selected]
    plan_id=create_plan(catalog,run_id=RUN,snapshot_id=snapshot,operations=ops,security_scope=SCOPE,execution_mode=mode,
                       idempotency_key="publish-demo",policy_version=POLICY,source_status=backend.statuses()) if make_plan and ops else ""
    service=CompilerService(backend,trust,validator,policy_version=POLICY,population=POPULATION,security_scope=SCOPE,
                            publication_mode=policy_mode,policy_hash=catalog.hash(policy_id))
    return DemoFixture(root,catalog,backend,trust,reviewer,validator,checkpoint,budget,policy_id,schema_id,claim,sources,evidence,
                       candidates,snapshot,pack_id,observations,batch,resolutions,evaluations,plan_id,service)


def run_demo(output_dir: str | Path | None=None) -> dict[str,Any]:
    with tempfile.TemporaryDirectory(prefix="trace-gc-isolated-") as temporary:
        fixture=build_fixture(Path(temporary))
        try:
            approvals=fixture.approvals()
            initial_bundle=fixture.bundle();validation=validate_bundle(initial_bundle,trust=fixture.trust)
            first=fixture.publish(approvals=approvals)
            duplicate=fixture.publish(approvals=approvals)
            before=fixture.backend.view(fixture.catalog)
            fixture.status_change(fixture.source_ids[0])
            one_remaining=fixture.backend.view(fixture.catalog)
            fixture.status_change(fixture.source_ids[1])
            none_remaining=fixture.backend.view(fixture.catalog)
            history=fixture.bundle(historical=True)
            replay=validate_bundle(history,trust=fixture.trust)
            audit=fixture.backend.audit()
            lifecycle=Lifecycle(fixture.catalog.hash(fixture.plan_id))
            lifecycle.advance("RESOLVED")
            lifecycle.advance("PREFLIGHT_VALIDATED",receipt_hash=digest(approvals[0]),checks={x:True for x in REQUIRED_CHECKS})
            lifecycle.advance("AUTHORIZED",receipt_hash=digest(approvals[1]))
            lifecycle.advance("COMMIT_RECHECK")
            lifecycle.advance("COMMITTED",receipt_hash=digest(first["receipt"]))
            require(len(before["edges"])==1 and len(before["edges"][0]["assertion_ids"])==2,"DEMO_INVARIANT","two OR proofs expected")
            require(len(one_remaining["edges"])==1 and len(one_remaining["edges"][0]["assertion_ids"])==1,"DEMO_INVARIANT","alternative proof must survive")
            require(none_remaining["edges"]==[] and duplicate["replayed"],"DEMO_INVARIANT","withdrawal/idempotency differs")
            report={"status":"PASS","execution_mode":"SYNTHETIC","backend":"isolated-sqlite-reference-v1",
                "provider_calls":0,"production_graph_writes":0,"test_transactions":fixture.backend.state()["graph_version"],
                "initial_validation":validation,"historical_replay":replay,"backend_audit":audit,
                "idempotent_retry":duplicate["replayed"],"proofs_before_withdrawal":2,"proofs_after_first_withdrawal":1,
                "edges_after_second_withdrawal":0,"unqualified_policy_outcomes":[fixture.catalog.get(x,"evaluation")["outcome"] for x in fixture.evaluation_ids],
                "lifecycle":lifecycle.events,"budget":fixture.budget.snapshot(),
                "qualification":"NOT_QUALIFIED: synthetic fixture only","legacy_conformance":"NOT_RUN: pinned upstream checkout required"}
            if output_dir is not None:
                target=Path(output_dir);target.mkdir(parents=True,exist_ok=True)
                write(target/"bundle.json",initial_bundle);write(target/"historical_bundle.json",history)
                write(target/"demo_results.json",report)
                # Public keys only; an application must separately enroll actual deployment keys.
                import base64
                write(target/"demo_public_keys.json",{s.issuer:base64.b64encode(s.public_key()).decode() for s in (fixture.reviewer,fixture.validator,fixture.checkpoint)})
            return report
        finally:fixture.close()

if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--output",type=Path)
    args=parser.parse_args();print(json.dumps(run_demo(args.output),indent=2))
