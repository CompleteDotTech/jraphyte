# 12 · Commands and resource budgets

[Atlas index](README.md) · [Mermaid source](12-commands-budgets.mmd) · [HD PNG](png/12-commands-budgets.png) · [Dark PNG](png/12-commands-budgets.dark.png)

The CLI exposes validation and reproducible experiments. An application invokes the trusted publication API with its own configuration and approvals. Resource usage is explicit: the shared `RunBudget` persists charges, while a `BudgetMeter` bounds an individual retrieval.

```mermaid
flowchart TB
    accTitle: Commands, execution boundaries and budgets
    accDescr: Offline CLI commands route to validation, demo, analysis replay, qualification evaluation and legacy conformance. Application APIs own publication. RunBudget persists shared usage while BudgetMeter bounds each retrieval.

    CLI["trace-gc command<br/>or python -m trace_gc"]:::input
    ROUTE{"Choose operation"}:::decision
    CLI --> ROUTE

    subgraph COMMANDS["OFFLINE COMMAND SURFACE"]
        DEMO["demo / graphrag-demo<br/>temporary synthetic lifecycles"]:::process
        BENCH["graphrag-benchmark<br/>synthetic retrieval comparisons"]:::process
        VALID["validate / canonical<br/>integrity checks and exact hashes"]:::process
        REPLAY["replay-policy<br/>unsigned analysis branch"]:::process
        QUAL["evaluate-labels / audit-sample<br/>unsigned qualification or sample"]:::process
        LEGACY["check-legacy<br/>exact upstream blob required"]:::external
    end
    ROUTE --> DEMO
    ROUTE --> BENCH
    ROUTE --> VALID
    ROUTE --> REPLAY
    ROUTE --> QUAL
    ROUTE --> LEGACY
    DEMO --> REPORT["JSON report or output artifacts<br/>command success / structured error"]:::artifact
    BENCH --> REPORT
    VALID --> REPORT
    REPLAY --> REPORT
    QUAL --> REPORT
    LEGACY --> REPORT

    subgraph LIMITS["RUNTIME RESOURCE ACCOUNTING"]
        APP["Application invokes runtime<br/>with explicit budget objects"]:::input
        RUN[("RunBudget / SQLite<br/>shared usage survives reopen")]:::artifact
        RESERVE{"Atomic reservation<br/>all requested resources fit?"}:::decision
        WORK["Retrieval, model request<br/>resolver search or review"]:::process
        METER["BudgetMeter / per retrieval<br/>work, latency and context bounds"]:::process
        STOP["Hold, truncate context or error<br/>according to the calling stage"]:::stop
        APP --> RUN --> RESERVE
        RESERVE -->|"yes"| WORK --> METER
        RESERVE -->|"no"| STOP
        METER -->|"local bound reached"| STOP
    end
    DEMO -. "fixture supplies budgets" .-> APP
    APP -. "publication is a separate API" .-> AUTH["CompilerService<br/>trusted policy and authorization"]:::authority

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

## Choose an entry point

| Command | Result and boundary |
| --- | --- |
| `python -m trace_gc demo --output <directory>` | Temporary sandbox lifecycle, bundle, public test keys and receipt report; fabricated responses and no provider calls. |
| `python -m trace_gc graphrag-demo --output <directory>` | Four synthetic retrieval/compilation/publication scenarios. |
| `python -m trace_gc graphrag-benchmark --output <directory>` | Synthetic retrieval and controlled-oracle comparisons. |
| `python -m trace_gc validate <bundle>` | Structural and provenance verification. Add `--trust <admin-file>` for independent checkpoint authentication. |
| `python -m trace_gc canonical <input.json>` | Canonical bytes and SHA-256 for `TRACE-C14N-1`. |
| `python -m trace_gc replay-policy <bundle> --policy <policy> --output <branch>` | Appended analysis policy branch with no new model inference and no authorization. |
| `python -m trace_gc evaluate-labels ...` | Unsigned qualification artifact; requires labels, scope, protocol, risk/coverage criteria and expiry. |
| `python -m trace_gc audit-sample <accepted-ids> --size <n> --seed <n> --output <sample>` | Deterministic random selection of accepted actions for independent audit. |
| `python -m trace_gc check-legacy --core <core.py>` | Pin verification and upstream conformance in temporary databases. |

`python -m trace_gc --help` and each command's `--help` are the authoritative argument lists. The CLI converts `ContractError` into a structured JSON failure and returns exit status 1; input errors are reported as `INPUT_ERROR`. Its `--version` exits through argparse. Research experiments have separate `python -m src...` entry points in [10 · Research experiments](10-research-experiments.md).

## Shared and local limits

| Scope | Accounted resources | Persistence and behavior |
| --- | --- | --- |
| `RunBudget` | `retrieval_requests`, `model_calls`, `retries`, `solver_expansions`, `review_actions`, `request_bytes` | SQLite row keyed by run ID. Limits must match on reopen. `consume_many` reserves all requested resources atomically under `BEGIN IMMEDIATE`; a failing reservation changes no usage. Callers charge the operations they initiate. |
| `BudgetMeter` | Cost units, candidates, nodes, edges, paths, communities, decisions, source spans, tokens, graph/vector queries and elapsed time | Local to one retrieval. Work limits raise `RETRIEVAL_BUDGET_EXHAUSTED`; `accept` can reject an item that would exceed context bounds. The retriever records why selection stopped. |
| Upstream acquisition | Tier, attempt and expansion budgets | `UpstreamGraphRAG.run` stops on declared outcomes or exhaustion and records the expansion history. It can request evidence without creating a graph mutation. |

Cost units are algorithm work units, not currency. The default retrieval token estimate counts canonical UTF-8 bytes conservatively; it is not a calibrated provider tokenizer. Model execution, byte budgets, solver exhaustion and retrieval truncation have their own caller-specific outcomes, shown in the detailed diagrams.

## Source evidence

- [`cli.parser` / `cli.main`](../../trace_gc/cli.py) and [`__main__.py`](../../trace_gc/__main__.py): command routing and errors.
- [`RunBudget`](../../trace_gc/budget.py): persistent configuration checks, atomic reservations and explicit close. Constructor failure closes SQLite before re-raising.
- [`BudgetMeter`](../../trace_gc/retrieval/budget.py) and [`RetrievalBudget`](../../trace_gc/retrieval/contracts.py): local retrieval bounds.
- [`TypeSafeAdapter`](../../trace_gc/adapter.py), [`solve`](../../trace_gc/resolver.py), [`UpstreamGraphRAG`](../../trace_gc/retrieval/planner.py): consuming stages.
- [`SharedBudgetTests`](../../tests/test_runtime_qualification.py): persistence, concurrent reservations, atomic multi-resource failure and invalid requests.

See [04 · Policy and publication](04-policy-publication.md) for application-owned write authority and [11 · Validation and delivery](11-validation-delivery.md) for runnable validation and packaging gates.
