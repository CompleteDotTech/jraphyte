# Selector acceptance and rollback (issue #19)

This gate evaluates a candidate extraction configuration on the previously
examined 200-paper development corpus. It cannot qualify production accuracy,
enable automatic fallback, approve a source, or write a graph. Hosted unit tests
exercise the gate's semantics; they do not supply the private corpus evidence.

## Frozen candidate policy

The native policy selects `parallel_structure_v4`, measures all four
existing V4 arms, uses fresh first-physical-page native evidence, disables
fallback, and excludes `pdf-image-evidence-v1`. Image evidence's
`REVIEWED_TEXT_EVIDENCE` state is an application handoff, not graph admission or a
native-span success. Enabling that route requires a separately measured policy
and its typed source/crop/review evidence. Unknown policy fields or values must
fail closed. The second supported policy adds an explicitly reviewed image
route, described below; it performs no automatic OCR call or admission.

The exact supported policy is in
[`examples/selector_promotion/native-review-configuration.json`](../examples/selector_promotion/native-review-configuration.json).
Copy it to a new private configuration file before measurement. `verify` takes
the intended configuration explicitly and compares its content with the
recorded policy. The exact image-enabled alternative is in
[`image-review-configuration.json`](../examples/selector_promotion/image-review-configuration.json).
It changes `image_evidence_policy` to
`source-bound-attributed-image-review-v1`. A native-only receipt cannot authorize
this configuration or an image-enabled qualification run in #20. Each policy
needs its own bound acceptance receipt. No empirical passing result is asserted
by the policy examples.

The gate binds the implementation import closure, runtime lock and loaded
dependencies, configuration, frozen corpus/reference protocol, all original
PDF/page/image identities, converter inputs, native representations, assessment
files and fidelity reviews. A review supplement is explicitly hash-pinned and
does not overwrite the frozen legacy labels. Legacy and reviewed-fidelity
results have separate denominators and claims.

## Acceptance checks

Every check reports `PASS`, `FAIL` or `BLOCKED`. A missing artifact, source review
or identity binding is blocked evidence, never a passing substitute.

1. **Source and runtime provenance:** validate all 200 original cases through the
   locked extraction preflight. Match the saved experiment's code/runtime/input
   identities and verify native spans against the same source representation.
2. **Historical replay:** replay all frozen v2 assessments exactly using their
   saved native evidence. Recompute the original 91 correct IDs; retain the full
   ID set and test set inclusion, not just the number of recovered cases.
3. **Selected primary safety:** zero false proposals under the frozen complete,
   partial and absent classifications, legacy text comparison, reviewed boundary
   and notation checks. Withheld matching text is not a correct proposal.
4. **Reviewed source fidelity:** proposed text must have attributed, source-bound
   transcription, boundary, reading-order and notation evidence. Missing or
   unresolved dimensions stay blocked. A hash is not an authenticated review or
   proof of transcription accuracy.
5. **Known source outcomes:** check complete proposals for f030/f192/f119/f150,
   abstention for f199's author list, and f195's reviewed abstract extent without
   its footnote marker. Report f039 separately in every arm. Diagnostic arms may
   fail; they remain excluded from automatic selection.
6. **Whole-corpus reporting:** preserve 200 rows per arm, conversion errors,
   truncations, partial/absent classifications, all losses and gains, reason
   counts and review workload. Recheck every input and code hash before writing
   a completion receipt.

The integrated #17 selector still has unresolved preservation losses. An earlier
paired diagnostic or an unsigned `PASS` field cannot stand in for the integrated
measurement. No current quality pass is asserted by this document.

## Commands and immutable outputs

Run from the repository checkout with the locked research interpreter. All
paths following `--data-root` are relative to that explicitly authorized
external directory. It must contain the original source PDFs, frozen
references, page/image preparations, converter caches and exact source map.
The command below uses the existing extraction CLI and all four default arms:

```powershell
python -m src.parallel_source_v4.extraction regression --data-root $DataRoot --source-map source-map.json --native-mode fresh --output runs/candidate-200
python -m src.parallel_source_v4.promotion_io assess --data-root $DataRoot --configuration candidate-configuration.json --source-map source-map.json --run runs/candidate-200 --run-sha256 $ResultsSha256 --review reviews/fidelity.json --review-sha256 $ReviewSha256 --output acceptance/candidate-200
python -m src.parallel_source_v4.promotion_io verify --data-root $DataRoot --configuration candidate-configuration.json --source-map source-map.json --receipt acceptance/candidate-200/acceptance.json --receipt-sha256 $AcceptanceSha256
```

The SHA variables are the full byte SHA-256 values recorded from the reviewed
results, review supplement and private acceptance file. They are mandatory
trust inputs, not values inferred from an untrusted receipt. `--runtime-lock`
may select an explicitly reviewed lock; its environment and hash remain bound.
Omitting both review arguments is supported and reports missing fidelity
evidence as `BLOCKED`. Exit codes are 0 for `PASS`, 1 for `FAIL`, 2 for `BLOCKED`.
Existing outputs and historical cache directories cannot be overwritten.

The regression results now contain `assessment_files_sha256` for the exact
bytes of all 800 assessment files. Older runs without this measured output
manifest cannot qualify. Creating a manifest afterward would not bind what
the measurement actually consumed. The acceptance adapter requires the
sealed native identity introduced in #17 and recomputes all legacy metrics.

`acceptance.json` is private: it records input paths, invocation and any derived
reviewed assessments. `reviewed-assessments/<case>.json` contains immutable
copies of derived assessments. `public-receipt.json` excludes private paths,
source text, reviewer names and review notes; it retains cases, counts, gate
outcomes, code/runtime/configuration hashes, asset hashes and the private
acceptance file hash. A public receipt alone cannot authorize promotion.

## Attributed fidelity and manual closure reviews

The optional supplement has the following structure:

```json
{
  "version": "promotion-fidelity-review-v1",
  "cases": {
    "f001": {
      "status": "complete",
      "text": "<source-reviewed reference transcription>",
      "fidelity_review": {"<fields>": "the existing #14 fidelity review contract"},
      "closure_review": {"<fields>": "the optional closure contract below"}
    }
  }
}
```

This is a schematic, not an executable review. `status` must equal the frozen
classification. `text` supplements the fidelity reference only; it cannot
rewrite legacy labels. The #14 review binds attribution, review timestamp,
reference text SHA, original PDF/page SHA, notation evidence, native identity,
ordered reference spans, section ownership and excluded role spans. The
acceptance adapter reads every reference span back from the current native
representation and checks its transcription. Missing or unresolved fidelity
evidence never becomes certified through manual closure.

`closure_review` is optional and applies only to the selected primary's held,
successful, nonempty native candidate. It cannot change the candidate text
except whitespace equivalence, exceed the original request budget, change a
partial/absent/error/truncated state, or add page-two text. All cases use the
same validation; there are no case-ID overrides. Its exact fields are:

| Field | Required content |
| --- | --- |
| `version` | `native-closure-review-v1` |
| `assessment_sha256`, `text_sha256` | Original sealed candidate identities |
| `source_sha256`, `page_sha256`, `image_sha256`, `native_sha256` | Verified original PDF, physical-page-one PDF, full image bytes and logical native representation |
| `physical_page`, `decision` | Integer `1`, `complete` |
| `reviewer`, `reviewer_kind`, `reviewed_at` | Nonempty attributed identity, `assistant` or `human`, timezone-aware timestamp no later than acceptance |
| `independent_review`, `exposure`, `source_before_predictions` | `false`, `previously_examined_development`, `false` |
| `checks` | Exact keys `transcription`, `reading_order`, `boundaries`, `notation`, `no_page_continuation`, each `true` after actual review |
| `accepted_spans` | Ordered exact native spans with source line IDs, Python code-point offsets, text, boxes and physical page one |
| `excluded_spans` | Groups with `role` (`metadata`, `body`, `footnote`, `other`) and exact `spans`; no overlap with the accepted extent |
| `excluded_regions` | Observed full-page image regions, or an empty list; each has `role`, finite `bbox`, `image_sha256`, integer `physical_page: 1`, and `coordinate_system: full-page-image-pixels-top-left` |
| `closure` | Exact keys `kind`, `page_one_image`, `next_page` as described below |

An image asset has exactly `relative`, `sha256`, `physical_page` and integer
`dpi: 120`. It must be a full PNG rendering of that original PDF page. Page-one
bytes must also match the frozen review image; the renderer comparison permits
only the existing preparation tolerance of two channel values. Page two must
render exactly. Excluded image regions must lie inside that image and cannot
cover accepted native line boxes. This permits an attributed reviewer to cite
a distinct shaded synopsis box or keyword/body transition without inventing a
native heading. A transition witness must follow the last accepted native
extent with compatible horizontal overlap (including wider body regions).
Image witnesses must also contain visible contrast; blank or preceding
rectangles and a footnote alone cannot establish closure.

`reviewed_section_transition` needs excluded native spans or observed image
regions and `next_page: null`. `reviewed_title_page_end` requires actual document
end (`next_page: {"document_end": true}`) for a one-page original. Longer
originals require `next_page: {"image": <asset>, "native": <asset>}`. The native
asset has exactly `relative`, `sha256`, integer `physical_page: 2`, and
`representation: pymupdf-page-dict-v1`; its JSON must equal the original page's
`get_text("dict", flags=fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES)` output.
The full image supplies drawing/background evidence omitted from that text
representation. The reviewer must actually inspect these bound assets. Hash
validation verifies identity and source correspondence, not a person's review.

A successful closure creates a new sealed assessment linked by
`original_assessment_sha256` and `manual_closure_review_sha256`. It always keeps
`eligible_for_jev` and `verified_admission` false and requires source review.
The receipt reports automatic assessments separately from the selected
reviewed path, including each manually resolved ID, blocked review and asset
identity. A reviewed result never replaces or relabels automatic recall.

### Observed candidate failures

A failed or unresolved **reference** notation review cannot prove that every
candidate is wrong. A source reviewer may instead add `candidate_observations`
to a supplement case. It is a nonempty list of negative-only records with these
exact fields:

- `version: candidate-fidelity-failure-v1`, `status: fail`, and a unique
  `dimension` of `notation`, `boundary` or `reading_order`.
- `assessment_sha256`, `text_sha256`, `source_sha256`, `page_sha256`,
  `native_sha256`, `image_sha256`, and integer `physical_page: 1`.
- `reviewer`, `reviewer_kind`, `reviewed_at`, `independent_review: false`,
  `exposure: previously_examined_development`, `source_before_predictions: false`.
- A nonempty `evidence_id` and private `note` describing the actually observed
  source mismatch. The reviewer must inspect the bound source image.

The adapter validates each record against the exact original primary candidate
and source representation. A stale identity or invalid review blocks the audit.
It then marks only the matching candidate's observed dimension as `fail`.
Failures also remain attached to a manual closure derived from that candidate:
resealing the same text and extent cannot repair known notation, order or
contamination errors. A separately reviewed image transcription needs its own
evidence. These records cannot certify a reference, rewrite text, select an image
route under the original image policy, or enable graph admission.
Public reports retain dimension and identity hashes, excluding reviewer notes.

## Image-enabled policy and route manifest

The image policy requires `--image-manifest <relative-path>` and
`--image-manifest-sha256 <externally-pinned-byte-hash>` on `assess`. The manifest
has exactly `version: promotion-image-route-v1`, `native_results_sha256`,
`configuration_sha256` (the semantic digest of the exact image policy), and
`cases`. Every original case ID must appear exactly once. Each case has:

| Field | Required content |
| --- | --- |
| `native_assessment_sha256` | Sealed original primary assessment from the pinned 200-case run |
| `source_sha256`, `page_sha256` | That case's original source and first-page PDF bytes |
| `route` | `native_or_hold` or `image_review` |
| `evidence`, `scope_review` | `null` for `native_or_hold`; the structures below for image review |

`native_or_hold` retains the automatic/native-closure result. `image_review`
cannot replace an already selected native proposal. It verifies each asset from
an explicit `{relative, sha256}` descriptor under `evidence`: `preparation`, `reviewed_candidate`,
`raw_ocr`, `page_image`, `crop_image`, `execution`, `handoff`, `catalog_records`.
The existing #18 CLI creates these artifacts. Execution and handoff receipts
must match the **current complete image code identity**, including schemas and
the Windows helper. Old code receipts require a fresh image exercise.
The preparation receipt's source identity, metadata and code must match, and
its exact byte SHA must equal the execution receipt's `preparation_sha256`.

The first implementation supports the installed local Windows OCR adapter.
It checks raw engine/revision/configuration, crop input hash, helper hash,
source render and exact image bytes. An optional single correction must link
to the original raw transcription and candidate; a new source review is
required afterward. Arbitrary imported OCR and unrecorded multi-step correction
histories remain blocked. Raw errors and correction counts are reported
separately from final reviewed text.

`scope_review` has exactly `candidate_sha256`, `decision` (`complete`, `partial`,
`absent`, `uncertain`), `reviewer`, `reviewer_kind`, `reviewed_at`,
`independent_review: false`, `exposure: previously_examined_development`,
`source_before_predictions: false`, `checks`, and `closure`. Checks are the
booleans `native_image_disagreement_examined` and `no_page_continuation`.
Both must be true for a proposal. A complete decision also requires closure:

- `reviewed_section_transition`: exact keys `kind`, `excluded_regions`,
  `next_page`; at least one nonblank image box follows the reviewed crop with
  compatible overlap, every box is in full-page pixel coordinates and disjoint
  from that crop, and `next_page` is null.
- `reviewed_title_page_end`: same keys; an actual one-page document needs
  `next_page: {document_end: true}`. Otherwise it requires the source-verified
  120-DPI page-two image and native dict assets used by the native closure
  contract. No page-two text is appended to the abstract.

Each image proposal additionally needs a separate `image_reference` under its
fidelity supplement case, with `status`, `text`, and `fidelity_review`. The
frozen status cannot change. Its #14 boundary representation must be
`image_regions`, bound to the rendered full-page PNG SHA and image dimensions,
with the exact reviewed crop region. Native offsets cannot certify this route.
Unresolved notation, boundaries or order cannot be cleared by a #18 handoff.

The adapter rebuilds the #18 handoff and typed catalog **in memory** and compares
the complete record set. It creates no assertions or application graph writes.
Partial/absent/uncertain and failed image reviews stay held and contribute zero
selected image proposals. All 200 routing outcomes remain in the receipt.
Image-policy acceptance also requires at least one successfully reviewed image
proposal in the real corpus run; a native-only table with an image-enabled
label remains blocked. Source fidelity, the original 91-ID preservation set,
all known source outcomes and every other gate still apply to the combined
reviewed path. The automatic, native manual-closure and image outcomes remain
separately visible.

## Release gate and trust

### Explicitly failed native candidate replacement

The third exact policy is
[`failed-native-image-review-configuration.json`](../examples/selector_promotion/failed-native-image-review-configuration.json).
It adds `native_failure_policy: source-bound-failed-native-image-replacement-v1`
to the image policy and has a different configuration digest. Earlier native
and image receipts cannot authorize it.

This policy permits an image route to replace an automatic native proposal only
when an attributed negative observation binds that exact original assessment,
text, source, page, native representation and source image. The selected native
assessment must still be that original; a closure-only reseal cannot create an
exception. The image adapter revalidates those observations itself. Healthy
native proposals, missing or stale observations, and purported positive
observations cannot enter this route.

Routing eligibility does not approve a transcription. Every preparation, OCR,
correction, source-render, code, scope, closure and image-fidelity check still
applies. A known notation or reading-order fault also requires an actual change
in the compared transcription; identical text or a whitespace-only rewrite
cannot clear it. A partial, absent or unresolved image remains held. The audit
retains automatic native failures and observation hashes; only a successfully
reviewed replacement records `superseded_native_assessment_sha256`. The derived
image assessment binds those failure hashes and its original native identity.
No automatic text repair or graph admission is performed.

This policy has authored/adversarial tests. Its empirical exact-tree 200-paper
and image receipts remain required before promotion; the earlier failed audit
does not measure this additional policy.

The intended release gate is an authorized maintainer's local verification with
the actual external corpus and an explicitly pinned acceptance-receipt hash.
It runs before selecting a new reviewed extraction configuration for a release.
The verifier checks the recorded acceptance from its bound artifacts and current
code/configuration/runtime/input identity. A changed configuration or stale
source/metric/code identity requires a new measurement and receipt.

Hashes establish identity and integrity, not who ran the experiment or who
reviewed its sources. The expected receipt hash must come from the maintainer's
reviewed release record; reading that expected hash from the untrusted receipt
itself would provide no trust anchor. The normal signed Git/release process
controls publication. Ordinary hosted CI remains an offline contract gate.

## Rollback

Disable selection of the failing candidate first and preserve its failure
receipt. Keep immutable current/previous configuration and receipt hashes in the
release record. Reverting code alone does not make a previous receipt current.

To restore a prior candidate, inspect its exact checkout in isolation and verify
the previously pinned receipt against the currently authorized source state and
the recorded runtime. If any required evidence has changed or is unavailable,
remain disabled. Never convert a failed receipt to `PASS`, rewrite historical
evidence, activate an unmeasured fallback, or use rollback to bypass source
review or graph publication gates. This extraction gate performs no application
configuration change or graph operation.

From the isolated previous checkout, `promotion_io rollback-plan` accepts the
same arguments as `verify`. It emits a plan only after the prior receipt passes
current verification. It records `disable_current_candidate_first: true` and
`activate_automatically: false`; an operator still controls release selection.

## Validation scope

### Recorded development audit, 2026-09-28

The [compact empirical receipt](../review/selector_promotion_v1/experiment_20260928.json)
binds a fresh 200-paper, four-arm run on base `36768a3` plus the recorded
implementation closure. Its automatic primary proposed 74 legacy-correct
abstracts and lost 20 of the original 91. Seven attributed native closure
reviews increased the selected count to 81; a separately reviewed, corrected
image transcription increased it to 82. These are legacy text/boundary counts:
only 9 native-policy and 10 image-policy proposals had completed source-fidelity
evidence in that audit. One proposed case failed notation review, and 71
proposed cases still lacked completed fidelity review. No production accuracy
or complete recovery is established.

Both acceptance receipts are **FAIL**. Original-ID preservation still loses
15 cases under the native policy and 14 under the image policy. The f192 review
found scientific typography absent from both native text and the old reference;
agreement with that reference cannot certify source fidelity. Both real
nonpassing receipts were rejected by `verify` with `BLOCKED` and exit code 2.

The image audit also exposed a default-reference adapter defect: frozen label
metadata was passed to the strict image-reference schema, incorrectly blocking
199 routing records. The implementation now projects only unreviewed scope and
text for the fallback. An authored 200-case test reproduced the defect and
passes after the fix; all 29 affected tests pass. This change occurred **after**
the recorded empirical run. It and later selector changes require fresh exact
code, image and 200-case receipts. The failed records remain immutable and
cannot authorize the current tree. The six actual local OCR calls comprised
four exposed real pages and two authored fixtures; no paid calls or production
graph writes occurred.

A subsequent [attributed source review receipt](../review/selector_promotion_v1/source_review_20260928.json)
records all 74 automatic proposals from that exact measured run: **57 verified
source-fidelity proposals and 17 observed failures**, with no unresolved reviews
among those 74. The failure set includes flattened scientific scripts, detached
accents and f149's interior footnote marker. Its reference extent excludes that
one native character. Negative observations retain the other candidate faults
without inventing corrected mathematical transcriptions. This source-review
rescore is separate from acceptance and does not qualify later code or activate
automatic correction. The original failed receipts remain unchanged.

`python -m unittest tests.test_selector_promotion tests.test_selector_promotion_image -v` exercises authored cases,
source-rendered PDF fixtures and actual immutable file readbacks. It tests
missing/altered receipts, output resealing, configuration drift, corpus set
replacement, review evidence gaps, mutation during verification, title-page
page-two substitution, geometry conflicts and false independence claims.
These tests neither read the private corpus nor qualify empirical accuracy.
