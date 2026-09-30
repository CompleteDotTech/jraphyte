"""Fixed local converter adapters. Invoked only by the explicit smoke executor."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trace_gc.canonical import loads
from src.parallel_source_v4.common import child, digest, write_once

REVISIONS = {"mineru": "1aa090b41282e64fadd79c10572221f91ec21924",
             "olmocr": "e52d6f090b7a9007afffbbd6ce510876222fea93"}
REQUIRED_PACKAGES = {
    "docling": {"docling": "2.130.0", "docling-ibm-models": "4.0.3", "rapidocr": "3.9.2"},
    "grobid": {"requests": None},
    "mineru": {"mineru-vl-utils": "2.0.5", "transformers": "4.57.6", "torch": "2.8.0+cu128", "pymupdf": "1.28.2", "pillow": "12.3.0"},
    "olmocr": {"transformers": "4.57.6", "torch": "2.8.0+cu128", "bitsandbytes": "0.50.2", "pymupdf": "1.28.2", "pillow": "12.3.0"}}
MINERU_KEYS = {"table", "equation", "image", "chart", "[default]", "[layout]", "[cross_page_table_merge]"}
SAMPLING_KEYS = {"temperature", "top_p", "top_k", "presence_penalty", "frequency_penalty", "repetition_penalty",
                 "no_repeat_ngram_size", "max_new_tokens"}


def package_name(value):
    return re.sub(r"[-_.]+", "-", value).lower()


def require(value, code):
    if not value:
        raise ValueError(code)


def _redirector_chain_matches(info, controller_pid, executable, executable_sha256):
    """Only the pinned Windows venv launcher may add one parent hop."""
    return (info["parent_parent_pid"] == controller_pid
            and Path(info["parent_executable"]).resolve() == Path(executable).resolve()
            and info["parent_executable_sha256"] == executable_sha256
            and info["controller_created"] < info["parent_created"] <= info["worker_created"]
            and info["controller_alive"] and info["parent_alive"])


def _process_handle_alive(kernel, handle):
    import ctypes
    result = kernel.WaitForSingleObject(handle, 0)
    if result not in (0, 258):
        raise ctypes.WinError(ctypes.get_last_error())
    return result == 258


def _windows_parent_info(controller_pid):
    import ctypes
    from ctypes import wintypes as w

    class Entry(ctypes.Structure):
        _fields_ = [("size", w.DWORD), ("usage", w.DWORD), ("pid", w.DWORD),
                    ("heap", ctypes.c_size_t), ("module", w.DWORD), ("threads", w.DWORD),
                    ("parent", w.DWORD), ("priority", w.LONG), ("flags", w.DWORD),
                    ("name", w.WCHAR * 260)]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [w.DWORD, w.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = w.HANDLE
    for name in ("Process32FirstW", "Process32NextW"):
        fn = getattr(kernel, name)
        fn.argtypes = [w.HANDLE, ctypes.POINTER(Entry)]; fn.restype = w.BOOL
    kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    kernel.OpenProcess.restype = w.HANDLE
    kernel.CloseHandle.argtypes = [w.HANDLE]; kernel.CloseHandle.restype = w.BOOL
    kernel.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD)]
    kernel.QueryFullProcessImageNameW.restype = w.BOOL
    kernel.GetProcessTimes.argtypes = [w.HANDLE, *([ctypes.POINTER(w.FILETIME)] * 4)]
    kernel.GetProcessTimes.restype = w.BOOL
    kernel.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
    kernel.WaitForSingleObject.restype = w.DWORD
    parent_pid = os.getppid()
    handles = []
    def check(ok):
        if not ok:
            raise ctypes.WinError(ctypes.get_last_error())
    try:
        snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
        check(snapshot not in (None, ctypes.c_void_p(-1).value))
        handles.append(snapshot)
        entry = Entry(); entry.size = ctypes.sizeof(entry)
        check(kernel.Process32FirstW(snapshot, ctypes.byref(entry)))
        parent_parent = None
        while True:
            if entry.pid == parent_pid:
                parent_parent = entry.parent
                break
            if not kernel.Process32NextW(snapshot, ctypes.byref(entry)):
                break
        check(parent_parent is not None)
        def opened(pid):
            handle = kernel.OpenProcess(0x101000, False, pid)
            check(handle); handles.append(handle)
            return handle
        parent, controller, worker = [opened(pid) for pid in (parent_pid, controller_pid, os.getpid())]
        image = ctypes.create_unicode_buffer(32768); size = w.DWORD(len(image))
        check(kernel.QueryFullProcessImageNameW(parent, 0, image, ctypes.byref(size)))
        def created(handle):
            times = [w.FILETIME() for _ in range(4)]
            check(kernel.GetProcessTimes(handle, *[ctypes.byref(value) for value in times]))
            return (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
        def alive(handle):
            # Exit code 259 is also a legal application exit code. Process
            # handles become signaled on exit regardless of the exit code.
            return _process_handle_alive(kernel, handle)
        result = {"parent_parent_pid": parent_parent, "parent_executable": image.value,
                  "parent_executable_sha256": digest(Path(image.value)),
                  "parent_created": created(parent), "controller_created": created(controller),
                  "worker_created": created(worker), "parent_alive": alive(parent),
                  "controller_alive": alive(controller)}
        check(os.getppid() == parent_pid)
        return result
    finally:
        for handle in reversed(handles):
            kernel.CloseHandle(handle)


def controller_parent_matches(controller_pid, executable, executable_sha256):
    if type(controller_pid) is not int or controller_pid <= 0:
        return False
    if os.getppid() == controller_pid:
        return True
    if os.name != "nt":
        return False
    try:
        return _redirector_chain_matches(_windows_parent_info(controller_pid),
                                         controller_pid, executable, executable_sha256)
    except (OSError, ValueError, KeyError):
        return False


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _asset_paths(plan):
    return {a["relative"] for a in plan["engine"]["assets"]}


def pinned_bytes(plan, root, relative):
    asset = next((a for a in plan["engine"]["assets"] if a["relative"] == relative), None)
    require(asset is not None, "engine_asset_pin_required")
    payload = child(root, relative).read_bytes()
    require(hashlib.sha256(payload).hexdigest() == asset["sha256"], "engine_asset_changed")
    return payload


def validate_profile(plan, root):
    """Pure metadata validation. No model import, network, or service start."""
    engine, assets = plan["engine"], _asset_paths(plan)
    options = engine["decoding"]
    require(type(options) is dict, "decoding_profile_required")
    if plan["mode"] == "AUTHORED_FIXTURE":
        require(set(options) == {"fixture_output"} and options["fixture_output"] in assets
                and engine["revision"] == "authored-fixture-v1" and engine["device"] == "synthetic_cpu", "synthetic_profile_required")
        return
    require(engine["revision"] != "authored-fixture-v1" and "fixture_output" not in options, "fixture_cannot_be_real_engine")
    packages = {package_name(k): v for k, v in plan["runtime"]["packages"].items()}
    require(len(packages) == len(plan["runtime"]["packages"]) and all(k in packages and (v is None or packages[k] == v)
            for k, v in REQUIRED_PACKAGES[engine["name"]].items()), "engine_runtime_profile_required")
    if engine["name"] in REVISIONS:
        common = {"model_directory", "render_dpi", "cpu_threads", "min_free_gpu_mib", "min_free_ram_bytes"}
        specific = {"sampling", "prompts"} if engine["name"] == "mineru" else {"prompt", "max_new_tokens", "longest_edge"}
        require(set(options) == common | specific and engine["revision"] == REVISIONS[engine["name"]]
                and engine["device"] == "cuda:0" and options["render_dpi"] == 200 and options["cpu_threads"] == 4,
                "unsupported_vision_profile")
        require(type(options["min_free_gpu_mib"]) is int and options["min_free_gpu_mib"] >= 8192
                and type(options["min_free_ram_bytes"]) is int and options["min_free_ram_bytes"] >= 20 * 1024**3,
                "explicit_resource_reservation_required")
        folder = child(root, options["model_directory"])
        require(folder.is_dir() and not folder.is_symlink(), "model_directory_required")
        files = {f.relative_to(root).as_posix() for f in folder.iterdir() if f.is_file()}
        require(files <= assets and not any(f.suffix in {".bin", ".pt", ".pth"} for f in folder.iterdir()),
                "complete_safetensors_snapshot_pin_required")
        require((folder / "config.json").is_file() and (folder / "tokenizer_config.json").is_file()
                and bool(list(folder.glob("*.safetensors"))), "model_snapshot_incomplete")
        index = folder / "model.safetensors.index.json"
        if index.exists():
            payload = index.read_bytes()
            expected = next(a["sha256"] for a in engine["assets"] if a["relative"] == index.relative_to(root).as_posix())
            require(hashlib.sha256(payload).hexdigest() == expected, "model_index_changed")
            weights = loads(payload)["weight_map"]
            require(set(weights.values()) == {f.name for f in folder.glob("*.safetensors")}, "model_shard_set_mismatch")
        for key in ("sampling", "prompts") if engine["name"] == "mineru" else ("prompt",):
            require(options[key] in assets, "prompt_or_sampling_not_pinned")
        if engine["name"] == "olmocr":
            require(options["max_new_tokens"] == 4096 and options["longest_edge"] == 1288
                    and plan["limits"]["request_tokens"] >= 4096, "unsupported_olmocr_decoding")
        else:
            prompt_bytes = pinned_bytes(plan, root, options["prompts"])
            prompts = loads(prompt_bytes)
            sampling = loads(pinned_bytes(plan, root, options["sampling"]))
            require(hashlib.sha256(prompt_bytes).hexdigest() == engine["prompt_sha256"], "mineru_prompt_hash_required")
            require(type(prompts) is dict and set(prompts) == {"prompts", "system_prompt"}
                    and type(prompts["prompts"]) is dict and set(prompts["prompts"]) == MINERU_KEYS and type(prompts["system_prompt"]) is str
                    and all(type(k) is str and type(v) is str for k, v in prompts["prompts"].items()), "mineru_prompt_shape")
            require(type(sampling) is dict and set(sampling) == MINERU_KEYS
                    and all(type(v) is dict and set(v) == SAMPLING_KEYS and type(v.get("max_new_tokens")) is int
                            and v["presence_penalty"] in {None, 0} and v["frequency_penalty"] in {None, 0}
                            and 0 < v["max_new_tokens"] <= plan["limits"]["request_tokens"] for v in sampling.values()), "mineru_all_calls_bounded")
            require(sum(len(v) for v in prompts["prompts"].values()) + len(prompts["system_prompt"]) <= plan["limits"]["request_characters"], "prompt_character_limit")
    elif engine["name"] == "docling":
        require(set(options) == {"layout_directory", "det_model", "cls_model", "rec_model", "rec_keys", "cpu_threads"}
                and options["cpu_threads"] == 4 and engine["device"] == "cpu" and engine["revision"] == "2.130.0",
                "unsupported_docling_profile")
        folder = child(root, options["layout_directory"])
        require(folder.is_dir() and {p.relative_to(root).as_posix() for p in folder.iterdir() if p.is_file()} <= assets
                and folder.name == "docling-project--docling-layout-heron"
                and (folder / "model.safetensors").is_file(), "docling_layout_not_pinned")
        require(all(options[k] in assets for k in ("det_model", "cls_model", "rec_model", "rec_keys")), "docling_ocr_not_pinned")
    elif engine["name"] == "grobid":
        require(set(options) == {"service_manifest"} and options["service_manifest"] in assets
                and engine["revision"] == "0.9.1" and engine["device"] == "local_docker_cpu", "unsupported_grobid_profile")
        manifest = loads(pinned_bytes(plan, root, options["service_manifest"]))
        require(type(manifest) is dict and manifest.get("docker_executable", {}).get("relative") in assets,
                "docker_executable_pin_required")
    else:
        raise ValueError("unknown_engine")


def _runtime(plan, root):
    actual = {"python_version": platform.python_version(), "packages": {
        name: importlib.metadata.version(name) for name in plan["runtime"]["packages"]}}
    require(actual["python_version"] == plan["runtime"]["python_version"]
            and actual["packages"] == plan["runtime"]["packages"], "loaded_converter_runtime_mismatch")
    if plan["mode"] == "EXPOSED_DEVELOPMENT":
        distributions = list(importlib.metadata.distributions())
        installed = {package_name(d.metadata["Name"]): d.version for d in distributions}
        require(installed == {package_name(k): v for k, v in actual["packages"].items()}, "complete_runtime_package_census_required")
        pinned = {child(root, asset["relative"]) for asset in plan["runtime"]["files"]}
        for distribution in distributions:
            require(distribution.files is not None, "runtime_file_inventory_missing")
            files = {Path(distribution.locate_file(p)).resolve() for p in distribution.files
                     if p.suffix != ".pyc" and "__pycache__" not in p.parts}
            require(files <= pinned, "complete_distribution_files_required")
    return actual


def _network_guard(engine):
    # GROBID uses only its already-running loopback service. Model downloads,
    # hosted inference, consolidation, telemetry and redirects cannot connect.
    def guard(event, args):
        if event == "socket.connect":
            address = args[1]
            allowed = engine == "grobid" and isinstance(address, tuple) and address[:2] == ("127.0.0.1", 18070)
            if not allowed:
                raise RuntimeError("nonlocal_network_forbidden")
    sys.addaudithook(guard)


def _memory():
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        class Status(ctypes.Structure):
            _fields_ = [("length", wintypes.DWORD), ("load", wintypes.DWORD)] + [
                (name, ctypes.c_ulonglong) for name in ("total", "available", "page_total", "page_available", "virtual_total", "virtual_available", "extended")]
        value = Status(); value.length = ctypes.sizeof(value)
        require(ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(value)), "ram_probe_failed")
        return value.available
    return os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")


def _gpu_ready(options):
    result = subprocess.run(["nvidia-smi", "--query-gpu=index,memory.free,utilization.gpu", "--format=csv,noheader,nounits"],
                            capture_output=True, text=True, timeout=10, check=True)
    first = result.stdout.splitlines()[0].split(",")
    require(int(first[0]) == 0 and int(first[1]) >= options["min_free_gpu_mib"] and int(first[2]) <= 5
            and _memory() >= options["min_free_ram_bytes"], "shared_resource_gate_not_ready")


def process_peak_memory():
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [(name, ctypes.c_size_t)
                for name in ("peak_working_set", "working_set", "peak_paged", "paged", "peak_nonpaged", "nonpaged", "pagefile", "peak_pagefile")]
        value = Counters(); value.cb = ctypes.sizeof(value)
        get_process = ctypes.windll.kernel32.GetCurrentProcess
        get_process.restype = wintypes.HANDLE
        get_memory = ctypes.windll.psapi.GetProcessMemoryInfo
        get_memory.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        get_memory.restype = wintypes.BOOL
        require(get_memory(get_process(), ctypes.byref(value), value.cb), "process_memory_probe_failed")
        return int(value.peak_working_set)
    import resource
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value if sys.platform == "darwin" else value * 1024)


def _docling(root, options, page, plan):
    import torch
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.base_models import InputFormat, DocumentStream
    from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions, LayoutOptions
    from docling.datamodel.layout_model_specs import LayoutModelConfig
    from docling.datamodel.accelerator_options import AcceleratorOptions, AcceleratorDevice
    torch.set_num_threads(4)
    opts = PdfPipelineOptions(do_ocr=True, do_table_structure=False, enable_remote_services=False, allow_external_plugins=False)
    opts.ocr_options = RapidOcrOptions(backend="torch", lang=["ch"],
        det_model_path=str(child(root, options["det_model"])), cls_model_path=str(child(root, options["cls_model"])),
        rec_model_path=str(child(root, options["rec_model"])), rec_keys_path=str(child(root, options["rec_keys"])))
    # The pinned resolver joins artifacts_path/repo_id.replace('/', '--').
    opts.artifacts_path = child(root, options["layout_directory"]).parent
    opts.layout_options = LayoutOptions(model_spec=LayoutModelConfig(name="pinned_local_heron",
        repo_id="docling-project/docling-layout-heron", revision="8f39ad3c0b4c58e9c2d2c84a38465abf757272d8"))
    opts.accelerator_options = AcceleratorOptions(num_threads=4, device=AcceleratorDevice.CPU)
    opts.document_timeout = min(180, plan["limits"]["timeout_seconds"])
    converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})
    converted = converter.convert(DocumentStream(name="page.pdf", stream=io.BytesIO(page)))
    document = converted.document.model_dump(mode="json")
    status = "success" if str(converted.status) == "ConversionStatus.SUCCESS" else "error"
    return {"docling": {"status": str(converted.status)}, "docling_document": document}, _json(document), status, {}


def _service_check(root, manifest):
    require(type(manifest) is dict and set(manifest) == {"container", "image_sha256", "files", "docker_endpoint", "docker_executable", "service_jar"}
            and type(manifest["container"]) is str and manifest["container"].isalnum()
            and isinstance(manifest["files"], dict) and manifest["files"], "invalid_grobid_service_manifest")
    require(manifest["docker_endpoint"] == "npipe:////./pipe/dockerDesktopLinuxEngine", "explicit_local_docker_endpoint_required")
    executable = child(root, manifest["docker_executable"]["relative"])
    require(digest(executable) == manifest["docker_executable"]["sha256"], "docker_executable_changed")
    command = [str(executable), "--host", manifest["docker_endpoint"]]
    environment = {k: v for k, v in os.environ.items() if not k.upper().startswith("DOCKER_")}
    def read(arguments, timeout=30):
        return subprocess.check_output(command + arguments, env=environment, text=True, timeout=timeout)
    actual = json.loads(read(["inspect", manifest["container"]], 20))[0]
    require(actual["State"]["Running"] and actual["Image"] == manifest["image_sha256"] and not actual["Mounts"], "grobid_service_identity_mismatch")
    require(actual["HostConfig"]["PortBindings"].get("8070/tcp") == [{"HostIp": "127.0.0.1", "HostPort": "18070"}], "grobid_service_endpoint_mismatch")
    roots = ["/opt/grobid/grobid-home/config", "/opt/grobid/grobid-home/models"]
    paths = set(read(["exec", manifest["container"], "find", *roots, "-type", "f", "-print"]).splitlines())
    require(paths and paths <= set(manifest["files"]) and manifest["service_jar"] in manifest["files"]
            and manifest["service_jar"].endswith(".jar"), "complete_grobid_effective_assets_required")
    for path, expected in manifest["files"].items():
        require(path.startswith("/opt/grobid/") and ".." not in Path(path).parts and "\n" not in path, "unsafe_container_asset_path")
        value = read(["exec", manifest["container"], "sha256sum", "--", path]).split()[0]
        require(value == expected, "grobid_effective_asset_changed")


def _grobid(root, options, page, plan):
    import requests
    manifest = loads(pinned_bytes(plan, root, options["service_manifest"]))
    _service_check(root, manifest)
    session = requests.Session(); session.trust_env = False
    version = session.get("http://127.0.0.1:18070/api/version", timeout=10, allow_redirects=False)
    version.raise_for_status()
    require(version.json()["version"] == plan["engine"]["revision"], "grobid_version_changed")
    response = session.post("http://127.0.0.1:18070/api/processHeaderDocument",
        files={"input": ("page.pdf", page, "application/pdf")}, data={"consolidateHeader": "0"},
        timeout=min(180, plan["limits"]["timeout_seconds"]), allow_redirects=False)
    response.raise_for_status()
    require(response.status_code == 200, "grobid_empty_or_redirect_response")
    raw = response.content
    parsed = ET.fromstring(raw)
    abstract = " ".join(" ".join(item.itertext()) for item in parsed.findall(".//{http://www.tei-c.org/ns/1.0}abstract"))
    _service_check(root, manifest)
    return {"grobid": {"status": "success", "text": abstract}}, raw, "success", {}


def _vision(root, options, page, plan):
    _gpu_ready(options)
    import torch
    import fitz
    from PIL import Image
    from transformers import AutoModelForImageTextToText, AutoProcessor, BitsAndBytesConfig
    torch.set_num_threads(4); torch.manual_seed(2026092502)
    torch.cuda.reset_peak_memory_stats()
    name = plan["engine"]["name"]
    model_path = str(child(root, options["model_directory"]))
    kwargs = {"torch_dtype": torch.bfloat16, "device_map": "cuda:0", "attn_implementation": "sdpa",
              "local_files_only": True, "trust_remote_code": False, "use_safetensors": True}
    if name == "olmocr":
        kwargs["quantization_config"] = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True)
    model = AutoModelForImageTextToText.from_pretrained(model_path, **kwargs).eval()
    processor = AutoProcessor.from_pretrained(model_path, local_files_only=True, trust_remote_code=False)
    generations = capture_generations(model, plan["limits"]["request_tokens"])
    with fitz.open(stream=page, filetype="pdf") as pdf:
        pix = pdf[0].get_pixmap(dpi=200, alpha=False)
        image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    with torch.inference_mode():
        if name == "mineru":
            from mineru_vl_utils import MinerUClient
            from mineru_vl_utils.vlm_client.base_client import SamplingParams
            prompts = loads(pinned_bytes(plan, root, options["prompts"]))
            sampling = loads(pinned_bytes(plan, root, options["sampling"]))
            require(set(prompts) == {"prompts", "system_prompt"} and isinstance(sampling, dict) and sampling,
                    "explicit_mineru_prompts_and_sampling_required")
            require(all(type(v.get("max_new_tokens")) is int and 0 < v["max_new_tokens"] <= plan["limits"]["request_tokens"]
                        for v in sampling.values()), "mineru_token_bounds_required")
            require(sum(len(v) for v in prompts["prompts"].values()) + len(prompts["system_prompt"]) <= plan["limits"]["request_characters"], "prompt_character_limit")
            client = MinerUClient(backend="transformers", model=model, processor=processor, batch_size=1,
                max_concurrency=1, max_retries=0, use_tqdm=False, skip_model_name_checking=True,
                prompts=prompts["prompts"], system_prompt=prompts["system_prompt"],
                sampling_params={k: SamplingParams(**v) for k, v in sampling.items()})
            blocks = client.two_step_extract(image)
            result = {"blocks": [dict(b) if isinstance(b, dict) else vars(b) for b in blocks], "status": "success"}
            require(generations, "mineru_no_generation_observed")
            status = "truncated" if any(row["hit_token_limit"] for row in generations) else "success"
            result["status"] = status
            raw = _json({"blocks": result["blocks"], "generations": generations})
        else:
            image.thumbnail((1288, 1288))
            prompt = pinned_bytes(plan, root, options["prompt"]).decode("utf-8")
            require(hashlib.sha256(prompt.encode()).hexdigest() == plan["engine"]["prompt_sha256"]
                    and len(prompt) <= plan["limits"]["request_characters"], "olmocr_prompt_identity_mismatch")
            messages = [{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image", "image": image}]}]
            rendered = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            inputs = processor(text=[rendered], images=[image], return_tensors="pt").to("cuda:0")
            require(inputs["input_ids"].shape[1] <= plan["limits"]["request_tokens"], "model_input_token_limit")
            output = model.generate(**inputs, max_new_tokens=4096, do_sample=False)
            generated = output[0, inputs["input_ids"].shape[1]:]
            text = processor.decode(generated, skip_special_tokens=True)
            status = "success" if len(generated) < 4096 else "truncated"
            result = {"raw_text": text, "output_tokens": len(generated), "status": status}
            raw = _json({"rendered_prompt": rendered, "rendered_prompt_sha256": hashlib.sha256(rendered.encode()).hexdigest(),
                         "output_token_ids": generated.tolist(), "text": text, "generations": generations})
    return {name: result}, raw, status, {"gpu_peak_allocated_bytes": torch.cuda.max_memory_allocated(),
                                       "gpu_peak_reserved_bytes": torch.cuda.max_memory_reserved()}


def capture_generations(model, token_limit):
    """Observe actual calls before MinerU removes token IDs and stop evidence."""
    original = model.generate
    rows = []
    def generate(*args, **kwargs):
        require(not args and "input_ids" in kwargs, "explicit_generation_inputs_required")
        input_ids = kwargs["input_ids"].tolist()
        maximum = kwargs.get("max_new_tokens")
        require(type(maximum) is int and 0 < maximum <= token_limit and len(input_ids) == 1
                and len(input_ids[0]) <= token_limit, "generation_token_limit")
        output = original(**kwargs)
        output_ids = output.tolist()
        require(len(output_ids) == 1 and output_ids[0][:len(input_ids[0])] == input_ids[0], "unsupported_generation_output")
        generated = output_ids[0][len(input_ids[0]):]
        require(len(generated) <= maximum, "generation_exceeded_limit")
        # Only scalar generation controls; tensor/image data remain hash-bound to
        # the prepared page. Preserve ALL IDs before any decoder filtering.
        controls = {k: v for k, v in kwargs.items() if v is None or type(v) in {str, bool, int, float}}
        rows.append({"input_token_ids": input_ids[0], "output_token_ids": generated, "effective_generate_kwargs": controls,
                     "model_generation_config": model.generation_config.to_dict(), "hit_token_limit": len(generated) >= maximum})
        return output
    model.generate = generate
    return rows


def run(root, plan_descriptor, output):
    root = Path(root).resolve(); out = child(root, output)
    raw_plan = child(root, plan_descriptor["relative"]).read_bytes()
    require(hashlib.sha256(raw_plan).hexdigest() == plan_descriptor["sha256"], "worker_plan_hash_mismatch")
    from src.paper_converter_smoke import validate_plan, code_identity, output_path, exact, descriptor, Inputs, write_output
    plan, snapshots, _ = validate_plan(root, plan_descriptor)
    require(out == output_path(root, output) and not (out / "INVALIDATED.json").exists()
            and not any((out / name).exists() for name in ("worker-result.json", "execution.json", "raw-response.bin", "COMPLETE.json",
                        "docling.json", "docling_document.json", "grobid.json", "mineru.json", "olmocr.json")), "worker_attempt_not_fresh")
    bytecode = out / "unused-bytecode"
    require(sys.pycache_prefix is not None and Path(sys.pycache_prefix).resolve() == bytecode
            and sys.dont_write_bytecode and not bytecode.exists(), "isolated_source_bytecode_required")
    prepared_bytes = Inputs(root).read(descriptor(root, out / "prepared.json"))
    prepared = loads(prepared_bytes)
    require(prepared == {"version": "paper-converter-prepared-v1", "plan": plan_descriptor, "mode": plan["mode"],
                         "input_hashes": dict(snapshots.hashes), "code_identity": plan["code_identity"]}, "worker_preparation_required")
    intent_bytes = Inputs(root).read(descriptor(root, out / "intent.json"))
    intent = loads(intent_bytes)
    exact(intent, {"version", "plan", "started_at", "mode", "attempt", "controller_pid"}, "worker_intent_required")
    require(intent["version"] == "paper-converter-intent-v1" and intent["plan"] == plan_descriptor
            and intent["mode"] == plan["mode"] and type(intent["attempt"]) is int and intent["attempt"] == 1
            and controller_parent_matches(intent["controller_pid"],
                child(root, plan["runtime"]["executable"]["relative"]),
                plan["runtime"]["executable"]["sha256"]), "worker_controller_intent_required")
    runtime = _runtime(plan, root)
    assets = plan["engine"]["assets"] + plan["runtime"]["files"] + [plan["runtime"]["executable"]]
    require(Path(sys.executable).resolve() == child(root, plan["runtime"]["executable"]["relative"]), "wrong_worker_interpreter")
    page_descriptor = {"relative": (out / "page.pdf").relative_to(root).as_posix(), "sha256": plan["page"]["sha256"]}
    def check():
        for asset in assets:
            require(digest(child(root, asset["relative"])) == asset["sha256"], "worker_asset_changed")
        Inputs(root).verify(page_descriptor)
        require(digest(Path(__file__)) == plan["code_identity"]["worker"]
                and code_identity() == plan["code_identity"]
                and Inputs(root).read(descriptor(root, out / "intent.json")) == intent_bytes
                and Inputs(root).read(descriptor(root, out / "prepared.json")) == prepared_bytes,
                "worker_code_or_page_changed")
        require(not bytecode.exists(), "bytecode_cache_appeared")
        snapshots.recheck()
        require(_runtime(plan, root) == runtime, "worker_runtime_changed")
    check()
    page = Inputs(root).read(page_descriptor)
    require(hashlib.sha256(page).hexdigest() == plan["page"]["sha256"], "worker_page_read_mismatch")
    started = dt.datetime.now(dt.timezone.utc).isoformat(); wall = time.monotonic(); cpu = time.process_time()
    name, options = plan["engine"]["name"], plan["engine"]["decoding"]
    _network_guard(name if plan["mode"] == "EXPOSED_DEVELOPMENT" else "synthetic")
    if plan["mode"] == "AUTHORED_FIXTURE":
        raw = child(root, options["fixture_output"]).read_bytes()
        fixture = loads(raw); outputs, status, resources = fixture["outputs"], fixture["status"], {"authored_fixture": True}
    elif name == "docling":
        outputs, raw, status, resources = _docling(root, options, page, plan)
    elif name == "grobid":
        outputs, raw, status, resources = _grobid(root, options, page, plan)
    else:
        outputs, raw, status, resources = _vision(root, options, page, plan)
    check()
    require(len(raw) <= 16 * 1024**2, "bounded_raw_output_exceeded")
    response = out / "raw-response.bin"
    with response.open("xb") as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    def desc(path):
        return descriptor(root, path)
    cache_descriptors = {}
    for key, value in outputs.items():
        require(key in {"docling", "docling_document", "grobid", "mineru", "olmocr"}, "unknown_worker_cache")
        cache = out / (key + ".json"); write_output(root, cache, value); cache_descriptors[key] = desc(cache)
    resources.update(wall_seconds=time.monotonic() - wall, cpu_seconds=time.process_time() - cpu,
                     peak_process_memory_bytes=process_peak_memory(),
                     scope="worker_process_only_excludes_children_grobid_server_other_processes")
    result = {"version": "paper-converter-worker-result-v1", "mode": plan["mode"], "engine": name,
              "revision": plan["engine"]["revision"], "plan_sha256": plan_descriptor["sha256"], "status": status,
              "outputs": cache_descriptors, "raw_response": desc(response), "started_at": started,
              "completed_at": dt.datetime.now(dt.timezone.utc).isoformat(), "runtime": runtime, "resources": resources}
    write_output(root, out / "worker-result.json", result)
    check()
    print(json.dumps({"mode": plan["mode"], "engine": name, "status": status, "outputs": cache_descriptors}), flush=True)
    return 0 if status == "success" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("data-root", "plan", "expected-plan-sha256", "output"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    try:
        return run(args.data_root, {"relative": args.plan, "sha256": args.expected_plan_sha256}, args.output)
    except Exception as exc:
        code = str(exc) if isinstance(exc, ValueError) and re.fullmatch(r"[a-z][a-z0-9_]{0,95}", str(exc)) else None
        print(json.dumps({"status": "WORKER_FAILED", "error": type(exc).__name__,
                          "error_code": code}), file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
