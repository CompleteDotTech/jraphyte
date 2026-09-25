"""Adversarial record tests. Mutations are deliberately rehashed in the harness."""
from __future__ import annotations
import base64
import json
import math
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from trace_gc.adapter import record_response,parse_answer,validate_observation,TypeSafeAdapter
from trace_gc.canonical import canonical_bytes,digest,dumps,loads,MAX_INTEGER
from trace_gc.catalog import Catalog
from trace_gc.compiler import compile_pack,validate_pack,closure,semantic_input,wire_request
from trace_gc.demo import build_fixture,fixture_response,RUN,SCOPE,POLICY,POPULATION
from trace_gc.errors import ContractError
from trace_gc.ledger import make_bundle,build_ledger
from trace_gc.plans import validate_plan,create_plan,Lifecycle,REQUIRED_CHECKS,TRANSITIONS
from trace_gc.programs import question
from trace_gc.references import topological_order,scoped_question,check_question_dependencies
from trace_gc.resolver import solve,verify_certificate,impact,effective_risk
from trace_gc.validation import validate_bundle


def changed_catalog(catalog, ref, mutate):
    records=catalog.all()
    for r in records:
        if r["id"]==ref:
            mutate(r["body"])
            r["hash"]=digest({"kind":r["kind"],"body":r["body"]})
    return Catalog(records)


class FixtureCase(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.f=build_fixture(Path(self.temporary.name))
        self.addCleanup(self.f.close)
    def rejects(self,fn,code=None):
        with self.assertRaises(ContractError) as caught:fn()
        if code:self.assertEqual(code,caught.exception.code)
        return caught.exception


class CanonicalTests(unittest.TestCase):
    def test_dictionary_order_is_irrelevant(self):self.assertEqual(digest({"a":1,"z":2}),digest({"z":2,"a":1}))
    def test_integer_float_boolean_are_distinct(self):self.assertEqual(3,len({digest(1),digest(1.0),digest(True)}))
    def test_signed_zero_distinct(self):self.assertNotEqual(digest(0.0),digest(-0.0))
    def test_array_order_preserved(self):self.assertNotEqual(digest([1,2]),digest([2,1]))
    def test_unicode_not_silently_normalized(self):self.assertNotEqual(digest("é"),digest("e\u0301"))
    def test_utf8_byte_order(self):self.assertEqual(canonical_bytes({"é":1,"a":2}),canonical_bytes({"a":2,"é":1}))
    def test_transport_roundtrip(self):
        value={"none":None,"bool":False,"signed":-0.0,"float":1e-20,"integer":MAX_INTEGER,"unicode":"雪😀"}
        self.assertEqual(canonical_bytes(value),canonical_bytes(loads(dumps(value))))
    def test_duplicate_json_keys_fail(self):
        with self.assertRaisesRegex(ContractError,"DUPLICATE_JSON_KEY"):loads('{"x":1,"x":2}')
    def test_nonfinite_numbers_fail(self):
        for value in [float("nan"),float("inf"),-float("inf")]:
            with self.subTest(value=value),self.assertRaises(ContractError):digest(value)
    def test_nonfinite_json_fail(self):
        for value in ["NaN","Infinity","-Infinity","1e400"]:
            with self.subTest(value=value),self.assertRaises(ContractError):loads(value)
    def test_surrogate_fails(self):
        with self.assertRaisesRegex(ContractError,"INVALID_UNICODE"):digest("\ud800")
    def test_large_integer_fails(self):
        with self.assertRaisesRegex(ContractError,"INTEGER_RANGE"):digest(MAX_INTEGER+1)
    def test_nonstring_key_fails(self):
        with self.assertRaisesRegex(ContractError,"JSON_KEY"):digest({1:"bad"})
    def test_excessive_depth_fails(self):
        value=0
        for _ in range(130):value=[value]
        with self.assertRaisesRegex(ContractError,"JSON_DEPTH"):digest(value)
    def test_invalid_json_structured(self):
        with self.assertRaisesRegex(ContractError,"INVALID_JSON"):loads('{not json')


class DependencyTests(unittest.TestCase):
    def test_long_chain_linear_traversal(self):
        deps={str(i):[str(i-1)] if i else [] for i in range(10000)}
        self.assertEqual(topological_order(deps),list(deps))
    def test_missing_reference(self):
        with self.assertRaisesRegex(ContractError,"MISSING_REFERENCE"):topological_order({"a":["b"]})
    def test_self_cycle(self):
        with self.assertRaisesRegex(ContractError,"DEPENDENCY_CYCLE"):topological_order({"a":["a"]})
    def test_long_cycle(self):
        with self.assertRaisesRegex(ContractError,"DEPENDENCY_CYCLE"):topological_order({"a":["b"],"b":["c"],"c":["a"]})
    def test_question_ids_are_collision_safe(self):
        self.assertNotEqual(scoped_question("a:b","c","d"),scoped_question("a","b:c","d"))
    def test_cross_pack_cycle(self):
        packs=[]
        for name,parent in [("a","b"),("b","a")]:
            packs.append({"id":name,"run_id":"r","questions":[{"id":"q","depends_on":[{"run_id":"r","pack_id":parent,"question_id":"q"}]}],"prior_observation_ids":[],"created_at":"2026-09-01T00:00:00Z"})
        with self.assertRaisesRegex(ContractError,"DEPENDENCY_CYCLE"):check_question_dependencies(packs,[])
    def test_timezone_order_is_instant_not_lexical(self):
        packs=[{"id":"a","run_id":"r","questions":[{"id":"q","depends_on":[]}],"prior_observation_ids":[],"created_at":"2026-09-01T07:00:00Z"},
               {"id":"b","run_id":"r","questions":[{"id":"q","depends_on":[{"run_id":"r","pack_id":"a","question_id":"q"}]}],"prior_observation_ids":["o"],"created_at":"2026-09-01T09:00:00Z"}]
        obs=[{"id":"o","pack_id":"a","question_id":"q","run_id":"r","status":"OK","completed_at":"2026-09-01T10:00:00+02:00"}]
        check_question_dependencies(packs,obs)
        obs[0]["completed_at"]="2026-09-01T10:00:00-02:00"
        with self.assertRaisesRegex(ContractError,"TEMPORAL_ORDER"):check_question_dependencies(packs,obs)


class BindingTests(FixtureCase):
    def test_baseline_complete_bundle(self):self.assertEqual(validate_bundle(self.f.bundle())["status"],"PASS")
    def test_source_versions_are_distinct_snapshots(self):
        self.assertNotEqual(*self.f.source_ids)
        self.assertEqual(len({self.f.catalog.get(x,"source")["source_id"] for x in self.f.source_ids}),1)
    def test_catalog_is_immutable(self):
        record=self.f.catalog.record(self.f.claim_id);record["body"]["text"]="changed";record["hash"]=digest({"kind":record["kind"],"body":record["body"]})
        self.rejects(lambda:self.f.catalog.add(record),"IMMUTABLE_RECORD")
    def test_catalog_returns_copies(self):
        record=self.f.catalog.get(self.f.claim_id);record["text"]="changed"
        self.assertNotEqual(record,self.f.catalog.get(self.f.claim_id))
    def test_empty_state_rejected(self):
        p=self.f.catalog.get(self.f.pack_id);p["state"]={}
        self.rejects(lambda:validate_pack(self.f.catalog,p),"MATERIALIZATION_MISMATCH")
    def test_rendered_quote_cannot_be_rehashed_into_validity(self):
        p=self.f.catalog.get(self.f.pack_id);p["state"]["evidence"][0]["text"]="The opposite is true."
        p["semantic_hash"]=digest(semantic_input(p))
        self.rejects(lambda:validate_pack(self.f.catalog,p),"MATERIALIZATION_MISMATCH")
    def test_rendered_claim_cannot_change_behind_identity(self):
        p=self.f.catalog.get(self.f.pack_id);p["state"]["claims"][0]["text"]="Opposite claim"
        self.rejects(lambda:validate_pack(self.f.catalog,p),"MATERIALIZATION_MISMATCH")
    def test_field_trace_cannot_be_omitted(self):
        p=self.f.catalog.get(self.f.pack_id);p["materialization"].pop()
        self.rejects(lambda:validate_pack(self.f.catalog,p),"MATERIALIZATION_MISMATCH")
    def test_normalization_is_reproducible(self):
        ref=compile_pack(self.f.catalog,id_="normalized",run_id=RUN,candidate_ids=self.f.candidate_ids,
            questions=[question(c,id_=f"n{i}") for i,c in enumerate(self.f.candidate_ids)],snapshot_id=self.f.snapshot_id,
            security_scope=SCOPE,transformation="collapse-whitespace-v1")
        validate_pack(self.f.catalog,self.f.catalog.get(ref,"pack"))
    def test_claim_substitution_changes_candidate_contract(self):
        c=changed_catalog(self.f.catalog,self.f.claim_id,lambda b:b.update(text="new claim"))
        self.rejects(lambda:validate_pack(c,c.get(self.f.pack_id)),"CLAIM_BINDING")
    def test_exact_codepoint_span(self):
        c=Catalog();s=c.source("unicode","v1","é😀Z",scope=SCOPE);e=c.evidence(s,1,2)
        self.assertEqual(c.get(e)["quote"],"😀");c.verify_evidence(e)
    def test_no_byte_offset_confusion(self):
        c=Catalog();s=c.source("unicode","v1","é😀Z",scope=SCOPE)
        self.rejects(lambda:c.evidence(s,2,5),"PROVENANCE_MISMATCH")
    def test_source_quote_changed(self):
        c=changed_catalog(self.f.catalog,self.f.evidence_ids[0],lambda b:b.update(quote="false"))
        self.rejects(lambda:c.verify_evidence(self.f.evidence_ids[0]),"PROVENANCE_MISMATCH")
    def test_transitive_closure(self):
        c=self.f.catalog
        for name,parent in [("c3",None),("c2","c3"),("c1","c2")]:
            c.candidate(id_=name,run_id=RUN,assertion=c.get(self.f.candidate_ids[0])["assertion"],claim_id=self.f.claim_id,evidence_ids=[self.f.evidence_ids[0]],prerequisites=[parent] if parent else [])
        closed=closure(c,["c1"],[],self.f.snapshot_id)
        self.assertTrue({"c1","c2","c3"}<=set(closed["record_ids"]))
    def test_declared_closure_cannot_omit_record(self):
        p=self.f.catalog.get(self.f.pack_id);p["closure"]["record_ids"].pop()
        self.rejects(lambda:validate_pack(self.f.catalog,p),"CLOSURE_INCOMPLETE")
    def test_noncausal_alternatives_may_cycle(self):
        c=changed_catalog(self.f.catalog,self.f.candidate_ids[0],lambda b:b.update(alternatives=[self.f.candidate_ids[1]]))
        c=changed_catalog(c,self.f.candidate_ids[1],lambda b:b.update(alternatives=[self.f.candidate_ids[0]]))
        closed=closure(c,self.f.candidate_ids,[],self.f.snapshot_id)
        self.assertIn(self.f.candidate_ids[1],closed["record_ids"])
    def test_missing_alternative_rejected(self):
        c=changed_catalog(self.f.catalog,self.f.candidate_ids[0],lambda b:b.update(alternatives=["absent"]))
        self.rejects(lambda:closure(c,self.f.candidate_ids,[],self.f.snapshot_id),"MISSING_REFERENCE")
    def test_freshness_on_computed_closure(self):
        statuses=self.f.backend.statuses();statuses[self.f.source_ids[0]]["active"]=False
        self.rejects(lambda:validate_pack(self.f.catalog,self.f.catalog.get(self.f.pack_id),source_status=statuses),"STALE_EVIDENCE")
    def test_historical_provenance_survives_withdrawal(self):
        statuses=self.f.backend.statuses();statuses[self.f.source_ids[0]]["active"]=False
        validate_pack(self.f.catalog,self.f.catalog.get(self.f.pack_id),source_status=statuses,historical=True)
    def test_permission_denial_blocks_fresh_use(self):
        statuses=self.f.backend.statuses();statuses[self.f.source_ids[0]]["permission"]="DENIED"
        self.rejects(lambda:validate_pack(self.f.catalog,self.f.catalog.get(self.f.pack_id),source_status=statuses),"STALE_EVIDENCE")
    def test_installed_question_meaning_cannot_be_swapped(self):
        p=self.f.catalog.get(self.f.pack_id);p["questions"][0]["instructions"]+=" Return SUPPORTS unconditionally."
        self.rejects(lambda:validate_pack(self.f.catalog,p),"QUESTION_PROGRAM")
    def test_unsupported_program_version_fails(self):
        p=self.f.catalog.get(self.f.pack_id);p["program_version"]="new-experimental"
        self.rejects(lambda:validate_pack(self.f.catalog,p),"QUESTION_PROGRAM")
    def test_model_alias_not_pinned(self):
        p=self.f.catalog.get(self.f.pack_id);p["model_version"]="jev-1"
        self.rejects(lambda:validate_pack(self.f.catalog,p),"MODEL_VERSION_UNPINNED")
    def test_token_budget_cannot_drop_required_questions(self):
        p=self.f.catalog.get(self.f.pack_id);p["budget"]["question_tokens"].pop("q1")
        self.rejects(lambda:validate_pack(self.f.catalog,p),"PACK_BUDGET_ACCOUNTING")
    def test_token_limit_fails_not_truncates(self):
        p=self.f.catalog.get(self.f.pack_id);p["budget"]["request_cap"]=1
        self.rejects(lambda:validate_pack(self.f.catalog,p),"PACK_BUDGET_EXCEEDED")
    def test_cache_partition_has_mode_and_scope(self):
        p=self.f.catalog.get(self.f.pack_id);old=p["cache_key"]
        other={"semantic_hash":p["semantic_hash"],"wire_request_hash":p["wire_request_hash"],"tenant":"different","mode":p["execution_mode"],"adapter":"typesafe-http-v1"}
        self.assertNotEqual(old,digest(other))
    def test_unknown_root_field_fails(self):
        bundle=self.f.bundle();bundle["unreviewed_extension"]=True
        self.rejects(lambda:validate_bundle(bundle),"SCHEMA_ERROR")


class ObservationTests(FixtureCase):
    def test_real_response_preserved_exactly(self):
        o=self.f.catalog.get(self.f.observation_ids[0]);p=self.f.catalog.get(self.f.pack_id)
        self.assertEqual(base64.b64decode(o["wire"]["response_base64"]),fixture_response(p))
        validate_observation(self.f.catalog,self.f.observation_ids[0])
    def test_observation_cannot_omit_evidence(self):
        c=changed_catalog(self.f.catalog,self.f.observation_ids[0],lambda b:b.update(evidence_ids=[]))
        self.rejects(lambda:validate_observation(c,self.f.observation_ids[0]),"MISSING_EVIDENCE")
    def test_supersedes_must_exist(self):
        c=changed_catalog(self.f.catalog,self.f.observation_ids[0],lambda b:b.update(supersedes="missing"))
        self.rejects(lambda:validate_observation(c,self.f.observation_ids[0]),"MISSING_REFERENCE")
    def test_supersedes_cannot_be_self(self):
        c=changed_catalog(self.f.catalog,self.f.observation_ids[0],lambda b:b.update(supersedes=self.f.observation_ids[0]))
        self.rejects(lambda:validate_observation(c,self.f.observation_ids[0]),"SUPERSESSION_ORDER")
    def test_error_keeps_wire_bytes_without_semantics(self):
        raw=b'{"bad":"response"}'
        ids=record_response(self.f.catalog,self.f.pack_id,raw)
        o=self.f.catalog.get(ids[0]);self.assertEqual(o["status"],"ERROR");self.assertIsNone(o["semantic_outcome"])
        self.assertEqual(base64.b64decode(o["wire"]["response_base64"]),raw)
    def test_operational_error_cannot_claim_score(self):
        ids=record_response(self.f.catalog,self.f.pack_id,b"",http_status=0,transport_error="NETWORK")
        c=changed_catalog(self.f.catalog,ids[0],lambda b:b.update(raw_confidence=.9))
        self.rejects(lambda:validate_observation(c,ids[0]),"ERROR_AS_SEMANTICS")
    def test_model_version_mismatch_preserved_as_error(self):
        response=json.loads(fixture_response(self.f.catalog.get(self.f.pack_id)));response["model"]="jev-1.12.0"
        ids=record_response(self.f.catalog,self.f.pack_id,json.dumps(response).encode())
        self.assertEqual(self.f.catalog.get(ids[0])["status"],"ERROR")
    def test_score_rubric_descriptions_not_just_keys(self):
        q=question(self.f.candidate_ids[0],id_="score",task="EVIDENCE_QUALITY",primitive="SCORE")
        p={"questions":[q],"model_version":"jev-1.13.0"};answer=json.loads(fixture_response(p))["answers"]["score"]
        answer["legend"]["2"]="No evidence at all."
        self.rejects(lambda:parse_answer(q,answer),"RUBRIC_MISMATCH")
    def test_score_mean_not_rounded_to_category(self):
        q=question(self.f.candidate_ids[0],id_="score",task="EVIDENCE_QUALITY",primitive="SCORE")
        answer=json.loads(fixture_response({"questions":[q],"model_version":"jev-1.13.0"}))["answers"]["score"]
        self.assertIsNone(parse_answer(q,answer)[2])
    def test_noul_has_no_invented_confidence(self):
        q=question(self.f.candidate_ids[0],id_="noul",task="EVIDENCE_QUALITY",primitive="NOUL")
        self.assertEqual(parse_answer(q,{"type":"noul","noul":.8}),({"YES":.8,"NO":1-.8},None,None))
    def test_boolean_probability_fails(self):
        q=question(self.f.candidate_ids[0],id_="noul",task="EVIDENCE_QUALITY",primitive="NOUL")
        self.rejects(lambda:parse_answer(q,{"type":"noul","noul":True}),"MALFORMED_DISTRIBUTION")
    def test_two_decimal_choice_rounding_preserves_raw_values(self):
        q={"id":"rounded","primitive":"CHOICE","criteria":[
            {"label":"YES","description":"yes"},
            {"label":"NO","description":"no"},
            {"label":"INSUFFICIENT","description":"insufficient"}]}
        answer={"type":"choice","choice":"INSUFFICIENT","confidence":0.8,
                "probabilities":{"YES":0.01,"NO":0.01,"INSUFFICIENT":0.97}}
        values,confidence,choice=parse_answer(q,answer)
        self.assertEqual(sum(values.values()),0.99)
        self.assertEqual((confidence,choice),(0.8,"INSUFFICIENT"))
        answer["probabilities"]["INSUFFICIENT"]=0.96
        self.rejects(lambda:parse_answer(q,answer),"MALFORMED_DISTRIBUTION")
    def test_two_decimal_choice_near_tie_preserves_reported_choice(self):
        q={"id":"near_tie","primitive":"CHOICE","criteria":[
            {"label":"YES","description":"yes"},
            {"label":"NO","description":"no"},
            {"label":"INSUFFICIENT","description":"insufficient"}]}
        answer={"type":"choice","choice":"YES","confidence":0.24,
                "probabilities":{"YES":0.49,"NO":0.50,"INSUFFICIENT":0.01}}
        values,_,choice=parse_answer(q,answer)
        self.assertEqual((values["YES"],values["NO"],choice),(0.49,0.50,"YES"))
        answer["probabilities"]={"YES":0.48,"NO":0.50,"INSUFFICIENT":0.02}
        self.rejects(lambda:parse_answer(q,answer),"CHOICE_OUTCOME_MISMATCH")
    def test_live_adapter_disabled_by_default(self):
        self.rejects(lambda:TypeSafeAdapter().evaluate(self.f.catalog,self.f.pack_id,source_status=self.f.backend.statuses(),budget=self.f.budget),"LIVE_DISABLED")


class PlanAndLedgerTests(FixtureCase):
    def test_duplicate_operation_id(self):
        p=self.f.catalog.get(self.f.plan_id);p["operations"][1]["id"]=p["operations"][0]["id"]
        self.rejects(lambda:validate_plan(self.f.catalog,p),"DUPLICATE_OPERATION_ID")
    def test_identity_requires_identity_candidate(self):
        p=self.f.catalog.get(self.f.plan_id);o=p["operations"][0];o["operation"]="ADD_IDENTITY_ASSERTION";o["component_certificate_id"]=self.f.batch_id;o["risk_class"]="R4"
        self.rejects(lambda:validate_plan(self.f.catalog,p),"OPERATION_CANDIDATE_KIND")
    def test_risk_projection_consistency(self):
        c=changed_catalog(self.f.catalog,self.f.resolution_ids[0],lambda b:b.update(risk_class="R0"))
        self.rejects(lambda:validate_plan(c,c.get(self.f.plan_id)),"RISK_UNDERCLASSIFIED")
    def test_typed_retraction_requires_revision(self):
        p=self.f.catalog.get(self.f.plan_id);p["operations"]=[{"id":"r","operation":"RETRACT_ASSERTION","risk_class":"R3","assertion_id":"unknown","reason":"test"}]
        self.rejects(lambda:validate_plan(self.f.catalog,p),"SCHEMA_ERROR")
    def test_failed_check_cannot_label_plan_validated(self):
        life=Lifecycle(self.f.catalog.hash(self.f.plan_id));life.advance("RESOLVED")
        self.rejects(lambda:life.advance("PREFLIGHT_VALIDATED",receipt_hash="a"*64,checks={x:x!="GLOBAL_FEASIBILITY" for x in REQUIRED_CHECKS}),"PREFLIGHT_FAILED")
    def test_lifecycle_all_allowed_and_forbidden_transitions(self):
        for before,allowed in TRANSITIONS.items():
            for after in TRANSITIONS:
                with self.subTest(before=before,after=after):
                    life=Lifecycle("a"*64)
                    if before!="DRAFT":life.events=[{"to":before,"hash":"b"*64}]
                    fn=lambda:life.advance(after,receipt_hash="c"*64,checks={x:True for x in REQUIRED_CHECKS})
                    if after in allowed:self.assertEqual(fn()["to"],after)
                    else:self.rejects(fn,"LIFECYCLE_TRANSITION")
    def test_partial_batch_publication_rejected(self):
        p=self.f.catalog.get(self.f.plan_id);p["operations"].pop()
        # Re-derive incidental source/context lists to target the joint-selection invariant.
        self.rejects(lambda:create_plan(self.f.catalog,run_id=RUN,snapshot_id=self.f.snapshot_id,operations=p["operations"],security_scope=SCOPE,
            execution_mode="SYNTHETIC",idempotency_key="partial",policy_version=POLICY,source_status=self.f.backend.statuses()),"PARTIAL_RESOLUTION_PUBLICATION")
    def test_finalized_ledger_cannot_be_empty(self):
        b=self.f.bundle(signed=False);b["ledger"]=[];b["manifest"].update(ledger_head=None,record_events={})
        self.rejects(lambda:validate_bundle(b),"LEDGER_COVERAGE")
    def test_partial_analysis_explicitly_allows_no_ledger(self):
        b=self.f.bundle(signed=False);b["ledger"]=[];b["manifest"].update(profile="PARTIAL_ANALYSIS",ledger_head=None,record_events={})
        self.assertFalse(validate_bundle(b)["lineage_complete"])
    def test_ledger_run_mode_mismatch_rejected(self):
        b=self.f.bundle(signed=False);b["ledger"][0]["execution_mode"]="LIVE"
        self.rejects(lambda:validate_bundle(b),"MODE_MISMATCH")
    def test_ledger_covers_sources_policy_schema(self):
        b=self.f.bundle(signed=False);covered=set(b["manifest"]["record_events"])
        self.assertTrue(set(self.f.source_ids+[self.f.policy_id,self.f.schema_id])<=covered)
    def test_checkpoint_not_implicitly_trusted(self):
        self.assertFalse(validate_bundle(self.f.bundle())["checkpoint_authenticated"])
        self.assertTrue(validate_bundle(self.f.bundle(),trust=self.f.trust)["checkpoint_authenticated"])
    def test_synthetic_run_cannot_claim_published_profile(self):
        b=self.f.bundle();b["manifest"]["profile"]="FINALIZED_PUBLISHED"
        self.rejects(lambda:validate_bundle(b,trust=self.f.trust),"SYNTHETIC_PUBLICATION_FORBIDDEN")
    def test_unresolved_solver_cannot_claim_selection(self):
        batch=solve(self.f.catalog,run_id=RUN,candidate_ids=self.f.candidate_ids,observation_ids=self.f.observation_ids,
                    snapshot_id=self.f.snapshot_id,budget=self.f.budget,max_expansions=1)
        self.assertEqual(self.f.catalog.get(batch)["status"],"BUDGET_EXHAUSTED")
        self.assertEqual(self.f.catalog.get(batch)["selected_ids"],[])
        c=changed_catalog(self.f.catalog,batch,lambda b:b.update(selected_ids=[self.f.candidate_ids[0]]))
        self.rejects(lambda:verify_certificate(c,batch,self.f.snapshot_id),"SOLVER_UNRESOLVED")
    def test_joint_impact_counts_cross_component_equivalences(self):
        nodes={f"a{i}":"Person" for i in range(100)}|{f"b{i}":"Person" for i in range(100)}
        before=[[f"a{i-1}",f"a{i}"] for i in range(1,100)]+[[f"b{i-1}",f"b{i}"] for i in range(1,100)]
        result=impact(nodes,before,[["a0","b0"]],{n:[] for n in nodes})
        self.assertEqual(result["implied_equivalences"],10000)
        self.assertEqual(effective_risk("ADD_IDENTITY_ASSERTION",{"impact":result}),"R5")
