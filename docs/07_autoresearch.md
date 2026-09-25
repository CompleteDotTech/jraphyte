# Optional optimization: outside the correctness-critical path

The implemented fixed-question lifecycle does not depend on autoresearch, beam search, learned resolution, schema induction, or cost-optimized packing. These remain optional, separately measured interventions after the deployed correctness and qualification gates pass.

Any change to candidate generation, question meaning, state construction, packing, model, resolver or policy changes its bound version/applicability context and invalidates automatic reuse of an incompatible qualification. Optimization cannot mutate frozen observations, lower required context, manufacture labels, self-enroll issuers or authorize publication.

The historical research program is retained in `archive/v0.2/docs/07_autoresearch.md`. This release makes no claim to have run that research or observed improved accuracy/cost. The requested implementation work places those experiments after the minimal complete workflow rather than fabricating their outcomes.

## Retrieval policy research in 0.4

`retrieval/evaluation.py` adds failure-driven retrieval proposals and a locked development/holdout gate. Hop depth, aliases, siblings, relation masks, provenance, contradiction-first search, community context, vector search and relevance questions can be compared without editing existing observations. Only a disjoint held-out improvement with passing safety checks can retain a proposed change; deployment still needs independent review and existing qualification. This is a research gate and protocol, not an autonomous model-controlled deployment service. See `19_graphrag_replay_evaluation.md`.
