# 09 · PDF evidence and source-review admission

[Atlas index](README.md) · [Mermaid source](09-pdf-evidence-review.mmd) · [High-resolution PNG](png/09-pdf-evidence-review.png)

The PDF modules select evidence from the **first physical page** and produce auditable proposals. The admission adapter can prepare an exact Jev request only from an attributed, complete source review. It performs no API call or graph mutation.

**Status at reviewed revision `d5ca636`: experimental.** V1/v2 eligibility flags are scoring signals; they cannot substitute for a review receipt. V3 and parallel v4 explicitly keep `eligible_for_jev=false` and `verified_admission=false`. Their preservation regressions remain failing; see [research evidence](10-research-experiments.md).

## Workflow

```mermaid
flowchart TB
    accTitle: First-page evidence, selector review, and request admission
    accDescr: Source files and experimental selectors produce reviewable receipts. Only an intact complete source review with current hashes and budgets can prepare a Jev request. Preparation does not send it or authorize a graph mutation.
    subgraph S["01 / SOURCE EVIDENCE"]
        A["Authorized original PDF"]:::input
        B["Extract physical page one<br/>Render image and native spans"]:::process
        C["Source / page / image hashes<br/>Source coordinates and text"]:::artifact
        A --> B --> C
    end
    subgraph PROPOSALS["02 / EXPERIMENTAL PROPOSALS"]
        D["Cached Docling / GROBID<br/>MinerU / olmOCR outputs"]:::external
        E["Frozen v1 geometry<br/>or v2 document structure"]:::process
        F["v3 native-source selector<br/>or separate parallel v4"]:::process
        G["Assess role, source location<br/>closure and conversion state"]:::process
        H["Sealed candidate receipt<br/>Text, spans, reasons, status"]:::artifact
        I["Error / truncated / partial<br/>absent / uncertain holds"]:::stop
        C --> E
        C --> F
        D --> E
        D --> F
        E --> G
        F --> G
        G --> H
        G --> I
    end
    subgraph R["03 / ATTRIBUTED SOURCE REVIEW"]
        J["Inspect original image<br/>Review role and notation"]:::authority
        K["Choose exact source blocks<br/>and character interval"]:::process
        L["source_review receipt<br/>Reviewer, status and hashes"]:::artifact
        H -. "proposal only" .-> J
        C --> J
        J --> K --> L
    end
    subgraph Q["04 / REQUEST PREPARATION"]
        M["Recompute current file hashes"]:::process
        N{"Review intact, page one<br/>and current hashes match?"}:::decision
        O{"Review complete and<br/>both budgets satisfied?"}:::decision
        P["Hold with explicit reason<br/>Preserve full evidence text"]:::stop
        T["Exact Jev request payload<br/>Request and evidence hashes"]:::artifact
        U["Future external executor<br/>Recheck checkpoint and budget"]:::external
        V["Separate graph authority<br/>Compiler publication gates"]:::authority
        A --> M
        L --> N
        M --> N
        N -->|"No"| P
        N -->|"Yes"| O
        O -->|"No"| P
        O -->|"Yes"| T
        T -. "not sent by this adapter" .-> U
        U -. "no direct write authority" .-> V
    end

%% BEGIN SHARED ATLAS STYLE
    classDef input fill:#E7F5F1,stroke:#348E82,color:#174D49,stroke-width:1.5px;
    classDef process fill:#EAF1FC,stroke:#6589BB,color:#203F68,stroke-width:1.5px;
    classDef decision fill:#FFF2D9,stroke:#CA963B,color:#6B4918,stroke-width:1.5px;
    classDef artifact fill:#EEEFFD,stroke:#8388C3,color:#414779,stroke-width:1.5px;
    classDef authority fill:#F4EBF9,stroke:#A181B9,color:#643E7A,stroke-width:1.5px;
    classDef stop fill:#FCECEA,stroke:#C57B74,color:#823F39,stroke-width:1.5px;
    classDef external fill:#F0F3F7,stroke:#92A0B2,color:#536277,stroke-width:1.5px,stroke-dasharray:5 4;
%% END SHARED ATLAS STYLE
```

## What each stage does

| Stage | Implemented behavior and source |
| --- | --- |
| Source preparation | [`prepare()`](../../src/parallel_source_v4/prepare.py#L10) reads an authorized local original, copies physical page one, renders it at 120 dpi, records exact native lines and emits hashes plus declared conversion paths. It creates no model predictions. |
| Source verification | [`verify_first_page_bundle()`](../../src/parallel_source_v4/common.py#L76) verifies original/page/image/native bindings in the external harness. Selector functions that receive hashes alone cannot certify that they read those files. |
| Geometry v1 | [`assess_first_page()`](../../trace_gc/pdf_evidence.py#L235) seals five dispositions from page boxes, abstract anchors, metadata exclusions and sentence/layout boundaries; compatible native text may replace the layout transcription. Its completeness assessment remains heuristic. |
| Structure v2 | [`assess_document()`](../../trace_gc/pdf_structure.py#L53) follows the Docling body tree and uses native agreement plus optional scholarly-field corroboration. Native agreement establishes text presence, not its abstract role. |
| Source v3 | [`assess_document()`](../../trace_gc/pdf_source_v3.py#L441) selects exact native character intervals, reconstructs text, requires a structural closure and separately records request budget status. `verify_scholarly_field()` requires located, bounded first-page corroboration. |
| Parallel v4 | [`assess_document()`](../../trace_gc/pdf_structure_parallel_v4.py#L295) combines document regions with [`locate()`](../../trace_gc/pdf_source_parallel_v4.py#L183), exact native spans and explainable boundaries. Ambiguous role, multi-column continuation, style changes and unresolved terminal notation cause holds. |
| Conversion adapters | [V4 adapters](../../src/parallel_source_v4/adapters.py) retain missing/error/truncated conversion states. GROBID fields must be corroborated on page one; olmOCR text must be located in native source. Unlocated text is not assigned a fabricated full-page rectangle. |
| Human or assistant review | [`source_review()`](../../trace_gc/pdf_admission.py#L23) takes a caller-specified ordered set of source blocks and an exact character interval into their space-joined text. It requires reviewer attribution and a nonempty time string, and validates hash format, page geometry, duplicate IDs and disposition consistency. Current source hashes are compared later by `prepare_jev_request`. |
| Request preparation | [`prepare_jev_request()`](../../trace_gc/pdf_admission.py#L65) checks receipt integrity, physical page, current source/page/image hashes, complete review status and whole-request limits. Defaults are 4,000 characters and 16,000 serialized UTF-8 request bytes. |
| Held or prepared output | Failed gates return `admitted=false` with an explicit reason. Success returns the exact payload, request byte count and request/review/evidence hashes. Neither path silently truncates source evidence. |

## Review is a separate decision

A reviewer must inspect page role, abstract boundaries and notation in the source image. Exact native text may still flatten fractions, reorder formula fragments or include body prose. A high string-match score does not resolve those defects. The selector can retain a complete over-budget abstract while independently refusing a request; a model generation limit is a distinct `truncated` conversion state.

Review hashes detect changes but are not signatures or proof of independent review. The admission adapter records `independent_review=false` even for an attributed human reviewer; independence must be established outside this data structure. The current research labels are assistant-reviewed.

The caller must recompute the three current source hashes immediately before preparing a request. The [audit path](../../src/abstract_validation/audit.py#L11) builds reviewed payloads and a reprocessing plan. [`reprocessing_action()`](../../trace_gc/pdf_evidence.py#L246) distinguishes holds, unchanged evaluation reuse and changed/recovered evidence. The repository does not implement an automatic connection from these experimental selectors to the live corpus executor.

Any future executor must reconcile the current checkpoint and budget, retain earlier attempts and charges, and obtain the applicable publication authority. Prepared requests and retrieved papers do not bypass the compiler's policy, signatures, qualification or graph transaction gates.

## Verification coverage

[`test_pdf_admission.py`](../../tests/test_pdf_admission.py) covers candidate-only rejection, exact reviewed text, changed source hashes, tampering, partial/uncertain reviews and both request limits. [V3 model boundaries](../../tests/test_first_page_v3_local_models.py) explicitly reject substituting a selector proposal for a source review. [V4 selector tests](../../tests/test_parallel_source_v4.py) exercise first-page scope, metadata boundaries, duplicate native locations, budget versus generation limits and sealed receipt tampering. These tests check implementation behavior; they do not establish real-paper accuracy.

The source experiment's observed limitations and operational reproduction commands are documented in [the v4 report](../30_first_page_parallel_experiment.md) and [its reproduction notes](../31_first_page_parallel_reproduction.md).
