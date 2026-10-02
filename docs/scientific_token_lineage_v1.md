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
Two additional, tightly scoped review events are supported. A
`reviewed_delta_alias` character can emit only Greek capital `Δ` from one raw
PDF increment glyph `∆` (U+2206), with its exact glyph ID and offset. This is
a candidate mapping to be checked against the source image and author TeX;
the event name does not assert that a reviewer has accepted it. No other
Unicode normalization or case conversion is permitted. The alias record must
also repeat the exact source glyph box, line ID, line offset and
`abstract_body` role from the bound source-line inventory.

A `line_join_space` can emit one space between the final glyph of a source
`abstract_body` line and the first glyph of the next included
`abstract_body` line. It needs a `line_join` typed node with those exact
endpoints and a source-line inventory. Each source line records its ID, role,
ordered complete glyph IDs and enclosing box; each glyph records matching
line ID, zero-based line offset and role. Lines between the endpoints may
exist only with explicit excluded roles; intervening numeric source line IDs
cannot be omitted. The inventory partitions the packet's
glyphs. The join node and output character both repeat the exact endpoint
boxes, roles and line offsets. The verifier checks that the synthetic space occurs precisely between
the endpoint glyph events. It does not infer line ownership from geometry or
silently skip a line, and it cannot justify a removed wrap hyphen. Callers must
regenerate and independently review the full source-line inventory from the
original PDF. When `source_lines` is present, it joins the glyphs and rules in
the canonical evidence hash; old packets without it retain their v1 hash.
Both the preceding and following output events must be the exact source-line
endpoint glyphs, including when the space falls across packet token boundaries.
An inserted or reordered body glyph cannot be hidden between the join and its
claimed right endpoint.

A source line may have `role: mixed` only with contiguous, nonoverlapping
`role_spans` that partition every original glyph offset into abstract body and
excluded heading or other roles. Glyph records retain the original line ID and
offset and must agree with their role span. This covers a heading and the first
abstract words on one physical PDF line without dropping the heading glyphs or
emitting them as body. All body-role glyphs, including those on mixed lines,
must still be emitted or explicitly listed as supported omissions.

The typed tree is recursively serialized to exact glyph-offset and synthetic
slash events, so a fraction rule emits one slash precisely between its full
numerator and denominator, including inside nested fractions. Ligature output
must remain contiguous.
`sequence` composes two or more typed or literal parts in exact output order;
the parts must use disjoint glyphs. Literal prose can therefore surround
scientific expressions without claiming that prose is an untyped gap.
`line_join_gap` is a zero-glyph separator within a `sequence` or relation
chain. It uses the same exact source-line endpoint witness as `line_join`;
the output event must still be adjacent to those two glyphs. A
`relation_chain` orders at least three operand parts and two comparison
operator parts. Intermediate parts may only be source whitespace or a
line-join gap. Each operator must be a literal source glyph from the bounded
comparison set, and operand/operator indices must strictly alternate. This
records chain structure without duplicating the middle operand.
`superscript` gives a base and exponent explicit source glyphs; every exponent
glyph center must be above every base glyph center. Like subscript geometry,
this is a structural check and still needs source-first semantic review.

When a source-line inventory is supplied, every `abstract_body` glyph must
either be emitted exactly once or listed in `reviewed_omissions`. The currently
permitted omission is a line-ending `-` dropped when the following included
body line continues a word. Its record binds the original glyph, box, two
source lines, neighboring glyph IDs and exact output junction. All intervening
source lines must be recorded with excluded roles. An omission cannot also be
emitted, and it joins the externally pinned evidence hash. The verifier checks
the mechanics of this omission; it does not establish that the visible hyphen
was only a line-wrap artifact. Actual PDF paint and matching TeX review remain
necessary before accepting the output.
Font-metric glyph boxes may overlap a fraction stroke even when the actual
ink does not. Optional `ink_box` values can resolve that geometric hold only
when `accurate_bbox_evidence` pins the original PDF and notation hashes,
PyMuPDF version, `TEXT_ACCURATE_BBOXES` flag 512, disabled quad corrections,
and fresh-original RAWDICT mode. The ink box must remain inside the nominal
box (0.001 pt coordinate tolerance) and entirely clear the original painted
stroke band. The source-bound ink inventory joins the externally trusted
evidence hash. Without it the original conservative box check still applies.
The verifier cannot regenerate the ink hull or decide paint order, occlusion,
or scientific scope; callers must independently capture and review them.
The script geometry and required relation/unit children are structural checks,
not proof of a scientifically correct subscript, equation, or unit attachment.

All glyph, source-line, rule and optional ink boxes must contain finite numeric
coordinates. The authored tests exercise mechanical invariants on synthetic
evidence; a private source-bound packet may pass mechanically while remaining
scientifically held.

Before this module could support scientific acceptance, an integrator must
bind the complete original-PDF paint/visible-text coverage, validate reviewed
corrections and normalization, prove typed serialization for every scientific
token, obtain actual source-first scientific review of competing readings,
and attach those decisions to the immutable assessment and promotion receipt.
The current reviewed abstract overlay independently hard-disables `accepted`.
