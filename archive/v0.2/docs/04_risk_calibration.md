# 4. Risk policy and empirical calibration

## 4.1 Four values, four meanings

Keep the semantic outcome, raw model distribution, raw distribution-derived confidence and application action separate. A policy or resolver score is a fifth value with a separate type. No monotonic transformation, weighted sum or product of local scores is a joint probability merely because it lies between zero and one.

For an ordered Score with levels 0, 1 and 2, both `P(0)=0.5, P(2)=0.5` and `P(1)=1` have mean 1. The first is polarized, the second concentrated. Routing both as an observed “middle” category discards relevant uncertainty. Use a nominal Choice when the task is to choose among meaningfully distinct outcomes. This is a mathematical example, not a claim about an observed Jev run.

Noul has no separate raw confidence field. Choice and Score provide a distribution-derived confidence statistic [T3]. Neither a high score nor a concentrated distribution proves an individual semantic judgment. Preserve the full distribution and evaluate task-specific calibration rather than treating confidence as another independent vote.

## 4.2 Risk classes

| Class | Minimum interpretation | Default in this revision |
|---|---|---|
| R0 | No accepted-graph state change; analysis or routing | Allow bounded analysis and audit recording |
| R1 | Quarantined candidate/support metadata; no promotion to accepted truth | Allow only deterministic integrity and access checks |
| R2 | New ordinary accepted relation or assertion | Automatic acceptance disabled until qualified |
| R3 | Modify, supersede or retract an existing accepted assertion | Qualified policy plus current-state validation; otherwise review |
| R4 | Identity equivalence or entity merge with potentially broad downstream effects | Reversible identity view, cluster/cannot-link checks, precision-focused qualification and review by default |
| R5 | Destructive or global/schema restructuring, mass migration | Shadow analysis and explicit authorization; no automatic deployment in the initial prototype |

These are lower bounds. A supposedly ordinary edge can be high risk in a consequential application. Compute effective risk from operation class, affected-object count, dependent assertions, data sensitivity and downstream use. The same framework does not prescribe a universal acceptable error rate.

A policy author, not a model, approves risk tolerance. A model cannot lower its own proposal's risk. Human review is still constrained by authorization and deterministic graph validity. Trusted source-withdrawal processing may run under an explicitly approved deterministic maintenance policy; it is not equivalent to a model deciding that evidence is false.

## 4.3 Analysis-only default

`policies/analysis-only.json` intentionally contains no production thresholds or qualification artifact. R2–R5 semantic auto-commit is disabled. The example candidate may have apparently strong synthetic probabilities and still ends in ABSTAIN. This is the expected result until the actual task/model/program/population is qualified.

The illustrative confidence ranges in the supplied requirements remain examples only [R1, §14]. `strong_no`, `likely_no`, `uncertain`, `likely_yes` and `strong_yes` become operational only through a versioned mapping learned and validated on appropriate data. Before qualification, the band is UNQUALIFIED; missing calibration does not mean zero or average confidence.

## 4.4 Qualification record

A qualification artifact must bind: task and predicate contract; risk class; source population; requested and observed exact model; full question-set hash; closure and packing policy; candidate generator/blocking version; feature/resolver version; calibration method; development, selection, calibration and test split manifests; evaluation-unit definition; target metric and denominator; confidence-bound procedure; minimum coverage; selected thresholds; date; reviewer; and expiry/drift rules.

Use identity-disjoint or connected-component splits for entity resolution. Group duplicate/source families and shared documents so near-identical evidence does not cross evaluation boundaries. For chronological maintenance, use forward-time evaluation with no future evidence. A random row split is not automatically suitable when multiple rows share the same underlying entity or claim.

Keep four roles distinct: development data for inventing questions; selection validation for comparing candidate programs; calibration data for fitting probability transforms and risk rules; locked test data for the final confirmatory estimate. Small datasets may require carefully documented nested or cross-fitted procedures, but repeated tuning on the final test remains prohibited.

## 4.5 What to measure and qualify

Report classification precision/recall/F1, Brier score, log loss where defined, expected calibration error with binning specified, reliability diagrams and risk-coverage curves. For identity, include false merges, false splits and cluster-level error. For mutation policies, report accepted assertion errors and transaction-level failures separately.

The false automatic mutation rate is incorrect automatically committed actions divided by all automatically committed actions. A false-positive rate is incorrect positive actions divided by gold-negative opportunities. These denominators are not interchangeable. With zero accepted actions, accepted-action risk is undefined, not zero.

Qualification should use an upper uncertainty bound on the approved risk measure and a nontrivial coverage condition, not merely empirical zero errors. Independent negative examples may support an exact binomial treatment; dependent components require a justified cluster-level method. Correct for selection over multiple thresholds and document assumptions. As a sanity check, with zero errors in independent Bernoulli trials, the one-sided upper bound is `1 - alpha**(1/n)`; small samples cannot support extremely small risk claims. This calculation is conditional on the sampling model, not a deployment guarantee.

Separate probability calibration from decision-policy selection. A calibrated classifier can still require conservative abstention for a high-impact merge. A policy that satisfies a particular false-positive criterion may still have poor precision under a different match prevalence. Report sensitivity to deployment class mixtures rather than transferring a convenient benchmark balance into production.

## 4.6 Model and program upgrades

Pin `jev-1.13.0` only for the documented version reviewed here; do not label it permanently latest [T1]. Store requested and returned versions. Aliases are unsuitable for stable calibrated production experiments unless the resolved version is verified and qualification explicitly targets that resolution.

Any change in model, question wording, option menu, demonstrations, retrieval policy, closure composition, packing behavior, resolver features or source population requires a compatibility assessment. A state hash alone cannot justify cache reuse after a changed question. Deploy a new policy version only after regression and qualification checks. Failed checks keep the previous promoted version or switch to analysis/review mode.

## 4.7 Aggregate probabilities and source dependence

A learned resolver may consume Jev outputs, source metadata and graph features. Train and calibrate it as a separate statistical model using out-of-fold or otherwise leakage-controlled features. Log its version and uncertainty assumptions. Until validated, call its output a resolver score.

Sources that copy the same article do not provide independent corroboration. Two prompts over the same model/state are not automatically independent judges. A distinct model family can still share errors. Track source families, question correlation and disagreement, then test whether a second judgment adds conditional predictive value and reduces high-risk errors.
