"""Qualification tests use fabricated fixtures and ephemeral test approvals only."""
from __future__ import annotations
import concurrent.futures
import json
import math
import tempfile
import unittest
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from trace_gc.adapter import TypeSafeAdapter
from trace_gc.budget import RunBudget
from trace_gc.canonical import digest,dumps
from trace_gc.catalog import Catalog
from trace_gc.compiler import now,timestamp,byte_estimate
from trace_gc.demo import build_fixture,limits,fixture_response,RUN,SCOPE,POLICY,POPULATION
from trace_gc.errors import ContractError
from trace_gc.plans import add_operation,create_plan
from trace_gc.qualification import upper_error_bound,evaluate_labels,QualificationRegistry,context_for,pipeline_fingerprint,evaluate_policy,audit_sample,SCOPE_FIELDS
from trace_gc.trust import authorize_plan,verify_authorization


def test_label_rows(n=100):
    return [{"action_id":f"test-action-{i}","group_id":f"test-group-{i}","source_ids":[f"test-source-{i}"],
             "label_correct":True,"labeler":"fabricated-unit-test-labeler","label_origin":"HUMAN","score":.95,
             "resolver_selected":True,"constraints_passed":True,"decision":"ACCEPT","split":"LOCKED_HOLDOUT"} for i in range(n)]


class StatisticalTests(unittest.TestCase):
    def test_zero_error_bound_is_not_zero(self):
        self.assertAlmostEqual(upper_error_bound(0,100,.95),1-.05**.01,places=12)
    def test_all_errors_bound_one(self):self.assertEqual(upper_error_bound(100,100,.95),1)
    def test_positive_error_exact_reference(self):
        bound=upper_error_bound(1,10,.95)
        self.assertAlmostEqual((1-bound)**10+10*bound*(1-bound)**9,.05,places=12)
    def test_zero_acceptance_is_undefined(self):
        with self.assertRaisesRegex(ContractError,"RISK_DENOMINATOR"):upper_error_bound(0,0,.95)
    def test_risk_bound_monotonicity(self):
        values=[upper_error_bound(k,100,.95) for k in range(20)]
        self.assertEqual(values,sorted(values));self.assertEqual(len(values),len(set(values)))
    def test_more_data_reduces_zero_error_bound(self):self.assertLess(upper_error_bound(0,1000,.95),upper_error_bound(0,100,.95))
    def test_higher_confidence_increases_bound(self):self.assertGreater(upper_error_bound(2,100,.99),upper_error_bound(2,100,.95))
    def test_nonboolean_counts(self):
        with self.assertRaises(ContractError):upper_error_bound(True,10,.95)
    def test_audit_sampling_reproducible_without_duplicates(self):
        ids=[f"accepted-{i}" for i in range(100)]
        sample=audit_sample(ids,20,seed=3)
        self.assertEqual(sample,audit_sample(list(reversed(ids)),20,seed=3));self.assertEqual(len(set(sample)),20)
        self.assertNotEqual(sample,audit_sample(ids,20,seed=4))


class QualificationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.f=build_fixture(Path(self.temp.name),mode="RECORDED",sandbox=False,policy_mode="QUALIFIED",token_counter=byte_estimate,tokenizer_version="test-tokenizer-v1")
        self.addCleanup(self.f.close)
        self.scope=context_for(self.f.catalog,self.f.candidate_ids[0],self.f.observation_ids,self.f.batch_id,population=POPULATION,policy_version=POLICY)
        self.protocol={"locked":True,"split":"LOCKED_HOLDOUT","threshold":.9,"pipeline_hash":pipeline_fingerprint(self.scope),
                       "calibration_group_ids":[],"development_group_ids":[]}
        self.expires=(timestamp(now())+timedelta(days=1)).isoformat()
    def artifact(self,rows=None,**changes):
        args={"scope":self.scope,"protocol":self.protocol,"threshold":.9,"risk_limit":.05,"minimum_coverage":.8,"confidence":.95,"expires_at":self.expires}
        args.update(changes)
        return evaluate_labels(test_label_rows() if rows is None else rows,**args)
    def register(self):
        q=self.artifact();qid=self.f.catalog.put("qualification",q)
        receipt=self.f.reviewer.issue("QUALIFICATION",{"qualification_hash":self.f.catalog.hash(qid),"pipeline_hash":q["pipeline_hash"],
                    "security_scope":SCOPE,"execution_mode":"RECORDED"},expires_at=self.expires)
        self.f.catalog.put("receipt",receipt)
        registry=QualificationRegistry(self.f.trust);registry.register(self.f.catalog,qid,receipt)
        return registry,qid
    def test_exact_applicability(self):
        registry,qid=self.register();self.assertEqual(registry.applicable(self.f.catalog,qid,self.scope)["n_accepted"],100)
    def test_every_scope_dimension_is_bound(self):
        registry,qid=self.register()
        for key in SCOPE_FIELDS:
            with self.subTest(field=key):
                bad=deepcopy(self.scope);bad[key]=str(bad[key])+"-changed"
                with self.assertRaisesRegex(ContractError,"QUALIFICATION_SCOPE"):registry.applicable(self.f.catalog,qid,bad)
    def test_no_unapproved_qualification(self):
        qid=self.f.catalog.put("qualification",self.artifact());registry=QualificationRegistry(self.f.trust)
        with self.assertRaisesRegex(ContractError,"UNQUALIFIED_POLICY"):registry.applicable(self.f.catalog,qid,self.scope)
    def test_revoke_qualification(self):
        registry,qid=self.register();registry.revoke(qid)
        with self.assertRaisesRegex(ContractError,"UNQUALIFIED_POLICY"):registry.applicable(self.f.catalog,qid,self.scope)
    def test_signed_approval_cannot_follow_rehashed_substitution(self):
        registry,qid=self.register();records=self.f.catalog.all()
        for r in records:
            if r["id"]==qid:r["body"]["threshold"]=.1;r["hash"]=digest({"kind":r["kind"],"body":r["body"]})
        altered=Catalog(records)
        with self.assertRaisesRegex(ContractError,"QUALIFICATION_BINDING"):registry.applicable(altered,qid,self.scope)
    def test_expired_qualification(self):
        registry,qid=self.register()
        with self.assertRaises(ContractError):registry.applicable(self.f.catalog,qid,self.scope,at=(timestamp(self.expires)+timedelta(days=1)).isoformat())
    def test_synthetic_population_cannot_be_qualified(self):
        scope=deepcopy(self.scope);scope["execution_mode"]="SYNTHETIC"
        with self.assertRaisesRegex(ContractError,"SYNTHETIC_QUALIFICATION"):self.artifact(scope=scope)
    def test_locked_threshold_required(self):
        with self.assertRaisesRegex(ContractError,"EVALUATION_PROTOCOL"):self.artifact(threshold=.85)
    def test_duplicate_action_id_rejected(self):
        rows=test_label_rows();rows[1]["action_id"]=rows[0]["action_id"]
        with self.assertRaisesRegex(ContractError,"EVALUATION_LEAKAGE"):self.artifact(rows)
    def test_correlated_source_groups_rejected(self):
        rows=test_label_rows();rows[1]["source_ids"]=rows[0]["source_ids"]
        with self.assertRaisesRegex(ContractError,"EVALUATION_DEPENDENCE"):self.artifact(rows)
    def test_development_holdout_overlap_rejected(self):
        protocol=deepcopy(self.protocol);protocol["development_group_ids"]=["test-group-1"]
        with self.assertRaisesRegex(ContractError,"EVALUATION_LEAKAGE"):self.artifact(protocol=protocol)
    def test_model_generated_labels_rejected(self):
        rows=test_label_rows();rows[0]["label_origin"]="MODEL"
        with self.assertRaisesRegex(ContractError,"INDEPENDENT_LABELS"):self.artifact(rows)
    def test_zero_acceptance_not_zero_risk(self):
        rows=test_label_rows()
        for row in rows:row.update(score=.1,decision="ABSTAIN")
        with self.assertRaisesRegex(ContractError,"NO_ACCEPTED_ACTIONS"):self.artifact(rows)
    def test_risk_limit_must_be_met(self):
        rows=test_label_rows();rows[0]["label_correct"]=False
        with self.assertRaisesRegex(ContractError,"QUALIFICATION_FAILED"):self.artifact(rows,risk_limit=.001)
    def test_final_pipeline_not_pre_resolver_score(self):
        rows=test_label_rows();rows[0]["resolver_selected"]=False
        with self.assertRaisesRegex(ContractError,"EVALUATION_PIPELINE"):self.artifact(rows)
    def test_frozen_observations_reused_for_policy_evaluation(self):
        before={r["id"]:r["hash"] for r in self.f.catalog.all("observation")};registry,qid=self.register()
        eid=evaluate_policy(self.f.catalog,candidate_id=self.f.candidate_ids[0],batch_id=self.f.batch_id,policy_version=POLICY,population=POPULATION,registry=registry,qualification_id=qid)
        self.assertEqual(self.f.catalog.get(eid)["outcome"],"ACCEPT")
        self.assertEqual(before,{r["id"]:r["hash"] for r in self.f.catalog.all("observation")})
        self.assertEqual(self.f.catalog.get(self.f.evaluation_ids[0])["outcome"],"ABSTAIN")
    def test_qualified_automatic_gate_still_requires_authorization(self):
        registry,qid=self.register();self.f.service.registry=registry
        evaluations=[evaluate_policy(self.f.catalog,candidate_id=c,batch_id=self.f.batch_id,policy_version=POLICY,population=POPULATION,registry=registry,qualification_id=qid) for c in self.f.candidate_ids]
        ops=[add_operation(self.f.catalog,r,e,operation_id=f"qualified:{i}") for i,(r,e) in enumerate(zip(self.f.resolution_ids,evaluations))]
        pid=create_plan(self.f.catalog,run_id=RUN,snapshot_id=self.f.snapshot_id,operations=ops,security_scope=SCOPE,execution_mode="RECORDED",idempotency_key="qualified-fixture",policy_version=POLICY,source_status=self.f.backend.statuses())
        pre=self.f.service.preflight(self.f.catalog,pid,reviewed=False)
        approval=authorize_plan(self.f.reviewer,self.f.catalog.get(pid),self.f.catalog.hash(pid))
        result=self.f.service.publish(self.f.catalog,pid,preflight=pre,authorization=approval)
        self.assertFalse(result["replayed"]);self.assertEqual(result["receipt"]["version"],2)


class SharedBudgetTests(unittest.TestCase):
    def test_persisted_usage_cannot_reset(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"budget.sqlite3"
            with RunBudget(path,"run",limits()) as b:b.consume("model_calls",2)
            with RunBudget(path,"run",limits()) as b:self.assertEqual(b.snapshot()["used"]["model_calls"],2)
            with self.assertRaisesRegex(ContractError,"BUDGET_CONFIG_CHANGED"):RunBudget(path,"run",limits(model_calls=100))
    def test_multiple_resources_reserved_atomically(self):
        with tempfile.TemporaryDirectory() as d,RunBudget(Path(d)/"b.sqlite3","r",limits(model_calls=1,retries=0)) as b:
            with self.assertRaisesRegex(ContractError,"RUN_BUDGET_EXHAUSTED"):b.consume_many({"model_calls":1,"retries":1})
            self.assertEqual(b.snapshot()["used"]["model_calls"],0)
    def test_concurrent_reservations_cannot_overspend(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"b.sqlite3"
            with RunBudget(p,"run",limits(model_calls=10)) as first,RunBudget(p,"run",limits(model_calls=10)) as second:
                def attempt(index):
                    try:(first if index%2 else second).consume("model_calls");return 1
                    except ContractError:return 0
                with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(attempt,range(40)))
                self.assertEqual(sum(results),10);self.assertEqual(first.snapshot()["used"]["model_calls"],10)
    def test_negative_and_boolean_reservations_fail(self):
        with tempfile.TemporaryDirectory() as d,RunBudget(Path(d)/"b.sqlite3","r",limits()) as b:
            for amount in [-1,True]:
                with self.assertRaisesRegex(ContractError,"BUDGET_REQUEST"):b.consume("model_calls",amount)


class MockTransportTests(unittest.TestCase):
    def test_retry_records_errors_and_signed_success_without_real_network(self):
        with tempfile.TemporaryDirectory() as d:
            f=build_fixture(Path(d),mode="LIVE",token_counter=byte_estimate,tokenizer_version="test-tokenizer-v1")
            calls=[]
            try:
                def transport(body,key,timeout):
                    calls.append(body)
                    return (429,{"Retry-After":"0"},b'{"error":"rate"}') if len(calls)==1 else (200,{},fixture_response(f.catalog.get(f.pack_id)))
                adapter=TypeSafeAdapter(enabled=True,api_key="unit-test-not-a-real-key",transport=transport,sleeper=lambda seconds:None,
                    token_counter=byte_estimate,tokenizer_version="test-tokenizer-v1",observation_signer=f.reviewer)
                ids=adapter.evaluate(f.catalog,f.pack_id,source_status=f.backend.statuses(),budget=f.budget,max_retries=1)
                self.assertEqual([f.catalog.get(x)["status"] for x in ids],["ERROR","ERROR","OK","OK"])
                self.assertEqual(len(calls),2);self.assertEqual(calls[0],calls[1])
                self.assertEqual(f.budget.snapshot()["used"]["model_calls"],2)
                self.assertEqual(f.budget.snapshot()["used"]["retries"],1)
                self.assertTrue(all(any(r["body"]["payload"].get("observation_hash")==f.catalog.hash(x) for r in f.catalog.all("receipt")) for x in ids))
            finally:f.close()
    def test_caller_cannot_claim_measured_tokenizer_without_injected_implementation(self):
        with tempfile.TemporaryDirectory() as d:
            f=build_fixture(Path(d),mode="LIVE",token_counter=byte_estimate,tokenizer_version="test-tokenizer-v1")
            try:
                adapter=TypeSafeAdapter(enabled=True,api_key="unit-test-not-a-real-key",transport=lambda *args:(_ for _ in ()).throw(AssertionError("must not run")))
                with self.assertRaisesRegex(ContractError,"TOKENIZER_UNQUALIFIED"):adapter.evaluate(f.catalog,f.pack_id,source_status=f.backend.statuses(),budget=f.budget)
                self.assertEqual(f.budget.snapshot()["used"]["model_calls"],0)
            finally:f.close()
