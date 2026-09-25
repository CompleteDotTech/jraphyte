# Retrieval Planner, budgets, expansion and cache

Implementation: `trace_gc/retrieval/{contracts,planner,budget,service}.py`.

## Planner contract

`RetrievalPlanner.plan` accepts candidate identity, task/question type, effective risk, known entities and relations, observed uncertainty, prior result IDs, budget and tier. It emits an immutable `retrieval-plan` record whose body contains ordered strategy steps, hop limits, policy version and `ON_UNCERTAINTY` expansion policy. `request` converts the plan into the strict GraphRetrievalQuery body. IDs follow the existing Catalog convention: the immutable envelope has the ID; bodies do not duplicate their own identity.

Task policies are separately versioned. Identity retrieves identifiers/aliases before local context and provenance; claim reconciliation introduces contradictory relationships early; ontology work retrieves schema/typed ancestry; temporal work emphasizes relation history and provenance; scientific work combines claims, sources, relation paths and conflict context. High-risk identity work adds conflict/provenance channels rather than treating every question alike.

The installed routing is an inspectable policy, not a learned or empirically optimized policy. Replace a reviewed policy with a new `policy_version`, run the held-out gate, and qualify the resulting pipeline independently before automatic publication.

## Progressive tiers

| Tier | Typical retrieval | Escalation condition |
|---|---|---|
| 0 | Exact entity/claim lookup and known source references. | Initial cheap search. |
| 1 | Direct neighbors, lexical/vector evidence, task-specific conflicts or schema. | Insufficient semantic evidence or selected risk policy. |
| 2 | Two-hop paths and relevant compilation provenance. | Insufficient evidence within remaining budget. |
| 3 | Additional paths, historical decisions, temporal/conflict/ontology context. | Continued unresolved question with new information. |
| 4 | Bounded community/global search. | Explicitly budgeted late expansion. |
| 5 | Human-guided or external evidence acquisition. | Not an automatic recursive retrieval tier. |

Methods accumulate across a task's tiers; hop depth never exceeds the query budget. The default four-round cap executes tiers 0–3. Configure at least five rounds, within the hard eight-round safety ceiling, to reach tier 4. A tier is not a guarantee that its entire potential context will fit.

## Budget policy

`policies/retrieval-budget.json` records the default limits and units. `RetrievalBudget` validates nonnegative integers, a maximum of eight hops, maximum provenance depth of sixteen and one to eight rounds. Defaults are two hops, twelve paths, forty nodes, forty edges, three communities, depth four, twelve resolver/history decisions, twenty source spans, 16,000 conservative context units, 2,000 ms retrieval deadline, 10,000 logical work units, 1,000 generated candidates and eight semantic-reranking items.

Resource accounting counts unique underlying nodes, edges and evidence spans, including path and summary members. A path cannot evade the edge/node budget by being represented as one object. Duplicate candidates are fused, while their channel contributions remain auditable. Whole items are retained or discarded; source spans are not arbitrarily clipped into new unattributed text.

An explicit contradiction pair is selected atomically. When it cannot fit, member-edge fallbacks are blocked and `CONFLICT_PAIR_EXCLUDED_BY_BUDGET` is reported. This does not promise exhaustive contradiction discovery; a partial search is labeled partial rather than presented as complete support.

`maximum_tokens` is a conservative UTF-8 serialized-byte estimate, not a provider token measurement. Custom retrieval counters cannot undercut that floor. The existing model adapter still requires an independently injected measured tokenizer and actual request-cap check for live execution. `maximum_cost_units` counts reference search work, not dollars. Billing limits require metered provider adapters.

The reference deadline is **cooperative**: checked during graph scan, pair comparison, strategy traversal, candidate production and selection. It cannot interrupt a blocked external adapter or embedding call. A production adapter must enforce its own I/O/server timeout and cancellation; the query carries the requested deadline. Catalog hydration, sorting and local validation are not a hard-real-time service-level guarantee.

## Acquisition state machine

`UpstreamGraphRAG.run` constructs a new query/result/context/pack/observation branch per round. The existing semantic outcome `INSUFFICIENT` causes a new policy evaluation branch with `RETRIEVE_MORE_EVIDENCE`. Previous observations and evaluations remain immutable. No universal 0.5 confidence cutoff was added.

A semantically selected but unqualified candidate stops at `HUMAN_REVIEW_REQUIRED`; it does not retrieve repeatedly until a favorable answer appears. A qualified acceptance can stop at sufficient evidence. Rejection, infeasibility, partial/budget-exhausted retrieval, no new information, maximum rounds and review requirements also stop the loop. A capped acquisition branch remains non-authoritative: its last acquisition record is not permission to publish.

Each `retrieval-expansion` records the round, reason, prior/result IDs, decisions, added items, confidence before/after/change, decision change, cost, latency and stop reason. Canonical item content signatures, not just IDs, detect revised information. The runtime `new_relevant_information_per_round` field is a **structural novelty proxy** for selected decision context; it is not a independently labeled semantic relevance estimate. Evaluation can compute label-aware relevance separately. This limitation is deliberate and exposed rather than disguised as calibration.

The current hypothesis and its in-flight decisions cannot be retrieved as independent corroboration for that same upstream candidate. Recursive reranking is disallowed. Reranking itself does not delete contradictions, produce synthesis acceptance probabilities, or bypass source attribution.

## Cache and index lifecycle

`RetrievalCache` is a bounded, thread-safe, deep-copy LRU. It caches candidate material shared across neighborhoods, paths, ontology/schema fragments, summaries, provenance and vector results. It does not cache permission decisions separately from their exact scope. Every invocation emits a fresh query/result/lineage record including cache state.

Cache keys bind the immutable graph snapshot hash, available non-retrieval record IDs, current source statuses/epochs, authenticated ACL content, structured query including all filters/scopes, strategy versions, embedding version, adapter version, ranking policy and budget. Query timestamps and round numbers are excluded when they do not change semantics. A `LATEST_VALID_STATE` query fixes its actual valid time in the query; that time remains in the cache key.

Graph commits, source changes and new relevant records change read identity. The service invalidates its LRU on the next read before serving cached material. `set_access_policy` immediately clears it. Invalidation is coarse-grained, intentionally favoring correctness over hit rate. Cache hits still perform a consistent graph/status read and record the hit. Retrieval ledger writes alone do not invalidate every cache entry.

The reference runtime rebuilds cheap adjacency and uses the query-result cache; it does not ship a durable incremental embedding index or a separate plan cache. Planner steps are inexpensive deterministic policy evaluation. A future persistent index or plan cache must use the same version/ACL/temporal identity and may never become a graph authority.

## Validation

`test_graphrag_retrieval.py` covers resource dimensions, deadlines, deduplication, version changes and cache isolation. `test_graphrag_pipeline.py` covers insufficient-evidence expansion, saturation, round caps, zero-budget behavior and commit visibility. `test_graphrag_security.py` covers contradiction-pair omission, version fingerprints, counter underreporting and self-reinforcement. The release validation report records actual outcomes.
