# Single exposed-page local converter smoke

This incremental #20 tool prepares and executes **one already exposed development
page, with one local engine per attempt**. The actual four-engine smoke has **not
been run**. Authored tests exercise the controller and serialization through
substituted process/network ports; they are not evidence of converter availability,
accuracy, unseen qualification, or GraphRAG completion.

The workflow does not select/open an unseen cohort, alter preregistration, start a
service, download a model, call a paid API, or write a graph. A successful exposed
smoke is a readiness input. The separate [paper qualification protocol](paper_qualification_v1.md)
still controls prospective access, reference review, freeze order and execution.

## Required external inputs

Keep the plan, page, model/runtime manifests, logs and receipts under an authorized
private data root outside this checkout. Paths in descriptors are contained,
forward-slash relative paths; every descriptor is exactly
`{"relative":"...","sha256":"<raw byte SHA-256>"}`. Symlink assets are rejected.
The caller supplies the plan hash and, later, the custodian attestation hash.

`paper-converter-smoke-plan-v1` has these exact fields:

| Field | Required meaning |
| --- | --- |
| `version`, `mode`, `created_at`, `case_id` | Version above; `EXPOSED_DEVELOPMENT` or `AUTHORED_FIXTURE`; timezone-aware time; stable local ID |
| `source`, `page` | Original PDF and isolated physical first page descriptors; their exact 120-DPI rendered pixels must agree |
| `exposure` | Hash-pinned `paper-exposed-source-v1` declaration: `version`, `case_id`, `source_sha256`, `page_sha256`, `scope` equal to mode, actual `attribution`, `recorded_at` no later than plan freeze |
| `engine` | `name`, `revision`, `license`, `device`, ordered `assets` descriptors, `decoding`, `prompt_sha256` (hash or null) |
| `runtime` | `executable` descriptor, `python_version`, complete installed `packages` name/version census, `files` descriptors covering **every declared distribution file except bytecode** |
| `limits` | Positive integer `request_characters`, `request_tokens`, `timeout_seconds` (at most 3600); `retries:0`, `device_concurrency:1`, `crop_policy:"physical_page_one_only"` |
| `code_identity` | Exact result of `src.paper_converter_smoke.code_identity()` in the final frozen tree, including controller, worker and extraction import closure |
| `configuration_sha256`, `evaluation_runtime_sha256`, `evaluation_code_sha256` | Explicit future evaluator/configuration pins; these do not claim that the model runtime is the native evaluator runtime or authorize a prospective run |

The runtime census can be collected with the selected interpreter's stdlib
`importlib.metadata.distributions()`, `distribution.files`, and
`distribution.locate_file()`, without importing an engine. Stream-hash each
non-bytecode file, the interpreter and additional interpreter/native support
files into the manifest. Preserve package `METADATA`, `WHEEL` and `RECORD`.
The worker independently requires the full installed package census and every
declared non-bytecode distribution file before importing an engine, then hashes
the manifest again after execution. An arbitrary unrelated pinned file is
insufficient. This is an explicit local runtime inventory, not a signed software
supply-chain attestation.
The worker starts with `-I -B` and a fresh absent `-X pycache_prefix` under its
attempt directory. Both ends require that prefix to remain absent. `-B` alone
would still read existing, unpinned bytecode; the isolated prefix ensures imports
use pinned source without modifying shared environment caches.

The worker verifies the controller PID recorded in the durable intent. Windows
virtual environments can insert a launcher between that controller and the
interpreter. This one extra hop is accepted only when the launcher uses the
exact pinned executable and hash, its parent is the controller, both processes
remain alive, and their creation times match the launch order. Process handles
are checked with a zero-timeout wait; an exit code of 259 does not establish
liveness. Unavailable process metadata fails closed. Other parent chains remain
unsupported. Worker failures include a bounded `error_code` for known contract
checks; arbitrary exception text and private paths are excluded.

The exposure declaration and custodian readback are attributed, externally pinned
local records. They are **unsigned assertions**, not independent human review or
unforgeable proof that a particular person inspected the evidence. The application
must supply honest attribution and authorized inputs.

## Supported real profiles

All model assets need fresh full-file hashes before the real call; header-only or
historical download hashes are insufficient. No real plan is supplied in the
repository because private assets and the final runtime/code pins must be checked
at the actual call boundary.

| Engine | Exact supported profile |
| --- | --- |
| Docling | `docling==2.130.0`, `docling-ibm-models==4.0.3`, `rapidocr==3.9.2`, CPU four threads; local Heron revision `8f39ad3c0b4c58e9c2d2c84a38465abf757272d8`; explicit RapidOCR detector/classifier/recognizer/dictionary assets; OCR on, table inference off |
| GROBID | Already-running local Docker service 0.9.1, loopback port 18070; exact image, container, Docker executable, complete effective config/model files and service JAR hashes |
| MinerU | Local `opendatalab/MinerU2.5-2509-1.2B` revision `1aa090b41282e64fadd79c10572221f91ec21924`; `mineru-vl-utils==2.0.5`, Transformers 4.57.6, Torch 2.8.0+cu128, BF16 SDPA; page render 200 DPI; one crop generation at a time |
| olmOCR | Local `allenai/olmOCR-2-7B-1025` revision `e52d6f090b7a9007afffbbd6ce510876222fea93`; Transformers 4.57.6, Torch 2.8.0+cu128, bitsandbytes 0.50.2; NF4 double quantization/BF16 compute, SDPA; page render 200 DPI resized within 1288 pixels; deterministic maximum 4096 generated tokens |

Vision profiles require PyMuPDF 1.28.2 and Pillow 12.3.0. Their `decoding` fields
are `model_directory`, `render_dpi:200`, `cpu_threads:4`,
`min_free_gpu_mib` (at least 8192), and `min_free_ram_bytes` (at least 20 GiB),
plus the engine-specific fields below. These are conservative **local scheduling
gates**, not measured peak requirements or a guarantee against out-of-memory.
GPU utilization must be at most 5% at the call boundary. The tool does not evict
other workloads, reserve the GPU globally, or restart WSL. Coordinate the resource
window with its owner before executing.

- Docling decoding: `layout_directory`, `det_model`, `cls_model`, `rec_model`,
  `rec_keys`, `cpu_threads:4`. Stage the pinned layout files in
  `<artifacts>/docling-project--docling-layout-heron/`. The adapter supplies the
  **parent** as `artifacts_path`, with the canonical repository ID and fixed
  revision. An absolute local `repo_id` is not the installed resolver's offline
  contract. Conversion receives the already hashed page bytes as `DocumentStream`.
- GROBID decoding: `service_manifest`. Its exact fields are `container`,
  `image_sha256`, `files` (container-path/hash map), `docker_endpoint`,
  `docker_executable` descriptor and `service_jar`. The Docker executable is also
  an engine asset. Only `npipe:////./pipe/dockerDesktopLinuxEngine` is supported;
  inherited Docker endpoint/context variables are removed. Config/model file
  enumeration and hashes plus the configured service JAR are checked before and
  after the request. The container must have no mounts and the exact loopback
  port binding. The actual effective service inventory/JAR path remains a
  **pre-call input**, not a guessed filename. No start/restart command exists.
- MinerU adds `prompts` and `sampling` asset paths. The prompt JSON has `prompts`
  and `system_prompt`; both prompt and sampling role maps have exactly `table`,
  `equation`, `image`, `chart`, `[default]`, `[layout]`, `[cross_page_table_merge]`.
  Every sampling role explicitly supplies `temperature`, `top_p`, `top_k`,
  `presence_penalty`, `frequency_penalty`, `repetition_penalty`,
  `no_repeat_ngram_size`, `max_new_tokens`. Ignored presence/frequency penalties
  must be null/zero. `prompt_sha256` is the entire pinned prompt JSON hash.
  Each real `generate` call records input/output token IDs, effective scalar
  controls and generation config before MinerU strips special tokens. Missing
  bounds or excess input tokens fail; hitting any output cap is `truncated`.
- olmOCR adds `prompt`, `max_new_tokens:4096`, `longest_edge:1288`.
  `prompt_sha256` binds exact UTF-8 prompt bytes. Rendered chat prompt, actual
  token IDs and effective generation controls are retained.

All engines use network-denial guards; GROBID alone may connect to its fixed
loopback HTTP endpoint with redirects and consolidation disabled. Hugging Face
offline flags and `local_files_only=True` apply to vision loaders. No remote code
is trusted. These controls constrain this supported adapter, not arbitrary hostile
native code or an untrusted Docker daemon.

## Durable commands

Run the controller in the pinned PDF validation interpreter; the plan specifies
the separate engine interpreter. Use a new private output directory per engine.

```powershell
python -m src.paper_converter_smoke prepare --data-root $dataRoot --plan plans/docling.json --expected-plan-sha256 $planSha --output smoke/docling-01
python -m src.paper_converter_smoke execute --data-root $dataRoot --plan plans/docling.json --expected-plan-sha256 $planSha --output smoke/docling-01
python -m src.paper_converter_smoke verify --data-root $dataRoot --plan plans/docling.json --expected-plan-sha256 $planSha --output smoke/docling-01
```

`prepare` checks inputs and copies the first page without importing a model.
`execute` is the explicit effect boundary. One OS lock per data root prevents
concurrent attempts in this workflow. An immutable root attempt registry also
blocks a new output directory while any prior registered intent is unresolved or
invalidated, even after a crashed controller releases the OS lock. Terminal
execution receipts must reverify before another engine may start. The controller writes `intent.json` before
launching the isolated worker. Existing matching `execution.json` is reverified,
never reexecuted. An intent without a terminal receipt is an **unknown outcome**:
it cannot be retried automatically, even if a partial cache exists. Preserve the
directory and manually reconcile the exact worker/PID and service state before
authorizing a separate attempt. There is no automatic registry-clear or
reconciliation-success command in this slice. The tool never adopts legacy converter caches.
On timeout it terminates only its owned worker process; it cannot infer that a
GROBID server-side request stopped, and it marks the attempt invalid.
Worker receipts report elapsed/CPU time and peak process memory; GPU receipts
also report allocator peaks. These measurements explicitly exclude child
processes, the external GROBID server and other workloads.

After checking actual execution, assets, raw output, logs and terminal status,
the custodian supplies a separate hash-pinned record with exactly:

```json
{
  "version": "paper-converter-custodian-readback-v1",
  "execution_sha256": "<actual execution.json byte hash>",
  "custodian": "<actual attributed reviewer>",
  "reviewed_at": "<timezone-aware time after worker completion>",
  "actual_engine_execution_confirmed": true,
  "assets_and_raw_outputs_checked": true,
  "independent_human": false,
  "mode": "EXPOSED_DEVELOPMENT"
}
```

```powershell
python -m src.paper_converter_smoke finalize --data-root $dataRoot --plan plans/docling.json --expected-plan-sha256 $planSha --output smoke/docling-01 --attestation reviews/docling.json --expected-attestation-sha256 $reviewSha
python -m src.paper_converter_smoke verify-readiness --data-root $dataRoot --plan plans/docling.json --expected-plan-sha256 $planSha --output smoke/docling-01 --attestation reviews/docling.json --expected-attestation-sha256 $reviewSha
```

Only a successful exit-zero actual engine execution plus that attributed readback
can yield `paper-local-readiness-v1`. It uses the evaluator's existing exact wire
fields. Authored mode instead emits **`synthetic-paper-local-readiness-v1`**, which
cannot satisfy the evaluator's real readiness contract. Finalization rechecks all
inputs, artifacts and code before/after writing immutable `COMPLETE.json`;
publication drift preserves evidence and writes `INVALIDATED.json`. Verification
requires completion, rejects invalidation, replays evidence and writes nothing.

The pure `validate_prospective_execution` API validates the existing
`paper-converter-execution-v1` **shape only**. This wrapper neither issues that
prospective receipt nor supplies the preregistered access/review/chronology
authority. Future production of such receipts must bind actual engine output to
the frozen evaluator inputs and source-first workflow; renaming an exposed smoke
receipt is invalid. #20 remains open.

## Verification

```powershell
python -m unittest tests.test_paper_converter_smoke -v
python tools/run_validation.py
python tools/validate_package.py
```

Tests cover immutable preparation, all four authored output shapes, unknown
outcomes/no retry, worker intent, truncation, forged claims/attribution, synthetic
mode separation, hash/path changes, an actual stale-bytecode import challenge,
orphan-controller concurrency and postpublication invalidation. Real-PDF
first-page equivalence uses a generated two-page fixture and skips only when the
optional PyMuPDF dependency is absent. No test imports a real model or starts a
service. Model correctness and four-engine compatibility remain unmeasured.
