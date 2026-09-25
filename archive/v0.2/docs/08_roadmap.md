# 8. Additive implementation roadmap and deliverable coverage

## 8.1 Integration target and preservation rules

The inspected implementation is `CompleteDotTech/paper-package/graph_synthesis/core.py`, blob `68217feec539d37e4a524432c93df035f9a0fe39` [B4]. This is a verified file revision, not an assertion that a particular repository HEAD commit is frozen. Resolve and pin the complete checkout before implementation. Read its contributor instructions and run its existing regression/replay checks before making changes.

The work below is a proposed sequence of additive pull requests, not PRs created or merged in this response. Do not change original raw responses, frozen prompts, source datasets, publication figures or empirical conclusions to make new architecture tests pass.

## 8.2 Dependency-ordered work

| Phase | Proposed work | Dependencies | Exit criteria |
|---|---|---|---|
| P0 — Baseline inventory | Pin checkout, validate original manifest, capture existing replay/tests and document supported operations | None | Historical evidence remains byte-identical; existing failures disclosed rather than silently repaired |
| P1 — Versioned contracts | Add IR sidecars, stable IDs, source representations and strict adapters around existing candidate/bind interfaces | P0 | JSON and cross-record tests pass; legacy replay works unchanged; synthetic mode cannot impersonate live observations |
| P2 — Evidence admission | Add integrity/access gate, candidate-relative semantic tags, duplicate families and contradiction retention | P1 | Tampered or missing spans rejected; copied sources not counted as independent; malicious content cannot alter permissions |
| P3 — Closure and packing | Add declared-dependency closure, topological stages, exact rendered request hashes and provider-budget checks | P1–P2 | Required context never silently truncated; answer-dependent questions split; packed/unpacked experiment is reproducible |
| P4 — Semantic adapters and resolver | Add exact model/request receipts, optional confidence, nominal/ordinal contracts, bounded beam and acquisition states | P3 | Missing/invalid outputs abstain; cannot-links survive identity closure; acquisition terminates on budget; nonexclusive relations preserved |
| P5 — Qualified policies | Add split manifests, per-task calibration, confidence bounds and R0–R5 policy registry | P4 and independent labeled data | No automatic consequential writes without matching qualified artifact; changed program/model invalidates qualification |
| P6 — Plan/commit bridge | Lower reviewed plans to existing GraphStore operations, add preflight and in-transaction rechecks | P4–P5 | Stale state and changed source rejected; idempotency preserved; no partial publication; legacy behavior unchanged |
| P7 — Full ledger and replay | Add upstream event journal, cache lineage, counterfactual branches and source-dependency invalidation | P1–P6 | Recorded replay reproduces expected graph; changed semantic inputs require new observations; independent proofs survive withdrawal |
| P8 — Autoresearch | Development-only question discovery, redundancy ablations, frozen finalists and release qualification | P5–P7 | Locked test inaccessible to optimizer; every promoted question set has documented gain, risk and cost impact |
| P9 — Controlled pilot | Fixed-schema document-evidence and identity tasks; matched candidate/model controls | P0–P8 | Declared risk/coverage goals evaluated with uncertainty; results may support, narrow or reject the hypotheses |
| P10 — Evolution and scale | Reviewed schema migration, interval-aware constraints, scalable backend and event-driven audit | P9 evidence | Separate backend atomicity/load tests; no unsupported extrapolation from the small snapshot store |

Initially preserve `core.py` as the sole graph authority. Candidate new modules might be `contracts.py`, `evidence_firewall.py`, `closure.py`, `packing.py`, `resolver.py`, `qualification.py`, `mutation_planner.py` and `decision_ledger.py`; these names are proposed integration locations, not existing files claimed to have been found.

## 8.3 Acceptance scenarios

A corrupt source span must fail before inference or commit. A contradiction must remain available to the resolver. An unrelated prompt instruction must not alter permitted operations even when tagging misses it. A question targeting entity A must state that target explicitly. A pack exceeding either context budget must split or abstain. A Noul must not acquire a fabricated vendor confidence field. A bimodal Score mean must not be treated as a middle-class observation.

A requested/returned model mismatch must prevent qualified acceptance. A changed question or evidence source must invalidate semantic cache reuse. An unqualified high-scoring synthetic decision must never commit. A same_as chain violating cannot-link must fail. A source withdrawal must deactivate all declared dependents but preserve independent alternative support. A concurrent graph change must invalidate a stale plan. A repeated identical idempotency key must return the original event, while a changed payload under the key fails.

The local package tests implement a subset of these record-level checks. The backend, model-behavior, optimization and scale criteria remain integration/research tests, not completed work.

## 8.4 The 18 requested deliverables

| # | Deliverable | Package location |
|---|---|---|
| 1 | Canonical architecture specification | `docs/01_architecture.md` |
| 2 | Architecture Mermaid diagram | `diagrams/architecture.mmd` |
| 3 | Graph IR schema | `schemas/graph.schema.json` |
| 4 | Decision IR schema | `schemas/decision.schema.json` |
| 5 | Evidence IR schema | `schemas/evidence.schema.json` |
| 6 | Mutation Plan schema | `schemas/mutation-plan.schema.json` |
| 7 | Question Pack schema | `schemas/question-pack.schema.json` |
| 8 | Risk policy specification | `docs/04_risk_calibration.md`; `schemas/risk-policy.schema.json`; `policies/analysis-only.json` |
| 9 | Confidence/calibration specification | `docs/04_risk_calibration.md` |
| 10 | Provenance/decision-ledger schema | `schemas/ledger-event.schema.json`; `docs/05_provenance_replay.md` |
| 11 | Replay specification | `docs/05_provenance_replay.md`; `diagrams/replay.mmd` |
| 12 | Evaluation methodology | `docs/06_evaluation.md` |
| 13 | Error taxonomy | `docs/10_error_taxonomy.md` |
| 14 | Autoresearch design | `docs/07_autoresearch.md`; `diagrams/autoresearch.mmd` |
| 15 | Revised implementation roadmap | This document |
| 16 | Revised paper outline | `docs/09_paper_novelty.md` |
| 17 | Updated novelty/contribution analysis | `docs/09_paper_novelty.md` |
| 18 | Open research questions | `docs/09_paper_novelty.md`, §9.5 |

Additional compatibility outputs are the Candidate and Resolution schemas, transaction diagram, complete before/after table, source register, synthetic fixture, offline validators and manifest.
