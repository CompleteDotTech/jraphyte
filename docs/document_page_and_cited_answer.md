# Document-page evidence and held cited answers

The physical-first-page abstract benchmark stays scoped to page one. For an
authorized whole-document pilot, `trace_gc.paper_ingestion.reviewed_page_source`
creates an immutable `source` record from an exact substring of native text on
any physical PDF page. It reads one immutable PDF byte snapshot, renders the
chosen page at 144 dpi, records the raw document and page-image hashes, and
checks the full native page text hash. The caller must supply an attributed
review with all four source checks passed. This API does not conduct the visual
review or publish to the graph.

The new `reviewed-native-pdf-page-v1` source representation includes
`page_lineage`: physical page, full native page hash, source substring offsets,
rendered page hash, reviewer and review time. `Catalog.evidence(source_id,
start, end)` then uses exact Unicode code-point offsets **inside the selected
source representation**. `verify_page_source(source, pdf_bytes=...)` reopens the
original PDF and checks the page rendering and native substring. Revisions
require new source records and new review; no record is edited in place.
Reviewed OCR text continues to use the separate
`reviewed-image-transcription-v1` representation and image-evidence contract.

`trace_gc.paper_answer.draft_answer` consumes a canonical `GraphRAGQueryService`
context, an application-owned **current** access policy, current durable graph
state and a caller-supplied pinned model adapter. It verifies citations against
canonical evidence before sending the prompt and rechecks graph version, source
status and access after the model returns. It retains the exact prompt/response
bytes in the private draft and accepts only a strict JSON shape with explicit
evidence IDs. A missing source or invalid citation fails closed; a model
abstention contains no answer claims. A draft with claims remains
`REVIEW_REQUIRED`.

`trace_gc.local_generation.LocalQwenAdapter` is one optional local adapter. It
checks a complete file-hash manifest for the pinned
`Qwen/Qwen3-4B-Instruct-2507` snapshot before loading Transformers with
`local_files_only=True` and remote code disabled. CPU is the default; GPU use
must be explicit. It enforces input/output token caps and returns raw bytes to
the strict answer parser. The application must retain the exact manifest and
runtime identity in its private run receipt. A local model's valid JSON shape
does not establish factual support. The
[official model card](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507)
lists its license and intended use; the local file manifest is the execution
identity used here.

`review_answer` requires the original draft SHA-256 from a durable checkpoint,
reparses the model response, reconstructs the prompt and rechecks current
source status and application access. An attributed reviewer supplies one
actual support judgment per claim. A citation identity match alone does not
establish entailment. The review receipt records `SUPPORTED` only when every
claim is judged supported; it otherwise records `REJECTED_UNSUPPORTED_CLAIM`.
Both drafts and reviews carry the graph version and source-status hash. A
serving application must revalidate them against current access and source
state before each display; withdrawals invalidate earlier live answers.

These components do not constitute the #23 end-to-end pilot. The remaining
application harness must persist checkpoints, enroll trust and reviewers, run
actual semantic observations, compile/review/publish through `CompilerService`,
reopen the durable graph, retrieve it, invoke the pinned model and measure
source support on authorized real papers. Synthetic unit tests establish only
the contract mechanics.
