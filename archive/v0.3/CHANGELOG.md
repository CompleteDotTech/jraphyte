# Changelog

## 0.3.0 — implemented design-review revision

Added the installable compiler runtime, 18 standalone runtime schemas, deterministic materialization/recursive closure, immutable observations and replay branches, typed operations, joint component resolution, scoped qualification and Ed25519 authority, transactional SQLite reference backend, pinned upstream bridge/conformance command, complete provenance profiles, source maintenance/erasure semantics, shared budgets, CLI, CI configuration and expanded regression/state-sequence tests.

Hardened the original synthetic fixture checker against all 18 reviewed probes without replacing the original 42 tests. Original v0.2 documents, contracts and tests are preserved under `archive/v0.2`. Changed lifecycle and IR definitions are explicitly versioned rather than silently reinterpreting old observations.

Release evidence is restricted to the locally executed suites and isolated demo. Exact pinned-upstream conformance, live provider operation, independent empirical calibration and a real controlled pilot remain external acceptance gates. The software does not manufacture successful evidence for them.
