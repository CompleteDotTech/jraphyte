# 9. Revised research framing, paper outline and novelty analysis

## 9.1 Working paper title and research claim

**TRACE-GC: Evidence-Gated, Risk-Aware Compilation of Semantic Decisions into Repairable Graphs**

The proposed system turns heterogeneous candidate evidence into reversible graph mutations through explicit evidence admission, bounded semantic judgments, uncertainty-aware resolution, deterministic constraints and versioned acceptance policies. Jev is one backend for typed judgments, not the system's orchestration or transaction authority.

The central test is whether this separation improves accepted-graph quality, selective automation, repairability and total cost under matched candidate recall and explicit dependency constraints. The architecture can remain useful even if a specialist classifier outperforms Jev. An evidence-preserving compiler should not be defined by loyalty to one model.

## 9.2 Proposed abstract, without invented results

Autonomous graph construction requires more than well-formed model outputs: accepted assertions must remain evidence-bound, constraint-valid and repairable as sources and semantic programs change. We propose TRACE-GC, an additive architecture that separates candidate discovery, source admission, bounded semantic judgments, global resolution and transactional graph publication. Its intermediate representations preserve evidence addresses, raw decision distributions, calibration identity, alternative hypotheses and mutation dependencies. Dependency-bounded context and compatible question packing are treated as compiler optimizations whose semantic and economic effects must be measured. A controlled question-set research loop operates outside production and promotes only independently evaluated program versions. The accompanying evaluation protocol separates fixed-candidate acceptance from end-to-end graph synthesis and measures risk, coverage, provenance, repair and cost. The present revision specifies contracts and offline checks; it does not report a new model experiment, qualified deployment threshold or end-to-end benchmark result.

## 9.3 Contribution analysis

| Element | Status of underlying idea | Possible TRACE-GC contribution | Evidence still required |
|---|---|---|---|
| Passage relevance/support/instruction classification | TypeSafe already documents RAG passage classification [T5] | Candidate-relative multi-axis admission tied to mutation lineage | Recall, contradiction handling and permission-boundary tests |
| Citation/source checking | TypeSafe documents citation checking; baseline code already binds exact spans [T6, B4] | Unified source/representation/decision verification at commit | Tamper and source-withdrawal experiments |
| Question batching | Documented System One usage pattern [T7] | Dependency-safe scheduling with closure, scope and request identities | Packed/unpacked quality and cost study |
| Hierarchical beam exploration | Documented TypeSafe cookbook pattern [T9] | Ontology DAG alternatives resolved under graph constraints | Matched-budget hierarchy and multi-label evaluation |
| Semantic question discovery | Documented feature-discovery pattern [T8] | Graph-level error/cost/risk objective and controlled promotion | Locked-test improvement beyond simpler rewrite baselines |
| Provenance | Established standardized vocabulary in PROV-O [W2] | Decision and mutation lineage integrated with uncertain alternatives | Interoperable export and causal repair tests |
| Graph validation | Established constraint validation; baseline already implements selected rules [W1, B4] | Explicit capability-bound compilation across backends | Backend conformance and migration tests |
| Transactions and retraction | Already implemented in the inspected research core [B4] | Upstream evidence/program lineage and counterfactual graph trajectories | Full dependency completeness and concurrency evaluation |
| Minimum Evidence Closure | Operational proposal in this revision; related to dependency analysis and context selection | A defined dependency contract plus evidence-loss/cost experiments | Formal scope, comparison with simpler context selection and novelty search |
| Typed probabilistic graph compilation | Earlier project thesis [B1], not introduced by this revision | Integrated contract, operational safety boundary and reproducible comparative study | End-to-end evidence and systematic closest-prior-work search |

No item is labeled a proven first. The current verification reviewed the project's actual code and selected official documentation, not an exhaustive systematic review of every new graph paper. The earlier report's literature table remains a set of useful leads; its publication claims and performance comparisons must be reverified before submission. Do not inherit a novelty claim merely because a system uses new terminology.

## 9.4 Revised paper outline

1. **Problem and scope:** accepted graph assertions versus candidate hypotheses; fixed-schema evidence links and identity as initial use cases.
2. **Prior work:** knowledge acquisition/fusion, entity-resolution blocking and global consistency, uncertain data and provenance, validation/transactions, structured semantic judgments and graph-enrichment agents.
3. **Requirements and threat model:** integrity versus authenticity, evidence support versus truth, model authority boundaries and conditional guarantees.
4. **Representation:** Evidence, Candidate, Question Pack, Decision, Resolution, Mutation and Graph IR; immutable identities; AND/OR proof semantics.
5. **Compilation pipeline:** admission, closure, scheduling, semantic adapters, beam/global resolution and bounded evidence acquisition.
6. **Risk and publication:** qualification artifacts, operation risk, deterministic validation, concurrent-state recheck and compensation.
7. **Research loop:** error-driven semantic programs, redundancy, data separation and controlled promotion.
8. **Implementation:** exact reused core and additive components, supported versus unsupported constraints, backend limits and operational modes.
9. **Evaluation design:** fixed-candidate and full-pipeline tracks, same-workflow model controls, scope-matched KARMA comparison, statistical units and budgets.
10. **Results:** only actually executed observations, separate software tests, frozen replay, synthetic challenges and fresh inference; no placeholders disguised as numbers.
11. **Ablations and failures:** candidate recall, context truncation, correlated signals, policy drift, source copying, global identity failures and null results.
12. **Limitations and reproducibility:** licensing/data access, source retention, unresolved calibration, human review, scale and incomplete prior-art coverage.

Keep the current empirical manuscript's findings and dates intact. Add this as a prospective architecture section or separate design manuscript. Update results only after the corresponding experiment has actually run with preserved evidence.

## 9.5 Open research questions

**Evidence sufficiency:** Can a declared closure predict semantic sufficiency, or merely make missing inputs visible? Which relevance filters lose the most counterevidence? What should the system do when credible sources disagree indefinitely?

**Context and packing:** When do extra questions or shared state change model judgments? Is exact closure grouping enough, or does semantic interference require a narrower packing rule? How large is the economic gain after generator, retrieval, solver and storage costs?

**Uncertainty and resolution:** Do local calibrated outputs remain calibrated after candidate selection and global constraints? Can a learned resolver model source dependence without double-counting copied evidence? How should uncertainty be represented in partially resolved identity components?

**Graph semantics:** What is an appropriate assertion-level contract for nonexclusive predicates and temporal scope? How much of schema evolution can be validated before migration? How do RDF and labeled-property-graph backends preserve equivalent provenance and repair behavior without conflating their semantics?

**Program evolution:** Can question discovery improve severe-error rates rather than only average prediction? When does optimization overfit the error corpus? How should changes to question sets trigger selective, rather than total, re-evaluation of the accepted graph?

**Reproducibility:** Which counterfactuals are identifiable from frozen observations, and which require new model calls or a complete trajectory rerun? Can dependency declarations be audited for completeness? What reproducibility remains after source deletion or provider retirement?

**Research value:** Does the integrated architecture outperform a simpler generator plus specialist verifier at matched recall and cost? Would a negative Jev result still support the compiler abstraction? Which claimed contribution survives the strongest contemporary prior-art comparison?
