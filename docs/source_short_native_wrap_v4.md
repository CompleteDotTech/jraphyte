# Native short-wrap source chain

The locator now considers one short, punctuated native line between two wide rows in the same lane when native font, left edge, vertical spacing, and full-page competing-row checks agree. This adds a candidate search chain. The existing exact occurrence and 98% alignment rules, source span validation, column-transition checks, and duplicate-occurrence hold still decide whether a proposal is possible.

The case arose when a width-filtered lane omitted a short but source-owned sentence. A fuzzy global match then met the 98% threshold while dropping that whole sentence; the paragraph composer correctly refused to use a model-box-only proof. The added native chain lets global matching retain the complete source text. Duplicate full occurrences remain ambiguous, and off-lane, changed-font, separated, or interrupted short rows do not get the added chain.

This is an extraction behavior change. Current-code source verification and full cohort acceptance must be repeated before a producer resumes. The stopped d06308 converter document is reused only through the sealed migration plan; the source replay does not call the converter again.
