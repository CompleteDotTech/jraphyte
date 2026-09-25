# 7. Question-set autoresearch and redundancy analysis

## 7.1 Controlled optimization target

Optimize the semantic program used by the compiler, not Jev's weights. TypeSafe's feature-discovery cookbook already illustrates an LLM proposing semantic questions whose Jev outputs become features for a downstream model [T8]. TRACE-GC adapts this pattern to graph outcomes, dependency-aware evidence and mutation risk; the pattern itself is not a new contribution.

A question-set version contains ordered questions/criteria, task families, required evidence fields, expected answer types, demonstrations, closure and packing policy versions, calibration compatibility and component hashes. Record the authoring model or human, proposal rationale, parent version and target errors. Production consumes only a promoted immutable version.

## 7.2 Search loop

Start from failures in a labeled development corpus. Classify the cause before proposing a semantic question: a missing candidate cannot necessarily be repaired by another verifier, a malformed span needs code, and a stale transaction needs synchronization. Proposals may change retrieval, parsing or rules as separate interventions rather than forcing every fix into Jev.

For a semantic proposal, specify the question, admissible answers, evidence requirements and expected downstream decision effect. Evaluate on development data, recompile the graph under a fixed policy experiment, then compare with the unchanged program. Retain raw observations, source hashes, search cost and both successful and failed proposals.

Use a separate selection set to compare bounded finalists, then freeze the program. Fit calibration and risk rules on separate calibration data. Evaluate once on the locked final test for the confirmatory report. Repeatedly reusing the final test to propose questions would turn it into development data; create a new untouched test before the next confirmatory release.

## 7.3 Selection objectives and safety constraints

The primary goal is approved graph quality at useful automation coverage. Cost and latency are explicit secondary objectives or resource constraints. A candidate program must not be promoted merely because it raises feature accuracy while increasing false identity merges, unsupported assertions, review load or end-to-end expense.

Define non-inferiority or maximum-regression rules before selection, by risk class and important population. Require sufficient evidence for rare severe errors. Use a Pareto comparison across quality, coverage and cost when a single weighted objective would hide policy choices. Weights and risk budgets are application decisions, not values the optimizing model invents.

## 7.4 Redundancy analysis

Measure feature correlation, decision agreement, conditional predictive value, correlated errors, request co-location and cost per useful decision. Perform removal ablations: does dropping question Q change accepted graph errors, abstention, identity components or source-withdrawal behavior? Test both common cases and the targeted rare failures.

Do not remove a question solely because it correlates with another. One may detect a rare subsidiary-versus-parent distinction the other misses. Conversely, retaining dozens of semantically similar questions can amplify a correlated misconception without adding evidence. Keep the smallest set that satisfies the measured performance and risk constraints on the declared population.

## 7.5 Candidate question examples

These are proposed hypotheses, not validated questions: does the source refer to the legal entity or a product brand; are two records different subsidiaries of the same parent; is a relationship historical rather than current; does a statement establish ownership rather than partnership; do apparently conflicting claims concern different populations; and do multiple sources trace to the same original report?

Every question must show incremental held-out value before promotion. Do not infer success from plausibility, an impressive example or the optimizing model's explanation.

## 7.6 Promotion protocol

A release candidate includes its full program, source and split manifests, observed model identities, baseline comparison, error deltas, removal ablations, calibration qualification, resource impact and an approval record. Reject programs that require unsupported evidence, violate packing dependencies or silently broaden mutation permissions.

Promotion changes the active question-program pointer under code/application control. Preserve the prior program for rollback and exact replay. Start with shadow evaluation and a bounded reviewed pilot. Rollback restores the old program for future decisions; it does not erase already committed graph mutations, which need their own audit and repair decisions.

## 7.7 Open improvement questions

Which errors are attributable to retrieval versus semantic judgment? Does added context reduce or increase ambiguity? Can a compact specialist replace a redundant question family? Do packed questions influence one another empirically despite API-level independent evaluation? How much reuse survives changing schemas? Does the optimization overfit rare adversarial examples? These are experimental questions, not capabilities established by the package tests.
