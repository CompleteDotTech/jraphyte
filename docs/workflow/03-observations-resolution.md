# 03 · Observations and global resolution

[Workflow index](README.md) · [Mermaid source](03-observations-resolution.mmd) · [High definition PNG](png/03-observations-resolution.png)

Evaluation records what a provider actually returned. Resolution then selects a jointly feasible set of candidates. The provider's answer, the resolver's selection and permission to publish remain distinct artifacts. This page follows the implementation at `d5ca636`.

```mermaid
flowchart TB
  accTitle: Provider observations and bounded global resolution
  accDescr: A validated pack is evaluated through explicit live capability gates or supplied recorded bytes. Every live attempt reserves persistent budget and preserves raw receipts. An explicit observation branch feeds bounded exact subset resolution, whose incomplete runs yield no selected candidates.
  PACK["Validated evaluation pack"]:::input
  MODE{"Execution path?"}:::decision
  subgraph OBSERVE["01 · CAPTURE EVERY ATTEMPT"]
    GATE["LIVE capability, key and signer<br/>tokenizer, sources and ACL checks"]:::authority
    QUOTA["Reserve call and request bytes<br/>plus retry count after attempt 0"]:::process
    HTTP["TypeSafe transport<br/>exact request bytes"]:::external
    IMPORT["Synthetic or recorded<br/>response bytes supplied"]:::input
    RECORD["record_response<br/>raw wire + OK or ERROR observations"]:::artifact
    ATTEST["LIVE observation attestations<br/>preserve every attempt"]:::authority
    RETRY{"429, 529 or transport error<br/>and retries remain?"}:::decision
    WAIT["Bounded retry delay<br/>at most 60 seconds"]:::process
    CHOOSE["Choose explicit immutable<br/>observation branch"]:::process
    GATE --> QUOTA --> HTTP --> RECORD
    IMPORT --> RECORD
    RECORD -->|LIVE| ATTEST --> RETRY
    RETRY -->|Yes| WAIT --> QUOTA
    RETRY -->|No| CHOOSE
    RECORD -->|Supplied bytes| CHOOSE
  end
  subgraph RESOLVE["02 · RESOLVE THE WHOLE BATCH"]
    VALIDATE["Validate observations<br/>at most one primary Choice"]:::process
    WEIGHTS["Build integer utilities<br/>from accepted-label probabilities"]:::process
    SEARCH["Enumerate candidate subsets<br/>charge each solver expansion"]:::process
    CONSTRAINTS["Check prerequisites, types<br/>exclusivity and identity conflicts"]:::process
    COMPLETE{"Search complete and<br/>feasible snapshot?"}:::decision
    OPTIMAL["OPTIMAL certificate<br/>best utility, lexical tie-break"]:::artifact
    UNRESOLVED["INFEASIBLE or BUDGET_EXHAUSTED<br/>empty selection, no objective"]:::stop
    PROJECT["Project per-candidate outcomes<br/>and structural risk classes"]:::artifact
    VALIDATE --> WEIGHTS --> SEARCH --> CONSTRAINTS --> COMPLETE
    COMPLETE -->|Yes| OPTIMAL --> PROJECT
    COMPLETE -->|No| UNRESOLVED --> PROJECT
  end
  STOP["ContractError<br/>no next call or decision"]:::stop
  PACK --> MODE
  MODE -->|LIVE| GATE
  MODE -->|Synthetic / recorded| IMPORT
  GATE -. unmet gate .-> STOP
  QUOTA -. run cap exhausted .-> STOP
  CHOOSE --> VALIDATE
  VALIDATE -. ambiguous or altered branch .-> STOP

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

## Evaluation and receipts

`TypeSafeAdapter.evaluate` requires explicit enablement, an externally supplied key, a `LIVE` pack, matching run budget, bounded retry configuration, current source status, an injected tokenizer implementation/version and an observation signer. Graph-context packs additionally require current application ACLs. It validates the pack, counts the actual emitted request and verifies every recorded component count before making a request.

Before **each** attempt, `RunBudget.consume_many` reserves one model call and request bytes; subsequent attempts also reserve a retry. Reservations use their own SQLite `BEGIN IMMEDIATE` transaction. Usage survives reopen, limits cannot be reset for the same run ID, and multiple requested resources are reserved together or not at all. A failed network attempt still consumes its committed reservation. Budget reservations are separate from graph publication transactions.

The adapter sends the exact stored request bytes. `record_response` creates one immutable observation per question, retaining request/response bytes, hashes, safe response headers, HTTP status, raw answers and input lineage. Ordinary HTTP/envelope/model/answer failures become `ERROR` observations with no probability, confidence or semantic outcome; hard receipt limits and invalid input contracts can raise `ContractError` instead. Live observations, including errors, receive signed attestations.

Only HTTP 429/529 and `OSError`/`TimeoutError` trigger retries. `max_retries` defaults to 2 and must be in `[0, 10]`; delays are bounded at 60 seconds. Every attempt remains visible. The adapter returns all attempt observations, so the caller must explicitly choose a retry branch before solving; feeding multiple primary answers for one candidate raises `AMBIGUOUS_PRIMARY_OBSERVATION`. Supersession is recorded explicitly by `record_response` when supplied and must pass identity/time checks.

| Primitive | Preserved semantics |
| --- | --- |
| `CHOICE` | Exact label probabilities, reported choice and raw confidence. Two-decimal provider rounding has a narrowly bounded sum/near-tie tolerance; values are never renormalized. |
| `SCORE` | The full probability distribution and rubric meanings; reported score must equal its expected value. |
| `NOUL` | A yes/no probability derived from `noul`; no separate confidence is invented. |

Recorded or synthetic response bytes can enter through `record_response` without making a network call. Merely importing bytes does not supply the trusted observation provenance required for publication outside the sandbox.

## Whole-batch resolution

`solve` validates supplied observations and constructs a problem from the exact snapshot. `primary_observation` permits at most one `SUPPORT/CHOICE` or `IDENTITY/CHOICE` observation per candidate. Its accepted label is `SUPPORTS`, `CONTRADICTS` for a `refutes` assertion, or `MATCH` for identity; a missing or operationally failed primary answer prevents selection.

Utility is `round(1_000_000 * (2*p - 1))`. The exact subset enumerator checks explicit exclusive groups and `validate_graph`: prerequisite closure, node/relation types, inverse/symmetric normalization, self-relation rules, incompatible qualified facts and transitive identity/cannot-link conflicts. It charges the shared `solver_expansions` budget for every subset. Ties use lexicographic candidate order.

The default expansion cap is 65,536; more than 24 candidates immediately yields `BUDGET_EXHAUSTED`. Invalid base graphs yield `INFEASIBLE`. Any incomplete search clears its selection and objective, producing per-candidate `UNRESOLVED` outcomes. Completed search projects `SELECTED` or `NOT_SELECTED`, together with structural risk. Identity impact counts new implied equivalences and dependent assertions, which can raise identity risk from R4 to R5.

`verify_certificate` rebuilds input bindings, feasibility, objective arithmetic and identity impact, and checks the completed enumeration count. It does **not** independently rerun optimization to prove global optimality, and no certificate grants write authority. [04 · Policy and publication](04-policy-publication.md) contains the next gates.

## Code and reviewed tests

- [adapter.py](../../trace_gc/adapter.py): `TypeSafeAdapter.evaluate`, `record_response`, `parse_answer`, `validate_observation`.
- [budget.py](../../trace_gc/budget.py): `RunBudget.consume_many`, constructor and `close`.
- [resolver.py](../../trace_gc/resolver.py): `primary_observation`, `solve`, `verify_certificate`, `project_resolutions`, `effective_risk`.
- [constraints.py](../../trace_gc/constraints.py): `validate_graph`, `UnionFind`, `impact`.
- [test_runtime_qualification.py](../../tests/test_runtime_qualification.py): `SharedBudgetTests`, `MockTransportTests.test_retry_records_errors_and_signed_success_without_real_network`.
- [test_runtime_contracts.py](../../tests/test_runtime_contracts.py): `ObservationTests`, `test_unresolved_solver_cannot_claim_selection`.
- [test_runtime_workflows.py](../../tests/test_runtime_workflows.py): `test_global_cannot_link_prevents_transitive_identity_contradiction`, `test_exclusive_alternatives_are_joint_not_independent`.

The inspected mock transport tests establish the intended local contract; they do not establish current provider availability, tokenizer qualification or live performance.
