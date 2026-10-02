"""Adversarial checks for the separate source-verified selector policy."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src import paper_selector_acceptance_v2 as gate_v2
from src.paper_selector_acceptance_v2 import _source_gate
from src.parallel_source_v4.promotion import CASE_IDS, METHODS, PRIMARY


def base():
    ids = sorted(CASE_IDS)
    original = ids[:91]
    rows = []
    for index, sid in enumerate(ids):
        gold = "complete" if index < 111 else "partial_on_page_one" if index < 118 else "no_abstract_text"
        proposed = index < 97
        rows.append({"id": sid, "gold": gold, "predicted": "complete" if proposed else "uncertain",
            "proposed": proposed, "conversion_status": "success",
            "review_dimensions": {d: "pass" if proposed else "unresolved" for d in
                ("notation", "boundary", "reading_order", "source_location")}})
    gates = {name: {"status": "PASS"} for name in ("provenance", "saved_v2_replay",
        "preserve_91", "zero_false_primary_proposals", "reviewed_fidelity",
        "original_source_outcomes", "f195_reviewed_boundary", "image_route")}
    gates["preserve_91"]["original_correct_ids"] = original
    gates["zero_false_primary_proposals"]["status"] = "FAIL"
    gates["reviewed_fidelity"].update(proposed=97, failed_ids=[], unresolved_ids=[])
    return {"status": "FAIL", "gates": gates, "eligible_for_reviewed_selector_release": False,
        "graph_admission_enabled": False, "production_graph_writes": 0,
        "automatic_fallback_enabled": False, "arms": {method: {} for method in METHODS},
        "cases": {method: deepcopy(rows) for method in METHODS},
        "image_review": {"enabled": True, "count": 24},
        "postrun_source_code_runtime_recheck": "PASS", "independent_qualification": False}


class SourceVerifiedSelectorTests(unittest.TestCase):
    def test_source_gate_preserves_frozen_legacy_failure(self):
        result = _source_gate(base())
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["legacy_failed_gate_names"], ["zero_false_primary_proposals"])
        self.assertTrue(result["original_91_included"])
        self.assertEqual(result["selected_source_verified_count"], 97)

    def test_source_gate_rejects_missing_or_false_evidence(self):
        mutations = [
            lambda b: b["cases"][PRIMARY][0]["review_dimensions"].__setitem__("notation", "fail"),
            lambda b: b["cases"][PRIMARY][0].__setitem__("gold", "no_abstract_text"),
            lambda b: b["cases"][PRIMARY][0].__setitem__("proposed", False),
            lambda b: b["cases"][PRIMARY].pop(),
            lambda b: b["gates"]["saved_v2_replay"].__setitem__("status", "FAIL"),
            lambda b: b["gates"]["preserve_91"].__setitem__("status", "BLOCKED"),
            lambda b: b["gates"]["reviewed_fidelity"].__setitem__("proposed", 96),
            lambda b: b["gates"]["f195_reviewed_boundary"].__setitem__("status", "BLOCKED"),
            lambda b: b["image_review"].__setitem__("enabled", False),
            lambda b: b.__setitem__("graph_admission_enabled", True),
        ]
        for index, mutation in enumerate(mutations):
            with self.subTest(mutation=index):
                candidate = base()
                mutation(candidate)
                with self.assertRaises((ValueError, KeyError, TypeError)):
                    _source_gate(candidate)

    def test_assess_rejects_policy_code_change_during_base_replay(self):
        with tempfile.TemporaryDirectory() as folder:
            tmp_path = Path(folder)
            def put(name, value):
                raw = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
                (tmp_path / name).write_bytes(raw)
                return {"relative": name, "sha256": hashlib.sha256(raw).hexdigest()}

            approval = put("approval.json", {"version": "user-approved-source-verified-gate-amendment-v1",
                "approval": "Approve source-verified gate; preserve legacy results",
                "automatic_fallback_authorized": False, "graph_admission_authorized": False,
                "scope": ("Source-verified preservation of all 91 original IDs and zero source-false selected proposals; "
                    "every selected proposal must pass original-source notation, boundary, reading order and location. "
                    "Retain unchanged legacy scorer, historical references, scores and failures; "
                    "no silent glyph folding, threshold or ID exemption.")})
            config = put("config.json", {})
            source_map = put("map.json", {})
            policy = put("policy.json", {"version": gate_v2.POLICY_VERSION, "approval": approval,
                "base_acceptance": {"relative": "base.json", "sha256": "0"*64},
                "configuration": config, "source_map": source_map})
            state = {"code": "a"*64}
            def replay(*args, **kwargs):
                state["code"] = "b"*64
                return {"eligible_for_reviewed_selector_release": False, "status": "FAIL",
                    "gates": {}, "scope": {}, "arms": {}, "fallback_increment": {}, "method_hashes": {},
                    "image_code_sha256": "0"*64, "runtime": {}, "input_manifest_sha256": "0"*64,
                    "derived_assessment_files_sha256": {}}
            with patch.object(gate_v2, "_code_identity", side_effect=lambda: state["code"]), \
                    patch.object(gate_v2, "_base_readback", side_effect=replay), \
                    patch.object(gate_v2, "_source_gate", return_value={"status": "PASS"}):
                with self.assertRaisesRegex(ValueError, "source_policy_inputs_changed_during_assessment"):
                    gate_v2.assess(tmp_path, policy_relative=policy["relative"], policy_sha256=policy["sha256"],
                        configuration_relative=config["relative"], source_map_relative=source_map["relative"])

    def test_cli_wrong_pin_is_structured_blocked_without_private_path(self):
        with tempfile.TemporaryDirectory() as folder:
            command = [sys.executable, "-m", "src.paper_selector_acceptance_v2", "verify",
                "--data-root", folder, "--policy", "secret/policy.json",
                "--policy-sha256", "0"*64, "--configuration", "config.json",
                "--source-map", "map.json", "--receipt", "secret/receipt.json",
                "--receipt-sha256", "1"*64]
            run = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(run.returncode, 2)
            self.assertEqual(json.loads(run.stdout)["status"], "BLOCKED")
            self.assertNotIn(folder, run.stdout + run.stderr)
            self.assertNotIn("Traceback", run.stdout + run.stderr)
