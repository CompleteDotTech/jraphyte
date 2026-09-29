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
from .retrieval.security import AccessFilter
from .trust import IssuerPolicy, Signer, TrustStore


def require_complete_native_anchor(native: str, start: int, end: int, quote: str) -> None:
    require(0 <= start < end <= len(native) and native[start:end] == quote and
            (start == 0 or not native[start - 1].isalnum()) and
            (end == len(native) or not native[end].isalnum()) and
            quote.rstrip().endswith((".", "!", "?")),
            "APPLICATION_BOUNDARY", "native anchor must cover complete source sentence")


class LocalPaperPilotApplication:
    """Bind a frozen private protocol to one application-owned PaperPilot."""

    def __init__(self, *, pilot, protocol_path, protocol_sha256, source_root,
                 reviewer: Signer, admitter: Signer, validator: Signer,
                 trust: TrustStore, access):
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
        protocol = loads(raw.decode("utf-8"))
        require(protocol["version"] == "issue23-real-paper-source-first-protocol-v3" and
                protocol["status"] == "COHORT_AND_SOURCE_REFERENCE_FROZEN_PENDING_APPLICATION_AUTHORITY_AND_FINAL_PROFILE",
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
                self.image_holds.append(anchor_id)
        require(pages and self.image_holds, "APPLICATION_COHORT", "expected native and image cases")
        require(set(protocol["numeric_gates"]) == {"extraction", "graph", "retrieval", "answers", "recovery"} and
                all(type(value) is dict and value for value in protocol["numeric_gates"].values()),
                "APPLICATION_PROTOCOL", "predeclared end-to-end gates missing")
        self.protocol = protocol
        self.controller = PaperPilotController(pilot, private_dir=pilot.root, manifest={
            "version": "real-paper-pilot-controller-v1", "pilot_config": pilot.config,
            "questions": pilot.config["questions"], "pages": pages,
            "acceptance": {"phase": "source_preparation_only", "source_review_checks": sorted(CHECKS)}})

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
        for sid, source in self.source_paths.items():
            fresh = source.read_bytes()
            require(bytes_digest(fresh) == self.protocol["documents"][sid]["source_sha256"],
                    "APPLICATION_SOURCE", "original PDF changed after application open")
            self.pdfs[sid] = fresh
        pdfs = {row["id"]: self.pdfs[row["source_id"]] for row in self.controller.manifest["pages"]}
        preflight = self.controller.preflight(pdfs)
        prepared = [self.controller.prepare(row["id"], pdfs[row["id"]])
                    for row in self.controller.manifest["pages"]]
        require(all(row["state"] == "WAIT_SOURCE_REVIEW" for row in prepared),
                "APPLICATION_PAUSE", "source preparation did not pause at review")
        return {"state": "WAIT_SOURCE_REVIEW", "preflight": preflight, "prepared": prepared,
                "image_route_held": self.image_holds, "model_calls": 0, "graph_version": self.pilot.backend.state()["graph_version"]}

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
