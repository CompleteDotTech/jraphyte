# TRACE-GC — Architecture Revision Package
## Typed, Risk-Aware Compilation of Evidence into Graphs

**Revision:** 0.2-design · **Prepared:** 25 September 2026  
**Status:** Proposed architecture and integration contracts, with offline schema and contract checks. This is not a new release of the existing graph compiler, a deployed system, or a new model experiment.

The revision preserves the existing candidate → bounded judgment → global resolution → constraint validation → transactional publication architecture. It adds explicit evidence admission, dependency-bounded context, question packing, versioned calibration, resolver outcomes, and controlled question-set research.

### Read first

| Artifact | Purpose |
|---|---|
| `docs/01_architecture.md` | Canonical revised design, ownership and safety conditions |
| `docs/02_deltas.md` | Before / after / why for all 27 requested sections |
| `docs/03_ir_contracts.md` | Typed representations and mapping to the existing implementation |
| `docs/04_risk_calibration.md` | Risk policies, probability semantics and qualification procedure |
| `docs/05_provenance_replay.md` | Evidence lineage, mutation protocol, repair and replay |
| `docs/06_evaluation.md` | Baselines, metrics, split controls, ablations and falsification |
| `docs/07_autoresearch.md` | Offline question discovery, pruning and promotion |
| `docs/08_roadmap.md` | Dependency-ordered integration plan and acceptance tests |
| `docs/09_paper_novelty.md` | Revised paper framing, prior-art distinctions and open questions |
| `docs/10_error_taxonomy.md` | Operational and semantic error codes |
| `docs/11_sources.md` | Verified source register, version notes and source boundaries |
| `diagrams/` | Editable Mermaid source files |
| `schemas/` | Standalone JSON Schema 2020-12 contracts |
| `examples/bundle.json` | Explicitly synthetic, non-authorized end-to-end contract fixture |
| `policies/analysis-only.json` | Safe default: no automatic consequential graph writes |
| `tools/validate_package.py` | Offline schema and selected cross-record invariant checks |
| `tests/test_contracts.py` | Positive and adversarial contract tests |
| `VALIDATION_REPORT.json` | Actual local test results produced during package assembly |

### What remains unchanged

The source baseline is the saved report **Autonomous Graph Synthesis as a Typed Probabilistic Graph Compiler**, together with the inspected `CompleteDotTech/paper-package/graph_synthesis` implementation. The report uses the provisional name PGC; this revision uses TRACE-GC consistently without describing PGC as a separate competing system. The current research repository already contains durable transactions, exact evidence binding, reversible identity views and dependency-based retraction [B1–B4].

No GitHub file, frozen observation, empirical manuscript, benchmark result or original Library attachment has been overwritten. Existing research findings are not relabeled as validation of this proposed architecture. The unavailable `CompleteTech-LLC-AI-Research/typed-probabilistic-graph-compiler` path returned HTTP 404 through the connected tool; this does not establish whether it was deleted, renamed or inaccessible. Integration targets below refer only to the inspected `paper-package` paths.

### Evidence categories

`EXISTING_CODE` means functionality observed in inspected source, not tests rerun here. `VENDOR_DOCUMENTED` means current official documentation. `PROPOSED` means this revision's contract or algorithm. `SYNTHETIC_TEST` means an offline fixture, not Jev output. `MEASURED_IN_THIS_PACKAGE` is reserved for the validation report.

### Run the package checks

```sh
python -m pip install -r requirements-validation.txt
python tools/validate_package.py
python -m unittest discover -s tests -v
```

The checks make no network or model calls and do not connect to a graph database. They establish schema conformance and the specifically implemented cross-record checks, not semantic truth, deployment calibration, backend transaction safety, or performance at scale. The fixture intentionally remains in analysis-only mode.

All 18 requested deliverables are mapped in `docs/08_roadmap.md`. The two supplied instruction files are byte-identical; one unchanged copy is retained under `sources/`, with both source identities recorded in the manifest. This package does not assign a new license to the user's existing code, sources or research.
