"""Local source-first application entry point for an externally frozen paper cohort.

All model, trust, ACL, source review and publication capabilities are injected.
This stage verifies real PDFs and stops at durable source-review packets.
"""
from __future__ import annotations

from pathlib import Path

from .canonical import bytes_digest, loads
from .errors import require
from .paper_ingestion import CHECKS
from .paper_pilot_controller import PaperPilotController
from .pdf_image_evidence import (CHECKS as IMAGE_CHECKS, candidate_hash,
    image_candidate, render_source, verify_artifacts)
from .retrieval.security import AccessFilter
from .trust import IssuerPolicy, Signer, TrustStore


def require_complete_native_anchor(native: str, start: int, end: int, quote: str) -> None:
    line_prefix = native[native.rfind("\n", 0, start) + 1:start] if 0 <= start <= len(native) else ""
    require(0 <= start < end <= len(native) and native[start:end] == quote and
            (start == 0 or not native[start - 1].isalnum()) and
            (end == len(native) or not native[end].isalnum()) and
            (not line_prefix.strip() or line_prefix.rstrip().endswith((".", "!", "?"))) and
            quote.rstrip().endswith((".", "!", "?")),
            "APPLICATION_BOUNDARY", "native anchor fails mechanical sentence-edge checks")


class LocalPaperPilotApplication:
    """Bind a frozen private protocol to one application-owned PaperPilot."""

    def __init__(self, *, pilot, protocol_path, protocol_sha256, source_root,
                 reviewer: Signer, admitter: Signer, validator: Signer,
                 trust: TrustStore, access, approved_v4_sha256=None,
                 parent_protocol_path=None, image_candidate_paths=None,
                 approval_manifest_path=None, approval_manifest_sha256=None):
        require(pilot.config["execution_mode"] == "LIVE" and not pilot.backend.sandbox,
                "APPLICATION_MODE", "real cohort needs isolated live reference mode")
        require(pilot.service.trust is trust and pilot.service.signer is validator and
                pilot.current_access is access, "APPLICATION_AUTHORITY", "injected authority differs from pilot")
        self._role(trust, reviewer, purpose="SOURCE_STATUS", operation="PAPER_SOURCE_REVIEW", review=True,
                   scope=pilot.config["security_scope"])
        self._role(trust, admitter, purpose="SOURCE_STATUS", operation="SOURCE_ADMIT", review=False,
                   scope=pilot.config["security_scope"])
        self._role(trust, validator, purpose="PREFLIGHT", operation=None, review=False,
                   scope=pilot.config["security_scope"])
        require(len({reviewer.issuer, admitter.issuer, validator.issuer}) == 3,
                "APPLICATION_AUTHORITY", "source reviewer, admitter and validator must be distinct")
        self.pilot = pilot
        self.reviewer = reviewer
        self.admitter = admitter
        self.validator = validator
        self.trust = trust
        self.access = access
        self._check_access()
        self.source_root = Path(source_root).resolve()
        path = Path(protocol_path).resolve()
        raw = path.read_bytes()
        require(bytes_digest(raw) == protocol_sha256, "APPLICATION_PROTOCOL", "frozen protocol bytes changed")
        self.protocol_path = path
        self.protocol_sha256 = protocol_sha256
        protocol = loads(raw.decode("utf-8"))
        self.v4 = protocol["version"] == "issue23-real-paper-source-first-protocol-v4"
        if self.v4:
            require(protocol["status"] == "APPROVED_SOURCE_REFERENCE_FROZEN_PENDING_RUN_ACTIVATION" and
                    type(approved_v4_sha256) is str and approved_v4_sha256 == protocol_sha256 and
                    parent_protocol_path is not None and image_candidate_paths is not None and
                    approval_manifest_path is not None and type(approval_manifest_sha256) is str,
                    "APPLICATION_PROTOCOL", "v4 needs explicit approved hash and frozen status")
            approval_path = Path(approval_manifest_path).resolve()
            require(approval_path.is_relative_to(self.source_root) and approval_path.is_file(),
                    "APPLICATION_PROTOCOL", "approval manifest outside authorized private root")
            approval_raw = approval_path.read_bytes()
            approval = loads(approval_raw.decode("utf-8"))
            require(bytes_digest(approval_raw) == approval_manifest_sha256 and
                    set(approval) == {"version", "decision", "approved_protocol_sha256",
                                      "parent_v3_sha256", "approved_by", "approved_at"} and
                    approval["version"] == "issue23-protocol-approval-v1" and
                    approval["decision"] == "APPROVED_SOURCE_REFERENCE_ONLY" and
                    approval["approved_protocol_sha256"] == protocol_sha256 and
                    approval["parent_v3_sha256"] == protocol["supersedes_if_approved"]["protocol_v3_sha256"] and
                    type(approval["approved_by"]) is str and approval["approved_by"].strip() and
                    type(approval["approved_at"]) is str and approval["approved_at"].strip(),
                    "APPLICATION_PROTOCOL", "approved protocol manifest differs")
            parent_path = Path(parent_protocol_path).resolve()
            require(parent_path.is_relative_to(self.source_root) and parent_path.is_file(),
                    "APPLICATION_PROTOCOL", "parent protocol outside authorized private root")
            parent_raw = parent_path.read_bytes()
            parent = loads(parent_raw.decode("utf-8"))
            require(parent["version"] == "issue23-real-paper-source-first-protocol-v3" and
                    parent["status"] == "COHORT_AND_SOURCE_REFERENCE_FROZEN_PENDING_APPLICATION_AUTHORITY_AND_FINAL_PROFILE" and
                    bytes_digest(parent_raw) == protocol["supersedes_if_approved"]["protocol_v3_sha256"] and
                    all(protocol[key] == parent[key] for key in
                        ("documents", "questions", "numeric_gates", "evidence_anchors")),
                    "APPLICATION_PROTOCOL", "v4 changes frozen v3 cohort, questions, gates or anchors")
            require(protocol["native_review_holds"] == {"f113-p4-quantitative": {
                "decision": "HOLD", "failed_check": "notation",
                "reason": "Visible m s⁻¹ and km² s⁻¹ are flattened in the native excerpt to m s−1 and km2 s−1.",
                "native_anchor_unchanged": True}}, "APPLICATION_PROTOCOL", "native notation hold changed")
            require(set(protocol["image_routes"]) == {"f076-cover-image", "f113-p4-quantitative"} and
                    set(image_candidate_paths) == set(protocol["image_routes"]) and
                    set(protocol["anchor_scoring_routes"]) == set(protocol["image_routes"]),
                    "APPLICATION_PROTOCOL", "image route map differs")
            self.parent_protocol_path = parent_path
            self.parent_protocol_sha256 = bytes_digest(parent_raw)
            self.approval_manifest_path = approval_path
            self.approval_manifest_sha256 = approval_manifest_sha256
            self.image_candidate_paths = {key: Path(value).resolve() for key, value in image_candidate_paths.items()}
        else:
            require(protocol["version"] == "issue23-real-paper-source-first-protocol-v3" and
                    protocol["status"] == "COHORT_AND_SOURCE_REFERENCE_FROZEN_PENDING_APPLICATION_AUTHORITY_AND_FINAL_PROFILE" and
                    approved_v4_sha256 is None and parent_protocol_path is None and image_candidate_paths is None and
                    approval_manifest_path is None and approval_manifest_sha256 is None,
                    "APPLICATION_PROTOCOL", "unsupported protocol or activation state")
        require([row["text"] for row in protocol["questions"]] == pilot.config["questions"] and
                pilot.config["cohort_manifest_sha256"] == protocol_sha256,
                "APPLICATION_COHORT", "pilot questions or cohort hash differ")
        frame = {row["source_id"]: row for row in pilot.config["documents"]}
        require(set(frame) == set(protocol["documents"]), "APPLICATION_COHORT", "document frame differs")
        self.pdfs = {}
        self.source_paths = {}
        for sid, doc in protocol["documents"].items():
            source = (self.source_root / doc["source_map_relative"]).resolve()
            require(source.is_relative_to(self.source_root) and source.is_file(),
                    "APPLICATION_SOURCE", "source escapes authorized root or is missing")
            pdf = source.read_bytes()
            require(bytes_digest(pdf) == doc["source_sha256"] == frame[sid]["document_sha256"],
                    "APPLICATION_SOURCE", "original PDF differs from frozen cohort")
            self.pdfs[sid] = pdf
            self.source_paths[sid] = source
        anchors = protocol["evidence_anchors"]
        pages = []
        self.image_holds = []
        try:
            import fitz
        except ImportError as exc:
            raise RuntimeError("PyMuPDF is required for local paper source preparation") from exc
        for anchor_id, anchor in anchors.items():
            sid, page = anchor["document"], anchor["physical_page"]
            require(sid in frame and page in frame[sid]["physical_pages"],
                    "APPLICATION_COHORT", "anchor page outside document frame")
            with fitz.open(stream=self.pdfs[sid], filetype="pdf") as pdf:
                native = pdf[page - 1].get_text("text")
            if anchor["representation"] == "pymupdf_native_text_v1":
                start, end = anchor["start_codepoint"], anchor["end_codepoint"]
                require(bytes_digest(native.encode()) == anchor["native_page_sha256"] and
                        native[start:end] == anchor["quote"], "APPLICATION_SOURCE", "native anchor differs")
                require_complete_native_anchor(native, start, end, anchor["quote"])
                pages.append({"id": anchor_id, "source_id": sid, "version": frame[sid]["version"],
                              "pdf_sha256": frame[sid]["document_sha256"], "physical_page": page,
                              "start": start, "end": end})
            else:
                with fitz.open(stream=self.pdfs[sid], filetype="pdf") as pdf:
                    images = pdf[page - 1].get_images(full=True)
                require(anchor["representation"] == "rendered_image_full_page_v1" and not native and images,
                        "APPLICATION_IMAGE", "image anchor needs separate reviewed transcription route")
                if not self.v4:
                    self.image_holds.append(anchor_id)
        require(pages and (self.v4 or self.image_holds), "APPLICATION_COHORT", "expected native and image cases")
        image_pages = []
        if self.v4:
            for anchor_id, route in protocol["image_routes"].items():
                anchor = anchors[anchor_id]
                sid = anchor["document"]
                candidate_path = Path(image_candidate_paths[anchor_id]).resolve()
                require(candidate_path.is_relative_to(self.source_root) and candidate_path.is_file(),
                        "APPLICATION_IMAGE", "candidate escapes authorized source root")
                candidate_bytes = candidate_path.read_bytes()
                candidate = loads(candidate_bytes.decode("utf-8"))
                require(bytes_digest(candidate_bytes) == route["candidate_file_sha256"] and
                        candidate_hash(candidate) == route["candidate_canonical_sha256"] and
                        candidate["review"] is None and candidate["source_id"] == sid and
                        candidate["source_sha256"] == protocol["documents"][sid]["source_sha256"] and
                        candidate["physical_page"] == anchor["physical_page"] and
                        candidate["fallback_reason"] == route["fallback_reason"] and
                        candidate["ocr"]["engine"] == route["engine"] == "manual-visual-transcription" and
                        candidate["ocr"]["revision"] == route["revision"] == "manual-v1" and
                        candidate["transcription"] == route["transcription"] and
                        candidate["transcription_sha256"] == route["transcription_sha256"] and
                        candidate["ocr"]["raw_output_sha256"] == route["manual_raw_output_sha256"] and
                        candidate["ocr"]["configuration"]["producer"] == route["producer"] and
                        candidate["ocr"]["configuration"].get("native_defect_note") == route["native_defect_note"],
                        "APPLICATION_IMAGE", "image candidate differs from frozen route")
                require(route["for_anchor"] == anchor_id and
                        route["representation"] == "reviewed-image-transcription-v1" and
                        route["source_pdf_sha256"] == candidate["source_sha256"] and
                        route["page_identity_sha256"] == candidate["page_identity_sha256"] and
                        route["render_dpi"] == candidate["render"]["dpi"] == 144 and
                        route["render_coordinate_system"] == candidate["render"]["coordinate_system"] and
                        route["render_dimensions"] == candidate["render"]["dimensions"] and
                        route["page_png_sha256"] == candidate["render"]["page_png_sha256"] and
                        route["page_pixels_sha256"] == candidate["render"]["page_pixels_sha256"] and
                        route["crop_bbox_pixel_edges_half_open"] == candidate["crop"]["bbox"] and
                        route["crop_coordinate_system"] == candidate["crop"]["coordinate_system"] and
                        route["crop_png_sha256"] == candidate["crop"]["png_sha256"] and
                        route["crop_pixels_sha256"] == candidate["crop"]["pixels_sha256"],
                        "APPLICATION_IMAGE", "image geometry or identity differs")
                raw_output = candidate["transcription"].encode("utf-8")
                verify_artifacts(candidate, pdf_bytes=self.pdfs[sid], raw_output=raw_output)
                metadata, _, _ = render_source(self.pdfs[sid], physical_page=anchor["physical_page"],
                    dpi=144, crop=candidate["crop"]["bbox"])
                require(metadata["source_sha256"] == candidate["source_sha256"] and
                        (anchor_id != "f076-cover-image" or metadata["native_observation"]["state"] == "absent") and
                        (anchor_id != "f113-p4-quantitative" or
                         (route["fallback_reason"] == "native_corrupt" and
                          metadata["native_observation"]["text_sha256"] == anchor["native_page_sha256"])),
                        "APPLICATION_IMAGE", "image route does not match frozen original page")
                expected_candidate = image_candidate(self.pdfs[sid], source_id=sid,
                    transcription=candidate["transcription"], raw_output=raw_output,
                    engine="manual-visual-transcription", revision="manual-v1",
                    configuration=candidate["ocr"]["configuration"],
                    physical_page=anchor["physical_page"], dpi=144,
                    crop=candidate["crop"]["bbox"],
                    input_crop_sha256=candidate["crop"]["png_sha256"],
                    fallback_reason=route["fallback_reason"])
                require(expected_candidate == candidate, "APPLICATION_IMAGE", "candidate reconstruction differs")
                score = protocol["anchor_scoring_routes"][anchor_id]
                require(score["selected_route"] == route["route_id"] and
                        score["count_once"] is True and score["native_offsets_forbidden"] is True and
                        (anchor_id != "f113-p4-quantitative" or score["native_anchor_remains_hold"] is True),
                        "APPLICATION_PROTOCOL", "image scoring route changed")
                image_pages.append({"id": "image:" + anchor_id, "source_id": sid, "version": frame[sid]["version"],
                    "pdf_sha256": frame[sid]["document_sha256"], "physical_page": anchor["physical_page"],
                    "crop_bbox": candidate["crop"]["bbox"], "candidate_sha256": candidate_hash(candidate),
                    "transcription": candidate["transcription"], "producer": route["producer"],
                    "raw_output_sha256": route["manual_raw_output_sha256"],
                    "fallback_reason": route["fallback_reason"],
                    "native_defect_note": route["native_defect_note"]})
        require(set(protocol["numeric_gates"]) == {"extraction", "graph", "retrieval", "answers", "recovery"} and
                all(type(value) is dict and value for value in protocol["numeric_gates"].values()),
                "APPLICATION_PROTOCOL", "predeclared end-to-end gates missing")
        self.protocol = protocol
        manifest = {
            "version": "real-paper-pilot-controller-v2" if self.v4 else "real-paper-pilot-controller-v1",
            "pilot_config": pilot.config,
            "questions": pilot.config["questions"], "pages": pages,
            "acceptance": {"phase": "source_preparation_only", "source_review_checks": sorted(CHECKS)}}
        if self.v4:
            manifest["image_pages"] = image_pages
            manifest["acceptance"]["image_review_checks"] = sorted(IMAGE_CHECKS)
        self.controller = PaperPilotController(pilot, private_dir=pilot.root, manifest=manifest)

    @staticmethod
    def _role(trust, signer, *, purpose, operation, review, scope):
        require(type(trust) is TrustStore and type(signer) is Signer and signer.issuer in trust._issuers,
                "APPLICATION_AUTHORITY", "private signer not enrolled")
        policy = trust._issuers[signer.issuer]
        require(type(policy) is IssuerPolicy and policy.public_key == signer.public_key() and
                policy.purposes == frozenset({purpose}) and
                policy.operations == (frozenset({operation}) if operation else frozenset()) and
                policy.scopes == frozenset({scope}) and policy.modes == frozenset({"LIVE"}) and
                policy.can_review is review and signer.issuer not in trust._revoked,
                "APPLICATION_AUTHORITY", "signer enrollment exceeds exact pilot role")

    def prepare_sources(self):
        """Preflight every frozen PDF; stop before signed review or model call."""
        self._role(self.trust, self.reviewer, purpose="SOURCE_STATUS", operation="PAPER_SOURCE_REVIEW",
                   review=True, scope=self.pilot.config["security_scope"])
        self._role(self.trust, self.admitter, purpose="SOURCE_STATUS", operation="SOURCE_ADMIT",
                   review=False, scope=self.pilot.config["security_scope"])
        self._role(self.trust, self.validator, purpose="PREFLIGHT", operation=None,
                   review=False, scope=self.pilot.config["security_scope"])
        self._check_access()
        require(bytes_digest(self.protocol_path.read_bytes()) == self.protocol_sha256,
                "APPLICATION_PROTOCOL", "protocol changed after application open")
        if self.v4:
            require(bytes_digest(self.parent_protocol_path.read_bytes()) == self.parent_protocol_sha256 and
                    bytes_digest(self.approval_manifest_path.read_bytes()) == self.approval_manifest_sha256 and
                    all(bytes_digest(self.image_candidate_paths[anchor_id].read_bytes()) ==
                            route["candidate_file_sha256"] for anchor_id, route in self.protocol["image_routes"].items()),
                    "APPLICATION_PROTOCOL", "v4 approval, parent or candidate changed after application open")
        for sid, source in self.source_paths.items():
            fresh = source.read_bytes()
            require(bytes_digest(fresh) == self.protocol["documents"][sid]["source_sha256"],
                    "APPLICATION_SOURCE", "original PDF changed after application open")
            self.pdfs[sid] = fresh
        pdfs = {row["id"]: self.pdfs[row["source_id"]] for row in
                self.controller.manifest["pages"] + self.controller.manifest.get("image_pages", [])}
        preflight = self.controller.preflight(pdfs)
        prepared = [self.controller.prepare(row["id"], pdfs[row["id"]])
                    for row in self.controller.manifest["pages"]]
        require(all(row["state"] == "WAIT_SOURCE_REVIEW" for row in prepared),
                "APPLICATION_PAUSE", "source preparation did not pause at review")
        image_prepared = []
        if self.v4:
            image_prepared = [self.controller.prepare_image(row["id"], pdfs[row["id"]],
                row["transcription"].encode("utf-8")) for row in self.controller.manifest["image_pages"]]
            require(all(row["state"] == "WAIT_IMAGE_SOURCE_REVIEW" for row in image_prepared),
                    "APPLICATION_PAUSE", "image preparation did not pause at review")
        result = {"state": "WAIT_IMAGE_SOURCE_REVIEW" if self.v4 else "WAIT_SOURCE_REVIEW",
                "preflight": preflight, "prepared": prepared,
                "image_route_held": self.image_holds, "model_calls": 0, "graph_version": self.pilot.backend.state()["graph_version"]}
        if self.v4:
            result["image_prepared"] = image_prepared
            result["native_review_holds"] = self.protocol["native_review_holds"]
        return result

    def close(self):
        self.controller.close()

    def _check_access(self):
        acl = self.access()
        AccessFilter(acl, self.pilot.catalog, self.pilot.backend.statuses())
        state = self.pilot.backend.state()
        allowed = ({"node:" + ref for ref in state["nodes"]} |
                   {"source:" + ref for ref in self.pilot.backend.statuses()} |
                   {"edge:" + ref for ref in state["assertions"]})
        require(acl["tenant"] == self.pilot.config["security_scope"] and
                set(acl["grants"]) <= allowed and all("*" not in key for key in acl["grants"]),
                "APPLICATION_ACCESS", "ACL must use current exact grants in this scope")
        for grant in acl["grants"].values():
            require(grant["tenant"] == acl["tenant"] and grant["workspace"] == acl["workspace"] and
                    ((grant["users"] == [acl["user"]] and not grant["roles"]) or
                     (not grant["users"] and len(grant["roles"]) == 1 and
                      grant["roles"][0] in acl["roles"])),
                    "APPLICATION_ACCESS", "grant must target this user or one held role")
