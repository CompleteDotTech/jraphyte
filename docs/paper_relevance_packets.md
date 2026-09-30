# Source-bound relevance review packets

`python -m src.paper_relevance_packets` prepares blinded source packets for an already completed, hash-pinned retrieval trial. It does not run retrieval, load models, judge relevance, or admit graph evidence. Use an application-approved prospective rubric and a separately approved authorization JSON. Reviewers receive only the `reviewer/` subdirectory; `coordinator_private/` contains target labels, rankings, source IDs, the full 60-query rank ledger, and the alias map.

The authorization file is private because it names the source root, query and corpus paths, target focus IDs, and output root. Its expected SHA-256 must come from a separate application owner approval record. A caller-generated SHA for an unreviewed file is not authorization. This does not require an independent human reviewer.

```json
{
  "schema_version": "paper-relevance-packet-authorization-v1",
  "data_root": "/authorized/data",
  "source_root": "/authorized/original-pdfs",
  "trial_relative": "runs/completed-trial",
  "protocol_relative": "protocol/trial-protocol.json",
  "protocol_sha256": "<64 lowercase hex>",
  "receipt_sha256": "<64 lowercase hex>",
  "rubric_path": "/authorized/private/rubric-approval.json",
  "rubric_sha256": "<64 lowercase hex>",
  "expected_prereg_sha256": "<64 lowercase hex>",
  "expected_queries_sha256": "<64 lowercase hex>",
  "expected_code_head": "<40 lowercase hex>",
  "coordinator_code_sha256": "<reviewed src/paper_relevance_packets.py SHA-256>",
  "focus_target_ids": ["<predeclared document ID>"],
  "authorized_output_root": "/authorized/private/packet-runs",
  "output_name": "new-unique-run"
}
```

Run from a source checkout only after a COMPLETE trial and a reviewed, frozen authorization. The repository's setuptools package installs `trace_gc`, while this `src` research command remains a source-checkout module:

```sh
python -m src.paper_relevance_packets \
  --authorization /authorized/private/packet-authorization.json \
  --expected-authorization-sha256 '<externally approved 64-hex SHA>'
```

The command requires the exact approved preregistration in the rubric approval, protocol/receipt hashes, the original query file hash, the measured code HEAD, reviewed coordinator file SHA, 10,000 fields and sources, 60 queries, and every measured arm result hash. The coordinator SHA check catches stale or changed code; it does not itself establish trust in unreviewed code. It checks each result's ranking and candidate-pool identity. A failed or partial trial cannot open source PDFs through this command. Output must be a new immediate child of `authorized_output_root`; an existing output is never overwritten. The output root and its ancestors may not be symlinks or junctions.

Selection follows the preregistered rules: all primary top-10 known-target misses, predeclared focus targets even if found, the primary top ten, the target, and one distinct paired top result from each measured comparison arm. The coordinator retains all 60 known-target ranks and candidate-union membership privately; absent or identical paired arms are explicit. For each selected query, source bytes are deduplicated only after all duplicate IDs' source PDF, page PDF, rendered image and physical page agree. Task order is SHA-256 of the fixed domain plus the query's ranking-input digest and source PDF SHA, with a collision hold. Reviewer query/source aliases are random and do not expose target ID, document ID, arm, rank or score. The unchanged source PDF can reveal its scholarly title, but the known-target designation remains private.

The command writes a private selection preflight before copying source bytes, verifies every original and alias copy's SHA-256, then rechecks the approved rubric, protocol, COMPLETE receipt, queries, fields, manifest, and every listed result file before reporting success. A changed input leaves a partial output for inspection and requires a new authorized attempt. It seals the raw reviewer packet file SHA in the private map. The reviewer package contains query text and opaque IDs plus alias-named source/page/render files. Source-first reviewers must work in fresh isolated contexts, disclose prior exposure to target labels, and produce attributed, hash-bound judgments with bounded source evidence. This tool does not enforce reviewer context isolation or create judgments. It makes no human-independence claim.

A COMPLETE trial proves execution integrity, not relevance. Keep known-item ranking metrics separate from later relevance judgments. An unmeasured optional arm is recorded as `NOT_RUN`; a result artifact missing or changed for an arm the COMPLETE receipt lists, or a declared measured arm absent from that receipt, is a hold. An incomplete source, changed hash, ordering collision, or divergent duplicate byte evidence is also a hold. Inspect a partial new output without retrying it under the same name. A new attempt requires a new reviewed output name and authorization.
