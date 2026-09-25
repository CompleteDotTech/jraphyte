# 11. Source register and evidence boundaries

## 11.1 Project sources

**R1 — Supplied revision instructions.** `Pasted text(8).txt` and `Pasted text(9).txt`, both 1,170 lines and byte-identical. One unchanged copy is included as `sources/revision_requirements.txt`; original content IDs are `file_000000005bac81f5ad2dc3dab6f083ae` and `file_0000000073ac81f590db8331747da06b`. The hash is recorded in `SOURCE_MANIFEST.json`. These are requirements, not proof that the requested components already exist.

**B1 — Earlier research architecture.** *Autonomous Graph Synthesis as a Typed Probabilistic Graph Compiler*, saved Library report, content ID `file_0000000065f881f7b40304ecd254ebee`, version 1. Entire rendered report reviewed. Original research cutoff: 17 September 2026. It calls the proposed system PGC. Used for architectural continuity, scope, earlier IRs and evaluation framing; its literature/performance claims are not silently treated as newly independently verified.

**B2 — Existing research package.** [Repository README](https://github.com/CompleteDotTech/paper-package/blob/main/README.md), inspected blob `a6afcbd988d12efc0bf17faf21a40d9977abcdaa`. Distinguishes narrow empirical evidence, exact response replay and broader prospective architecture. Mutable `main` links are navigation aids; the listed blob is the observed file identity.

**B3 — Graph extension and manuscript.** [Graph extension README](https://github.com/CompleteDotTech/paper-package/blob/main/graph_synthesis/README.md), blob `515993d23a36c92c77d2b70e700993b7c109ae86`; [graph overview](https://github.com/CompleteDotTech/paper-package/blob/main/GRAPH_SYNTHESIS.md), blob `89b5ea262dbcef79905b55a5b6647fb11a1d673d`; [graph manuscript](https://github.com/CompleteDotTech/paper-package/blob/main/graph_synthesis/paper.md), inspected relevant methods/status sections. The manuscript response was truncated; no complete-manuscript or complete-repository review is claimed. Methods distinguish support/refutation links, identity views and post-hoc graph analysis from end-to-end synthesis. The manuscript's later update weakens the earlier identity finding; this revision reports no new model-quality numbers.

**B4 — Existing executable graph core.** [core.py](https://github.com/CompleteDotTech/paper-package/blob/main/graph_synthesis/core.py), fully read through two bounded connector requests, blob `68217feec539d37e4a524432c93df035f9a0fe39`. Observed source supports the described span checks, assertion binding, predicate contracts, identity/cannot-link validation, SQLite transactions, idempotency, retraction and journal. The original engine's tests were not rerun in this package.

**Unresolved path.** Fetching `CompleteTech-LLC-AI-Research/typed-probabilistic-graph-compiler/README.md` returned 404 through the connected GitHub tool. No inference is made about its existence or visibility. No files in that path were changed or reviewed.

## 11.2 Current official TypeSafe references

Accessed 25 September 2026. Documentation and vendor examples establish API contracts and design patterns, not independent TRACE-GC quality or calibration results. Example performance, prices and threshold choices are not transferred into this package's empirical claims.

| ID | Primary source | Used for |
|---|---|---|
| T0 | [Documentation index](https://docs.typesafe.ai/llms.txt) | Discovery of current official documentation |
| T1 | [Models](https://docs.typesafe.ai/models) | Exact model identity, alias behavior and the two context budgets |
| T2 | [API reference](https://docs.typesafe.ai/api) | Typed request/response contracts; question IDs not model input; Choice options and Score levels |
| T3 | [Confidence](https://docs.typesafe.ai/confidence) | Distinction between distribution and confidence; Noul lacks separate confidence |
| T4 | [Score](https://docs.typesafe.ai/primitives/score) | Ordered levels and probability-weighted expected value |
| T5 | [Classifying RAG passages](https://docs.typesafe.ai/cookbooks/classifying_rag_passages) | Relevance, evidence, contradiction and instructional-content judgments before generation |
| T6 | [Double-checking citations](https://docs.typesafe.ai/cookbooks/citation_check) | Claim/citation verification pattern |
| T7 | [Speculative fan-out](https://docs.typesafe.ai/patterns/fan-out) | Multiple independent questions sharing state |
| T8 | [Autoresearch feature discovery](https://docs.typesafe.ai/cookbooks/autoresearch_feature_discovery) | Question proposal and downstream feature-model optimization pattern |
| T9 | [Hierarchical classification](https://docs.typesafe.ai/cookbooks/hierarchical_classification) | Retaining and exploring alternative hierarchy paths |
| T10 | [Knowledge graph entity alignment](https://docs.typesafe.ai/cookbooks/entity_alignment) | Candidate-first entity matching and ordinary-code routing |

## 11.3 Standards references

**W1 — W3C, Shapes Constraint Language (SHACL).** [Normative specification](https://www.w3.org/TR/shacl/). Used to identify a graph-validation target; no full SHACL implementation is claimed.

**W2 — W3C, PROV-O: The PROV Ontology.** [Normative specification](https://www.w3.org/TR/prov-o/). Used for provenance entity/activity/agent mapping; no complete serializer is claimed.

## 11.4 What this research pass does and does not establish

This revision verifies selected current official contracts and inspects existing project evidence. It does not rerun the original study, execute KARMA, independently benchmark Jev, qualify a threshold or conduct an exhaustive systematic novelty review. Further literature verification is a submission requirement, not a completed novelty certificate.

Artifact designs and algorithmic refinements are proposals derived from the supplied requirements, the actual baseline and explicit reasoning. They are marked as such rather than attributed wholesale to TypeSafe. Offline fixture numbers are invented test data with SYNTHETIC execution mode, never measured probabilities or deployment recommendations.
