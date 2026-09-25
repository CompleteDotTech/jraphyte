# Revised delivery and deployment sequence

| Stage | Delivered software | Remaining acceptance evidence |
|---|---|---|
| 1 — Contract hardening | Deterministic materialization, recursive closure, typed refs/DAGs, operation variants, coherent lifecycle, complete lineage, hardened legacy checker | Release tests and review probes are recorded locally. |
| 2 — Minimal complete workflow | Fixed-question compiler, raw observation adapter, global resolver, reviewed isolated transaction, replay and source maintenance | Reference backend is tested; exact pinned upstream and live-provider acceptance remain separate gates. |
| 3 — Qualification and reviewed pilot | Independent-label evaluation, exact applicability, signed approvals, persistent budgets, accepted-action sampling | Representative labels, real preregistration, configured authorities, empirical bounds, drift policy and a controlled pilot must be supplied/performed externally. |
| 4 — Optional optimization | Version/qualification boundaries that prevent silent reuse after changes | Packing, learned resolution and autoresearch require separate measured comparisons; none blocks stage 2. |

The executable release is not held hostage to optional optimization, and a local test result is not promoted into production qualification. See `14_deployment.md` for commands and trust responsibilities.
