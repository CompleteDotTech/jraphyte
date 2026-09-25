# Hybrid retrieval and downstream GraphRAG specification

Implementation: `trace_gc/retrieval/{store,strategies,items,vector,service,reranker}.py`.

## Storage, retrieval algorithm and synthesis are different abstractions

`GraphQueryAdapter.read(query) -> GraphReadView` supplies a consistent immutable snapshot, available record identities, current source status and a journal horizon. `GraphRetriever.retrieve(SearchSpace)` supplies candidate context from an already ACL-filtered view. `EmbeddingModel.embed(texts)` supplies exact-version vectors. `HybridRetriever` combines candidates, verifies canonical material, ranks and budgets it. TRACE-GC's existing compiler/resolver/transaction code remains separate.

Shipped adapters are `SQLiteGraphAdapter` over the existing `SQLiteReferenceBackend` journal/state/catalog and `InMemoryGraphAdapter` over supplied snapshots. The SQLite adapter does not mirror state into a new authoritative graph. The existing pinned legacy bridge can supply the same interface when its separate conformance gate is satisfied; that gate was not run without the required checkout.

Neo4j/property graphs, PostgreSQL/pgvector, Apache AGE, PuppyGraph, RDF/SPARQL and custom stores are **adapter targets, not installed/tested connectors**. A new adapter must implement consistent snapshot reads, stable assertion/source IDs, available-at-version record visibility, current permissions, source epochs, deterministic relation/temporal filters and backend-enforced deadlines. It must never interpret free text as Cypher, SQL or SPARQL. Query serialization and parameter binding belong in that adapter, not in semantic synthesis.

## Implemented channels

| Channel | Reference implementation and boundary |
|---|---|
| ENTITY / CLAIM | Authorized identifier/name matching; claims retrieve immutable claim text, not just entity labels. |
| LEXICAL | Token overlap against authorized immutable source spans. No claim of BM25 equivalence. |
| VECTOR | Cosine ranking over injected vectors for authorized spans. Default 128-dimensional token hashing is an offline lexical baseline. `PrecomputedEmbedding` accepts independently produced exact-version vectors; a trained embedding adapter is injectable. |
| NEIGHBORHOOD | Bounded breadth-first graph traversal. Undirected traversal locates context while retaining the original asserted edge orientation. |
| PATH | Bounded simple multi-hop paths, cycle avoidance, canonical identity and source pointers. No implication that a path entails a new relation. |
| COMMUNITY / GLOBAL | Bounded connected-component retrieval summaries and a global authorized assertion scan. Not an implementation of Microsoft GraphRAG's full hierarchical community/map-reduce pipeline. |
| ONTOLOGY / SCHEMA | Authorized relation domain/range/restriction fragments; typed ancestry/sibling graph context over declared type predicates. Schema compatibility remains deterministic code. |
| RELATION / TEMPORAL | Relation-centric lookup with exact predicate, source and validity filters; historical selectors use the journal. |
| PROVENANCE | Exact assertion → committed transaction/plan → resolver decision → semantic observations → evidence/source chain. Depth-capped and explicitly incomplete when required links are absent. |
| SOURCE / EVIDENCE | Known source IDs, candidate evidence and authorized graph-linked spans. New documents/rows/API material must first become existing source/evidence records through the firewall. |
| CONFLICT | Explicit schema-declared incompatibilities, including opposing paper support/refutation of a claim. Disjoint validity intervals are not automatically simultaneous contradictions. Unstated semantic contradictions require a separately reviewed semantic task. |
| DECISION / SIMILAR_CASE | Available, authorized observations/resolutions/evaluations and, in explicit history mode, proposed hypotheses. Current in-flight self-context is excluded. |

All source material uses `Catalog.verify_evidence`: immutable source hash, exact Unicode offsets and quote agreement. Retrieval never registers a generated summary as source evidence. Relevance features include lexical/embedding overlap, entity relevance, graph distance, relation relevance, provenance completeness, contradiction value and history penalties. The installed utility and reciprocal-rank fusion strategies are named, pinned policies; their scores are **not truth probabilities**.

## Graph trust classes

| Classification | Meaning in the reference implementation |
|---|---|
| VERIFIED_GRAPH_FACT | Complete available compilation provenance with non-synthetic semantic observations, from the configured trusted graph adapter. This is a provenance classification, not universal semantic correctness or a new qualification. |
| PROVISIONAL_GRAPH_FACT | An assertion with source evidence but incomplete provenance or synthetic semantics. |
| DERIVED_GRAPH_FACT | A retrieved path or provenance/community artifact derived from canonical members. It does not entail a new source claim. |
| CONFLICTED_GRAPH_FACT | A canonical assertion participates in an explicit applicable incompatibility. |
| SUPERSEDED_GRAPH_FACT | An inactive assertion explicitly identifies its superseder. |
| HISTORICAL_GRAPH_FACT | Historical mode/inactive state or a decision-history item, separate from current asserted state. |
| UNVERIFIED_GRAPH_CONTEXT | Candidate context such as a node/type locator without a complete evidential proof. |

Classification precedence preserves inactive/superseded/conflicted status rather than flattening all edges into verified facts. Each item carries canonical IDs, member assertions, entities, evidence and source IDs, decision/observation/transaction/plan pointers, status, risk class, graph version, timestamps where available and provenance completeness. Source confidence and model metadata remain accessible through immutable observation references. `calibration.qualified` is false for the retrieval object: a ranking or provenance tag is never presented as a calibrated probability of truth.

Generated community/provenance text is labeled `NONCANONICAL RETRIEVAL SUMMARY`, with `generated_summary=true`, source membership and `instruction_authority=false`. It can be regenerated from the versioned membership. The sources and original assertion records remain canonical even when the summary is omitted or reworded.

## Query modes

The default is `BALANCED_EVIDENCE`. Applicable explicit conflicts are searched with graph channels and prioritized as atomic pairs. `CONSENSUS` retains those warnings rather than suppressing disagreement; this release does not invent a majority-vote truth aggregator. `CONTRADICTIONS_ONLY` restricts channels to explicit conflicts. `PROVENANCE_ONLY` selects provenance context when enabled. `HISTORICAL` includes historical decision/hypothesis context under current permissions. `LATEST_VALID_STATE` excludes inactive assertions and fixes `valid_at` to the query time unless supplied explicitly.

`include_historical` and `include_superseded` are independent switches. A caller asking for history does not automatically gain superseded evidence or access to denied sources. Explicitly disabling conflict search is possible for ablations but produces a warning. No retrieval mode grants mutation rights.

## Temporal and decision-aware behavior

`graph_version` selects an exact snapshot. `temporal_scope.as_of` uses the commit journal to identify what had been recorded then. `before_source` selects the version before the first journaled source admission. `valid_at` filters asserted validity intervals `[valid_from, valid_until)`, which is distinct from transaction/knowledge time. Conflicting explicit selectors fail closed. Malformed temporal qualifiers cannot satisfy a valid-time query.

A custom in-memory adapter without a journal cannot invent source arrival or historical decision availability. It can retrieve snapshot facts, but unavailable historical evidence/decisions remain unavailable. Current READ permission, tombstones and tenant ACLs govern all historical reads. Authorized withdrawn evidence may be inspected through an explicit historical path; it is not silently restored as current support.

Decision retrieval answers why a candidate was selected, rejected, unresolved or sent for review using stored outcomes/reasons and original semantic questions/observations. `HYPOTHESIS` items carry `PROPOSED_NOT_GRAPH_TRUTH` and have no authoritative assertion IDs. Rejected, abstained and superseded items stay separate from default current state. Merge/split history is represented by existing identity assertions, retractions, source changes and journal/decision provenance—not by a second identity store.

## Downstream API

```python
from trace_gc.retrieval.contracts import query, RetrievalBudget
from trace_gc.retrieval.service import GraphRAGQueryService

# retriever has been created by the trusted application with an authenticated ACL.
request = query(
    requesting_component="downstream-research",
    security_scope=authenticated_tenant,
    focus_entities=[claim_id],
    strategies=["CLAIM", "NEIGHBORHOOD", "PATH", "PROVENANCE", "CONFLICT"],
    budget=RetrievalBudget(maximum_hops=2, maximum_paths=8),
    mode="BALANCED_EVIDENCE",
)
answer = GraphRAGQueryService(retriever).query(request)
# answer["context"] has items, canonical citations, graph_version and warnings.
# answer["context"]["can_mutate_graph"] is always False.
```

The complete runnable fixture example is `examples/graphrag/query_example.py`; it is not production authentication code. An application-facing HTTP wrapper may expose a read-only query endpoint, but no server, user directory or production ACL provider is invented by this release.

Every citation contains the evidence ID, immutable source snapshot/hash, logical source document ID, exact start/end offsets and quote. Answer validation requires each selected canonical evidence span exactly once; source names cannot be substituted. A selected relationship can be traced through its transaction, plan, resolver decision, semantic observations and source documents. Incomplete chains produce warnings rather than fabricated IDs.

The same context can support entity exploration, scientific search, claim/replication/condition comparison, provenance inspection, timelines, literature review and hypothesis discovery. Those are consumer uses of retrieved data, not claims that an answer-generation agent or new scientific conclusions were validated.
