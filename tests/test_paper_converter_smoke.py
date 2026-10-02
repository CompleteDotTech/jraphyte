"""Authored fixtures only: these tests never execute a real converter/model."""
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
import datetime as dt
import json
import os
from pathlib import Path
import platform
import py_compile
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from src import paper_converter_smoke as smoke
from src import paper_converter_worker as worker


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        identity = {"controller": smoke.digest(Path(smoke.__file__)), "worker": smoke.digest(Path(worker.__file__)), "dependencies": {}}
        self.identity = identity
        self.addCleanup(patch.stopall)
        patch.object(smoke, "code_identity", return_value=identity).start()
        patch.object(smoke, "source_check").start()  # PDF buffers exercised separately below.
        self.calls = 0
        self.plan, self.pin = self.make_plan("docling")

    def asset(self, relative, payload):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload if type(payload) is bytes else json.dumps(payload).encode())
        return smoke.descriptor(self.root, path)

    def make_plan(self, engine, status="success"):
        source = self.asset("source.pdf", b"AUTHORED original PDF placeholder")
        page = self.asset("page.pdf", b"AUTHORED first PDF page placeholder")
        fixture = self.asset("fixture.json", {"outputs": {k: {"status": status, "text": "Authored fixture"}
                                                           for k in smoke.CACHES[engine]}, "status": status})
        exe = self.asset("python.exe", b"AUTHORED fake interpreter; worker launch is substituted")
        runtime_file = self.asset("runtime.txt", b"AUTHORED pinned runtime file")
        exposure = self.asset("exposure.json", {"version": "paper-exposed-source-v1", "case_id": "authored", "source_sha256": source["sha256"],
            "page_sha256": page["sha256"], "scope": "AUTHORED_FIXTURE", "attribution": "authored test fixture", "recorded_at": smoke.now()})
        plan = {"version": smoke.VERSION, "mode": "AUTHORED_FIXTURE", "created_at": smoke.now(), "case_id": "authored", "source": source,
                "page": page, "exposure": exposure, "engine": {"name": engine, "revision": "authored-fixture-v1", "license": "authored",
                "device": "synthetic_cpu", "assets": [fixture], "decoding": {"fixture_output": "fixture.json"}, "prompt_sha256": None},
                "runtime": {"executable": exe, "python_version": platform.python_version(), "packages": {}, "files": [runtime_file]},
                "limits": {"request_characters": 2000, "request_tokens": 1000, "retries": 0, "timeout_seconds": 20,
                           "device_concurrency": 1, "crop_policy": "physical_page_one_only"},
                "code_identity": self.identity, "configuration_sha256": "a" * 64, "evaluation_runtime_sha256": "b" * 64,
                "evaluation_code_sha256": "c" * 64}
        return plan, self.asset("plan.json", plan)

    def worker_port(self, root, pin, out, plan):
        """Run actual authored worker serialization; replace only process/network ports."""
        self.calls += 1
        with (out / "stdout.txt").open("x", encoding="utf8") as stdout, (out / "stderr.txt").open("x", encoding="utf8") as stderr:
            with redirect_stdout(stdout), redirect_stderr(stderr), patch.object(worker.sys, "executable", str(self.root / "python.exe")), \
                 patch.object(worker.os, "getppid", return_value=os.getpid()), patch.object(worker, "_network_guard"), \
                 patch.object(worker.sys, "pycache_prefix", str(out / "unused-bytecode")), patch.object(worker.sys, "dont_write_bytecode", True), \
                 patch.object(worker, "_vision", side_effect=AssertionError("model forbidden")), \
                 patch.object(worker, "_docling", side_effect=AssertionError("engine forbidden")), \
                 patch.object(worker, "_grobid", side_effect=AssertionError("service forbidden")):
                return worker.run(root, pin, out.relative_to(root).as_posix())

    def execute(self):
        with patch.object(smoke, "_worker", side_effect=self.worker_port):
            return smoke.execute(self.root, self.pin, "attempt")

    def attestation(self):
        return self.asset("attestation.json", {"version": "paper-converter-custodian-readback-v1",
            "execution_sha256": smoke.digest(self.root / "attempt/execution.json"), "custodian": "authored test custodian",
            "reviewed_at": smoke.now(), "actual_engine_execution_confirmed": True, "assets_and_raw_outputs_checked": True,
            "independent_human": False, "mode": "AUTHORED_FIXTURE"})

    def test_prepare_is_durable_and_never_calls_worker(self):
        with patch.object(smoke, "_worker", side_effect=AssertionError("not authorized")):
            first = smoke.prepare(self.root, self.pin, "attempt")
            self.assertEqual(first, smoke.prepare(self.root, self.pin, "attempt"))
        self.assertFalse((self.root / "attempt/intent.json").exists())
        self.assertFalse((self.root / "attempt/readiness.json").exists())

    def test_all_four_authored_shapes_are_resumable_and_not_real_readiness(self):
        for name in smoke.METHODS:
            with self.subTest(engine=name), tempfile.TemporaryDirectory() as temporary:
                self.root = Path(temporary).resolve()
                self.plan, self.pin = self.make_plan(name)
                output = "attempt-" + name
                with patch.object(smoke, "_worker", side_effect=self.worker_port):
                    result = smoke.execute(self.root, self.pin, output)
                    self.assertEqual(result, smoke.execute(self.root, self.pin, output))
                self.assertFalse(result["readiness_pass"])
                self.assertEqual(name, result["engine"])
        self.assertEqual(4, self.calls)

    def test_finalize_requires_external_custodian_and_emits_synthetic_version(self):
        self.execute()
        attestation = self.attestation()
        marker = smoke.finalize(self.root, self.pin, "attempt", attestation)
        self.assertEqual(marker, smoke.verify_readiness(self.root, self.pin, "attempt", attestation))
        readiness = smoke.loads((self.root / "attempt/readiness.json").read_bytes())
        self.assertEqual("synthetic-paper-local-readiness-v1", readiness["version"])
        self.assertFalse(marker["prospective_execution_authorized"])
        self.assertFalse(marker["graph_admission_enabled"])
        self.assertEqual(1, self.calls)

    def test_unknown_attempt_is_not_retried(self):
        smoke.prepare(self.root, self.pin, "attempt")
        (self.root / "attempt/intent.json").write_text("{}")
        with patch.object(smoke, "_worker", side_effect=AssertionError("retry forbidden")):
            with self.assertRaisesRegex(ValueError, "unknown_attempt"):
                smoke.execute(self.root, self.pin, "attempt")

    def test_worker_cannot_execute_without_controller_intent(self):
        smoke.prepare(self.root, self.pin, "attempt")
        with patch.object(worker.sys, "pycache_prefix", str(self.root / "attempt/unused-bytecode")), \
             patch.object(worker.sys, "dont_write_bytecode", True), self.assertRaises(FileNotFoundError):
            worker.run(self.root, self.pin, "attempt")

    def test_existing_bytecode_cache_rejects_before_engine(self):
        smoke.prepare(self.root, self.pin, "attempt")
        (self.root / "attempt/unused-bytecode").mkdir()
        with self.assertRaisesRegex(ValueError, "bytecode"):
            self.execute()

    def test_prepopulated_converter_cache_is_never_adopted(self):
        smoke.prepare(self.root, self.pin, "attempt")
        (self.root / "attempt/docling.json").write_text('{"status":"success"}')
        with self.assertRaisesRegex(ValueError, "not_fresh"):
            self.execute()

    def test_outside_artifact_symlink_rejected_before_read(self):
        with tempfile.TemporaryDirectory() as other:
            outside = Path(other) / "private.json"; outside.write_text("outside private bytes")
            link = self.root / "artifact.json"
            try:
                link.symlink_to(outside)
            except OSError:
                self.skipTest("symlink creation unavailable")
            with patch.object(smoke, "digest", side_effect=AssertionError("must reject before reading outside")):
                with self.assertRaisesRegex(ValueError, "outside_authorized_root"):
                    smoke.descriptor(self.root, link)

    def test_truncation_cannot_finalize(self):
        self.plan, self.pin = self.make_plan("olmocr", "truncated")
        self.execute()
        with self.assertRaisesRegex(ValueError, "not_ready"):
            smoke.finalize(self.root, self.pin, "attempt", self.attestation())

    def test_output_and_claim_tampering_reject(self):
        self.execute()
        path = self.root / "attempt/execution.json"
        original = path.read_bytes()
        for field, value in (("exit_code", True), ("readiness_pass", True), ("input_hashes", {}), ("status", "error")):
            with self.subTest(field=field):
                record = smoke.loads(original); record[field] = value
                path.write_text(json.dumps(record))
                with self.assertRaises(ValueError):
                    smoke.verify_execution(self.root, self.pin, "attempt")
        path.write_bytes(original)
        (self.root / "attempt/docling.json").write_text('{"different":true}')
        with self.assertRaises(ValueError):
            smoke.verify_execution(self.root, self.pin, "attempt")

    def test_changed_source_and_caller_plan_are_bound(self):
        smoke.prepare(self.root, self.pin, "attempt")
        (self.root / "source.pdf").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "hash_mismatch"):
            self.execute()
        self.assertEqual(0, self.calls)

    def test_finalization_race_is_durably_invalidated(self):
        self.execute(); attestation = self.attestation()
        original = smoke.write_once
        def racing(path, value):
            result = original(path, value)
            if path.name == "COMPLETE.json":
                (self.root / "runtime.txt").write_bytes(b"changed after completion")
            return result
        with patch.object(smoke, "write_once", side_effect=racing):
            with self.assertRaises(ValueError):
                smoke.finalize(self.root, self.pin, "attempt", attestation)
        self.assertTrue((self.root / "attempt/INVALIDATED.json").is_file())
        (self.root / "runtime.txt").write_bytes(b"AUTHORED pinned runtime file")
        with self.assertRaisesRegex(ValueError, "invalidated"):
            smoke.verify_readiness(self.root, self.pin, "attempt", attestation)

    def test_forged_custodian_or_completion_rejects(self):
        self.execute(); attestation = self.attestation()
        value = smoke.loads((self.root / "attestation.json").read_bytes()); value["independent_human"] = True
        bad = self.asset("bad-attestation.json", value)
        with self.assertRaises(ValueError):
            smoke.finalize(self.root, self.pin, "attempt", bad)
        smoke.finalize(self.root, self.pin, "attempt", attestation)
        (self.root / "attempt/readiness.json").write_text('{}')
        with self.assertRaises(ValueError):
            smoke.verify_readiness(self.root, self.pin, "attempt", attestation)

    def test_mode_relabel_and_unsafe_descriptor_block(self):
        plan = deepcopy(self.plan); plan["mode"] = "EXPOSED_DEVELOPMENT"
        with self.assertRaises(ValueError):
            smoke.prepare(self.root, self.asset("real.json", plan), "attempt")
        for relative in ("../outside", "C:/outside", "a\\b"):
            with self.subTest(relative=relative), self.assertRaises(ValueError):
                smoke.Inputs(self.root).read({"relative": relative, "sha256": "a" * 64})

    def test_failed_launch_preserves_intent_and_never_retries(self):
        with patch.object(smoke, "_worker", side_effect=OSError("private path must not leak")):
            with self.assertRaises(OSError):
                smoke.execute(self.root, self.pin, "attempt")
        marker = smoke.loads((self.root / "attempt/INVALIDATED.json").read_bytes())
        self.assertEqual("OSError", marker["reason"])
        with self.assertRaisesRegex(ValueError, "invalidated"):
            self.execute()

    def test_orphan_attempt_blocks_a_different_output_after_lock_release(self):
        with patch.object(smoke, "_worker", side_effect=OSError("lost process outcome")):
            with self.assertRaises(OSError):
                smoke.execute(self.root, self.pin, "attempt")
        with patch.object(smoke, "_worker", side_effect=AssertionError("duplicate engine forbidden")):
            with self.assertRaisesRegex(ValueError, "unreconciled_attempt"):
                smoke.execute(self.root, self.pin, "different-attempt")
        self.assertFalse((self.root / "different-attempt/intent.json").exists())

    def test_finished_execution_permits_next_attempt_with_same_frozen_inputs(self):
        self.execute()
        with patch.object(smoke, "_worker", side_effect=self.worker_port):
            second = smoke.execute(self.root, self.pin, "second-attempt")
        self.assertEqual("success", second["status"])
        self.assertEqual(2, self.calls)
        result = smoke.loads((self.root / "second-attempt/worker-result.json").read_bytes())
        self.assertGreater(result["resources"]["peak_process_memory_bytes"], 0)

    def test_registry_resolves_intent_leaf_before_any_digest(self):
        self.execute()
        original_child, original_digest = smoke.child, smoke.digest
        opened = []
        def reject_leaf(root, relative):
            if relative == "attempt/intent.json":
                raise ValueError("path_outside_authorized_root")
            return original_child(root, relative)
        def record_open(path):
            if Path(path) == self.root / "attempt/intent.json":
                opened.append(path)
            return original_digest(path)
        with patch.object(smoke, "child", side_effect=reject_leaf), patch.object(smoke, "digest", side_effect=record_open):
            with self.assertRaisesRegex(ValueError, "outside_authorized_root"):
                smoke.outstanding_attempts(self.root)
        self.assertEqual([], opened)


class ContractTests(unittest.TestCase):
    def test_fresh_bytecode_prefix_uses_pinned_source_not_unchecked_pyc(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); module = root / "authored_module.py"
            module.write_text("VALUE = 'stale bytecode'\n")
            py_compile.compile(str(module), invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH)
            module.write_text("VALUE = 'pinned source'\n")
            code = "import sys; sys.path.insert(0, sys.argv[1]); import authored_module; print(authored_module.VALUE)"
            base = [sys.executable, "-I", "-B"]
            stale = subprocess.check_output(base + ["-c", code, str(root)], text=True)
            prefix = root / "unused-bytecode"
            fresh = subprocess.check_output(base + ["-X", "pycache_prefix=" + str(prefix), "-c", code, str(root)], text=True)
            self.assertEqual("stale bytecode", stale.strip())
            self.assertEqual("pinned source", fresh.strip())
            self.assertFalse(prefix.exists())

    def test_mineru_requires_every_bounded_role_before_model_import(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(); folder = root / "model"; folder.mkdir()
            for name in ("config.json", "tokenizer_config.json", "model.safetensors"):
                (folder / name).write_text("AUTHORED placeholder; never loaded")
            prompts = {"prompts": {k: "Authored prompt" for k in worker.MINERU_KEYS}, "system_prompt": "Authored"}
            sampling = {k: {**{field: None for field in worker.SAMPLING_KEYS}, "max_new_tokens": 40} for k in worker.MINERU_KEYS}
            (root / "prompts.json").write_text(json.dumps(prompts))
            (root / "sampling.json").write_text(json.dumps(sampling))
            assets = [smoke.descriptor(root, p) for p in [*folder.iterdir(), root / "prompts.json", root / "sampling.json"]]
            options = {"model_directory": "model", "render_dpi": 200, "cpu_threads": 4, "min_free_gpu_mib": 8192,
                       "min_free_ram_bytes": 20 * 1024**3, "prompts": "prompts.json", "sampling": "sampling.json"}
            plan = {"mode": "EXPOSED_DEVELOPMENT", "engine": {"name": "mineru", "revision": worker.REVISIONS["mineru"],
                    "device": "cuda:0", "assets": assets, "decoding": options, "prompt_sha256": smoke.digest(root / "prompts.json")},
                    "runtime": {"packages": worker.REQUIRED_PACKAGES["mineru"]}, "limits": {"request_tokens": 100, "request_characters": 1000}}
            worker.validate_profile(plan, root)
            for altered in ({"bogus": {"max_new_tokens": 40}}, {k: v for k, v in sampling.items() if k != "[layout]"},
                            {**sampling, "[default]": {**sampling["[default]"], "max_new_tokens": None}}):
                (root / "sampling.json").write_text(json.dumps(altered))
                plan["engine"]["assets"][-1] = smoke.descriptor(root, root / "sampling.json")
                with self.assertRaisesRegex(ValueError, "all_calls_bounded"):
                    worker.validate_profile(plan, root)

    def test_local_only_socket_audit_guard(self):
        for engine in ("grobid", "docling", "mineru", "olmocr", "synthetic"):
            with self.subTest(engine=engine), patch.object(worker.sys, "addaudithook") as hook:
                worker._network_guard(engine)
                guard = hook.call_args.args[0]
                with self.assertRaises(RuntimeError):
                    guard("socket.connect", (object(), ("external.example", 443)))
                if engine == "grobid":
                    guard("socket.connect", (object(), ("127.0.0.1", 18070)))
                else:
                    with self.assertRaises(RuntimeError):
                        guard("socket.connect", (object(), ("127.0.0.1", 18070)))

    def test_prospective_wire_is_validation_only(self):
        value = {"version": "paper-converter-execution-v1", "engine": "grobid", "method": smoke.METHODS["grobid"],
                 "revision": "0.9.1", "execution_kind": "LOCAL_CONVERTER", "status": "success", "started_at": smoke.now(),
                 "completed_at": smoke.now(), "output_sha256": {"grobid": "a" * 64},
                 "raw_response": {"relative": "private/raw.bin", "sha256": "b" * 64}, "new_paid_api_calls": 0, "production_graph_writes": 0}
        value.update({k: "c" * 64 for k in ("access_sha256", "source_sha256", "page_sha256", "configuration_sha256", "runtime_sha256", "code_sha256", "limits_sha256")})
        self.assertEqual(value, smoke.validate_prospective_execution(value))
        for field, bad in (("production_graph_writes", False), ("output_sha256", []), ("method", "parallel_olmocr_v4")):
            other = deepcopy(value); other[field] = bad
            with self.subTest(field=field), self.assertRaises(ValueError):
                smoke.validate_prospective_execution(other)
        value["raw_response"]["relative"] = "../outside"
        with self.assertRaises(ValueError):
            smoke.validate_prospective_execution(value)

    def test_real_engine_requires_runtime_packages(self):
        for name in smoke.METHODS:
            plan = {"mode": "EXPOSED_DEVELOPMENT", "engine": {"name": name, "assets": [], "revision": "unverified", "decoding": {}}, "runtime": {"packages": {}}}
            with self.subTest(engine=name), self.assertRaisesRegex(ValueError, "runtime_profile"):
                worker.validate_profile(plan, Path.cwd())

    def test_complete_runtime_file_inventory_required(self):
        class Distribution:
            metadata = {"Name": "authored"}; version = "1"; files = [Path("unbound.py")]
            def locate_file(self, path): return Path.cwd() / path
        plan = {"mode": "EXPOSED_DEVELOPMENT", "runtime": {"python_version": platform.python_version(), "packages": {"authored": "1"}, "files": []}}
        with patch.object(worker.importlib.metadata, "version", return_value="1"), patch.object(worker.importlib.metadata, "distributions", return_value=[Distribution()]):
            with self.assertRaisesRegex(ValueError, "distribution_files"):
                worker._runtime(plan, Path.cwd())

    def test_capture_actual_generations_bounds_and_truncation(self):
        class Tensor:
            def __init__(self, value): self.value = value
            def tolist(self): return self.value
        class Config:
            def to_dict(self): return {"eos_token_id": 2}
        class Model:
            generation_config = Config()
            def generate(self, **kwargs): return Tensor([[1, 3, 4, 5]])
        model = Model(); rows = worker.capture_generations(model, 3)
        model.generate(input_ids=Tensor([[1, 3]]), max_new_tokens=2, do_sample=False)
        self.assertTrue(rows[0]["hit_token_limit"])
        self.assertEqual([4, 5], rows[0]["output_token_ids"])
        for kwargs in ({"input_ids": Tensor([[1, 2, 3, 4]]), "max_new_tokens": 2}, {"input_ids": Tensor([[1]]), "max_length": 20}):
            with self.assertRaisesRegex(ValueError, "token_limit"):
                model.generate(**kwargs)

    def test_remote_docker_endpoint_rejected_before_subprocess(self):
        manifest = {"container": "abc123", "image_sha256": "sha256:" + "a" * 64, "files": {"/opt/grobid/x": "a" * 64},
                    "docker_endpoint": "tcp://remote:2375", "docker_executable": {}, "service_jar": "service.jar"}
        with patch.object(worker.subprocess, "check_output", side_effect=AssertionError("network forbidden")):
            with self.assertRaisesRegex(ValueError, "local_docker"):
                worker._service_check(Path.cwd(), manifest)


try:
    import fitz
except ImportError:
    fitz = None


@unittest.skipUnless(fitz, "optional PyMuPDF authored PDF check")
class SourcePDFTests(unittest.TestCase):
    def test_original_first_page_exact_render_and_wrong_page(self):
        with fitz.open() as pdf:
            pdf.new_page().insert_text((40, 40), "Authored page one")
            pdf.new_page().insert_text((40, 40), "Authored page two")
            source = pdf.tobytes()
            with fitz.open() as first, fitz.open() as second:
                first.insert_pdf(pdf, from_page=0, to_page=0)
                second.insert_pdf(pdf, from_page=1, to_page=1)
                smoke.source_check(source, first.tobytes())
                with self.assertRaisesRegex(ValueError, "copy_mismatch"):
                    smoke.source_check(source, second.tobytes())


if __name__ == "__main__":
    unittest.main()
