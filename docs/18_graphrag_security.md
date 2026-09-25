# GraphRAG security and evidence boundary

## Threat model and ownership

Source text, graph labels, user-authored claims and generated summaries are untrusted **data**. Application configuration, pinned question programs, authenticator output, enrolled issuer keys, tokenizer implementations, graph adapters and access policies are trusted deployment inputs. A retrieved document cannot change any of those capabilities.

The reference implementation is an in-process service. `GraphRAGQueryService` is not a network authentication provider. A deployed wrapper must authenticate the principal, build their ACL server-side, rate-limit requests and restrict access to internal Catalog/ledger objects. Never accept a caller-provided `graph-access` object as authentication.

## Deny-by-default ACL contract

`AccessFilter` evaluates tenant, workspace, authenticated user, roles, security classification/clearance, exact source ACL, exact node ACL and exact edge ACL. Missing grants deny access. There is no wildcard expansion along an edge. An edge is visible only when its own ACL, both endpoint ACLs and all canonical evidence sources are usable. A decision additionally checks its candidate endpoints and supporting source evidence.

Source READ/active/tombstone state is read from the existing authority. Historical queries still require current READ and non-tombstoned sources. Merely being connected to an accessible node does not make a hidden node, edge, community member or source retrievable.

Filtering precedes adjacency construction, path/community expansion, vector input construction and semantic model context. Hidden intermediary nodes cannot bridge an otherwise apparently useful path. Community text is generated only from authorized members. Internal adapters may read a complete local trusted snapshot; they must not export it to the external model or an untrusted caller. Backend-native security predicate pushdown is a required deployment optimization for larger/multi-tenant stores, not a shipped remote connector.

## Model boundary

Retrieval-aware model materialization includes only selected canonical items and exact source spans. The complete graph snapshot and ACL/status maps stay internal. Candidate source ACLs and endpoint ACLs are checked as well; a candidate cannot smuggle a forbidden source around retrieval filtering.

`TypeSafeAdapter.evaluate(..., current_graph_access=...)` requires current application ACLs for retrieval-aware live packs and rechecks current source status before emitting a request. The existing measured-tokenizer, API-key capability, model pinning and observation-attestation requirements remain in force. The fixed question templates already instruct Jev to treat state text as untrusted data. The new relevance template preserves that rule and distinguishes relevance from truth.

Graph context items are reconstructed from immutable originals before use. A retriever plugin cannot substitute a fabricated quote, path, source identity, trust class or summary membership. Query strategy versions and retrieval fingerprints are recomputed; reranked order/scores are reconstructed from exact original relevance observations. Semantic reranking has a bounded item count, cannot remove contradictions, cannot revise source text and cannot recursively rerank its own already reranked output.

These controls constrain provenance and capability misuse. They do not prove that a language model is immune to every adversarial text. Semantic robustness requires separate adversarial/live evaluation under the exact deployment configuration.

## Cache and audit isolation

Cache identity includes ACL content, tenant/workspace principal, source epochs/status, graph snapshot, query scope and exact algorithm/model versions. Every retrieval uses current statuses before a cached result is served. ACL refresh clears cached candidates immediately; graph/source changes invalidate on the next read.

The immutable retrieval ledger intentionally records candidates, selection/discard reasons, source references and scope. **Do not return a complete internal Catalog or analysis bundle to an ordinary downstream user.** It may contain other graph regions, source records, ACL metadata or historical data. Return the authorized `GraphRAGAnswerContext` projection instead. Persisted audit artifacts require their own authorization and retention policy.

Source erasure does not magically erase copies already delivered to an authorized consumer, an exported bundle or a long-lived process Catalog. Revoke access, invalidate retrieval caches, end affected sessions, and follow the existing erasure/audit retention policy for all copies. Missing erased canonical evidence fails closed; it is never replaced with a summary to fake replay completeness.

## Write boundary and concurrency

A retrieval result contains no credential and no backend write method. Upstream retrieval produces immutable analysis. Existing source admission and mutation publication still require service-owned policy, independent signed approval/preflight, exact source hashes/epochs and graph/schema compare-and-swap under the existing transaction lock.

The model receives bounded context, but deterministic graph checking still uses the authoritative complete snapshot. No retrieval omission can waive a cannot-link or other structural constraint. A failed transaction or rolled-back state is not visible as committed GraphRAG evidence. Historical snapshots cannot be used to publish against a later version without a new valid plan.

## Security verification

Run `python -m unittest tests.test_graphrag_security tests.test_graphrag_retrieval tests.test_graphrag_pipeline -v`.

The suites cover tenant/workspace/user-role/classification filtering, source denial and revocation, hidden intermediaries, pre-embedding filtering, canonical text/trust forgery, candidate closure ACLs, misbound lineage, fabricated citations, stale snapshots, superseded state, budget loss of contradiction pairs and retrieval/reranking self-reinforcement. The existing transaction/signature/qualification tests remain unchanged. A passing offline suite is not a production penetration test or security certification.
