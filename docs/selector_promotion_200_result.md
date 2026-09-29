# Reviewed selector result: 200-paper development corpus

The exact reviewed configuration passed the full acceptance audit and its
verifier replay on 2026-09-28. The selected 97 proposals passed
source-fidelity review and the unchanged legacy text98/boundary48 checks. All
91 historical successes were preserved.

The [redacted receipt](../review/selector_promotion_200_20260928/receipt.json)
records the counts, gate outcomes and artifact hashes. Its SHA-256 is
`fb1b32a0ecb896901a95b94950cee19f6126e82249054aead9a6464aa62b20e3`.

## Scope and measured results

The measurement used commit
`7cbc22fb217f2ccac822f7e3badf2815fdb3ea13`, fresh native extraction of the first
physical page of 200 previously examined papers, and four assessment arms
using frozen converter outputs. All 800 assessment files were bound to the
run. The primary policy is
[`failed-native-image-review-configuration.json`](../examples/selector_promotion/failed-native-image-review-configuration.json).

| Measure | Automatic primary | Reviewed primary |
| --- | ---: | ---: |
| Proposed complete abstracts | 79 | 97 |
| Legacy text98 and boundary48 correct | 79 | 97 |
| Proposals verified for source fidelity | 62 | 97 |
| Proposed notation failures | 17 | 0 |
| Historical successes lost | 16 | 0 |
| Complete first-page abstracts withheld | 32 | 14 |

There are 111 complete first-page abstracts in the frozen corpus. The reviewed
result retains 91/91 historical successes, adds six correct proposals and has
97/111 verified complete-abstract recall (87.39%). It has zero false, partial or
absent proposals under the frozen classifications and reviewed evidence.

The 97 selected proposals comprise:

- **62 native proposals** with attributed source-fidelity evidence.
- **11 native proposals with attributed closure/ownership reviews**, preserving
  their original text and native spans.
- **24 corrected image transcriptions**, each with current-code local OCR
  lineage, source/crop evidence, explicit correction and source review. These
  are separate typed image representations with no invented native offsets.

All 24 original native-negative records remain in the evidence history,
including the 17 failures among automatic proposals. Reviewers were internally
attributed assistants working on previously examined development cases. No
independent-human or unseen-corpus qualification is claimed. Fourteen complete
first-page abstracts remain withheld.

## Gate and integrity readback

All eight acceptance gates passed: provenance, exact saved v2 replay for all
200 cases, preservation of the historical success set, zero false primary
proposals, reviewed fidelity for every proposal, specified original-source
outcomes, reviewed boundary extent, and the image-route gate covering all 200
cases. Diagnostic arms remain outside automatic selection.

The actual promotion verifier repeated the full analysis and matched the
private receipt exactly. Subsequent readback checked **3,613 bound inputs**,
**35 sealed derived assessments**, the public/private projection, and the
method, image implementation and runtime identities. Postwrite checks passed.

| Artifact | SHA-256 |
| --- | --- |
| Fresh extraction results | `532bb1f40718c8f5aa441be229ef2acd351a0c70b1d42bce5ec90f7f5bac87f8` |
| Private passing acceptance | `40a6263d5c7b25100ba4a0b8bf46cb36459e93320446b87c5dc6afb5b1412477` |
| Verifier/readback receipt | `699d826d7cfd5f0cc99b71b7bfb145f8be4ff2030daf934254dcb09ab001347c` |
| Consolidated review supplement | `5f2e3c90bfbe313f2f3d3e0f4e1b3c45e459fa27c7d60d52ab941cf1e64f1dad` |
| All-case image-route manifest | `8f7c5c6b5b644537f82d2cf493e6e858d4273bce9fd84e18a03315eb143abfda` |

The earlier acceptance remains an immutable **FAIL** receipt
(`c1476ff7551dc89b0f8dfa2b8a6c7cf17f4baefdd1243fcc6edd5155f1a3521e`). It
recorded 16 selected notation failures and three legacy serialization
mismatches. Separately reviewed corrections resolved these. The three
serialization replacements preserve source-visible fraction grouping, accents
and glyph identities with explicit plain/Unicode notation. Neither the frozen
reference nor the 98% and boundary thresholds changed. Earlier candidates and
their reviews remain in the private lineage.

## Verification and limits

With authorized access to the private evidence archive and its locked runtime,
use the existing [acceptance commands](selector_promotion.md#commands-and-immutable-outputs).
The verification invocation accepts the externally pinned private receipt hash:

```powershell
python -m src.parallel_source_v4.promotion_io verify --data-root $DataRoot --configuration $ConfigurationRelative --source-map $SourceMapRelative --receipt $AcceptanceRelative --receipt-sha256 40a6263d5c7b25100ba4a0b8bf46cb36459e93320446b87c5dc6afb5b1412477
```

The public artifact contains aggregate counts and hashes; source documents,
transcriptions, per-case labels, reviewer notes and private paths remain in the
authorized archive. Public hashes alone cannot replay the private corpus or
authorize promotion. A change to the measured code, configuration, review or
source identities requires the corresponding fresh measurement and verifier
readback.

This result applies to the exact reviewed first-page configuration. Automatic
fallback, source admission and graph admission remain disabled. The audit
made no paid calls or production graph writes and activated no release.
Document-wide extraction, unseen qualification, retrieval and a cited GraphRAG
pilot retain their separate acceptance requirements.
