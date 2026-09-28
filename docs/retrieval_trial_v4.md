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

## Review and interpretation

Review f115 and f076 from the original first-page images and native lines.
Report the exact page-one title, abstract, and body lengths alongside their
searchability states. For misses, inspect candidate-stage recall before
attributing failure to the reranker. Record competing relevant documents with
attributed source-first judgments. Do not silently remove unsearchable pages
from the denominator or claim that first-page retrieval measures full-paper
retrieval. Keep all raw text and per-query details outside this repository.
