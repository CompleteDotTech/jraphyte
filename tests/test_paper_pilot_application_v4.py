"""Authored v4 source-only fixture; no research PDFs, signatures or model calls."""
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest

try:
    import fitz
    from PIL import Image, ImageDraw
    AVAILABLE = True
except ImportError:
    AVAILABLE = False

from trace_gc.backend import CompilerService, SQLiteReferenceBackend
from trace_gc.budget import RunBudget
from trace_gc.canonical import bytes_digest
from trace_gc.catalog import Catalog
from trace_gc.demo import limits, relation
from trace_gc.errors import ContractError
from trace_gc.paper_pilot import PaperPilot
from trace_gc.paper_pilot_application import LocalPaperPilotApplication
from trace_gc.pdf_image_evidence import candidate_hash, image_candidate, render_source
from trace_gc.policy import create_policy
from trace_gc.retrieval.security import access_policy, grant
from trace_gc.trust import IssuerPolicy, Signer, TrustStore


def encoded(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode()


@unittest.skipUnless(AVAILABLE, "PyMuPDF and Pillow required")
class V4ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.run = self.root / "private-run"
        self.run.mkdir()
        cover = Image.new("RGB", (250, 100), "white")
        ImageDraw.Draw(cover).text((12, 18), "Authored cover title", fill="black")
        output = io.BytesIO(); cover.save(output, format="PNG")
        pdf = fitz.open()
        pdf.new_page(width=250, height=100).insert_image(fitz.Rect(0, 0, 250, 100),
                                                          stream=output.getvalue())
        pdf.new_page().insert_text((30, 40), "Authored native method sentence.")
        pdf.new_page().insert_text((30, 40), "Authored native result 650 km2 s-1.")
        self.original = pdf.tobytes()
        native2, native3 = pdf[1].get_text("text"), pdf[2].get_text("text")
        pdf.close()
        (self.root / "source.pdf").write_bytes(self.original)
        documents = {"paper": {"source_map_relative": "source.pdf",
                                "source_sha256": bytes_digest(self.original)}}
        anchors = {
            "f076-cover-image": {"document": "paper", "physical_page": 1,
                                  "representation": "rendered_image_full_page_v1"},
            "method": {"document": "paper", "physical_page": 2,
                       "representation": "pymupdf_native_text_v1", "start_codepoint": 0,
                       "end_codepoint": len(native2.strip()), "quote": native2.strip(),
                       "native_page_sha256": bytes_digest(native2.encode())},
            "f113-p4-quantitative": {"document": "paper", "physical_page": 3,
                                       "representation": "pymupdf_native_text_v1", "start_codepoint": 0,
                                       "end_codepoint": len(native3.strip()), "quote": native3.strip(),
                                       "native_page_sha256": bytes_digest(native3.encode())}}
        self.parent = {"version": "issue23-real-paper-source-first-protocol-v3",
            "status": "COHORT_AND_SOURCE_REFERENCE_FROZEN_PENDING_APPLICATION_AUTHORITY_AND_FINAL_PROFILE",
            "documents": documents, "questions": [{"id": "q1", "text": "What is authored?"}],
            "numeric_gates": {key: {"fixture_target": 1} for key in
                              ("extraction", "graph", "retrieval", "answers", "recovery")},
            "evidence_anchors": anchors}
        self.parent_path = self.root / "v3.json"
        self.parent_path.write_bytes(encoded(self.parent))
        self.routes = {}
        self.candidate_paths = {}
        for anchor_id, page, text, reason, note in (
            ("f076-cover-image", 1, "Authored cover title", "native_absent", None),
            ("f113-p4-quantitative", 3, "Authored result 650 km² s⁻¹.",
             "native_corrupt", "Authored fixture: visible superscripts differ from native layer")):
            metadata, _, _ = render_source(self.original, physical_page=page, dpi=144)
            crop = metadata["crop"]["bbox"]
            configuration = {"producer": "fixture-producer", "method": "visual-reading-of-original-full-page"}
            if note is not None:
                configuration["native_defect_note"] = note
            candidate = image_candidate(self.original, source_id="paper", transcription=text,
                raw_output=text.encode(), engine="manual-visual-transcription", revision="manual-v1",
                configuration=configuration, physical_page=page, dpi=144, crop=crop,
                input_crop_sha256=metadata["crop"]["png_sha256"], fallback_reason=reason)
            path = self.root / (anchor_id + ".json")
            path.write_bytes(encoded(candidate))
            self.candidate_paths[anchor_id] = path
            route_id = anchor_id + "-route-v1"
            self.routes[anchor_id] = {"route_id": route_id, "for_anchor": anchor_id,
                "representation": "reviewed-image-transcription-v1", "fallback_reason": reason,
                "native_status": "ABSENT" if note is None else "HOLD_NOTATION",
                "source_pdf_sha256": candidate["source_sha256"], "physical_page": page,
                "page_identity_sha256": candidate["page_identity_sha256"],
                "render_dpi": 144, "render_coordinate_system": candidate["render"]["coordinate_system"],
                "render_dimensions": candidate["render"]["dimensions"],
                "page_png_sha256": candidate["render"]["page_png_sha256"],
                "page_pixels_sha256": candidate["render"]["page_pixels_sha256"],
                "crop_bbox_pixel_edges_half_open": crop,
                "crop_coordinate_system": candidate["crop"]["coordinate_system"],
                "crop_png_sha256": candidate["crop"]["png_sha256"],
                "crop_pixels_sha256": candidate["crop"]["pixels_sha256"],
                "candidate_canonical_sha256": candidate_hash(candidate),
                "candidate_file_sha256": bytes_digest(path.read_bytes()),
                "manual_raw_output_sha256": candidate["ocr"]["raw_output_sha256"],
                "transcription_sha256": candidate["transcription_sha256"],
                "transcription": text, "producer": "fixture-producer", "engine": "manual-visual-transcription",
                "revision": "manual-v1", "native_defect_note": note,
                "candidate_review": "PENDING_NEW_RUN_SIGNED_SOURCE_REVIEW",
                "source_admission": "PENDING_NEW_RUN_DISTINCT_AUTHORITY"}
        self.v4 = copy.deepcopy(self.parent)
        self.v4.update(version="issue23-real-paper-source-first-protocol-v4",
            status="APPROVED_SOURCE_REFERENCE_FROZEN_PENDING_RUN_ACTIVATION",
            supersedes_if_approved={"protocol_v3_sha256": bytes_digest(self.parent_path.read_bytes())},
            native_review_holds={"f113-p4-quantitative": {
                "decision": "HOLD", "failed_check": "notation",
                "reason": "Visible m s⁻¹ and km² s⁻¹ are flattened in the native excerpt to m s−1 and km2 s−1.",
                "native_anchor_unchanged": True}}, image_routes=self.routes,
            anchor_scoring_routes={
                "f076-cover-image": {"selected_route": self.routes["f076-cover-image"]["route_id"],
                                      "count_once": True, "native_offsets_forbidden": True},
                "f113-p4-quantitative": {"selected_route": self.routes["f113-p4-quantitative"]["route_id"],
                                          "count_once": True, "native_offsets_forbidden": True,
                                          "native_anchor_remains_hold": True}})
        self.protocol_path = self.root / "v4.json"
        self.protocol_path.write_bytes(encoded(self.v4))
        self.protocol_sha = bytes_digest(self.protocol_path.read_bytes())
        self.approval = {"version": "issue23-protocol-approval-v1",
            "decision": "APPROVED_SOURCE_REFERENCE_ONLY", "approved_protocol_sha256": self.protocol_sha,
            "parent_v3_sha256": bytes_digest(self.parent_path.read_bytes()),
            "approved_by": "authored-fixture-owner", "approved_at": "2026-09-29T12:00:00Z"}
        self.approval_path = self.root / "approval.json"
        self.approval_path.write_bytes(encoded(self.approval))
        self.catalog = Catalog()
        claim = self.catalog.claim("Authored fixture claim")
        schema = self.catalog.put("schema", {"version": "authored-v4-v1",
            "relations": {"supports": relation("Document", "Claim")}})
        policy = create_policy(self.catalog, version="authored-v4-policy-v1", scope="authored-v4",
            population="authored-fixture", mode="REVIEWED", allowed_modes=["LIVE"])
        self.review = Signer.ephemeral("v4-reviewer")
        self.admit = Signer.ephemeral("v4-admitter")
        self.validator = Signer.ephemeral("v4-validator")
        self.trust = TrustStore()
        for signer, principal, purpose, operation, can_review in (
            (self.review, "reviewer", "SOURCE_STATUS", "PAPER_SOURCE_REVIEW", True),
            (self.admit, "admitter", "SOURCE_STATUS", "SOURCE_ADMIT", False),
            (self.validator, "validator", "PREFLIGHT", None, False)):
            self.trust.enroll(signer.issuer, IssuerPolicy(signer.public_key(), principal,
                frozenset({purpose}), frozenset({operation} if operation else ()),
                frozenset({"authored-v4"}), frozenset({"LIVE"}), can_review=can_review))
        model = {"provider": "AUTHORED_NO_MODEL", "model_id": "jev-1.13.0",
                 "model_revision": "fixture", "tokenizer_id": "fixture-counter"}
        self.config = {"run_id": "authored-v4", "security_scope": "authored-v4", "execution_mode": "LIVE",
            "documents": [{"source_id": "paper", "version": "v1", "document_sha256": bytes_digest(self.original),
                           "physical_pages": [1, 2, 3]}], "questions": ["What is authored?"],
            "cohort_manifest_sha256": self.protocol_sha, "semantic_model": model, "answer_model": model}
        nodes = {"paper": "Document", claim: "Claim"}
        grants = {"node:" + ref: grant("authored-v4", "private", users=["reviewer"]) for ref in nodes}
        self.acl = lambda: access_policy(tenant="authored-v4", workspace="private", user="reviewer", grants=grants)
        self.backend = SQLiteReferenceBackend(self.run / "graph.sqlite3", catalog=self.catalog,
            schema_id=schema, nodes=nodes, sandbox=False)
        self.budget = RunBudget(self.run / "budget.sqlite3", "authored-v4", limits(model_calls=1))
        self.service = CompilerService(self.backend, self.trust, self.validator,
            policy_version="authored-v4-policy-v1", population="authored-fixture",
            security_scope="authored-v4", policy_hash=self.catalog.hash(policy), publication_mode="REVIEWED")
        self.pilot = PaperPilot(self.run, config=self.config, catalog=self.catalog, backend=self.backend,
            service=self.service, budget=self.budget, current_access=self.acl,
            token_counter=lambda value: len(json.dumps(value)))

    def tearDown(self):
        self.pilot.close(); self.backend.close(); self.budget.close(); self.temp.cleanup()

    def app(self, **overrides):
        args = {"pilot": self.pilot, "protocol_path": self.protocol_path,
            "protocol_sha256": self.protocol_sha, "source_root": self.root,
            "reviewer": self.review, "admitter": self.admit, "validator": self.validator,
            "trust": self.trust, "access": self.acl, "approved_v4_sha256": self.protocol_sha,
            "parent_protocol_path": self.parent_path, "image_candidate_paths": self.candidate_paths,
            "approval_manifest_path": self.approval_path,
            "approval_manifest_sha256": bytes_digest(self.approval_path.read_bytes())}
        args.update(overrides)
        return LocalPaperPilotApplication(**args)

    def test_prepares_native_and_two_image_packets_without_review_or_model(self):
        app = self.app()
        try:
            result = app.prepare_sources()
            self.assertEqual(result["state"], "WAIT_IMAGE_SOURCE_REVIEW")
            self.assertEqual(len(result["prepared"]), 2)
            self.assertEqual(len(result["image_prepared"]), 2)
            self.assertEqual(result["native_review_holds"]["f113-p4-quantitative"]["decision"], "HOLD")
            self.assertEqual(self.backend.state()["graph_version"], 0)
            self.assertEqual(self.backend.statuses(), {})
            self.assertEqual(self.budget.snapshot()["used"]["model_calls"], 0)
            repeated = app.prepare_sources()["image_prepared"]
            self.assertEqual([(r["request_id"], r["candidate_sha256"]) for r in repeated],
                             [(r["request_id"], r["candidate_sha256"]) for r in result["image_prepared"]])
        finally:
            app.close()

    def test_rejects_unapproved_or_changed_parent_and_candidate(self):
        with self.assertRaises(ContractError):
            self.app(approved_v4_sha256="0" * 64)
        with self.assertRaises(ContractError):
            self.app(approval_manifest_sha256="0" * 64)
        changed = copy.deepcopy(self.v4)
        changed["status"] = "PROSPECTIVE_UNAPPROVED_DO_NOT_ACTIVATE"
        path = self.root / "draft.json"; path.write_bytes(encoded(changed))
        with self.assertRaises(ContractError):
            self.app(protocol_path=path, protocol_sha256=bytes_digest(path.read_bytes()),
                     approved_v4_sha256=bytes_digest(path.read_bytes()))
        changed = copy.deepcopy(self.v4)
        changed["questions"][0]["text"] = "Changed question?"
        path = self.root / "drift.json"; path.write_bytes(encoded(changed))
        with self.assertRaises(ContractError):
            self.app(protocol_path=path, protocol_sha256=bytes_digest(path.read_bytes()),
                     approved_v4_sha256=bytes_digest(path.read_bytes()))
        candidate = self.candidate_paths["f076-cover-image"]
        candidate.write_bytes(candidate.read_bytes() + b"changed")
        with self.assertRaises(ContractError):
            self.app()

    def test_changed_second_candidate_or_original_after_open_blocks_all_preparation(self):
        app = self.app()
        try:
            candidate = self.candidate_paths["f113-p4-quantitative"]
            candidate.write_bytes(candidate.read_bytes() + b"changed")
            with self.assertRaises(ContractError):
                app.prepare_sources()
            self.assertEqual(self.pilot.status()["requests"], [])
        finally:
            app.close()

    def test_missing_original_after_open_blocks_all_preparation(self):
        app = self.app()
        try:
            (self.root / "source.pdf").unlink()
            with self.assertRaises(OSError):
                app.prepare_sources()
            self.assertEqual(self.pilot.status()["requests"], [])
        finally:
            app.close()


if __name__ == "__main__":
    unittest.main()
