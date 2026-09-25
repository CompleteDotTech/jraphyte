# Trust and security scope

This is an inspectable research/reference runtime, not a security certification. Model-produced JSON, source text, arbitrary hashes, policy flags, included public keys, synthetic labels and self-reported completeness are untrusted. Immutable content binding and validation establish consistency, not truth.

The trusted computing base includes installed compiler/schema/question/adapter code, administrator-enrolled issuer capabilities, signers/private-key handling, the selected graph backend and its host, the SQLite budget store, approved tokenizer and the independent labeling/qualification process. An attacker who controls the host, trusted code or signing keys can bypass library-level controls; this release does not claim protection from that threat.

Analysis is the default. Synthetic data cannot authorize non-sandbox publication. Receipts bind plan bytes, operation scope, principal capabilities and expiry, and are rechecked under transaction locks. Full signed provenance needs external trust; an internally rehashed ledger is not an authorization mechanism. Do not pass credentials through prompts, source documents or bundles. Exported evidence/observations may contain confidential source text and need access controls.

Before deployment complete the gates in `docs/14_deployment.md`. The exact upstream compatibility gate, live-provider acceptance and empirical qualification were not completed here. Configure source permissions, revocation, backups, retention, least-privilege service access and monitoring in the actual environment. Local cache erasure does not promise removal of every source-derived datum or upstream backup.

Untrusted remote JSON-schema references are not resolved. Legacy source is checked against the exact reviewed Git blob before import. The adapter does not silently send authorization to redirect targets. Input depth/size, request budgets, solver expansions and retries are bounded. Unsupported operations fail rather than falling back to a less constrained implementation.

No private keys or credentials are included in this project. Demo keys exist only in memory; exported keys are public and must not be auto-enrolled for deployment.

## GraphRAG-specific boundary

Retrieved text is data, never instructions. The service applies deny-by-default tenant/workspace/principal/role/classification/source/node/edge ACLs before traversal, embeddings or model-context construction; current source READ/epoch/tombstone status also controls historical reads. A live retrieved pack requires a current application ACL. Summaries are noncanonical and item text/provenance is reconstructed from immutable originals. Exact retrieval fingerprints and receipt-derived reranking protect lineage.

The internal Catalog/audit bundle is privileged and is not an appropriate downstream-user response. Expose only the authorized GraphRAGAnswerContext. Retention and erasure must cover exported bundles, caches and in-memory catalogs; revocation cannot recall text already delivered. The reference timeout is cooperative, so external adapters must enforce I/O deadlines. See `docs/18_graphrag_security.md` for the threat model, operational limits and tests.
