"""Authored synthetic service tests; these are not real-paper qualifications."""
import json
from contextlib import nullcontext
from pathlib import Path
import tempfile
import unittest

try:
    import fitz
except ImportError:
    fitz = None
from trace_gc.backend import SQLiteReferenceBackend
from trace_gc.canonical import digest
from trace_gc.trust import attest_observation, authorize_plan
from trace_gc.paper_pilot_lifecycle import (
    _bytes, _sha, _write_once, parent_proof, prepare_successor,
    reconcile_status, status_change_once,
)
from trace_gc.trust import IssuerPolicy, Signer, TrustStore


@unittest.skipIf(fitz is None, "optional PyMuPDF fixture dependency unavailable")
class LifecycleTests(unittest.TestCase):
    def setUp(self):
        from tests import test_paper_pilot as pilot_tests
        self.fixture = pilot_tests.PaperPilotTests(
            methodName="test_complete_synthetic_mechanics_reopen_at_every_external_pause")
        self.fixture.setUp()
        self.out = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.fixture.tearDown()
        self.out.cleanup()

    def _inputs(self):
        fixture = self.fixture
        _, reviewed = fixture.published()
        response = fixture.pilot.requests["response"]
        raw = fixture.pilot._read_blob(response["args"]["response_blob"])
        assertions = set(fixture.backend.state()["assertions"])
        sources = {reviewed["source_id"]}
        imports = {"response": raw}
        return assertions, sources, imports, reviewed

    def _qualify(self, assertions, sources, imports):
        fixture = self.fixture
        proof = parent_proof(fixture.pilot, assertion_ids=assertions,
            source_ids=sources, completed_request_ids={"publish"},
            imported_outputs=imports, historical_execution_contexts={})
        evaluator_path = Path(self.out.name) / "authored-fixture-evaluator.py"
        evaluator_path.write_bytes(b"# Authored synthetic evaluator identity fixture.\n")
        evaluator_sha = _sha(evaluator_path.read_bytes())
        gates = {name: "PASS" for name in ("extraction", "graph", "retrieval", "answers")}
        report = {"version": "paper-pilot-parent-qualification-v1",
            "phase": "PARENT_READY_FOR_POSTPUBLICATION_SCENARIOS",
            "status": "PASS", "recovery_status": "NOT_RUN", "gates": gates,
            "evaluator_version": "synthetic-only-v1",
            "evaluator_code_sha256": evaluator_sha,
            "parent_run_id": proof["run_id"],
            "config_sha256": proof["config_sha256"],
            "checkpoint_head": proof["checkpoint_head"],
            "graph_journal_head": proof["graph_journal_head"],
            "imported_output_sha256": proof["imported_output_sha256"]}
        report_path = Path(self.out.name) / "parent-ready-report.json"
        report_path.write_bytes(_bytes(report))
        report_sha = _sha(report_path.read_bytes())
        decision = {"kind": "PARENT_QUALIFICATION", "approved": True,
            "phase": "PARENT_READY_FOR_POSTPUBLICATION_SCENARIOS",
            "report_sha256": report_sha,
            "evaluator_code_sha256": evaluator_sha,
            "security_scope": fixture.config["security_scope"],
            "execution_mode": fixture.config["execution_mode"],
            "reviewer": "authored-fixture-reviewer", "evaluator_version": "synthetic-only-v1",
            "gates": gates,
            "parent_run_id": proof["run_id"],
            "config_sha256": proof["config_sha256"],
            "checkpoint_head": proof["checkpoint_head"],
            "graph_journal_head": proof["graph_journal_head"],
            "imported_output_sha256": proof["imported_output_sha256"],
            "historical_execution_context_sha256": {}, "artifact_sha256": {}}
        signer = Signer.ephemeral("authored-qualification-reviewer")
        trust = TrustStore()
        trust.enroll(signer.issuer, IssuerPolicy(signer.public_key(),
            "authored-fixture-reviewer", frozenset({"AUTHORIZATION"}),
            frozenset({"PARENT_QUALIFICATION"}), frozenset({"pilot-test"}),
            frozenset({"SYNTHETIC"}), can_review=True))
        path = Path(self.out.name) / "qualification.json"
        path.write_bytes(_bytes(signer.issue("AUTHORIZATION", decision)))
        return (path, _sha(path.read_bytes()), trust, report_path, report_sha,
                signer, evaluator_path, evaluator_sha)

    def test_fork_and_signed_status_replay(self):
        fixture = self.fixture
        assertions, sources, imports, reviewed = self._inputs()
        (qualification_path, qualification_hash, qualification_trust,
         report_path, report_hash, _, evaluator_path, evaluator_hash) = self._qualify(assertions, sources, imports)
        config = {**fixture.config, "run_id": "authored-successor",
                  "cohort_manifest_sha256": "2" * 64,
                  "documents": [{**fixture.config["documents"][0], "version": "v2",
                                 "document_sha256": "3" * 64}]}
        destination = Path(self.out.name) / "fork"
        manifest = prepare_successor(fixture.pilot, destination, successor_config=config,
            assertion_ids=assertions, source_ids=sources,
            completed_request_ids={"publish"}, changed_documents={"authored-paper"},
            imported_outputs=imports, historical_execution_contexts={},
            qualification_receipt_path=qualification_path,
            qualification_receipt_sha256=qualification_hash,
            qualification_trust=qualification_trust,
            qualification_report_path=report_path,
            qualification_report_sha256=report_hash,
            qualification_evaluator_path=evaluator_path,
            qualification_evaluator_sha256=evaluator_hash,
            required_qualification_gates=frozenset({"extraction", "graph", "retrieval", "answers"}),
            application_artifacts={}, application_databases={},
            application_quiescence=nullcontext())
        self.assertEqual(manifest["parent"]["graph_version"], 2)
        self.assertFalse((destination / "successor/checkpoint.sqlite3").exists())
        self.assertFalse((destination / "successor/budget.sqlite3").exists())
        self.assertEqual((destination / "parent_archive/imported_responses/response.raw").read_bytes(), imports["response"])
        backend = SQLiteReferenceBackend(destination / "successor/graph.sqlite3",
            catalog=fixture.catalog, schema_id=fixture.schema, nodes=fixture.nodes, sandbox=True)
        try:
            source_id = reviewed["source_id"]
            action = {"action": "STATUS_CHANGE", "source_id": source_id,
                      "source_hash": fixture.catalog.hash(source_id), "active": False,
                      "permission": "DENIED", "expected_epoch": 0,
                      "expected_version": 2, "security_scope": "pilot-test",
                      "reason": "authored synthetic withdrawal", "tombstone": False}
            authorization = fixture.signer.issue("SOURCE_STATUS", action)
            intent = destination / "status.intent.json"
            first = status_change_once(backend, fixture.catalog, fixture.trust,
                source_id=source_id, active=False, permission="DENIED",
                expected_epoch=0, expected_version=2, key="authored-status-once",
                reason=action["reason"], authorization=authorization, intent_path=intent)
            self.assertEqual(backend.state()["graph_version"], 3)
            self.assertEqual(reconcile_status(backend, intent_path=intent,
                                              authorization=authorization)["receipt"], first["receipt"])
            second = status_change_once(backend, fixture.catalog, fixture.trust,
                source_id=source_id, active=False, permission="DENIED",
                expected_epoch=0, expected_version=2, key="authored-status-once",
                reason=action["reason"], authorization=authorization, intent_path=intent)
            self.assertTrue(second["replayed"])
            self.assertEqual(backend.state()["graph_version"], 3)
            self.assertEqual(fixture.backend.state()["graph_version"], 2)
        finally:
            backend.close()

    def test_tampered_response_and_parent_path_rejected_before_fork(self):
        fixture = self.fixture
        assertions, sources, imports, _ = self._inputs()
        (qualification_path, qualification_hash, qualification_trust,
         report_path, report_hash, signer, evaluator_path, evaluator_hash) = self._qualify(assertions, sources, imports)
        with self.assertRaises(Exception):
            parent_proof(fixture.pilot, assertion_ids=assertions, source_ids=sources,
                completed_request_ids={"publish"}, imported_outputs={"response": b"tampered"},
                historical_execution_contexts={})
        config = {**fixture.config, "run_id": "authored-successor",
                  "cohort_manifest_sha256": "2" * 64,
                  "documents": [{**fixture.config["documents"][0], "version": "v2",
                                 "document_sha256": "3" * 64}]}
        forbidden = fixture.root / "fork"
        with self.assertRaises(Exception):
            prepare_successor(fixture.pilot, forbidden, successor_config=config,
                assertion_ids=assertions, source_ids=sources,
                completed_request_ids={"publish"}, changed_documents={"authored-paper"},
                imported_outputs=imports, historical_execution_contexts={},
                qualification_receipt_path=qualification_path,
                qualification_receipt_sha256=qualification_hash,
                qualification_trust=qualification_trust,
                qualification_report_path=report_path,
                qualification_report_sha256=report_hash,
                qualification_evaluator_path=evaluator_path,
                qualification_evaluator_sha256=evaluator_hash,
                required_qualification_gates=frozenset({"extraction", "graph", "retrieval", "answers"}),
                application_artifacts={}, application_databases={},
                application_quiescence=nullcontext())
        self.assertFalse(forbidden.exists())
        malformed = {**config, "documents": [{**config["documents"][0],
                      "document_sha256": "X" * 64}]}
        external = Path(self.out.name) / "invalid-hash-fork"
        with self.assertRaises(Exception):
            prepare_successor(fixture.pilot, external, successor_config=malformed,
                assertion_ids=assertions, source_ids=sources,
                completed_request_ids={"publish"}, changed_documents={"authored-paper"},
                imported_outputs=imports, historical_execution_contexts={},
                qualification_receipt_path=qualification_path,
                qualification_receipt_sha256=qualification_hash,
                qualification_trust=qualification_trust,
                qualification_report_path=report_path,
                qualification_report_sha256=report_hash,
                qualification_evaluator_path=evaluator_path,
                qualification_evaluator_sha256=evaluator_hash,
                required_qualification_gates=frozenset({"extraction", "graph", "retrieval", "answers"}),
                application_artifacts={}, application_databases={},
                application_quiescence=nullcontext())
        self.assertFalse(external.exists())
        partial_decision = json.loads(qualification_path.read_text())["payload"]
        partial_decision["gates"] = {"extraction": "PASS"}
        partial_receipt = Path(self.out.name) / "partial-signed-review.json"
        partial_receipt.write_bytes(_bytes(signer.issue("AUTHORIZATION", partial_decision)))
        partial_target = Path(self.out.name) / "partial-gates-fork"
        shared = dict(successor_config=config, assertion_ids=assertions,
            source_ids=sources, completed_request_ids={"publish"},
            changed_documents={"authored-paper"}, imported_outputs=imports,
            historical_execution_contexts={}, qualification_trust=qualification_trust,
            qualification_report_path=report_path,
            qualification_report_sha256=report_hash,
            qualification_evaluator_path=evaluator_path,
            qualification_evaluator_sha256=evaluator_hash,
            required_qualification_gates=frozenset({"extraction", "graph", "retrieval", "answers"}),
            application_artifacts={}, application_databases={},
            application_quiescence=nullcontext())
        with self.assertRaises(Exception):
            prepare_successor(fixture.pilot, partial_target,
                qualification_receipt_path=partial_receipt,
                qualification_receipt_sha256=_sha(partial_receipt.read_bytes()), **shared)
        self.assertFalse(partial_target.exists())
        wrong_report_target = Path(self.out.name) / "wrong-report-fork"
        with self.assertRaises(Exception):
            prepare_successor(fixture.pilot, wrong_report_target,
                qualification_receipt_path=qualification_path,
                qualification_receipt_sha256=qualification_hash,
                **{**shared, "qualification_report_sha256": "0" * 64})
        self.assertFalse(wrong_report_target.exists())
        wrong_version = dict(json.loads(qualification_path.read_text())["payload"])
        wrong_version["evaluator_version"] = "unreviewed-evaluator-v9"
        wrong_version_receipt = Path(self.out.name) / "wrong-evaluator-signed.json"
        wrong_version_receipt.write_bytes(_bytes(signer.issue("AUTHORIZATION", wrong_version)))
        wrong_version_target = Path(self.out.name) / "wrong-evaluator-fork"
        with self.assertRaises(Exception):
            prepare_successor(fixture.pilot, wrong_version_target,
                qualification_receipt_path=wrong_version_receipt,
                qualification_receipt_sha256=_sha(wrong_version_receipt.read_bytes()), **shared)
        self.assertFalse(wrong_version_target.exists())
        # The same Ed25519 key under a new issuer name is still parent authority.
        alias = Signer("alias-of-parent-action-key", fixture.signer._key)
        alias_trust = TrustStore()
        alias_trust.enroll(alias.issuer, IssuerPolicy(alias.public_key(),
            "apparent-qualifier", frozenset({"AUTHORIZATION"}),
            frozenset({"PARENT_QUALIFICATION"}), frozenset({"pilot-test"}),
            frozenset({"SYNTHETIC"}), can_review=True))
        alias_receipt = Path(self.out.name) / "same-key-alias-signed.json"
        alias_receipt.write_bytes(_bytes(alias.issue("AUTHORIZATION",
            json.loads(qualification_path.read_text())["payload"])))
        alias_target = Path(self.out.name) / "same-key-alias-fork"
        with self.assertRaises(Exception):
            prepare_successor(fixture.pilot, alias_target,
                qualification_receipt_path=alias_receipt,
                qualification_receipt_sha256=_sha(alias_receipt.read_bytes()),
                **{**shared, "qualification_trust": alias_trust})
        self.assertFalse(alias_target.exists())

    def test_after_commit_lost_result_reconciles_without_retry(self):
        fixture = self.fixture
        reviewed = fixture.admit()
        source_id = reviewed["source_id"]
        action = {"action": "STATUS_CHANGE", "source_id": source_id,
                  "source_hash": fixture.catalog.hash(source_id), "active": False,
                  "permission": "DENIED", "expected_epoch": 0,
                  "expected_version": 1, "security_scope": "pilot-test",
                  "reason": "authored interrupted status", "tombstone": False}
        authorization = fixture.signer.issue("SOURCE_STATUS", action)
        intent = Path(self.out.name) / "lost.intent.json"
        _write_once(intent, _bytes({"version": "paper-pilot-status-intent-v1",
            "key": "authored-lost-result", "action": action,
            "authorization_sha256": digest(authorization),
            "issued_at": authorization["issued_at"], "at": None}))
        fixture.backend.change_source_status(fixture.catalog, source_id,
            active=False, permission="DENIED", expected_epoch=0,
            expected_version=1, key="authored-lost-result", reason=action["reason"],
            authorization=authorization, trust=fixture.trust)
        # Simulate a controller dying after commit and before writing its receipt.
        self.assertFalse(intent.with_name("lost.intent.receipt.json").exists())
        recovered = reconcile_status(fixture.backend, intent_path=intent,
                                     authorization=authorization)
        self.assertTrue(recovered["replayed"])
        self.assertEqual(fixture.backend.state()["graph_version"], 2)
        self.assertTrue(intent.with_name("lost.intent.receipt.json").exists())

    def test_historical_local_execution_uses_original_graph_one_context(self):
        from tests.test_local_semantic_pilot import LocalSemanticPilotTests
        local = LocalSemanticPilotTests(
            methodName="test_resume_local_profile_through_core_solver_and_explicit_reviewed_publish")
        local.setUp()
        try:
            compiled, reviewed = local.compiled()
            original_context = local.pilot.semantic_execution_context("compile")
            raw, execution, receipt = local.exchange(compiled)
            observed = local.pilot.record_semantic_response("response", compile_id="compile",
                response=raw, local_execution=execution, execution_receipt=receipt)
            attestations = {ref: attest_observation(local.signer, local.catalog.record(ref))
                            for ref in observed["observation_ids"]}
            resolved = local.pilot.resolve_plan("resolve", response_id="response",
                                                attestations=attestations)
            local.pilot.preflight_plan("preflight", resolve_id="resolve")
            authorization = authorize_plan(local.signer,
                local.catalog.get(resolved["plan_id"]), local.catalog.hash(resolved["plan_id"]),
                reviewed_by="authored-test-reviewer")
            local.pilot.publish_plan("publish", preflight_id="preflight",
                                     authorization=authorization)
            self.assertEqual(local.backend.state()["graph_version"], 2)
            args = dict(assertion_ids=set(local.backend.state()["assertions"]),
                        source_ids={reviewed["source_id"]},
                        completed_request_ids={"publish"},
                        imported_outputs={"response": raw},
                        historical_execution_contexts={"response": original_context})
            proof = parent_proof(local.pilot, **args)
            self.assertEqual(proof["historical_execution_context_sha256"]["response"],
                             digest(original_context))
            changed_context = dict(original_context)
            changed_context["graph_version"] = 2
            with self.assertRaises(Exception):
                parent_proof(local.pilot, **{**args,
                    "historical_execution_contexts": {"response": changed_context}})
        finally:
            local.tearDown()
