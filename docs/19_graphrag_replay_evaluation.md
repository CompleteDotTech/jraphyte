# Retrieval replay, evaluation, ablations and research protocol

Implementation: `trace_gc/replay.py`, `trace_gc/retrieval/{evaluation,benchmark}.py`.

## Retrieval-aware replay

`replay_retrieval(retriever, original_result_id, changes, synthesize=None)` appends a retrieval replay branch. It can change strategies, hop/path/context budgets, vector/community participation, historical flags, graph snapshot and ranking policy. Tenant, requesting role and candidate binding cannot be silently changed.

By default replay requests the original graph version, while current permissions remain authoritative. The record stores original/replayed result IDs and versions, changed parameters, added/removed context IDs and the hashes of previous observations. An optional synthesis callback emits **new** observations under the new context. Previously recorded model answers are never relabeled as answers to a different retrieval request. Replay cannot authorize or commit a mutation.

Historical availability depends on the adapter journal and retained source material. A versioned in-memory graph without history cannot fabricate past source/decision presence. Erasure or revoked permissions can make a historical replay unavailable. Report that failure instead of substituting current evidence.

## Reproducibility manifest

The immutable chain binds graph snapshot/version/hash, structured query and filters, retrieval algorithm/strategy versions, embedding version, adapter version, ranking version, context budgets, ACL/version/epochs, cache key/version/hit state, source snapshots, Jev version, question-set version, materializer/packing policy, resolver version, constraint schema hash and policy/qualification context. `retrieval_fingerprint` participates in packing policy and exact input/wire hashes, so an old qualification cannot silently cover a changed retrieval configuration.

`source_retrieval_ids` are the hybrid `retrieval-result` IDs; their graph and source projections are one auditable result, not a duplicated source IR. `evidence_closure_id` derives from the existing exact closure hash. The resolver combines the actual observation lineages. Mutation plans retain those decisions through their existing operation references and protect all required source epochs.

## Metrics

`retrieval_metrics` computes precision@k, recall@k, MRR, graded nDCG@k, entity/path/evidence/contradiction/provenance recall, item redundancy, evidence-level redundancy, novelty and saturation. Precision@k uses the declared k denominator even when fewer results are returned. Duplicate item IDs do not inflate relevance counts. A missing gold denominator is `None`, not a fabricated perfect score. Item/path/provenance gold targets must be labeled at the appropriate representation level.

`synthesis_metrics` supports graph precision/recall/edge F1, entity-resolution accuracy, false merge/split rates, unsupported assertion rate, contradiction handling, abstention quality and review volume. `efficiency_metrics` records retrieval/Jev/total latency, graph/vector query counts, context sizes, tokens, logical work, expansions and per-accepted/per-resolved work. Monetary cost is explicitly unmeasured without a metered provider. Empty denominators are nullable.

The runtime expansion novelty field is a structural context-change proxy; label-aware novelty and relevance are research metrics, not an automatic semantic truth criterion.

## Executed synthetic benchmark

```sh
python -m trace_gc graphrag-benchmark --output benchmarks/graphrag
```

The runner executes **91 runs**: seven task families × eight upstream configurations and five downstream configurations. The families are entity alignment, relation synthesis, claim reconciliation, ontology typing, temporal updates, contradiction handling and scientific knowledge synthesis.

Upstream configurations are candidate-source-only/no graph, one-hop neighborhood, vector only, paths only, graph only, hybrid, hybrid plus actual bounded relevance packs, and the actual adaptive retrieval controller. Downstream configurations are vector RAG context, plain graph retrieval, neighborhood/path/community GraphRAG, provenance-aware GraphRAG and contradiction-aware GraphRAG. The no-graph baseline is explicitly source-scoped, so it does not use graph adjacency to choose its source evidence.

The fixture is hand-authored and openly synthetic. Source spans, graph edges, paths and conflicts have explicit relevance labels. The semantic oracle intentionally sees those labels and changes its fabricated outcome when relevant context is available. This tests the wiring from context to new decisions and abstention; **it is not an unbiased model-accuracy experiment**. Relevance-only reranking currently uses a fixed synthetic classifier in the smoke runner. The actual pinned Jev adapter/reranker path exists separately and still needs live acceptance evidence.

Reports include `dataset.json`, `benchmark_results.json` and `benchmark_summary.md`. They record actual fixture retrieval metrics, parameters, context fingerprints, measured local latencies and controlled outcomes. `real_synthesis_accuracy`, `real_model_accuracy` and held-out production results remain null. Connected-component summaries and the hashing baseline are labeled as such. Do not quote a toy contrast as proof that GraphRAG improves real synthesis.

## Preregistered production comparison plan

Freeze entity/source-family and time-separated development, calibration and final holdout partitions before tuning. Keep related papers, near-duplicate documents, repeated entity pairs and shared-source graph paths in the same group to avoid retrieval leakage. Version the initial graph and enforce source arrival cutoffs so future evidence cannot enter an earlier task. Independent adjudicators label exact source support, identity, temporal qualifiers, contradictions, graph structure and legitimate abstention.

Compare the same candidate tasks across A–G: no prior graph, vector only, local graph, paths only, hybrid, hybrid with semantic reranking and adaptive GraphRAG. The executable runner adds graph-only as a separate eighth diagnostic. Use identical initial snapshots, source availability, authenticated scope, Jev/question/resolver/constraint/policy versions and overall resource budgets wherever applicable. Freeze and disclose any necessary differing context-size settings. Report cold and warm cache runs separately.

Measure retrieval quality and final synthesis quality jointly. Include false merges and unsupported additions, not only positive recall. Report condition-specific contradictions, rejected/abstained candidates, review workload, source provenance coverage, uncertainty intervals and all failure categories. Separate model latency from retrieval and transaction latency; report actual billing units where available. Include high-degree graphs, inaccessible bridges, expired/superseded assertions, misleading communities and malicious source text.

Acceptance requires a held-out improvement on the preregistered objective without safety regression, plus the existing independent deployment qualification procedure. Improving recall while increasing false merges is not automatically a win. A tuned policy that fails the final holdout is not repeatedly retuned on that holdout; designate a fresh untouched evaluation set for the next research iteration.

## Retrieval autoresearch extension

`propose_retrieval_changes` maps the added failure taxonomy to reviewed experiments: aliases/siblings for identity, one versus two hops for acquisitions, provenance-first relation updates, community context for scientific claims, contradiction-first reconciliation, ontology neighbors for typing, vector omission and ranking alternatives.

`heldout_policy_gate` selects the winner using development scores only, requires a pre-locked candidate and disjoint groups, and retains a change only if its held-out gain exceeds the declared minimum and safety checks pass. It returns an auditable research decision, not an enrolled authority, production qualification, code rewrite or automatic deployment.

This extends the existing optional optimization/research boundary. The supplied 0.3 project had question/version/qualification safeguards and a research protocol; it did **not** contain a completed autonomous optimization service. That fact is preserved rather than calling the firewall, calibration or autoresearch newly invented, or pretending optional prior research had run.
