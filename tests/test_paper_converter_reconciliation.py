"""Authored no-converter tests for the explicit old-attempt handoff."""
from __future__ import annotations

import base64
from contextlib import contextmanager
from copy import deepcopy
import datetime as dt
import json
import os
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from trace_gc.canonical import canonical_bytes
from src import paper_converter_smoke as smoke
from src import paper_converter_reconciliation as rec
from src import paper_converter_trusted_application_v1 as concrete_application
from tests import test_paper_converter_smoke as fixture_module


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_module.LifecycleTests("test_prepare_is_durable_and_never_calls_worker")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        smoke.prepare(self.root, self.fixture.pin, "old")
        old = self.root / "old"
        smoke.write_output(self.root, old / "intent.json", {
            "version": "paper-converter-intent-v1", "plan": self.fixture.pin,
            "started_at": smoke.now(), "mode": "AUTHORED_FIXTURE",
            "attempt": 1, "controller_pid": os.getpid()})
        self.intent = smoke.loads((old / "intent.json").read_bytes())
        self.intent_pin = smoke.descriptor(self.root, old / "intent.json")
        smoke.write_output(self.root, old / "INVALIDATED.json", {
            "version": "paper-converter-invalidated-v1", "at": smoke.now(),
            "reason": "authored worker failure", "unknown_outcome": True})
        (old / "raw-partial.txt").write_bytes(b"AUTHORED unknown partial raw; preserved")
        registry = {"version": "paper-converter-active-attempt-v1", "output": "old",
                    "plan": self.fixture.pin, "intent_sha256": self.intent_pin["sha256"]}
        reg = self.root / ".paper-converter-attempts" / (smoke.sha(b"old") + ".json")
        reg.parent.mkdir()
        smoke.write_output(self.root, reg, registry)
        self.registry_pin = smoke.descriptor(self.root, reg)
        new_plan = deepcopy(self.fixture.plan)
        new_plan["evaluation_code_sha256"] = "d" * 64
        self.new_pin = self.fixture.asset("successor-plan.json", new_plan)
        self.key = Ed25519PrivateKey.generate()
        public = self.key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw).hex()
        self.authority = self.fixture.asset("reconciliation/authority.json", {
            "version": rec.AUTHORITY_VERSION, "issuer": "authored-reviewer",
            "public_key_hex": public, "old_registry_sha256": self.registry_pin["sha256"],
            "successor_plan_sha256": self.new_pin["sha256"],
            "successor_output": "new", "expires_at": "2099-01-01T00:00:00+00:00"})
        worker_evidence = self.fixture.asset("reconciliation/worker-evidence.txt",
            b"AUTHORED process handle and descendant census placeholder")
        created_at, observed_exit_at, recorded_at = smoke.now(), smoke.now(), smoke.now()
        closure = self.fixture.asset("reconciliation/closure.json", {
            "version": rec.CLOSURE_VERSION, "recorded_at": recorded_at,
            "intent_sha256": self.intent_pin["sha256"],
            "worker": {"controller_pid": os.getpid(), "worker_pid": 12345,
                       "created_at": created_at, "observed_exit_at": observed_exit_at,
                       "owned_descendants_zero": True, "evidence": worker_evidence},
            "server": {"status": "NOT_APPLICABLE_LOCAL_ENGINE"}})
        self.payload = {"old_output": "old", "old_registry": self.registry_pin,
            "old_intent": self.intent_pin,
            "old_invalidation": smoke.descriptor(self.root, old / "INVALIDATED.json"),
            "old_inventory": rec._inventory(self.root, "old"), "closure": closure,
            "historical_outcome": "UNKNOWN_UNATTESTED_NO_RETRY",
            "successor_plan": self.new_pin, "successor_output": "new",
            "old_retry_authorized": False}
        self.receipt = self._signed(self.payload)
        test = self
        class AuthoredApplication:
            def verify_authority(self, proof):
                return proof["authority_sha256"] == test.authority["sha256"]

            @contextmanager
            def hold_live_exclusion(self, root, proof):
                class Observation:
                    def reobserve(self):
                        return {"old_controller_pid": proof["old_controller_pid"],
                                "old_worker_pid": proof["old_worker_pid"],
                                "observed_at": smoke.now(), "controller_absent": True,
                                "worker_absent": True, "descendants_absent": True,
                                "provider_idle": True, "launch_exclusion_held": True}
                yield Observation()
        # Mechanics fixture only: the separately reviewed enrollment is absent.
        # The V6 negative test proves this stand-in cannot enable a real effect.
        authored = AuthoredApplication()
        self.application = object.__new__(concrete_application.RootEnrolledConverterApplication)
        self.application.reviewed_sha256 = "AUTHORED_FIXTURE_PIN"
        self.application.verify_authority = authored.verify_authority
        self.application.hold_live_exclusion = authored.hold_live_exclusion

    def _signed(self, payload, *, signature_payload=None):
        body = {"version": rec.RECEIPT_VERSION, "issuer": "authored-reviewer",
                "issued_at": smoke.now(), "payload": payload}
        message = body if signature_payload is None else signature_payload
        body["signature"] = base64.b64encode(self.key.sign(canonical_bytes(message))).decode()
        path = self.root / "reconciliation" / ("receipt-" + str(len(list((self.root / "reconciliation").glob("receipt-*.json")))) + ".json")
        return self.fixture.asset(path.relative_to(self.root).as_posix(), body)

    def _verify(self, receipt=None, authority=None, output="new"):
        receipt = receipt or self.receipt
        authority = authority or self.authority
        return rec.verify_reconciliation(self.root,
            authority_relative=authority["relative"], authority_sha256=authority["sha256"],
            receipt_relative=receipt["relative"], receipt_sha256=receipt["sha256"],
            successor_plan=self.new_pin, successor_output=output)

    def test_signed_exact_lineage_allows_distinct_authored_successor(self):
        proof = self._verify()
        with patch.object(smoke, "_worker", side_effect=self.fixture.worker_port):
            with self.assertRaisesRegex(ValueError, "unreconciled_attempt"):
                smoke.execute(self.root, self.new_pin, "ordinary")
            result = smoke.execute_successor(self.root, self.new_pin, "new",
                authority_relative=self.authority["relative"],
                authority_sha256=self.authority["sha256"],
                receipt_relative=self.receipt["relative"],
                receipt_sha256=self.receipt["sha256"],
                trusted_application=self.application)
        self.assertEqual(result["status"], "success")
        self.assertIn("reconciliation_parent", result["artifacts"])
        with self.assertRaisesRegex(ValueError, "independent_reconciliation_readback_required"):
            smoke.verify_execution(self.root, self.new_pin, "new")
        self.assertEqual(smoke.verify_execution(self.root, self.new_pin, "new",
            trusted_application=self.application), result)
        self.assertEqual(self.fixture.calls, 1)
        self.assertEqual(proof["historical_outcome"], "UNKNOWN_UNATTESTED_NO_RETRY")
        self.assertTrue((self.root / "old/INVALIDATED.json").is_file())
        self.assertTrue((self.root / self.registry_pin["relative"]).is_file())

    def test_forged_receipt_and_self_signed_authority_reject(self):
        forged = deepcopy(self.payload)
        forged["old_retry_authorized"] = True
        with self.assertRaises(ValueError):
            self._verify(self._signed(forged, signature_payload={
                "version": rec.RECEIPT_VERSION, "issuer": "authored-reviewer",
                "issued_at": smoke.now(), "payload": self.payload}))
        fake_key = Ed25519PrivateKey.generate()
        other = smoke.loads((self.root / self.authority["relative"]).read_bytes())
        other["public_key_hex"] = fake_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw).hex()
        self.assertRaises(ValueError, self._verify,
            authority=self.fixture.asset("reconciliation/self-key.json", other))

    def test_missing_closure_or_changed_old_bytes_reject_before_worker(self):
        (self.root / self.payload["closure"]["relative"]).unlink()
        with patch.object(smoke, "_worker", side_effect=AssertionError("worker forbidden")):
            with self.assertRaises(ValueError):
                smoke.execute_successor(self.root, self.new_pin, "new",
                    authority_relative=self.authority["relative"],
                    authority_sha256=self.authority["sha256"],
                    receipt_relative=self.receipt["relative"],
                    receipt_sha256=self.receipt["sha256"],
                    trusted_application=self.application)
        self.assertFalse((self.root / "new").exists())

    def test_application_enrollment_and_live_exclusion_are_required(self):
        arguments = {"authority_relative": self.authority["relative"],
                     "authority_sha256": self.authority["sha256"],
                     "receipt_relative": self.receipt["relative"],
                     "receipt_sha256": self.receipt["sha256"]}
        with self.assertRaisesRegex(ValueError, "root_owned_concrete_application_required"):
            smoke.execute_successor(self.root, self.new_pin, "new", **arguments)
        class RefusesAuthority:
            def verify_authority(self, proof): return False
            def hold_live_exclusion(self, root, proof): raise AssertionError("must not enter")
        with self.assertRaisesRegex(ValueError, "root_owned_concrete_application_required"):
            smoke.execute_successor(self.root, self.new_pin, "new",
                trusted_application=RefusesAuthority(), **arguments)
        self.assertFalse((self.root / "new").exists())

    def test_standalone_cli_cannot_self_enroll_authority(self):
        arguments = ["paper_converter_smoke", "execute-successor", "--data-root",
                     str(self.root), "--plan", self.new_pin["relative"],
                     "--expected-plan-sha256", self.new_pin["sha256"],
                     "--output", "new", "--reconciliation-authority",
                     self.authority["relative"],
                     "--expected-reconciliation-authority-sha256",
                     self.authority["sha256"], "--reconciliation-receipt",
                     self.receipt["relative"],
                     "--expected-reconciliation-receipt-sha256",
                     self.receipt["sha256"]]
        with patch.object(sys, "argv", arguments), patch.object(smoke, "_worker",
                side_effect=AssertionError("worker forbidden")):
            self.assertEqual(smoke.main(), 2)
        self.assertFalse((self.root / "new").exists())

    def test_late_live_closure_failure_prevents_worker(self):
        class BadExclusion:
            def verify_authority(self, proof): return True
            @contextmanager
            def hold_live_exclusion(self, root, proof):
                class Observation:
                    def reobserve(self):
                        return {"old_controller_pid": proof["old_controller_pid"],
                                "old_worker_pid": proof["old_worker_pid"],
                                "observed_at": smoke.now(), "controller_absent": True,
                                "worker_absent": False, "descendants_absent": True,
                                "provider_idle": True, "launch_exclusion_held": True}
                yield Observation()
        self.application.hold_live_exclusion = BadExclusion().hold_live_exclusion
        with patch.object(smoke, "_worker", side_effect=AssertionError("worker forbidden")):
            with self.assertRaisesRegex(ValueError, "live_closure_or_launch_exclusion_unproved"):
                smoke.execute_successor(self.root, self.new_pin, "new",
                    authority_relative=self.authority["relative"],
                    authority_sha256=self.authority["sha256"],
                    receipt_relative=self.receipt["relative"],
                    receipt_sha256=self.receipt["sha256"],
                    trusted_application=self.application)

    def test_later_readback_replays_old_inventory_and_enrollment(self):
        with patch.object(smoke, "_worker", side_effect=self.fixture.worker_port):
            smoke.execute_successor(self.root, self.new_pin, "new",
                authority_relative=self.authority["relative"],
                authority_sha256=self.authority["sha256"],
                receipt_relative=self.receipt["relative"],
                receipt_sha256=self.receipt["sha256"],
                trusted_application=self.application)
        (self.root / "old/raw-partial.txt").write_bytes(b"changed after successor")
        with self.assertRaisesRegex(ValueError, "old_attempt_inventory_changed"):
            smoke.verify_execution(self.root, self.new_pin, "new",
                                   trusted_application=self.application)

    def test_completed_successor_replays_after_expiry_but_no_new_effect(self):
        arguments = {"authority_relative": self.authority["relative"],
                     "authority_sha256": self.authority["sha256"],
                     "receipt_relative": self.receipt["relative"],
                     "receipt_sha256": self.receipt["sha256"],
                     "trusted_application": self.application}
        with patch.object(smoke, "_worker", side_effect=self.fixture.worker_port):
            first = smoke.execute_successor(self.root, self.new_pin, "new", **arguments)
        self.assertEqual(self.fixture.calls, 1)
        with patch.object(smoke, "now", return_value="2100-01-01T00:00:00+00:00"):
            with patch.object(smoke, "_worker", side_effect=AssertionError("no replay worker")):
                self.assertEqual(smoke.execute_successor(self.root, self.new_pin,
                    "new", **arguments), first)
                self.assertEqual(smoke.verify_execution(self.root, self.new_pin,
                    "new", trusted_application=self.application), first)
                with self.assertRaisesRegex(ValueError,
                                            "reconciliation_authority_expired_for_action"):
                    rec.verify_reconciliation(self.root,
                        authority_relative=self.authority["relative"],
                        authority_sha256=self.authority["sha256"],
                        receipt_relative=self.receipt["relative"],
                        receipt_sha256=self.receipt["sha256"],
                        successor_plan=self.new_pin, successor_output="new",
                        allow_successor_created=True)
        self.assertEqual(self.fixture.calls, 1)

    def test_worker_started_before_expiry_can_finish_after_expiry(self):
        authority = smoke.loads((self.root / self.authority["relative"]).read_bytes())
        authority["expires_at"] = (dt.datetime.now(dt.timezone.utc) +
                                   dt.timedelta(seconds=1)).isoformat()
        self.authority = self.fixture.asset("reconciliation/authority-short.json", authority)
        arguments = {"authority_relative": self.authority["relative"],
                     "authority_sha256": self.authority["sha256"],
                     "receipt_relative": self.receipt["relative"],
                     "receipt_sha256": self.receipt["sha256"],
                     "trusted_application": self.application}
        def slower_worker(*args):
            time.sleep(1.2)
            return self.fixture.worker_port(*args)
        with patch.object(smoke, "_worker", side_effect=slower_worker):
            result = smoke.execute_successor(self.root, self.new_pin, "new", **arguments)
        self.assertEqual(result["status"], "success")
        self.assertEqual(self.fixture.calls, 1)
        self.assertEqual(smoke.verify_execution(self.root, self.new_pin, "new",
            trusted_application=self.application), result)
        with self.assertRaisesRegex(ValueError, "reconciliation_authority_expired_for_action"):
            self._verify()

    def test_preserved_raw_or_registry_mutation_rejects(self):
        (self.root / "old/raw-partial.txt").write_bytes(b"repinned-looking changed raw")
        with self.assertRaisesRegex(ValueError, "old_attempt_inventory_changed"):
            self._verify()
        (self.root / "old/raw-partial.txt").write_bytes(b"AUTHORED unknown partial raw; preserved")
        (self.root / self.registry_pin["relative"]).write_bytes(b"{}")
        with self.assertRaises(ValueError):
            self._verify()

    def test_grobid_requires_separate_server_closure(self):
        with self.assertRaisesRegex(ValueError, "server_closure_required"):
            rec._closure(self.root, self.payload["closure"], self.intent,
                         self.intent_pin["sha256"], "grobid")

    def test_old_output_and_other_successor_reject(self):
        with self.assertRaises(ValueError):
            self._verify(output="old")
        with self.assertRaises(ValueError):
            self._verify(output="other")


if __name__ == "__main__":
    unittest.main()
