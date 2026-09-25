# 6. Evaluation methodology

## 6.1 Hypotheses rather than presumed improvements

H1: Evidence admission and exact claim-source binding reduce unsupported accepted assertions without an unacceptable recall loss. H2: dependency-bounded closures and compatible packing reduce end-to-end cost at matched semantic quality. H3: global resolution reduces identity/constraint errors compared with independent local thresholds. H4: qualified policies improve selective automation at approved risk. H5: offline question-set optimization improves held-out graph outcomes after accounting for added latency and cost.

Each hypothesis can fail. A specialist classifier may dominate Jev. A larger shared context may improve recall despite higher cost. Candidate generation or global solving may dominate runtime. More precise accepted edges may simply reflect more abstention. These are meaningful results, not reasons to change the success metric after testing.

## 6.2 Two evaluation tracks

**Fixed-candidate track:** Freeze source snapshots, candidate objects, blocking outputs, schema and ground-truth units. Vary evidence processing, semantic backend, resolver and acceptance policy. This isolates acceptance quality and repairs while exposing candidate-recall limitations.

**End-to-end track:** Start from the same source stream and initial graph. Allow each system its candidate-generation strategy under declared resource budgets. Measure discovery, retrieval, selection, compilation and maintenance jointly. Results from the first track do not establish the second.

Reuse the existing bibliographic identity and document-to-claim evidence-link tasks with their original limitations and manifests [B2–B3]. Do not call those tasks unrestricted relation extraction, newly induced ontologies, production graphs or a KARMA replication. Use a fresh locked evaluation set for confirmatory claims about changes designed after inspecting the historical results.

## 6.3 Architecture and model controls

| Arm | Definition | Critical control |
|---|---|---|
| A | Generative model proposes graph edits directly in an isolated evaluation sandbox | No production write permissions; record malformed and unsupported edits |
| B | Same generator plus deterministic graph validation | Hold candidate discovery and evidence fixed where the comparison requires it |
| C | Candidate generator, bounded Jev judgments and existing compiler boundary | Match question meaning, evidence and output actions |
| D | Full proposed TRACE-GC: admission, closure, packing, resolver, constraints and qualified risk policy | Report rejected, missing, failed and abstained cases |
| E | D with an autoresearch-selected question set | Freeze selection and calibration before final test |
| F | Same D workflow with a specialist classifier or another structured-output model | Separates workflow benefit from Jev benefit |
| G | Matched-scope KARMA implementation or clearly labeled KARMA-style baseline | Verify actual implementation, publication version, dataset and scope before claiming replication |

Do not import a published score from a different task into a head-to-head comparison. The original report supplies literature leads; a KARMA reproduction needs its own immutable source/commit and protocol. An actual replication has not been performed for this package.

## 6.4 Data partitions and annotation

Partition entities, source families, claims and connected evidence components before generating prompts. Record exclusions and dropped cross-partition pairs. Use temporal holdout for evolution. Gold annotations must distinguish supported, contradicted, unsupported and genuinely indeterminate cases with scope and time qualifiers.

Double-annotate consequential identity/contradiction cases where feasible, retain adjudication disagreements, and blind annotators to model arm. Synthetic adversarial cases test specified failure modes but do not replace naturally sampled evaluation data. Keep generated challenge labels separate from independent human or reference labels.

The model and resolver never receive evaluation labels. Include a negative control that changes evaluator labels and confirms identical graph output. Inspect duplicate leakage, source copying and entity overlap explicitly. Freeze the question program, schema, candidate universe, model pin, policies and all declared random seeds before final test.

## 6.5 Metrics and exact denominators

| Metric | Definition / reporting requirement |
|---|---|
| Candidate recall | Gold target objects represented among proposed candidates / all gold target objects |
| Evidence retrieval recall | Required annotated evidence retrieved / all annotated evidence required for the task |
| Accepted-edge precision | Correct typed, scoped accepted edges / all accepted edges |
| Accepted-edge recall | Correct typed, scoped accepted edges / all gold edges |
| Candidate coverage | Candidates receiving accepted actions / all candidates, including operational failures in the denominator |
| False automatic mutation rate | Incorrect auto-committed actions / all auto-committed actions; undefined when none |
| False-positive rate | Incorrect positive actions / gold-negative opportunities |
| Transaction failure/corruption | Invalid or partially published transactions / attempted transactions; report kinds separately |
| Identity quality | Pair metrics plus false merge/split counts, cluster metrics, cannot-link violations and affected-cluster size |
| Calibration | Brier/log loss, explicit ECE bins, reliability curves and uncertainty intervals by task/risk/source population |
| Provenance correctness | Assertions with verified source/version/span and correct evidence relationship / audited assertions |
| Repair quality | Correct deactivations, missed dependents, unnecessary removals and survival of independent support |
| Schema quality | Constraint violations, schema churn, migration impact and backward compatibility |
| Operational cost | Per-component and end-to-end billed usage, elapsed/active time, retries, storage and human-review minutes |
| Packing quality | State size, request/question count, estimator error, batch failure rate, per-question disagreement and latency |
| Replay quality | Exact-input recovery, semantic graph equality, artifact-byte equality where specified, and missing-dependency rate |

Polarity matters: accepting a refutation as support is a wrong typed edge and a missed correct edge. Isolation and density are graph-structure diagnostics, not truth metrics. A large graph is not automatically a better graph. Report severe errors and their dependency blast radius, not only average F1.

## 6.6 Matched operating points and statistical analysis

Compare both matched candidate/acceptance coverage and matched recall where attainable. Also report complete risk-coverage frontiers. Keep equal-score groups together, disclose ties and avoid inventing a perfect zero-risk origin when there were no accepted actions. Fix ranking rules without using gold labels.

Use paired comparisons over the same independent evaluation units. If documents/entities share dependencies, resample clusters rather than isolated rows. Report effect sizes and uncertainty intervals, with the bootstrap or statistical model fully specified. Primary outcomes and multiplicity treatment are preregistered for confirmatory studies; exploratory analyses remain labeled exploratory.

For very rare false merges, report absolute errors, affected records and an appropriate upper risk bound. Do not equate lack of a statistically resolved difference with equality. Do not claim better calibration from a single bin or from a vendor's global evaluation. Cost estimates from advertised rates remain estimates unless reconciled against billing.

## 6.7 Required ablations

Remove each of: Evidence Firewall tagging, dependency closure, packing, beam search, calibrated policy, claim-source verification, global identity resolution, independent verifier, and autoresearch. All unsafe variants run only in the sandbox. Keep the raw input and measurement pipeline identical.

Compare one broad prompt against atomic questions; atomic independent judgments against joint inference; and atomic judgments plus global constraints. Compare packed and unpacked exact-question programs, including shuffled question order and unrelated distractor context. Compare individual signals, simple composites and a separately calibrated learned resolver. Include a same-model repeated-judge control to test whether apparent independence is real.

For autoresearch, compare no optimization, rewrite-only, question discovery, redundancy pruning and complete optimization at a common search budget. Evaluate final graph outcomes rather than selecting questions solely by local feature fit.

## 6.8 Adversarial and lifecycle experiments

Test source withdrawal, copied sources, contradictory time periods, forged provenance, injected source instructions, irrelevant high-similarity passages, long required evidence, missing retrieval candidates, nonexclusive predicates, ambiguous identity bridges, stale snapshots, changed schemas and interrupted commits.

Use separate deterministic test oracles for span integrity, dependency closure, cannot-links, transaction atomicity and idempotency. Test legitimate instruction-like quotations so the Evidence Firewall does not erase useful evidence indiscriminately. An adversarial source classifier's score is not an authority test; permissions must remain unchanged even when classification fails.

## 6.9 Scaling and stop conditions

Measure at increasing source, candidate, question, assertion and dependency sizes. Initial tiers may be 1K, 10K and 100K decisions; larger tiers follow only after resource measurement. Keep measured and extrapolated results visibly separate. Report component costs and whether candidate generation, batching, solver work, graph snapshots or human review dominates.

Stop a run when budgets are exhausted, source integrity fails, qualification is absent, requested and returned model differ, or required invariants cannot be evaluated. Record the stopped run in the denominator and manifest. No threshold or extra retry may be introduced after seeing test outcomes without declaring a new exploratory run.
