# Optional optimization: outside the correctness-critical path

The implemented fixed-question lifecycle does not depend on autoresearch, beam search, learned resolution, schema induction, or cost-optimized packing. These remain optional, separately measured interventions after the deployed correctness and qualification gates pass.

Any change to candidate generation, question meaning, state construction, packing, model, resolver or policy changes its bound version/applicability context and invalidates automatic reuse of an incompatible qualification. Optimization cannot mutate frozen observations, lower required context, manufacture labels, self-enroll issuers or authorize publication.

The historical research program is retained in `archive/v0.2/docs/07_autoresearch.md`. This release makes no claim to have run that research or observed improved accuracy/cost. The requested implementation work places those experiments after the minimal complete workflow rather than fabricating their outcomes.
