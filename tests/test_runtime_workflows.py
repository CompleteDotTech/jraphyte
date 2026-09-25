"""Operation variants, identity components, policy branches and release tooling."""
from __future__ import annotations
import contextlib
import io
import os
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from trace_gc.canonical import digest,load,write
from trace_gc.catalog import Catalog
from trace_gc.cli import main
from trace_gc.compiler import compile_pack
from trace_gc.constraints import validate_graph
from trace_gc.demo import build_fixture,fixture_response,relation,RUN,SCOPE,POLICY,POPULATION
from trace_gc.adapter import record_response
from trace_gc.errors import ContractError
from trace_gc.legacy import load_pinned_core,git_blob_hash,PINNED_CORE_BLOB
from trace_gc.plans import create_plan,add_operation,validate_plan
from trace_gc.programs import question
from trace_gc.qualification import evaluate_policy
from trace_gc.replay import replay_analysis_policy
from trace_gc.resolver import solve,project_resolutions,verify_certificate
from trace_gc.trust import authorize_plan
from trace_gc.validation import validate_bundle


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.f=build_fixture(Path(self.temp.name));self.addCleanup(self.f.close)
    def maintenance(self,operation):
        f=self.f;sid=f.backend.snapshot(f.catalog)
        return create_plan(f.catalog,run_id=RUN,snapshot_id=sid,operations=[operation],security_scope=SCOPE,
            execution_mode="SYNTHETIC",idempotency_key="maintenance:"+operation["id"],policy_version=POLICY,source_status=f.backend.statuses())
    def publish(self,plan_id):
        f=self.f;p=f.catalog.get(plan_id)
        pre=f.service.preflight(f.catalog,plan_id,reviewed=True)
        auth=authorize_plan(f.reviewer,p,f.catalog.hash(plan_id),reviewed_by="isolated-test-reviewer")
        return f.service.publish(f.catalog,plan_id,preflight=pre,authorization=auth)
    def test_retract_variant_preserves_alternate_proof(self):
        f=self.f;f.publish()
        pid=self.maintenance({"id":"retract-one","operation":"RETRACT_ASSERTION","risk_class":"R3",
                             "assertion_id":f.candidate_ids[0],"expected_revision":1,"reason":"reviewed test correction"})
        self.publish(pid)
        self.assertEqual(f.backend.view(f.catalog)["edges"][0]["assertion_ids"],[f.candidate_ids[1]])
        self.assertEqual(f.backend.state()["assertions"][f.candidate_ids[0]]["revision"],2)
        f.backend.audit()
    def test_retract_stale_assertion_revision_fails(self):
        self.f.publish()
        with self.assertRaisesRegex(ContractError,"ASSERTION_REVISION"):
            self.maintenance({"id":"retract-one","operation":"RETRACT_ASSERTION","risk_class":"R3",
                "assertion_id":self.f.candidate_ids[0],"expected_revision":8,"reason":"test"})
    def test_metadata_is_separate_from_candidate_semantics(self):
        f=self.f;before=f.catalog.hash(f.candidate_ids[0])
        pid=self.maintenance({"id":"note","operation":"ATTACH_CANDIDATE_METADATA","risk_class":"R1",
                             "candidate_id":f.candidate_ids[0],"metadata":{"review_note":"test only"}})
        self.publish(pid)
        self.assertEqual(f.catalog.hash(f.candidate_ids[0]),before)
        self.assertEqual(f.backend.state()["metadata"][f.candidate_ids[0]]["note"]["review_note"],"test only")
        self.assertEqual(f.backend.view(f.catalog)["edges"],[])
    def migration(self,operation="APPLY_SCHEMA_MIGRATION",bad=False):
        f=self.f;old=f.catalog.get(f.schema_id);new=deepcopy(old);new["version"]="reviewed-schema-v2"
        new["relations"]["annotates"]=relation("Document","Claim")
        target=f.catalog.put("schema",new)
        impact={"before_schema_hash":f.catalog.hash(f.schema_id),"target_schema_hash":f.catalog.hash(target),
                "affected_assertion_ids":[],"affected_node_ids":[]}
        if bad:impact["affected_assertion_ids"]=["invented"]
        return self.maintenance({"id":"schema-change","operation":operation,"risk_class":"R5","target_schema_id":target,
                                 "mapping":{},"impact":impact,"reason":"reviewed test-only relation addition"}),target
    def test_schema_migration_is_explicit_and_transactional(self):
        f=self.f;f.publish();pid,target=self.migration();self.publish(pid)
        self.assertEqual(f.backend.state()["schema_id"],target)
        self.assertIn("annotates",f.catalog.get(target)["relations"])
        self.assertEqual(len(f.backend.view(f.catalog)["edges"]),1);f.backend.audit()
    def test_schema_proposal_does_not_change_active_schema(self):
        pid,target=self.migration("PROPOSE_SCHEMA_MIGRATION");self.publish(pid)
        self.assertEqual(self.f.backend.state()["schema_id"],self.f.schema_id)
        self.assertTrue(self.f.backend.state()["schema_proposals"])
    def test_schema_impact_must_match(self):
        with self.assertRaisesRegex(ContractError,"SCHEMA_IMPACT"):self.migration(bad=True)
    def test_schema_migration_requires_reviewer_authority(self):
        pid,_=self.migration();f=self.f
        pre=f.service.preflight(f.catalog,pid,reviewed=True)
        auth=authorize_plan(f.reviewer,f.catalog.get(pid),f.catalog.hash(pid))
        with self.assertRaisesRegex(ContractError,"REVIEW_REQUIRED"):
            f.service.publish(f.catalog,pid,preflight=pre,authorization=auth)
    def identity_batch(self, *, cannot=False, exclusive=False):
        f=self.f;c=f.catalog;snapshot=f.snapshot_id
        if cannot:
            body=c.get(snapshot);body["assertions"]["cannot-ac"]={"assertion":{"subject":"person-a","predicate":"different_from","object":"person-c","qualifiers":{}},
                "evidence_ids":f.evidence_ids,"prerequisites":[],"active":True,"revision":1}
            snapshot=c.put("graph-snapshot",body)
        ids=[]
        for index,(a,b) in enumerate([("person-a","person-b"),("person-b","person-c")]):
            claim=c.claim(f"{a} and {b} denote the same person.")
            ids.append(c.candidate(id_=f"identity-{index}",run_id=RUN,kind="IDENTITY",assertion={"subject":a,"predicate":"same_as","object":b,"qualifiers":{}},
                claim_id=claim,evidence_ids=[f.evidence_ids[index]],mode="SYNTHETIC"))
        qs=[question(cid,id_=f"i{i}",task="IDENTITY") for i,cid in enumerate(ids)]
        pack=compile_pack(c,id_="identity-pack",run_id=RUN,candidate_ids=ids,questions=qs,snapshot_id=snapshot,security_scope=SCOPE,execution_mode="SYNTHETIC")
        obs=record_response(c,pack,fixture_response(c.get(pack)))
        batch=solve(c,run_id=RUN,candidate_ids=ids,observation_ids=obs,snapshot_id=snapshot,budget=f.budget,exclusive_groups=[ids] if exclusive else [])
        verify_certificate(c,batch,snapshot)
        return batch,ids,snapshot
    def test_joint_identity_component_publication_and_reversal(self):
        f=self.f;bid,ids,snapshot=self.identity_batch();batch=f.catalog.get(bid)
        self.assertEqual(batch["selected_ids"],ids);self.assertEqual(batch["impact"]["implied_equivalences"],3)
        resolutions=project_resolutions(f.catalog,bid)
        evals=[evaluate_policy(f.catalog,candidate_id=x,batch_id=bid,policy_version=POLICY,population=POPULATION) for x in ids]
        ops=[add_operation(f.catalog,r,e,operation_id=f"identity-op-{i}") for i,(r,e) in enumerate(zip(resolutions,evals))]
        self.assertTrue(all(o["risk_class"]=="R5" for o in ops))
        pid=create_plan(f.catalog,run_id=RUN,snapshot_id=snapshot,operations=ops,security_scope=SCOPE,execution_mode="SYNTHETIC",idempotency_key="identity-publication",policy_version=POLICY,source_status=f.backend.statuses())
        self.publish(pid)
        state=f.backend.state();roots=validate_graph(state["nodes"],state["assertions"],f.catalog.get(f.schema_id)["relations"])
        self.assertEqual(roots["person-a"],roots["person-c"])
        f.status_change(f.source_ids[0]);state=f.backend.state()
        roots=validate_graph(state["nodes"],state["assertions"],f.catalog.get(f.schema_id)["relations"])
        self.assertNotEqual(roots["person-a"],roots["person-c"]);self.assertEqual(roots["person-b"],roots["person-c"])
        f.backend.audit()
    def test_global_cannot_link_prevents_transitive_identity_contradiction(self):
        bid,ids,_=self.identity_batch(cannot=True)
        self.assertEqual(len(self.f.catalog.get(bid)["selected_ids"]),1)
    def test_exclusive_alternatives_are_joint_not_independent(self):
        bid,ids,_=self.identity_batch(exclusive=True)
        self.assertEqual(len(self.f.catalog.get(bid)["selected_ids"]),1)
    def test_policy_branch_retains_exact_observations_and_old_evaluations(self):
        f=self.f;b=f.bundle(signed=False);policy=f.catalog.get(f.policy_id)
        policy.update(version="analysis-replay-v2",mode="ANALYSIS_ONLY")
        output=replay_analysis_policy(b,policy);validate_bundle(output)
        original={r["id"]:r["hash"] for r in b["records"] if r["kind"]=="observation"}
        self.assertEqual(original,{r["id"]:r["hash"] for r in output["records"] if r["kind"]=="observation"})
        self.assertEqual(len([r for r in output["records"] if r["kind"]=="evaluation"]),4)
        self.assertEqual(output["manifest"]["policy_version"],"analysis-replay-v2")
    def test_policy_replay_cannot_mint_qualification(self):
        with self.assertRaisesRegex(ContractError,"REPLAY_MODE"):
            replay_analysis_policy(self.f.bundle(signed=False),self.f.catalog.get(self.f.policy_id))
    def test_cli_validate_reports_no_write_authority(self):
        path=Path(self.temp.name)/"input.json";write(path,self.f.bundle(signed=False))
        with contextlib.redirect_stdout(io.StringIO()) as stream:self.assertEqual(main(["validate",str(path)]),0)
        self.assertIn('"authorization_granted": false',stream.getvalue())
    def test_cli_bad_json_returns_structured_error(self):
        path=Path(self.temp.name)/"bad.json";path.write_text('{"x":1,"x":2}')
        with contextlib.redirect_stderr(io.StringIO()) as stream:self.assertEqual(main(["validate",str(path)]),1)
        self.assertIn("DUPLICATE_JSON_KEY",stream.getvalue())


class LegacyPinTests(unittest.TestCase):
    def test_nonmatching_source_is_never_executed(self):
        with tempfile.TemporaryDirectory() as d:
            file=Path(d)/"core.py";marker=Path(d)/"executed"
            file.write_text(f"from pathlib import Path\nPath({str(marker)!r}).write_text('unsafe')\n")
            with self.assertRaisesRegex(ContractError,"UPSTREAM_PIN_MISMATCH"):load_pinned_core(file)
            self.assertFalse(marker.exists())
    def test_git_blob_hash_known_empty_object(self):
        self.assertEqual(git_blob_hash(b""),"e69de29bb2d1d6434b8b29ae775ad8c2e48c5391")
    def test_cli_pin_mismatch_is_explicit(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"core.py";path.write_text("# not upstream\n")
            with contextlib.redirect_stderr(io.StringIO()) as stream:self.assertEqual(main(["check-legacy","--core",str(path)]),1)
            self.assertIn("UPSTREAM_PIN_MISMATCH",stream.getvalue())
    def test_pinned_loader_executes_verified_bytes_not_a_second_path_read(self):
        from unittest.mock import patch
        import sys
        good=b"GraphStore=Policy=Relation=object\ncandidate=evidence=bind=lambda: None\n"
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"core.py";marker=Path(d)/"executed";path.write_bytes(good)
            def checked_read(file):
                file.write_text(f"from pathlib import Path\nPath({str(marker)!r}).write_text('unsafe')\n")
                return good
            pin=git_blob_hash(good)
            with patch("trace_gc.legacy.PINNED_CORE_BLOB",pin),patch.object(Path,"read_bytes",checked_read):
                module=load_pinned_core(path)
                self.assertTrue(hasattr(module,"GraphStore"));self.assertFalse(marker.exists())
            sys.modules.pop("_trace_gc_pinned_upstream_"+pin,None)
    @unittest.skipUnless(os.environ.get("TRACE_GC_LEGACY_CORE"),"External pinned core.py not supplied; not a passed integration gate")
    def test_pinned_upstream_conformance(self):
        from trace_gc.conformance import check_legacy
        report=check_legacy(os.environ["TRACE_GC_LEGACY_CORE"])
        self.assertEqual(report["status"],"PASS");self.assertEqual(report["core_blob"],PINNED_CORE_BLOB)

if __name__=="__main__":unittest.main()
