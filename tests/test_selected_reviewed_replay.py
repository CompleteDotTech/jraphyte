"""Adversarial checks for the selected replay adapter's trust boundaries."""
from __future__ import annotations

import base64
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from trace_gc.trust import Signer
from trace_gc.pdf_source_parallel_v4 import digest_value
from tools.selected_reviewed_replay import (_baseline, _bind_frozen_inputs, _historical_correct,
                                           _output_target, _trust, selected_replay)
from src.parallel_source_v4.extraction import METHODS
from src.parallel_source_v4.metrics import score_case, summary


class SelectedReviewedReplayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.signers = [Signer.ephemeral("reviewer-a"), Signer.ephemeral("reviewer-b")]
        self.reviewers = [{"issuer": s.issuer, "principal": s.issuer,
                           "public_key_base64": base64.b64encode(s.public_key()).decode("ascii"),
                           "reviewer_kind": "assistant"} for s in self.signers]

    def _write(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def test_missing_completed_baseline_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "completed_baseline_required"):
            _baseline(self.root, self.root / "repo", "missing", {}, {})

    def test_drifted_assessment_file_rejected_before_scoring(self):
        ids = {f"f{i:03d}" for i in range(1, 201)}
        gate = {"status": "PASS", "source_geometry_policy": "source_fraction_v1",
                "method_hashes": {}, "runtime": {}, "input_file_hashes": {},
                "repository_input_hashes": {}}
        self._write("baseline/preflight.json", gate)
        hashes = {f"assessments/{method}/{sid}.json": "0" * 64
                  for method in METHODS for sid in ids}
        self._write("baseline/results.json", {
            "cohort": "regression200", "source_geometry_policy": "source_fraction_v1",
            "saved_replay_gate": {"status": "PASS"}, "status": "FAILED_REGRESSION_PRESERVATION_GATE",
            "experiment_sha256": digest_value(gate), "assessment_files_sha256": hashes,
            "details": {method: [{"id": sid} for sid in sorted(ids)] for method in METHODS}})
        self._write("baseline/assessments/parallel_structure_v4/f001.json", {})
        with patch("tools.selected_reviewed_replay.method_hashes", return_value={}), \
             patch("tools.selected_reviewed_replay.runtime_receipt", return_value={}), \
             patch("tools.selected_reviewed_replay.verify_files"):
            with self.assertRaisesRegex(ValueError, "baseline_assessment_file_drift"):
                _baseline(self.root, self.root / "repo", "baseline", {sid: "source" for sid in sorted(ids)},
                          {sid: {} for sid in sorted(ids)})

    def test_tampered_preservation_gate_cannot_hide_lost_historical_id(self):
        ids = [f"f{i:03d}" for i in range(1, 201)]
        labels = {sid: {"status": "complete", "text": "x"} for sid in ids}
        input_hashes = {}
        old_details = []
        for index, sid in enumerate(ids):
            prediction = {"status": "complete", "text": "x", "eligible_for_jev": index < 91}
            relative = f"validation_expanded200/assessments/structure_v2/{sid}.json"
            self._write(relative, prediction)
            input_hashes[relative] = hashlib.sha256((self.root / relative).read_bytes()).hexdigest()
            old_details.append(score_case(sid, {**prediction, "proposal": index < 91,
                                                 "eligible_for_jev": False}, labels[sid]))
        current = [score_case(sid, {"status": "complete", "text": "x", "proposal": index < 90},
                              labels[sid]) for index, sid in enumerate(ids)]
        result = {"v2_baseline": summary(old_details),
                  "details": {"parallel_structure_v4": current},
                  "preserve_91_gate": {"status": "PASS", "old_correct": 91, "lost_correct_ids": []}}
        with self.assertRaisesRegex(ValueError, "historical_preservation_gate_mismatch"):
            _historical_correct(self.root, {"input_file_hashes": input_hashes}, labels, result)

    def test_enrollment_requires_two_distinct_reviewers(self):
        with self.assertRaisesRegex(ValueError, "distinct_reviewers_required"):
            _trust([self.reviewers[0], {**self.reviewers[1], "principal": "reviewer-a"}])
        with self.assertRaisesRegex(ValueError, "reviewer_enrollment_shape_invalid"):
            _trust([self.reviewers[0], {**self.reviewers[1], "private_key": "forbidden"}])

    def test_wrong_signature_is_rejected(self):
        trust = _trust(self.reviewers)
        receipt = self.signers[0].issue("OBSERVATION", {"test": True},
                                         issued_at="2026-01-01T00:00:00Z",
                                         expires_at="2027-01-01T00:00:00Z")
        receipt["signature"] = base64.b64encode(b"\0" * 64).decode("ascii")
        with self.assertRaises(Exception):
            trust.verify(receipt, "OBSERVATION", at="2026-06-01T00:00:00Z")

    def _frozen_gate(self):
        ids = [f"f{i:03d}" for i in range(1, 201)]
        labels_path = "validation_expanded200/labels.json"
        self._write(labels_path, {sid: {"status": "complete", "text": "x"} for sid in ids})
        source_map = {}
        hashes = {labels_path: hashlib.sha256((self.root / labels_path).read_bytes()).hexdigest()}
        verified = []
        for sid in ids:
            payload = b"test-pdf:" + sid.encode("ascii")
            sha = hashlib.sha256(payload).hexdigest()
            relative = f"validation_v3_private/sources/{sid}.pdf"
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
            source_map[sid] = relative
            hashes[relative] = sha
            verified.append({"id": sid, "source_sha256": sha})
        gate = {"input_file_hashes": hashes, "verified_sources": verified}
        return gate, source_map

    def test_changed_labels_are_rejected(self):
        gate, source_map = self._frozen_gate()
        self._write("validation_expanded200/labels.json", {"f001": {"status": "absent"}})
        with self.assertRaisesRegex(ValueError, "frozen_labels_hash_mismatch"):
            _bind_frozen_inputs(self.root, gate, "validation_expanded200/labels.json", source_map)
        with self.assertRaisesRegex(ValueError, "frozen_labels_path_required"):
            _bind_frozen_inputs(self.root, gate, "other/labels.json", source_map)

    def test_changed_source_map_is_rejected(self):
        gate, source_map = self._frozen_gate()
        source_map["f001"] = source_map["f002"]
        with self.assertRaisesRegex(ValueError, "source_map_gate_binding_mismatch"):
            _bind_frozen_inputs(self.root, gate, "validation_expanded200/labels.json", source_map)

    def test_output_cannot_enter_frozen_or_source_trees(self):
        for path in ("validation_v2/new", "validation_expanded200/new",
                     "validation_v3_private/sources/new", "validation_v3_private/baseline/new"):
            with self.assertRaisesRegex(ValueError, "new_private_output_directory_required"):
                _output_target(self.root, path, "validation_v3_private/baseline")
        target = _output_target(self.root, "validation_v3_private/new", "validation_v3_private/baseline")
        self.assertEqual(target, self.root / "validation_v3_private/new")

    def test_source_map_mismatch_rejected_before_review_application(self):
        self._write("source.json", {"f001": "sources/real.pdf"})
        self._write("labels.json", {"f001": {"status": "complete", "text": "x"}})
        self._write("baseline/preflight.json", {})
        self._write("map.json", {"schema_version": 1, "baseline": "baseline",
                                  "source_map": "source.json", "labels": "labels.json",
                                  "reviewers": self.reviewers,
                                  "cases": {"f001": {"source_pdf": "sources/wrong.pdf",
                                                      "page_pdf": "validation_v2/pages/f001/page.pdf",
                                                      "page_image": "image.png", "notation": "notation.json",
                                                      "tex": "tex", "manifest": "manifest.json",
                                                      "reviews": ["a.json", "b.json"],
                                                      "converter_assets": {}}}})
        with patch("tools.selected_reviewed_replay._bind_frozen_inputs"), \
             patch("tools.selected_reviewed_replay._baseline", return_value=({}, {}, "hash", set())):
            with self.assertRaisesRegex(ValueError, "review_source_map_mismatch"):
                selected_replay(root=self.root, repo=self.root / "repo", review_map="map.json", output="out")

    def test_unreviewed_id_cannot_be_inserted(self):
        self._write("source.json", {"f001": "sources/real.pdf"})
        self._write("labels.json", {"f001": {"status": "complete", "text": "x"}})
        self._write("baseline/preflight.json", {})
        self._write("map.json", {"schema_version": 1, "baseline": "baseline",
                                  "source_map": "source.json", "labels": "labels.json",
                                  "reviewers": self.reviewers, "cases": {"f999": {}}})
        with patch("tools.selected_reviewed_replay._bind_frozen_inputs"), \
             patch("tools.selected_reviewed_replay._baseline", return_value=({}, {}, "hash", set())):
            with self.assertRaisesRegex(ValueError, "reviewed_ids_outside_frozen_cohort"):
                selected_replay(root=self.root, repo=self.root / "repo", review_map="map.json", output="out")


if __name__ == "__main__":
    unittest.main()
