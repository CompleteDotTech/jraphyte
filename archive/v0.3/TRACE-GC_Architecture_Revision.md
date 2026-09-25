# TRACE-GC executable architecture revision — 0.3.0

The earlier monolithic design is preserved unchanged at `archive/v0.2/TRACE-GC_Architecture_Revision.md`. The implemented architecture and current contract definitions are maintained in:

- `docs/01_architecture.md`: processing stages and authority boundary.
- `docs/03_ir_contracts.md`: immutable runtime record families and typed operations.
- `docs/04_risk_calibration.md`: qualification metrics, applicability, and external evidence requirements.
- `docs/05_provenance_replay.md`: lifecycle, ledger, transaction, policy replay and erasure semantics.
- `docs/12_implementation.md`: serialization, materialization, backend, adapter and capability details.
- `docs/13_recommendation_traceability.md`: all eleven review findings mapped to code and tests.
- `docs/14_deployment.md`: service-owned trust, acceptance gates and pinned legacy integration.

The executable runtime is `trace_gc/`. Its schemas are `schemas/runtime/`. The old fixture checker is retained only as a hardened compatibility surface. These current specifications supersede historical future-tense promises or conflicting lifecycle names in the archived design.
