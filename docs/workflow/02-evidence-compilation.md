# 02 · Evidence compilation

[Workflow index](README.md) · [Mermaid source](02-evidence-compilation.mmd) · [High definition PNG](png/02-evidence-compilation.png)

The compiler turns immutable evidence into an evaluation request whose meaning and exact transmitted bytes can be reconstructed. This page describes the implementation at `d5ca636`; the catalog and pack are analysis artifacts, and creating them grants no graph write authority.

```mermaid
flowchart TB
  accTitle: Evidence becomes a reproducible evaluation pack
  accDescr: Immutable sources, claims, candidates, graph snapshots and installed questions feed complete dependency closure, deterministic materialization and exact wire validation. Invalid bindings or oversized requests stop compilation.
  subgraph INPUTS["01 · IMMUTABLE INPUTS"]
    SOURCE["Source snapshot<br/>text, version and scope"]:::input
    CLAIM["Immutable claim<br/>text and identity"]:::input
    EVIDENCE["Exact evidence span<br/>Unicode code-point offsets"]:::artifact
    CANDIDATE["Candidate assertion<br/>claim, evidence and dependencies"]:::artifact
    SNAPSHOT["Graph snapshot<br/>version and schema hash"]:::input
    PROGRAM["Installed question program<br/>candidate-bound rubric"]:::authority
    SOURCE --> EVIDENCE
    CLAIM --> CANDIDATE
    EVIDENCE --> CANDIDATE
  end
  subgraph COMPILE["02 · DERIVE EVERY MODEL FIELD"]
    ROOTS["compile_pack<br/>pin model and validate roots"]:::process
    CLOSURE["Traverse record closure<br/>verify spans and causal DAG"]:::process
    BOUNDED{"Retrieval lineage<br/>arguments supplied?"}:::decision
    FULL["Include full snapshot<br/>and active evidence closure"]:::process
    SELECTED["Include selected graph context<br/>and snapshot identity only"]:::process
    STATE["Materialize state and traces<br/>from immutable records"]:::artifact
    BUDGET["Account for state and questions<br/>with injected counter or estimate"]:::process
    WIRE["Encode exact provider request<br/>semantic, wire and cache hashes"]:::process
    ROOTS --> CLOSURE --> BOUNDED
    BOUNDED -->|No| FULL --> STATE
    BOUNDED -->|Yes, including empty lists| SELECTED --> STATE
    STATE --> BUDGET --> WIRE
  end
  subgraph VERIFY["03 · RECONSTRUCT BEFORE ACCEPTING"]
    CHECK["Rebuild state, closure and traces<br/>check questions, lineage and time"]:::process
    PASS{"Bindings and both<br/>pack caps valid?"}:::decision
    PACK["Immutable pack<br/>ready for adapter boundary"]:::artifact
    STOP["ContractError<br/>preserve complete evidence"]:::stop
    CHECK --> PASS
    PASS -->|Yes| PACK
    PASS -->|No| STOP
  end
  CANDIDATE --> ROOTS
  SNAPSHOT --> ROOTS
  PROGRAM --> ROOTS
  WIRE --> CHECK
  CLOSURE -. invalid reference or cycle .-> STOP
  CHECK -. altered content or rubric .-> STOP

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

## Source of each input

| Input | Implemented contract |
| --- | --- |
| Source snapshot | `Catalog.source` stores text, its byte hash, source ID, version and security scope. A new source version has its own immutable record. |
| Evidence | `Catalog.evidence` stores a nonempty `[start, end)` span measured in Unicode code points. `verify_evidence` checks the source record hash, text hash and exact quote. |
| Claim and candidate | `Catalog.claim` identifies the exact claim text. `Catalog.candidate` binds that claim hash to an assertion and evidence. For `supports`/`refutes`, the object must be the claim ID and citations must name the asserted source. |
| Graph snapshot | The compiler uses its graph version, schema identity and assertions. Freshness is checked again at later live and publication boundaries. |
| Question | `programs.question` emits an installed rubric. `verify_question` reconstructs it; changing its wording under the same program version fails. |

`Catalog.add` validates record/body schemas and the hash of `{kind, body}`, then rejects changes to an existing ID. Reads return copies. Hashing uses `TRACE-C14N-1`: a typed binary encoding that distinguishes integers, floats, booleans and signed zero, preserves array order and Unicode spelling, and rejects duplicate JSON keys, nonfinite values, excessive nesting and invalid Unicode. This is the project's own profile, not JSON Canonicalization Scheme.

## Closure and materialization

`closure` traverses candidates, claims, evidence, source snapshots, prior observations, their packs and graph dependencies. Candidate prerequisites must form a DAG; alternative/context links may cycle. A prior observation included as an input must have `status == "OK"`. The closure records its roots, records, typed relationship edges, evidence, sources and a hash; compilation never drops required closure to fit a cap.

With both retrieval arguments omitted, `materialize` includes the full graph snapshot and evidence behind its active assertions. Supplying `graph_context_ids` or `source_retrieval_ids`, even as an empty list, enables bounded materialization: the full snapshot remains available to deterministic code, while the model sees snapshot identity and selected, validated graph context. An explicit empty selection is therefore a meaningful no-graph experiment. Selected context declares `instruction_authority: false`.

Each rendered claim, evidence span and prior answer has a trace back to immutable records, including the declared `identity-v1` or `collapse-whitespace-v1` transformation. `validate_pack` reconstructs state, closure and traces, verifies causal timing and question dependencies, checks run/mode/scope and snapshot bindings, and recomputes request identities before `Catalog.put("pack", ...)` accepts the result.

## Budget and current-state boundaries

The two compiler caps are `state + sum(question sizes) <= request_cap` and `state + longest question <= state_longest_cap`; defaults are 64,000 and 32,000. The default counter measures serialized UTF-8 bytes and is explicitly an offline estimate. Live calls additionally require an injected measured tokenizer, independently recompute accounting and count the complete emitted request. These per-pack checks are separate from the persistent shared run budget in [03 · Observations and resolution](03-observations-resolution.md).

Compilation does not itself admit a source into the backend or query current source status. `validate_pack(..., source_status=...)` rejects inactive, denied or tombstoned sources during fresh use; its historical mode permits provenance inspection of retained source bytes. Retrieval lineage can impose additional current ACL checks. Publication always rechecks current state.

## Code and reviewed tests

- [catalog.py](../../trace_gc/catalog.py): `Catalog.add`, `source`, `evidence`, `candidate`, `verify_evidence`.
- [canonical.py](../../trace_gc/canonical.py): `canonical_bytes`, `digest`, `loads`.
- [compiler.py](../../trace_gc/compiler.py): `closure`, `materialize`, `compile_pack`, `wire_request`, `validate_pack`.
- [programs.py](../../trace_gc/programs.py): `question`, `verify_question`, `retrieval_question`.
- [test_runtime_contracts.py](../../tests/test_runtime_contracts.py): `CanonicalTests`, `BindingTests.test_rendered_quote_cannot_be_rehashed_into_validity`, `test_transitive_closure`, `test_noncausal_alternatives_may_cycle`, `test_exact_codepoint_span`, `test_token_limit_fails_not_truncates`.
- [test_graphrag_pipeline.py](../../tests/test_graphrag_pipeline.py): `test_minimum_closure_materialization`, `test_legacy_pack_unchanged`, `test_no_graph_ablation_is_explicit_empty_selection`.

The tests above were inspected as implementation evidence for this documentation; this page does not report a fresh test run or provider qualification.
