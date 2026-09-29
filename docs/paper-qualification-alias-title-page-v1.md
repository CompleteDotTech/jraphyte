# Prospective alias and title-page evidence

This document describes two optional inputs to `paper_qualification_v1`. They do not change the 400-paper primary target, 1,200 source screens, challenge quotas, four genuine converter arms, or review and signoff phases.

## Identity exclusion

Each entry in `sampling.identity_exclusions` names a versionless arXiv work, a reason (`same_doi`, `same_source`, or `same_page`), and an immutable `evidence` descriptor. The descriptor resolves to `paper-identity-alias-proof-v1`, which names an exposed work, the reason, a timestamp before cohort freeze, and either:

- `same_doi`: no assets; the candidate DOI in the frozen metadata projection must exactly equal a DOI in the named exposed work's reconciled inventory.
- `same_source` or `same_page`: a complete candidate source/page/image/native asset set and pinned version and DOI. The verifier reopens the source PDF, confirms the extracted first page, re-renders the original image, re-extracts native spans, and compares the nominated byte hash to the named exposed work.

The work is excluded before deterministic sampling rank is computed. An unavailable, corrupt, encrypted, or failed converter case cannot use this path. Unknown aliases fail closed. The exposure snapshot remains a separately pinned cohort-freeze input; rerun reconciliation before freezing a new cohort.

## Title-page closure

`reviewed_title_page_end` requires an explicit `next_page` witness. A one-page PDF must say `{"document_end": true}`. For a longer PDF, the witness carries an exact page-two PNG at 120 dpi and a PyMuPDF native page dictionary; both are checked against page two of the original PDF. Page-one excluded regions remain disjoint and visibly nonblank. The separately signed reference phase must contain source-review events for both page-two hashes before `references_frozen`, after the first-page image event. Candidate scope review and the independently frozen source extent proof must agree on the exact closure witness. This is a source identity, access, and extent check; the attributed source reviewer must still judge whether page two continues the abstract. The existing adjudication, audit, and signatures remain mandatory.

No authored fixture or adapter unit test is an empirical paper qualification result. Any evaluator-code change requires a new code hash in access and execution artifacts before a prospective run.
