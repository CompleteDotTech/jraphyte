# Source-verified selector acceptance v2

This is a separate, user-approved development regression policy. It leaves the
frozen selector promotion v1 scorer, references, thresholds, cases, and receipt
unchanged. A v1 `FAIL` remains a v1 `FAIL` in the new receipt. The v2 gate is
eligible only when the authentic v1 analysis replays byte for byte and its only
failed gates are `preserve_91` or `zero_false_primary_proposals`. Every other
v1 gate must pass. A blocked legacy gate cannot be reclassified.

The new gate checks all 200 cases and all four converter arms, the frozen gold
counts (111 complete, 7 partial, 82 absent), the original 91 correct IDs as a
subset of currently source-verified selected proposals, and zero selected
proposals with non-complete gold or unresolved notation, boundary, reading
order, or source location. It requires the v1 source-fidelity gate's trusted
verified-correct count, original-source outcomes, f195 boundary, saved replay,
and complete image route gate to pass. No Unicode alias, threshold change, or
case exception is introduced.

The policy file has exact keys `version`, `approval`, `base_acceptance`,
`configuration`, and `source_map`. The four latter values are `{relative,
sha256}` descriptors inside the authorized private data root. The caller must
provide the policy's SHA-256 separately. The approval descriptor must identify
the exact user-approved amendment record. The code verifies those hashes,
reopens all derived assessments, and replays the authentic v1 analyzer against
the pinned inputs and runtime before issuing the v2 receipt. Verification
repeats the complete process and compares the receipt exactly. The v2 code
hash is included, so changing this policy code invalidates the receipt.

Example invocation (fill exact private paths and hashes from the release
record):

```text
python -m src.paper_selector_acceptance_v2 assess --data-root DATA_ROOT \
  --policy POLICY_RELATIVE --policy-sha256 POLICY_SHA256 \
  --configuration CONFIG_RELATIVE --source-map SOURCE_MAP_RELATIVE \
  --output validation_v3_private/NEW_PRIVATE_OUTPUT
python -m src.paper_selector_acceptance_v2 verify --data-root DATA_ROOT \
  --policy POLICY_RELATIVE --policy-sha256 POLICY_SHA256 \
  --configuration CONFIG_RELATIVE --source-map SOURCE_MAP_RELATIVE \
  --receipt V2_RECEIPT_RELATIVE --receipt-sha256 V2_RECEIPT_SHA256
```

`paper_qualification_v1` accepts a v2 regression only with an additional
`regression_policy` descriptor in its bundle and phase commitments. A v1
bundle keeps its original contract and rejects that extra field. Qualification
still applies its own preregistration, unseen-source, reviewer, converter,
statistical, and publication gates. The source-verified development regression
is not independent human review, graph admission, automatic fallback, or an
authorization to write production graphs.

## Original 200-paper development result

The actual integrated run proposes 97 of the 111 complete abstracts: 73 native
and 24 current, attributed image routes. All 97 pass source-bound notation,
boundary, reading-order and source-location review. Source-verified complete
recall is 97/111 (87.39%); source-verified proposal precision is 97/97 (100%).
Fourteen complete abstracts remain withheld. The full denominator also retains
all seven partial and 82 absent cases. This is an examined development cohort;
these fractions do not establish unseen-paper accuracy.

All 91 original legacy-success IDs are included, with six additional correct
proposals. The unchanged legacy text comparator reports 97 successes, while
its boundary check fails for f081: the source uses Greek Delta and the frozen
reference uses the distinct increment character. The authentic v1 receipt
therefore remains `FAIL`. No reference, comparator, threshold or paper-specific
alias was changed to obtain the separate v2 `PASS`.

The public [empirical receipt](../review/source_verified_selector_acceptance_v2/empirical_receipt_20260929.json)
binds the private approval, policy, authentic legacy receipt, source-verified
receipt and separate replay readback by SHA-256. Private source text, models,
PDFs and reference labels remain outside this repository. The earlier replay
attempts are preserved as invalid in a separately hashed history; only stable
assess03 and its fresh verification supply this result.
