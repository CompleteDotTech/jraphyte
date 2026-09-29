"""Authored source-first application mechanics; no real paper or model call."""
import io
import json
from pathlib import Path
import tempfile
import unittest

try:
    import fitz
    from PIL import Image, ImageDraw
except ImportError:
    fitz = None
    Image = ImageDraw = None

from trace_gc.backend import CompilerService, SQLiteReferenceBackend
from trace_gc.budget import RunBudget
from trace_gc.canonical import bytes_digest
from trace_gc.catalog import Catalog
from trace_gc.demo import limits, relation
from trace_gc.errors import ContractError
from trace_gc.paper_pilot import PaperPilot
from trace_gc.paper_pilot_application import LocalPaperPilotApplication, require_complete_native_anchor
from trace_gc.policy import create_policy
from trace_gc.retrieval.security import access_policy, grant
from trace_gc.trust import IssuerPolicy, Signer, TrustStore


@unittest.skipIf(fitz is None, "optional PyMuPDF/Pillow fixture dependencies unavailable")
class ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.run = self.root / "private-run"
        self.run.mkdir()
        cover = Image.new("RGB", (160, 80), "white")
        ImageDraw.Draw(cover).text((8, 8), "Authored image cover", fill="black")
        png = io.BytesIO()
        cover.save(png, format="PNG")
        pdf = fitz.open()
        pdf.new_page().insert_image(fitz.Rect(0, 0, 160, 80), stream=png.getvalue())
        pdf.new_page().insert_text((30, 40), "Authored native evidence on page two.")
        self.original = pdf.tobytes()
        native = pdf[1].get_text("text")
        pdf.close()
        (self.root / "source.pdf").write_bytes(self.original)
        self.catalog = Catalog()
        self.claim = self.catalog.claim("Authored native evidence on page two.")
        schema = self.catalog.put("schema", {"version": "application-test-v1",
            "relations": {"supports": relation("Document", "Claim")}})
        policy = create_policy(self.catalog, version="pilot-reviewed-v1", scope="private-test",
            population="authored-fixture", mode="REVIEWED", allowed_modes=["LIVE"])
        self.review = Signer.ephemeral("source-reviewer")
        self.admit = Signer.ephemeral("source-admitter")
        self.validator = Signer.ephemeral("preflight-validator")
        self.trust = TrustStore()
        for signer, principal, purposes, operations, can_review in (
            (self.review, "reviewer", {"SOURCE_STATUS"}, {"PAPER_SOURCE_REVIEW"}, True),
            (self.admit, "admitter", {"SOURCE_STATUS"}, {"SOURCE_ADMIT"}, False),
            (self.validator, "validator", {"PREFLIGHT"}, set(), False)):
            self.trust.enroll(signer.issuer, IssuerPolicy(signer.public_key(), principal,
                frozenset(purposes), frozenset(operations), frozenset({"private-test"}),
                frozenset({"LIVE"}), can_review=can_review))
        model = {"provider": "AUTHORED_NO_MODEL", "model_id": "jev-1.13.0",
                 "model_revision": "authored-v1", "tokenizer_id": "authored-counter-v1"}
        self.protocol = {"version": "issue23-real-paper-source-first-protocol-v3",
            "status": "COHORT_AND_SOURCE_REFERENCE_FROZEN_PENDING_APPLICATION_AUTHORITY_AND_FINAL_PROFILE",
            "numeric_gates": {key: {"fixture_target": 1} for key in
                              ("extraction", "graph", "retrieval", "answers", "recovery")},
            "questions": [{"id": "q1", "text": "What does page two say?"}],
            "documents": {"paper": {"source_map_relative": "source.pdf", "source_sha256": bytes_digest(self.original)}},
            "evidence_anchors": {
                "cover": {"document": "paper", "physical_page": 1,
                          "representation": "rendered_image_full_page_v1"},
                "native": {"document": "paper", "physical_page": 2,
                           "representation": "pymupdf_native_text_v1", "start_codepoint": 0,
                           "end_codepoint": len(native.strip()), "quote": native.strip(),
                           "native_page_sha256": bytes_digest(native.encode())}}}
        raw = (json.dumps(self.protocol, sort_keys=True) + "\n").encode()
        self.protocol_path = self.root / "protocol.json"
        self.protocol_path.write_bytes(raw)
        self.protocol_sha = bytes_digest(raw)
        self.config = {"run_id": "authored-live-app", "security_scope": "private-test", "execution_mode": "LIVE",
            "documents": [{"source_id": "paper", "version": "v1", "document_sha256": bytes_digest(self.original),
                           "physical_pages": [1, 2]}], "questions": ["What does page two say?"],
            "cohort_manifest_sha256": self.protocol_sha,
            "semantic_model": model, "answer_model": {**model, "model_id": "authored-answer"}}
        self.nodes = {"paper": "Document", self.claim: "Claim"}
        self.grants = {"node:" + ref: grant("private-test", "pilot", users=["reviewer"]) for ref in self.nodes}
        self.acl = lambda: access_policy(tenant="private-test", workspace="pilot", user="reviewer",
                                         grants=self.grants, revision="acl-v1")
        self.backend = SQLiteReferenceBackend(self.run / "graph.sqlite3", catalog=self.catalog,
                                              schema_id=schema, nodes=self.nodes, sandbox=False)
        self.budget = RunBudget(self.run / "budget.sqlite3", self.config["run_id"], limits(model_calls=1))
        self.service = CompilerService(self.backend, self.trust, self.validator,
            policy_version="pilot-reviewed-v1", population="authored-fixture", security_scope="private-test",
            policy_hash=self.catalog.hash(policy), publication_mode="REVIEWED")
        self.pilot = PaperPilot(self.run, config=self.config, catalog=self.catalog, backend=self.backend,
                                service=self.service, budget=self.budget, current_access=self.acl,
                                token_counter=lambda value: len(json.dumps(value)))
        self.app = LocalPaperPilotApplication(pilot=self.pilot, protocol_path=self.protocol_path,
            protocol_sha256=self.protocol_sha, source_root=self.root, reviewer=self.review,
            admitter=self.admit, validator=self.validator, trust=self.trust, access=self.acl)

    def tearDown(self):
        self.app.close(); self.pilot.close(); self.backend.close(); self.budget.close(); self.tmp.cleanup()

    def test_prepares_native_and_holds_image_without_model_or_graph_write(self):
        result = self.app.prepare_sources()
        self.assertEqual(result["state"], "WAIT_SOURCE_REVIEW")
        self.assertEqual(result["image_route_held"], ["cover"])
        self.assertEqual(result["model_calls"], 0)
        self.assertEqual(result["graph_version"], 0)
        self.assertEqual(self.budget.snapshot()["used"]["model_calls"], 0)
        self.assertEqual(self.app.prepare_sources()["prepared"], result["prepared"])

    def test_changed_source_blocks_before_preflight(self):
        (self.root / "source.pdf").write_bytes(self.original + b"changed")
        with self.assertRaises(ContractError):
            LocalPaperPilotApplication(pilot=self.pilot, protocol_path=self.protocol_path,
                protocol_sha256=self.protocol_sha, source_root=self.root, reviewer=self.review,
                admitter=self.admit, validator=self.validator, trust=self.trust, access=self.acl)

    def test_changed_source_after_open_blocks_preparation(self):
        (self.root / "source.pdf").write_bytes(self.original + b"changed")
        with self.assertRaises(ContractError):
            self.app.prepare_sources()
        self.assertEqual(self.pilot.status()["requests"], [])

    def test_broad_review_role_rejected(self):
        policy = self.trust._issuers[self.review.issuer]
        self.trust._issuers[self.review.issuer] = IssuerPolicy(policy.public_key, policy.principal,
            policy.purposes, frozenset({"PAPER_SOURCE_REVIEW", "ADD_ASSERTION"}), policy.scopes,
            policy.modes, can_review=True)
        with self.assertRaises(ContractError):
            LocalPaperPilotApplication(pilot=self.pilot, protocol_path=self.protocol_path,
                protocol_sha256=self.protocol_sha, source_root=self.root, reviewer=self.review,
                admitter=self.admit, validator=self.validator, trust=self.trust, access=self.acl)

    def test_broad_recipient_grant_rejected(self):
        self.grants["node:paper"] = grant("private-test", "pilot")
        with self.assertRaises(ContractError):
            LocalPaperPilotApplication(pilot=self.pilot, protocol_path=self.protocol_path,
                protocol_sha256=self.protocol_sha, source_root=self.root, reviewer=self.review,
                admitter=self.admit, validator=self.validator, trust=self.trust, access=self.acl)

    def test_broad_grant_after_open_blocks_preparation(self):
        self.grants["node:paper"] = grant("private-test", "pilot")
        with self.assertRaises(ContractError):
            self.app.prepare_sources()
        self.assertEqual(self.pilot.status()["requests"], [])

    def test_mid_word_and_mid_sentence_source_spans_rejected(self):
        native = "Complete source sentence. Next sentence.\n"
        require_complete_native_anchor(native, 0, len("Complete source sentence."),
                                       "Complete source sentence.")
        with self.assertRaises(ContractError):
            require_complete_native_anchor(native, 0, len("Complete source sent"),
                                           "Complete source sent")
        with self.assertRaises(ContractError):
            require_complete_native_anchor(native, 0, len("Complete source sentence. Next"),
                                           "Complete source sentence. Next")
        mid_start = native.index("sentence.")
        with self.assertRaises(ContractError):
            require_complete_native_anchor(native, mid_start, len("Complete source sentence."),
                                           "sentence.")
