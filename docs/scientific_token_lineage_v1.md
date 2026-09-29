# Scientific output token lineage, draft v1

`trace_gc.scientific_token_verifier.verify_scientific_token_packet` checks a
review packet's output characters, typed nodes, source glyphs, fraction rules,
matching-version TeX anchors, and declared alternate-scope rejections. It
returns `MECHANICALLY_VERIFIED_REVIEW_REQUIRED` on success. It cannot return
`accepted`, change a selector, or authorize graph admission.

The caller supplies independently trusted SHA-256 values for the original PDF,
notation sidecar, TeX source, and canonical reviewed glyph/rule evidence. It
must regenerate the glyph/rule inventory from the original PDF and bind every
ID, box, printed character, and rule to that source. Merely passing hashes
copied from a packet does not establish this. The `tex_anchor` check requires
exactly one occurrence in the bound TeX bytes; it does not prove the published
PDF was compiled from those bytes or that the TeX semantics are correct.

The v1 packet covers its entire `text` with contiguous tokens. Each token has
an exact output range, one output-character lineage record per character, a
typed tree whose leaf glyph IDs cover the token exactly, and a nonempty list
of alternate readings with attributed rejection reasons. A synthetic `/` is
permitted only for a `fraction` tree with the same source rule and exact
numerator/denominator glyph IDs. The rule's horizontal and vertical geometry
must cover those operands; this rejects an earlier same-looking symbol pulled
into the fraction. `script` nodes require the subscript glyphs to sit below
their base. `relation` and `quantity` nodes require explicit operator and unit
children. Each output-character record identifies one source glyph and its
exact character offset. Every glyph must be consumed fully, once, and in
order; only the five explicit Latin ligature code points `ﬀ`, `ﬁ`, `ﬂ`, `ﬃ`,
and `ﬄ` can expand to multiple output characters. Other normalization is held.
The typed tree is recursively serialized to exact glyph-offset and synthetic
slash events, so a fraction rule emits one slash precisely between its full
numerator and denominator, including inside nested fractions. Ligature output
must remain contiguous.
The script geometry and required relation/unit children are structural checks,
not proof of a scientifically correct subscript, equation, or unit attachment.

The private f081 complete-transcript candidate has 907 output characters and
160 preliminary token records, plus a separate 41-tree typed AST draft. The
audits identify a source-backed stacked `spin-1/2`, two chemical subscripts,
several variable subscripts, an inverse unit, and a terminal stacked fraction.
Those artifacts are **not a v1 packet**: the 41 draft trees do not partition
every scientific token, the output slash policy and unit/operator attachments
have not been approved, and every alternate scope has not been rejected in a
signed source-first review. No f081 PASS or promotion is claimed. The authored
tests exercise only mechanical behavior on synthetic evidence.

Before this module could support scientific acceptance, an integrator must
bind the complete original-PDF paint/visible-text coverage, validate reviewed
corrections and normalization, prove typed serialization for every scientific
token, obtain actual source-first scientific review of competing readings,
and attach those decisions to the immutable assessment and promotion receipt.
The current reviewed abstract overlay independently hard-disables `accepted`.
