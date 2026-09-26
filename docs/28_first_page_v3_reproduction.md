# Reproduce the v3 patch without publishing unreviewed evidence

> For the completed checkout replay and its failed preservation gate, see [the integration report](29_first_page_v3_integration.md). The patch-application and blocked-gate instructions below describe the original handoff.

See [the report and limitations](27_first_page_source_v3.md). All new methods are experimental. The 200-page set is regression-only; no new real-paper accuracy results accompany this patch.

## Apply to the pinned public history

Use a checkout with authorized write access and its existing SSH signer. Do not copy a private key into this package or a chat. The delivered archive contains `first-page-v3.patch` and a `changes/` overlay, **not a full repository**. Apply the patch, not both representations.

```sh
git status --short
git remote -v
git branch --show-current
git fetch origin main
git rev-parse origin/main
# The patch was prepared against:
# 02e9c1fc530bec1b9a766caa4282ada2e5b957bf
# If main moved, inspect/reconcile the new main before applying. Preserve unrelated work.
git switch -c fix/first-page-source-bound-v3 origin/main
git apply --check /path/to/first-page-v3.patch
git apply /path/to/first-page-v3.patch
```

`review/first_page_v3/change_manifest.json` records the two modified preimages and the added files. It is a scoped manifest, not a replacement for the repository root `MANIFEST.json`. Frozen v1/v2 and admission code are not changed. Preserve their original bytes/line endings for the recorded method hashes.

## Focused tests and full checkout gates

The new selector/lexical logic uses the standard library. Real-PDF fixtures additionally need PyMuPDF; those tests explicitly skip when it is absent. It was present for the delivered focused run. The optional real local reranker needs PyTorch, Transformers and an authorized local safetensors snapshot; none is downloaded automatically. Keep project dependency versions pinned in the local environment and record them for empirical runs.

```sh
python -m unittest discover -s tests -p '*v3*.py' -v
python -m unittest discover -s tests -p 'test_pdf_structure.py' -v
python tools/run_validation.py
python tools/validate_package.py
python -m compileall -q trace_gc/pdf_source_v3.py src/abstract_validation_v3 tests tools/package_project.py
```

The delivered focused run has 80 passing tests and the exact frozen-v2 file has six. The broader supplied runtime result is explicitly scoped to a reconstructed reference runtime; **run all current-main tests again on this real checkout**. Do not promote the supplied partial-snapshot count into a current-main check result. The external pinned legacy conformance, model, deployed-backend, calibration and review gates remain distinct.

## Authorized data root and immutable regression replay

Set `TRACE_GC_TEST_DATA_ROOT` or pass `--data-root`. The default is the sibling `TRACE-GC_RealPaper_Test`. Data roots and private output directories inside the checkout are rejected. No `.env` loading occurs.

The external `source-map.json` maps each original source SHA-256 to a relative PDF path beneath the authorized data root. Do not put machine-specific absolute paths into the map. Original source bytes, retained first-page PDFs, renders and native reference blocks must match their public hashes.

Preserve the historical layout under that root: `validation_v2/` caches for prior100; `validation_expanded200/` for the expanded manifest, labels, protocol, reference freeze and saved assessments. Each retained page folder has `receipt.json`, `page.pdf`, `page.png`, `lines.json`, and `reference_blocks.json`. Cached Docling, GROBID, MinerU, olmOCR and current-baseline files are read in place. The harness only imports frozen offline selector functions; it does not call the active corpus worker or paid provider clients.

```sh
python -m src.abstract_validation_v3.evaluate \
  --data-root /authorized/TRACE-GC_RealPaper_Test \
  --source-map /authorized/source-map.json \
  --out /authorized/experiments/source-v3-regression-run01
```

Use a new versioned output directory for every run. Changed receipts cannot overwrite prior ones; even a repeated run with a different timestamp/timing must use a new directory. First verify the original five method hashes and reference/manifest bindings. Every saved six-pipeline assessment is replayed and compared, then v3 results are written separately. Any failed hash, failed saved-assessment replay or missing source blocks a full-200 aggregate. The command returns 2 unless the run completes and the preserve-91 gate passes. Inspect its per-case ledger and source artifacts before changing policy or references. Do not claim improved precision from a smaller successful subset.

The new primary is native-source-first with Docling/GROBID corroboration. MinerU/olmOCR wrappers require the same selected source interval to be supported by their conversions. These are different versioned methods, not retrospectively altered frozen baselines. Automatic fallback remains disabled.

## Freeze new references before opening predictions

First create an external input manifest containing only `id`, canonical `work_id`, and relative `source_path` for genuinely unexposed papers. Exclude previous work identities and versions, not just identical PDF bytes. A reviewer must actually determine prior exposure; software overlap checks alone do not prove novelty.

```sh
python -m src.abstract_validation_v3.prepare \
  --data-root /authorized/new-paper-cohort \
  --manifest /authorized/new-paper-cohort/input-manifest.json \
  --out /authorized/new-paper-cohort/source-views
```

Review the original page-one images and native intervals **before** opening predictions. `prepare` reads physical page zero only and emits no prediction. Its output manifest binds source, first-page serialization, image and native-line bytes. Keep the pinned PyMuPDF version; serialization/render hashes can change across versions.

An external reviews object is keyed by source ID. Each review contains `status` (`complete`, `partial_on_page_one`, `no_abstract_text`, or `uncertain`), exact `text`, and `spans` with native `line_id`, `physical_page: 1`, `start`, `end`, exact `text`, and containing-line `bbox`. It also contains the four source/page/image/native-line hashes from the prepared manifest, `reviewer`, `reviewer_kind` (`assistant` or `human`), a timezone-qualified `reviewed_at`, `prediction_seen: false`, `image_reviewed: true`, and `native_spans_reviewed: true`. Mark math notation cases explicitly. Empty/absent references must not contain abstract text.

Do not falsely sign these declarations on a person's behalf. An assistant review must say assistant. These attestations do not establish independent human validation.

```sh
python -m src.abstract_validation_v3.freeze freeze \
  --data-root /authorized/new-paper-cohort \
  --manifest /authorized/new-paper-cohort/source-views/source_manifest.json \
  --reviews /authorized/new-paper-cohort/source-reviews.json \
  --seen-manifest /authorized/TRACE-GC_RealPaper_Test/validation_expanded200/manifest.json \
  --seen-hashes review/first_page_expanded200/source_hashes.json \
  --out /authorized/new-paper-cohort/freeze-v3-01

python -m src.abstract_validation_v3.freeze evaluate \
  --data-root /authorized/new-paper-cohort \
  --frozen /authorized/new-paper-cohort/freeze-v3-01 \
  --out /authorized/new-paper-cohort/evaluation-v3-01
```

This fresh-cohort entry point explicitly names its method `source_v3_native_only`. Do not conflate it with the Docling/GROBID-correlated regression pipeline. It uses the same scoring definition but a different declared input path. To compare a full model-backed policy, freeze that identical pipeline and its conversion/model identities on the new cohort too. Keep cohort reports separate, retain the original reference freeze, and acquire independent labels before policy promotion.

## Fields, query-blind candidates and optional local reranking

Use a frozen source manifest and an authorized source map for the **whole** evaluation catalog. There is no known-target pool insertion. Image-only documents enter a review queue until an actual first-page image transcription is supplied. The image-review wrapper contains `image_path`, `render_dpi` (default 120), and a `review` object. Its sealed review binds the current source/page/image hashes, physical page 1, reviewer kind/name/time, `source_image_reviewed: true`, `title`, and transcribed `text`. `review_sha256` is `digest(review_without_review_sha256)` using the v3 canonical digest. The source wrapper reproduces the page image before accepting the transcription as retrieval-only metadata.

```sh
python -m src.abstract_validation_v3.retrieval_experiment fields \
  --data-root /authorized/corpus \
  --manifest /authorized/corpus/frozen-catalog.json \
  --source-map /authorized/corpus/source-map.json \
  --out /authorized/experiments/v3-fields-01

python -m src.abstract_validation_v3.retrieval_experiment evaluate \
  --fields /authorized/experiments/v3-fields-01/fields.json \
  --queries /authorized/frozen-queries.json \
  --out /authorized/experiments/v3-candidates-01
```

The candidate-only run leaves reranker metrics null. The new lexical path is BM25 with repeated title/abstract weighting plus an independent full-page BM25 channel, not the old tuned BM25F. Each query row supplies `query_id`, `text`, `target_id`; target IDs are consulted only for post-generation metrics. Cached SPECTER2 rankings are optional and must bind the exact `fields_sha256`, `queries_sha256`, channel `specter2`, and a model revision. Outdated embeddings from old fields are rejected.

For real local scores, supply an external snapshot with `config.json`, tokenizer inputs and safetensors weights, plus an external manifest containing a 40-hex `model_revision` and `files` mapping every snapshot-relative file to its SHA-256. Resolve cache symlinks into a separate authorized snapshot first; do not put it in Git. The manifest pins actual bytes but does not independently prove a claimed upstream revision. The loader uses local files only, refuses remote model Python/pickle weights, and runs a single-logit cross-encoder on CPU. Missing optional libraries/weights are an unavailable gate, never a reason to fetch a model implicitly.

```sh
python -m src.abstract_validation_v3.retrieval_experiment evaluate \
  --fields /authorized/experiments/v3-fields-01/fields.json \
  --queries /authorized/frozen-queries.json \
  --local-model-dir /authorized/model-snapshots/local-cross-encoder \
  --local-model-manifest /authorized/model-manifests/cross-encoder.json \
  --out /authorized/experiments/v3-local-rerank-01
```

Alternatively provide externally generated score receipts using `--rerank-receipts`; each query's receipt must bind the exact candidate receipt, exact query/document pairs, model revision and complete score vector. Do not mix live local scoring and cached scores in the same invocation. Report candidate coverage, candidate ordering and reranker ordering separately, including unjudged competitors. f020's first-ranked result still needs source relevance judgement.

## Public source archive and signed GitHub delivery

Review the actual diff and untracked paths. Keep private source PDFs, renders, parser outputs, weights and `.env` data external. The packager defaults to tracked files, rejects symlinks and unsafe file signatures, and does not include nested archives or wheels. Stage only reviewed implementation/test/report files before generating a full source archive, so new intended source files are in the tracked listing.

```sh
git diff --check
git diff --stat
# Review every change and stage the exact paths from change_manifest.json.
# Do not use a blanket add of private/unreviewed files.
python tools/package_project.py --output /authorized/releases/jraphyte-source-v3.zip
python tools/package_project.py --audit /authorized/releases/jraphyte-source-v3.zip
# Review and stage the refreshed root MANIFEST.json and approved validation receipts.
test "$(git config --get gpg.format)" = ssh
test -n "$(git config --get user.signingkey)"
git commit -S -m "Add source-bound first-page v3 proposals and local retrieval gates"
git verify-commit HEAD
git push -u origin fix/first-page-source-bound-v3
gh pr create --base main --head fix/first-page-source-bound-v3 --body-file /path/to/PR_BODY.md
gh pr checks --watch
# Inspect review decision, mergeability, required checks, and any new main changes.
# Merge only when those gates allow it; do not use an admin override.
gh pr merge --merge
git switch main
git pull --ff-only origin main
git rev-list --left-right --count main...origin/main
git status --porcelain
```

Verify the merged commit and its hosted signature/checks against the PR, not merely against the pre-existing main commit. Zero divergence and a clean worktree must be observed after synchronization. A private mirror must not be pushed without explicit authorization and verification that it shares the public history. This package does not claim any of these remote writes happened.
