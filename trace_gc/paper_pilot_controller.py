"""Application controller for frozen, reviewed paper pilot requests.

The controller owns no signing key, provider or graph authority. An embedding
application injects its PaperPilot with enrolled trust and current ACL.
"""
from __future__ import annotations

from pathlib import Path
import sqlite3

from .canonical import bytes_digest, digest, dumps, loads
from .errors import require
from .paper_ingestion import CHECKS
from .pdf_image_evidence import CHECKS as IMAGE_CHECKS


class PaperPilotController:
    """Hash-bound application journal around one already configured PaperPilot."""

    def __init__(self, pilot, *, manifest: dict, private_dir: str | Path):
        self.pilot = pilot
        self.root = Path(private_dir).resolve()
        require(self.root == pilot.root, "CONTROLLER_DIRECTORY", "journal must share the pilot's private run directory")
        version = manifest.get("version")
        require((version == "real-paper-pilot-controller-v1" and
                 set(manifest) == {"version", "pilot_config", "pages", "questions", "acceptance"}) or
                (version == "real-paper-pilot-controller-v2" and
                 set(manifest) == {"version", "pilot_config", "pages", "image_pages", "questions", "acceptance"}),
                "CONTROLLER_MANIFEST", "invalid frozen manifest")
        require(manifest["pilot_config"] == pilot.config and manifest["questions"] == pilot.config["questions"],
                "CONTROLLER_COHORT", "questions or pilot configuration differ")
        frame = {(row["source_id"], row["version"]): row for row in pilot.config["documents"]}
        require(type(manifest["pages"]) is list and manifest["pages"], "CONTROLLER_COHORT", "no frozen pages")
        ids = set()
        for row in manifest["pages"]:
            require(set(row) == {"id", "source_id", "version", "pdf_sha256", "physical_page", "start", "end"},
                    "CONTROLLER_COHORT", "invalid page frame")
            require(row["id"] not in ids and type(row["id"]) is str and row["id"],
                    "CONTROLLER_COHORT", "duplicate or empty page ID")
            ids.add(row["id"])
            document = frame.get((row["source_id"], row["version"]))
            require(document is not None and row["pdf_sha256"] == document["document_sha256"] and
                    row["physical_page"] in document["physical_pages"] and
                    type(row["start"]) is int and type(row["end"]) is int and 0 <= row["start"] < row["end"],
                    "CONTROLLER_COHORT", "page differs from frozen document")
        image_pages = manifest.get("image_pages", [])
        if version == "real-paper-pilot-controller-v2":
            require(type(image_pages) is list and image_pages,
                    "CONTROLLER_COHORT", "v2 requires frozen image pages")
            for row in image_pages:
                require(set(row) == {"id", "source_id", "version", "pdf_sha256", "physical_page",
                    "crop_bbox", "candidate_sha256", "transcription", "producer", "raw_output_sha256",
                    "fallback_reason", "native_defect_note"}, "CONTROLLER_COHORT", "invalid image frame")
                require(row["id"] not in ids and type(row["id"]) is str and row["id"],
                        "CONTROLLER_COHORT", "duplicate image/native ID")
                ids.add(row["id"])
                document = frame.get((row["source_id"], row["version"]))
                require(document is not None and row["pdf_sha256"] == document["document_sha256"] and
                        row["physical_page"] in document["physical_pages"] and
                        type(row["transcription"]) is str and row["transcription"].strip() and
                        type(row["producer"]) is str and row["producer"].strip() and
                        row["raw_output_sha256"] == bytes_digest(row["transcription"].encode("utf-8")) and
                        row["fallback_reason"] in {"native_absent", "native_corrupt"} and
                        ((row["fallback_reason"] == "native_absent" and row["native_defect_note"] is None) or
                         (row["fallback_reason"] == "native_corrupt" and
                          type(row["native_defect_note"]) is str and row["native_defect_note"].strip())) and
                        type(row["crop_bbox"]) is list and len(row["crop_bbox"]) == 4 and
                        all(type(v) is int for v in row["crop_bbox"]) and
                        type(row["candidate_sha256"]) is str and len(row["candidate_sha256"]) == 64 and
                        all(char in "0123456789abcdef" for char in row["candidate_sha256"]),
                        "CONTROLLER_COHORT", "image page differs from frozen document")
        acceptance = {"phase": "source_preparation_only", "source_review_checks": sorted(CHECKS)}
        if version == "real-paper-pilot-controller-v2":
            acceptance["image_review_checks"] = sorted(IMAGE_CHECKS)
        require(manifest["acceptance"] == acceptance, "CONTROLLER_ACCEPTANCE",
                "this controller freezes source-review checks only; final pilot criteria need a separate protocol")
        self.manifest = loads(dumps(manifest))
        self.manifest_sha256 = digest(self.manifest)
        self.db = sqlite3.connect(self.root / "application-journal.sqlite3", isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY, body TEXT NOT NULL, hash TEXT NOT NULL)")
        events = self.db.execute("SELECT seq,body,hash FROM events ORDER BY seq").fetchall()
        previous = None
        for expected_index, (index, raw, recorded_hash) in enumerate(events, 1):
            event = loads(raw)
            require(index == expected_index and event["previous"] == previous and digest(event) == recorded_hash,
                    "CONTROLLER_JOURNAL", "journal chain changed")
            previous = recorded_hash
        if events:
            first = loads(events[0][1])
            require(first["kind"] == "FREEZE" and first["manifest"] == self.manifest and
                    first["pilot_head"] == self._open_head(), "CONTROLLER_FREEZE", "cohort or pilot opening changed")
        else:
            require(len(pilot.requests) == 0, "CONTROLLER_FREEZE", "freeze before preparing sources")
            self._append({"kind": "FREEZE", "manifest": self.manifest, "pilot_head": self._open_head()})
        self._check_actions()

    def _open_head(self):
        row = self.pilot.db.execute("SELECT hash FROM events WHERE seq=1").fetchone()
        require(row is not None, "CONTROLLER_FREEZE", "pilot has no opening checkpoint")
        return row[0]

    def _append(self, body):
        row = self.db.execute("SELECT seq,hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        event = {**body, "previous": row[1] if row else None}
        self.db.execute("INSERT INTO events(seq,body,hash) VALUES (?,?,?)",
                        ((row[0] + 1) if row else 1, dumps(event), digest(event)))

    def _check_actions(self):
        preflight_seen = False
        seen_image_prepares = set()
        for _, raw in self.db.execute("SELECT seq,body FROM events WHERE seq>1 ORDER BY seq"):
            event = loads(raw)
            if event["kind"] == "PREFLIGHT":
                require(not preflight_seen and event["manifest_sha256"] == self.manifest_sha256 and
                        event["pdf_sha256_by_page"] == {row["id"]: row["pdf_sha256"] for row in
                            self.manifest["pages"] + self.manifest.get("image_pages", [])},
                        "CONTROLLER_PREFLIGHT", "preflight differs from frozen cohort")
                preflight_seen = True
            elif event["kind"] == "PREPARE":
                require(preflight_seen, "CONTROLLER_PREFLIGHT", "source prepared before full-cohort preflight")
                result = self.pilot.requests.get(event["request_id"], {}).get("result")
                require(result is not None and digest(result) == event["result_sha256"],
                        "CONTROLLER_RECONCILIATION", "prepared source differs or is missing")
            elif event["kind"] == "PREPARE_IMAGE":
                require(self.manifest["version"] == "real-paper-pilot-controller-v2" and preflight_seen,
                        "CONTROLLER_PREFLIGHT", "image prepared before full-cohort preflight")
                image_rows = {"source-prepare-image:" + row["id"]: row for row in self.manifest["image_pages"]}
                request_id = event["request_id"]
                request = self.pilot.requests.get(request_id, {})
                result = request.get("result")
                require(request_id in image_rows and request_id not in seen_image_prepares and
                        request.get("kind") == "PREPARE_SOURCE_IMAGE" and result is not None and
                        result.get("candidate_sha256") == image_rows[request_id]["candidate_sha256"] and
                        digest(result) == event["result_sha256"],
                        "CONTROLLER_RECONCILIATION", "prepared image source differs or is missing")
                seen_image_prepares.add(request_id)
            else:
                require(False, "CONTROLLER_JOURNAL", "unknown journal action")

    def _preflight_recorded(self):
        return any(loads(raw)["kind"] == "PREFLIGHT" for (raw,) in
                   self.db.execute("SELECT body FROM events WHERE seq>1"))

    def preflight(self, pdfs: dict[str, bytes]) -> dict:
        """Read all frozen PDFs before any source preparation or model action."""
        rows = self.manifest["pages"] + self.manifest.get("image_pages", [])
        expected = {row["id"] for row in rows}
        require(set(pdfs) == expected, "CONTROLLER_COHORT", "every frozen page needs its original PDF bytes")
        for row in rows:
            require(type(pdfs[row["id"]]) is bytes and bytes_digest(pdfs[row["id"]]) == row["pdf_sha256"],
                    "CONTROLLER_SOURCE_CHANGED", "original PDF hash mismatch")
        if not self._preflight_recorded():
            self._append({"kind": "PREFLIGHT", "manifest_sha256": self.manifest_sha256,
                          "pdf_sha256_by_page": {row["id"]: row["pdf_sha256"] for row in rows}})
        self._check_actions()
        return {"status": "PREFLIGHT_PASS", "manifest_sha256": self.manifest_sha256,
                "pages": len(expected), "pilot_checkpoint_head": self.pilot.status()["checkpoint_head"]}

    def prepare(self, page_id: str, pdf_bytes: bytes) -> dict:
        """Stop at source review; no model execution, trust bootstrap or graph write."""
        row = next((r for r in self.manifest["pages"] if r["id"] == page_id), None)
        require(self._preflight_recorded(), "CONTROLLER_PREFLIGHT", "verify the entire frozen cohort before preparation")
        require(row is not None and type(pdf_bytes) is bytes and bytes_digest(pdf_bytes) == row["pdf_sha256"],
                "CONTROLLER_SOURCE_CHANGED", "unfrozen or changed PDF")
        request_id = "source-prepare:" + page_id
        result = self.pilot.prepare_native_page(request_id, pdf_bytes=pdf_bytes,
            source_id=row["source_id"], version=row["version"], physical_page=row["physical_page"],
            start=row["start"], end=row["end"])
        prior = [loads(raw) for (raw,) in self.db.execute("SELECT body FROM events WHERE seq>1")]
        if not any(e.get("kind") == "PREPARE" and e.get("request_id") == request_id for e in prior):
            self._append({"kind": "PREPARE", "request_id": request_id, "result_sha256": digest(result)})
        self._check_actions()
        return {"request_id": request_id, "state": result["state"], "packet_sha256": result["packet_sha256"],
                "checkpoint_head": self.pilot.status()["checkpoint_head"]}

    def prepare_image(self, page_id: str, pdf_bytes: bytes, raw_output: bytes) -> dict:
        """Durably prepare a frozen image candidate after full-cohort preflight."""
        require(self.manifest["version"] == "real-paper-pilot-controller-v2" and self._preflight_recorded(),
                "CONTROLLER_PREFLIGHT", "v2 full-cohort preflight required")
        row = next((r for r in self.manifest["image_pages"] if r["id"] == page_id), None)
        require(row is not None and type(pdf_bytes) is bytes and
                bytes_digest(pdf_bytes) == row["pdf_sha256"] and type(raw_output) is bytes and
                bytes_digest(raw_output) == row["raw_output_sha256"],
                "CONTROLLER_SOURCE_CHANGED", "unfrozen or changed image input")
        request_id = "source-prepare-image:" + page_id
        result = self.pilot.prepare_image_page(request_id, pdf_bytes=pdf_bytes,
            source_id=row["source_id"], version=row["version"], physical_page=row["physical_page"],
            crop_bbox=row["crop_bbox"], transcription=row["transcription"],
            producer=row["producer"], raw_output=raw_output,
            fallback_reason=row["fallback_reason"], native_defect_note=row["native_defect_note"])
        require(result["candidate_sha256"] == row["candidate_sha256"],
                "CONTROLLER_SOURCE_CHANGED", "prepared image differs from frozen candidate")
        prior = [loads(raw) for (raw,) in self.db.execute("SELECT body FROM events WHERE seq>1")]
        if not any(e.get("kind") == "PREPARE_IMAGE" and e.get("request_id") == request_id for e in prior):
            self._append({"kind": "PREPARE_IMAGE", "request_id": request_id, "result_sha256": digest(result)})
        self._check_actions()
        return {"request_id": request_id, "state": result["state"],
                "candidate_sha256": result["candidate_sha256"],
                "checkpoint_head": self.pilot.status()["checkpoint_head"]}

    def status(self) -> dict:
        self._check_actions()
        return {"manifest_sha256": self.manifest_sha256, "pilot": self.pilot.status(),
                "journal_head": self.db.execute("SELECT hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()[0]}

    def close(self):
        self.db.close()
