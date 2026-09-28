"""Authored comparison receipts exercise identity replay, not corpus quality."""
from contextlib import ExitStack, contextmanager
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.parallel_source_v4 import extraction, promotion_io
from src.parallel_source_v4.common import digest
from src.parallel_source_v4.runtime import verify_native_manifest
from tests.test_selector_promotion import authored_run
from trace_gc.pdf_source_parallel_v4 import json_bytes


@contextmanager
def fixture():
    with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
        root = Path(directory)
        gate, code, kwargs = authored_run(root, native_reference=True)
        kwargs.update(native_manifest_relative="reference.json",
                      native_manifest_sha256=gate["native_manifest_sha256"])

        def replay(*args, **options):
            if options.get("native_manifest") is None:
                omitted = deepcopy(gate)
                omitted["native_manifest_sha256"] = None
                omitted["native_comparison"] = {"status": "NO_REFERENCE_SUPPLIED", "changed_ids": []}
                omitted["input_file_hashes"].pop("reference.json")
                return omitted
            # This real verifier checks the authored reference and every raw
            # payload. Only PDF extraction/baseline preparation is substituted.
            verify_native_manifest(root, options["native_manifest"], options["native_manifest_sha256"])
            return deepcopy(gate)

        preflight = stack.enter_context(patch.object(extraction, "preflight", side_effect=replay))
        final = stack.enter_context(patch.object(extraction, "verify_preflight_inputs"))
        stack.enter_context(patch.object(promotion_io, "method_hashes", return_value=code))
        stack.enter_context(patch.object(promotion_io, "runtime_receipt", return_value=gate["runtime"]))
        yield root, gate, kwargs, preflight, final


class NativeReferenceAuditTests(unittest.TestCase):
    def test_pinned_comparison_replays_fresh_and_verifies_published_receipt(self):
        with fixture() as (root, gate, kwargs, preflight, final):
            result = promotion_io.analyze(root, **kwargs)
            self.assertEqual(result["status"], "PASS", result)
            self.assertEqual(preflight.call_args.kwargs["native_mode"], "fresh")
            self.assertEqual(preflight.call_args.kwargs["native_manifest"], root/"reference.json")
            self.assertEqual(preflight.call_args.kwargs["native_manifest_sha256"], kwargs["native_manifest_sha256"])
            self.assertEqual(result["invocation"]["native_manifest_relative"], "reference.json")
            self.assertEqual(result["input_file_hashes"]["archive/f001.json"], digest(root/"archive/f001.json"))
            final.assert_called_once()
            public = promotion_io.publish(root, "acceptance", result)
            verified = promotion_io.verify(root, "acceptance/acceptance.json", public["private_acceptance_sha256"],
                configuration_relative="config.json", source_map_relative="map.json")
            self.assertEqual(verified["status"], "PASS")
            self.assertFalse(verified["graph_admission_enabled"])

    def test_missing_partial_or_stale_external_pin_is_blocked_before_preflight(self):
        with fixture() as (root, gate, kwargs, preflight, final):
            for relative, sha in ((None, None), ("reference.json", None),
                                  (None, kwargs["native_manifest_sha256"]),
                                  ("reference.json", "f"*64), ("reference.json", "bad")):
                with self.subTest(relative=relative, sha=sha):
                    result = promotion_io.analyze(root, **{**kwargs, "native_manifest_relative": relative,
                        "native_manifest_sha256": sha})
                    self.assertEqual(result["status"], "BLOCKED")
                    self.assertFalse(result["eligible_for_reviewed_selector_release"])
            preflight.assert_not_called()

    def test_changed_reference_or_archived_payload_cannot_pass(self):
        with fixture() as (root, gate, kwargs, preflight, final):
            for relative, expected in (("reference.json", "native_reference_manifest_hash_mismatch"),
                                       ("archive/f001.json", "native_file_hash_mismatch")):
                path = root/relative
                original = path.read_bytes()
                try:
                    path.write_bytes(b"{}\n")
                    result = promotion_io.analyze(root, **kwargs)
                    self.assertEqual(result["status"], "BLOCKED")
                    self.assertEqual(result["reason"], expected)
                finally:
                    path.write_bytes(original)

    def test_reference_payload_is_rechecked_after_assessment_evaluation(self):
        with fixture() as (root, gate, kwargs, preflight, final):
            path = root/"archive/f001.json"
            original = path.read_bytes()
            final.side_effect = lambda *args: path.write_bytes(b"[]\n")
            try:
                result = promotion_io.analyze(root, **kwargs)
                self.assertEqual(result["status"], "BLOCKED")
                self.assertFalse(result["eligible_for_reviewed_selector_release"])
            finally:
                path.write_bytes(original)

    def test_exact_preflight_equality_and_fresh_only_policy_are_retained(self):
        with fixture() as (root, gate, kwargs, preflight, final):
            for key, value in (("native_comparison", {"status": "COMPARED", "changed_ids": ["f001"]}),
                               ("runtime", {"fixture": "changed"}), ("method_hashes", {"fixture.py": "e"*64})):
                original = deepcopy(gate[key])
                gate[key] = value
                try:
                    result = promotion_io.analyze(root, **kwargs)
                    self.assertEqual(result["reason"], "experiment_preflight_identity_is_stale_or_altered")
                finally:
                    gate[key] = original
            path = root/"run/preflight.json"
            original = path.read_bytes()
            changed = json.loads(original)
            changed["native_mode"] = "replay"
            path.write_bytes(json_bytes(changed))
            try:
                self.assertEqual(promotion_io.analyze(root, **kwargs)["reason"], "promotion_requires_fresh_native_experiment")
            finally:
                path.write_bytes(original)

    def test_manifest_cannot_be_added_to_a_run_without_recorded_comparison(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            gate, code, kwargs = authored_run(root)
            with patch.object(promotion_io, "method_hashes", return_value=code), patch.object(extraction, "preflight") as preflight:
                result = promotion_io.analyze(root, **kwargs, native_manifest_relative="reference.json", native_manifest_sha256="a"*64)
            self.assertEqual(result["reason"], "native_reference_not_recorded_in_experiment")
            preflight.assert_not_called()


if __name__ == "__main__":
    unittest.main()
