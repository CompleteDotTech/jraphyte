"""Authored image-only page exercises signed source preparation without a model."""
import json
from pathlib import Path
import tempfile
import unittest

try:
    import fitz
    import PIL
    AVAILABLE = True
except ImportError:
    AVAILABLE = False

from tools.image_evidence_fixtures import TEXT, synthetic_pdf
from trace_gc.backend import CompilerService, SQLiteReferenceBackend
from trace_gc.budget import RunBudget
from trace_gc.canonical import bytes_digest
from trace_gc.catalog import Catalog
from trace_gc.compiler import now
from trace_gc.demo import limits, relation
from trace_gc.errors import ContractError
from trace_gc.paper_pilot import PaperPilot
from trace_gc.pdf_image_evidence import CHECKS, render_source
from trace_gc.policy import create_policy
from trace_gc.retrieval.security import access_policy, grant
from trace_gc.trust import IssuerPolicy, Signer, TrustStore


@unittest.skipUnless(AVAILABLE, "PyMuPDF and Pillow required")
class PilotImageRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.pdf = synthetic_pdf()
        self.corrupt_pdf = synthetic_pdf(corrupt=True)
        self.other_pdf = synthetic_pdf(repeated=True)
        self.catalog = Catalog()
        self.claim = self.catalog.claim(TEXT)
        self.schema = self.catalog.put("schema", {"version": "image-pilot-test-v1",
            "relations": {"supports": relation("Document", "Claim")}})
        self.policy = create_policy(self.catalog, version="image-pilot-policy-v1", scope="image-test",
            population="authored-fixture", mode="REVIEWED", allowed_modes=["SYNTHETIC"])
        self.reviewer = Signer.ephemeral("image-reviewer")
        self.admitter = Signer.ephemeral("image-admitter")
        self.validator = Signer.ephemeral("image-validator")
        self.trust = TrustStore()
        for signer, principal, purpose, operations, can_review in (
            (self.reviewer, "authored-reviewer", "SOURCE_STATUS", {"PAPER_SOURCE_REVIEW"}, True),
            (self.admitter, "authored-admitter", "SOURCE_STATUS",
             {"SOURCE_ADMIT", "SOURCE_WITHDRAW", "SOURCE_PERMISSION"}, False),
            (self.validator, "authored-validator", "PREFLIGHT", set(), False)):
            self.trust.enroll(signer.issuer, IssuerPolicy(signer.public_key(), principal,
                frozenset({purpose}), frozenset(operations), frozenset({"image-test"}),
                frozenset({"SYNTHETIC"}), can_review=can_review))
        model = {"provider": "AUTHORED_TEST", "model_id": "none", "model_revision": "fixture-v1",
                 "tokenizer_id": "utf8-v1"}
        self.config = {"run_id": "image-pilot", "security_scope": "image-test", "execution_mode": "SYNTHETIC",
            "documents": [{"source_id": "authored-image", "version": "v1", "document_sha256": bytes_digest(self.pdf),
                           "physical_pages": [1]},
                          {"source_id": "authored-corrupt", "version": "v1",
                           "document_sha256": bytes_digest(self.corrupt_pdf), "physical_pages": [1]}],
            "questions": ["What is visible?"],
            "cohort_manifest_sha256": "1" * 64, "semantic_model": model, "answer_model": model}
        self.nodes = {"authored-image": "Document", "authored-corrupt": "Document", self.claim: "Claim"}
        self.grants = {"node:" + ref: grant("image-test", "private", users=["test-user"]) for ref in self.nodes}
        self.open()

    def open(self):
        self.backend = SQLiteReferenceBackend(self.root / "graph.sqlite3", catalog=self.catalog,
            schema_id=self.schema, nodes=self.nodes, sandbox=True)
        self.budget = RunBudget(self.root / "budget.sqlite3", "image-pilot", limits(review_actions=4))
        self.service = CompilerService(self.backend, self.trust, self.validator,
            policy_version="image-pilot-policy-v1", population="authored-fixture",
            security_scope="image-test", policy_hash=self.catalog.hash(self.policy), publication_mode="REVIEWED")
        self.pilot = PaperPilot(self.root, config=self.config, catalog=self.catalog, backend=self.backend,
            service=self.service, budget=self.budget,
            current_access=lambda: access_policy(tenant="image-test", workspace="private", user="test-user",
                                                  grants=self.grants), token_counter=lambda value: len(json.dumps(value)))

    def reopen(self):
        self.pilot.close(); self.backend.close(); self.budget.close()
        self.catalog = Catalog([self.catalog.record(ref) for ref in (self.schema, self.policy, self.claim)])
        self.open()

    def tearDown(self):
        self.pilot.close(); self.backend.close(); self.budget.close(); self.temp.cleanup()

    def prepare(self):
        metadata, _, _ = render_source(self.pdf, dpi=144, crop=[0, 0, 600, 240])
        self.assertEqual(metadata["native_observation"]["state"], "absent")
        return self.pilot.prepare_image_page("image-prepare", pdf_bytes=self.pdf,
            source_id="authored-image", version="v1", physical_page=1,
            crop_bbox=[0, 0, 600, 240], transcription=TEXT,
            producer="authored-manual-fixture", raw_output=TEXT.encode())

    def review(self):
        self.prepare()
        at = now()
        payload = self.pilot.image_review_payload("image-prepare", reviewer="authored-reviewer",
            reviewer_kind="assistant", reviewed_at=at, checks={key: True for key in CHECKS})
        receipt = self.reviewer.issue("SOURCE_STATUS", payload, issued_at=at)
        return self.pilot.accept_image_review("image-review", prepared_id="image-prepare", receipt=receipt)

    def test_signed_image_review_admission_and_reopen(self):
        reviewed = self.review()
        material = self.pilot.image_review_material("image-prepare")
        self.assertEqual(material["candidate"]["crop"]["bbox"], [0, 0, 600, 240])
        self.assertNotIn("start", material["candidate"])
        self.assertEqual(self.backend.state()["graph_version"], 0)
        self.grants["source:" + reviewed["source_id"]] = grant("image-test", "private", users=["test-user"])
        authorization = self.admitter.issue("SOURCE_STATUS",
            self.pilot.admission_payload(["image-review"], expected_version=0))
        self.pilot.admit_sources("image-admit", review_ids=["image-review"], expected_version=0,
                                 authorization=authorization)
        self.reopen()
        self.pilot.admit_sources("image-admit", review_ids=["image-review"], expected_version=0,
                                 authorization=authorization)
        self.assertEqual(self.backend.state()["graph_version"], 1)
        self.assertEqual(len(list(self.backend.load_catalog().all("assertion"))), 0)
        self.pilot._source(reviewed["source_id"])

    def test_wrong_page_crop_producer_receipt_and_retry_fail(self):
        with self.assertRaises(ContractError):
            self.pilot.prepare_image_page("bad-page", pdf_bytes=self.pdf, source_id="authored-image",
                version="v1", physical_page=2, crop_bbox=[0, 0, 600, 240],
                transcription=TEXT, producer="authored", raw_output=TEXT.encode())
        with self.assertRaises(ContractError):
            self.pilot.prepare_image_page("bad-pdf", pdf_bytes=self.other_pdf, source_id="authored-image",
                version="v1", physical_page=1, crop_bbox=[0, 0, 600, 240],
                transcription=TEXT, producer="authored", raw_output=TEXT.encode())
        self.prepare()
        with self.assertRaises(ContractError):
            self.pilot.prepare_image_page("image-prepare", pdf_bytes=self.pdf, source_id="authored-image",
                version="v1", physical_page=1, crop_bbox=[1, 0, 600, 240],
                transcription=TEXT, producer="authored-manual-fixture", raw_output=TEXT.encode())
        candidate = self.pilot.image_review_material("image-prepare")["candidate"]
        self.assertEqual(candidate["ocr"]["revision"], "manual-v1")
        live = self.pilot.requests["image-prepare"]["result"]["candidate"]
        live["ocr"]["revision"] = "wrong-revision"
        with self.assertRaises(ContractError):
            self.pilot.image_review_material("image-prepare")
        live["ocr"]["revision"] = "manual-v1"
        live["crop"]["bbox"][0] = 1
        with self.assertRaises(ContractError):
            self.pilot.image_review_material("image-prepare")
        live["crop"]["bbox"][0] = 0
        bad = self.reviewer.issue("SOURCE_STATUS", self.pilot.image_review_payload("image-prepare",
            reviewer="authored-reviewer", reviewer_kind="assistant", reviewed_at=now(),
            checks={key: True for key in CHECKS}))
        bad["payload"]["candidate_sha256"] = "0" * 64
        with self.assertRaises(ContractError):
            self.pilot.accept_image_review("bad-review", prepared_id="image-prepare", receipt=bad)
        producer_receipt = self.admitter.issue("SOURCE_STATUS", self.pilot.image_review_payload("image-prepare",
            reviewer="authored-admitter", reviewer_kind="assistant", reviewed_at=now(),
            checks={key: True for key in CHECKS}))
        with self.assertRaises(ContractError):
            self.pilot.accept_image_review("wrong-role", prepared_id="image-prepare", receipt=producer_receipt)

    def test_second_review_of_same_physical_page_cannot_be_admitted_together(self):
        first = self.review()
        self.pilot.prepare_image_page("other-prepare", pdf_bytes=self.pdf, source_id="authored-image",
            version="v1", physical_page=1, crop_bbox=[0, 0, 600, 240],
            transcription="Abstract\n" + TEXT, producer="authored-manual-fixture",
            raw_output=("Abstract\n" + TEXT).encode())
        at = now()
        payload = self.pilot.image_review_payload("other-prepare", reviewer="authored-reviewer",
            reviewer_kind="assistant", reviewed_at=at, checks={key: True for key in CHECKS})
        second = self.pilot.accept_image_review("other-review", prepared_id="other-prepare",
            receipt=self.reviewer.issue("SOURCE_STATUS", payload, issued_at=at))
        self.assertNotEqual(first["source_id"], second["source_id"])
        with self.assertRaises(ContractError):
            self.pilot.admission_payload(["image-review", "other-review"], expected_version=0)
        authorization = self.admitter.issue("SOURCE_STATUS",
            self.pilot.admission_payload(["image-review"], expected_version=0))
        self.pilot.admit_sources("first-admit", review_ids=["image-review"],
                                 expected_version=0, authorization=authorization)
        competing = self.admitter.issue("SOURCE_STATUS",
            self.pilot.admission_payload(["other-review"], expected_version=1))
        with self.assertRaises(ContractError):
            self.pilot.admit_sources("competing-admit", review_ids=["other-review"],
                                     expected_version=1, authorization=competing)
        self.assertEqual(self.backend.state()["graph_version"], 1)
        action = {"action": "STATUS_CHANGE", "source_id": first["source_id"],
                  "source_hash": self.catalog.hash(first["source_id"]), "active": True,
                  "permission": "DENIED", "expected_epoch": 0, "expected_version": 1,
                  "security_scope": "image-test", "reason": "temporary permission hold",
                  "tombstone": False}
        self.backend.change_source_status(self.catalog, first["source_id"], active=True,
            permission="DENIED", expected_epoch=0, expected_version=1, key="permission-hold",
            reason="temporary permission hold", trust=self.trust,
            authorization=self.admitter.issue("SOURCE_STATUS", action))
        competing_after_deny = self.admitter.issue("SOURCE_STATUS",
            self.pilot.admission_payload(["other-review"], expected_version=2))
        with self.assertRaises(ContractError):
            self.pilot.admit_sources("competing-after-deny", review_ids=["other-review"],
                                     expected_version=2, authorization=competing_after_deny)
        self.assertEqual(self.backend.state()["graph_version"], 2)

    def test_corrupt_native_requires_explicit_defect_and_stays_separate(self):
        with self.assertRaises(ContractError):
            self.pilot.prepare_image_page("invalid-corrupt", pdf_bytes=self.corrupt_pdf,
                source_id="authored-corrupt", version="v1", physical_page=1,
                crop_bbox=[0, 0, 600, 240], transcription=TEXT,
                producer="authored-manual-fixture", raw_output=TEXT.encode())
        with self.assertRaises(ContractError):
            self.pilot.prepare_image_page("unnamed-defect", pdf_bytes=self.corrupt_pdf,
                source_id="authored-corrupt", version="v1", physical_page=1,
                crop_bbox=[0, 0, 600, 240], transcription=TEXT,
                producer="authored-manual-fixture", raw_output=TEXT.encode(),
                fallback_reason="native_corrupt")
        result = self.pilot.prepare_image_page("corrupt-image", pdf_bytes=self.corrupt_pdf,
            source_id="authored-corrupt", version="v1", physical_page=1,
            crop_bbox=[0, 0, 600, 240], transcription=TEXT,
            producer="authored-manual-fixture", raw_output=TEXT.encode(),
            fallback_reason="native_corrupt", native_defect_note="hidden text layer maps to X")
        self.assertEqual(result["candidate"]["fallback_reason"], "native_corrupt")
        self.assertEqual(result["candidate"]["ocr"]["configuration"]["native_defect_note"],
                         "hidden text layer maps to X")

    def test_withdrawn_image_source_can_be_replaced_without_reusing_receipt(self):
        first = self.review()
        first_auth = self.admitter.issue("SOURCE_STATUS",
            self.pilot.admission_payload(["image-review"], expected_version=0))
        self.pilot.admit_sources("first-admit", review_ids=["image-review"],
                                 expected_version=0, authorization=first_auth)
        source = first["source_id"]
        action = {"action": "STATUS_CHANGE", "source_id": source,
                  "source_hash": self.catalog.hash(source), "active": False,
                  "permission": "DENIED", "expected_epoch": 0, "expected_version": 1,
                  "security_scope": "image-test", "reason": "corrected manual transcription",
                  "tombstone": False}
        self.backend.change_source_status(self.catalog, source, active=False, permission="DENIED",
            expected_epoch=0, expected_version=1, key="withdraw-for-correction",
            reason="corrected manual transcription", trust=self.trust,
            authorization=self.admitter.issue("SOURCE_STATUS", action))
        self.pilot.prepare_image_page("replacement-prepare", pdf_bytes=self.pdf,
            source_id="authored-image", version="v1", physical_page=1,
            crop_bbox=[0, 0, 600, 240], transcription="Abstract\n" + TEXT,
            producer="authored-manual-fixture", raw_output=("Abstract\n" + TEXT).encode())
        at = now()
        payload = self.pilot.image_review_payload("replacement-prepare", reviewer="authored-reviewer",
            reviewer_kind="assistant", reviewed_at=at, checks={key: True for key in CHECKS})
        replacement = self.pilot.accept_image_review("replacement-review", prepared_id="replacement-prepare",
            receipt=self.reviewer.issue("SOURCE_STATUS", payload, issued_at=at))
        replacement_auth = self.admitter.issue("SOURCE_STATUS",
            self.pilot.admission_payload(["replacement-review"], expected_version=2))
        self.pilot.admit_sources("replacement-admit", review_ids=["replacement-review"],
                                 expected_version=2, authorization=replacement_auth)
        self.assertNotEqual(source, replacement["source_id"])
        self.assertFalse(self.backend.statuses()[source]["active"])
        self.assertTrue(self.backend.statuses()[replacement["source_id"]]["active"])
        self.assertEqual(self.backend.state()["graph_version"], 3)


if __name__ == "__main__":
    unittest.main()
