# Source-bound retrieval trial

This trial ranks a fixed document set for a fixed query set. It does not admit
evidence to the graph. Keep original PDFs, labels, model snapshots, extracted
fields, and full rankings in the authorized external data root.

## Inputs and ordering

1. Generate the immutable 10,000-document fields manifest from the pinned
   original PDFs and the final native extractor. Check the field receipt and
   count all documents, including pages with no usable native text.
2. Freeze the query IDs and text before evaluating any target labels. The
   `ranking_inputs_sha256` binds only ID and text; `evaluation_labels_sha256`
   binds ID and target separately. A target-only edit must leave candidate
   pools and reranked order unchanged.
3. Build the local SPECTER2 discovery cache using `python -m
   src.parallel_source_v4.specter2_cache` with `--data-root`, `--fields`,
   `--queries`, `--model-root`, `--model-manifest`, and `--output` paths relative
   to that root. The producer requires a complete hash manifest for a local
   base model and distinct paper/query adapters, 512-token input limit,
   normalized CLS vectors, and cosine ranking. It loads no remote code or
   remote model files. Every vector checkpoint has an immutable batch receipt
   binding its exact bytes, text inputs, and protocol. A checkpoint without
   its receipt is held for investigation; resume in a new output directory.
   Documents with neither a title nor an
   abstract stay in the 10,000-document denominator but are masked from the
   dense ranking; the cache lists their IDs and count.
   The [SPECTER2 base model card](https://huggingface.co/allenai/specter2_base)
   and [adhoc query adapter card](https://huggingface.co/allenai/specter2_adhoc_query)
   identify the Apache 2.0 license and the paper/query adapter pairing.
4. Evaluate the frozen lexical, dense, and page candidate channels at the
   recorded depth, then rerank their union with a locally pinned reranker.
   Report each channel's candidate recall, union recall, final recall and MRR,
   runtime, missing text, converter errors, and source/field hashes. Reranker
   output must bind its exact model files and inputs in the private receipt.
   The pinned [MS MARCO MiniLM cross-encoder model card](https://huggingface.co/cross-encoder/ms-marco-MiniLM-L6-v2)
   lists the Apache 2.0 license; use only the verified local safetensors snapshot.

The SPECTER2 cache uses `ranking-inputs-v2`: target labels are excluded from
ranking inputs. Legacy caches without that version remain accepted only when
their full query records, including targets, match exactly. An unsupported
binding version fails closed. The cache is a ranking aid; a high similarity
score never supplies a source quote or graph-publication authority.

## Freeze and run an empirical receipt

`src.parallel_source_v4.retrieval_trial` wraps the existing producer and
reranker. Generate fields on the final implementation tree first: the wrapper
requires the field receipt's entire module map to equal the current module
map. Its new module therefore also requires a new field build. Use the pinned
PDF environment for fields and a separate, unchanged local model environment
for this wrapper. The model environment needs PyTorch, Transformers, adapters,
NumPy, tokenizers, safetensors and sentence-transformers; freezing records all
their installed versions and both interpreter file hashes. It does not install
packages or fetch models.

Freeze the full 10,000-document/60-query configuration before scoring. All paths
below except `--source-root` are relative to the authorized external data root;
the protocol is private because it records that source root. Use new output
names. The `freeze` command verifies every original PDF and saved page, image
and native JSON against the preparation manifest. It also checks exact field
and query identities, code, runtime and all installed model files.

```sh
python -m src.parallel_source_v4.retrieval_trial freeze \
  --data-root /authorized/TRACE-GC_RealPaper_Test \
  --source-root /authorized/original-pdfs \
  --preparation-manifest runs/preparation/manifest.json \
  --fields runs/final-fields.json \
  --queries validation_expanded200/queries.json \
  --dense-model-root models/specter2 \
  --dense-model-manifest protocol/specter2-model.json \
  --reranker-directory models/reranker \
  --reranker-manifest protocol/reranker-model.json \
  --cpu-threads 4 --without-dense-ablation \
  --output runs/trial-protocol.json
```

Keep the printed protocol file SHA-256 outside the file itself and supply it
explicitly when running. The original expanded-200 query file contains 60
queries; the earlier `validation_200_10k/retrieval_queries.json` contains a
different set and is not interchangeable. Query IDs must be explicit, and every
target must exist in the unchanged corpus denominator.

```sh
python -m src.parallel_source_v4.retrieval_trial run \
  --data-root /authorized/TRACE-GC_RealPaper_Test \
  --protocol runs/trial-protocol.json \
  --expected-protocol-sha256 <externally-recorded-64-hex-file-hash> \
  --output runs/trial-UNIQUE
```

The wrapper uses CPU only, four PyTorch/BLAS threads and one PyTorch interop
thread. The existing dense producer sets four threads explicitly, so other
thread budgets are rejected. Dense batches contain 16 inputs and each channel
contributes at most 50 candidates. The cross-encoder scores the actual union,
then scores it again after rotating only the target labels by one position.
The same dense cache is used for both passes. Success requires identical query
ranking-input hashes, candidate pools, dense-cache identity and final ranking
hashes, with different evaluation-label hashes. This is an empirical check;
unit-test scorers do not substitute for the local model on the real corpus.
Each reranker call records a hash of its exact input pairs and the returned
scores, enabling private readback without exposing text in public reports.
Every full ranking is retained and its order is checked against the evaluator's
ranking hash, including its rule that tied scores retain candidate-pool order.

`--without-dense-ablation` freezes one supported additional condition: the
existing evaluator with its optional dense cache omitted and the same fields
and reranker. A page-channel removal or historical-field-policy ablation is
not implemented by this wrapper and remains explicit in the receipt. No
channel or field is silently relabeled to claim those comparisons.

Source/page/image/native files are verified at run start and immediately before
completion. Parsed JSON and its file hash use the same byte buffer. Model,
field, query, code and runtime identities are checked after dense production,
after model loading, after each evaluation and again at publication. Saved
dense artifacts and measured outputs also undergo final readback. Modified
inputs or an unavailable runtime produce a redacted `BLOCKED` receipt; a
ranking change under target permutation produces `FAIL`. Intermediate result
files explicitly remain pending until `receipt.json` says `COMPLETE`.

The receipt records total wall/current-process CPU time and separate dense
production and reranker-load timings, including elapsed time on failed loads.
Each evaluation also records its measured ranking-stage times. It records the operating
system's lifetime peak resident memory for the wrapper process, including its
model threads. It does **not** claim host-wide or child-process memory. This
scope includes preflight work and model loading; it is not an isolated model
benchmark. All calls use local model files and produce no graph writes.

The wrapper refuses to reuse an output directory. An interrupted directory is
retained for diagnosis; start a new wrapper run rather than treating a partial
receipt as complete. Its dense checkpoints remain individually bound, but this
wrapper does not claim whole-experiment resume support. A numerical `COMPLETE`
receipt does not close the issue: attributed relevance judgments, miss
classification, f115/f076 source readback and the required comparable ablations
remain separate deliverables. `issue_acceptance_complete` stays false.

## Review and interpretation

Review f115 and f076 from the original first-page images and native lines.
Report the exact page-one title, abstract, and body lengths alongside their
searchability states. For misses, inspect candidate-stage recall before
attributing failure to the reranker. Record competing relevant documents with
attributed source-first judgments. Do not silently remove unsearchable pages
from the denominator or claim that first-page retrieval measures full-paper
retrieval. Keep all raw text and per-query details outside this repository.
