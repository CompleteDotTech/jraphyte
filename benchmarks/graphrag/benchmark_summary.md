# GraphRAG synthetic benchmark

Synthetic retrieval/pipeline wiring only. The semantic oracle sees fixture relevance; its decisions are not an unbiased model evaluation. No claim that GraphRAG improves real synthesis is established.

91 actual runs: 7 cases × (8 upstream + 5 downstream).

| Case | Configuration | Evidence recall | Contradiction recall | Synthetic selection |
|---|---|---:|---:|---|
| entity_alignment | no_graph | 0.0 | None | False |
| entity_alignment | one_hop | 1.0 | None | True |
| entity_alignment | vector_only | 1.0 | None | True |
| entity_alignment | paths_only | 0.0 | None | False |
| entity_alignment | graph_only | 1.0 | None | True |
| entity_alignment | hybrid | 1.0 | None | True |
| entity_alignment | hybrid_semantic | 1.0 | None | True |
| entity_alignment | adaptive | 1.0 | None | True |
| relation_synthesis | no_graph | 0.0 | None | False |
| relation_synthesis | one_hop | 0.5 | None | False |
| relation_synthesis | vector_only | 1.0 | None | True |
| relation_synthesis | paths_only | 1.0 | None | True |
| relation_synthesis | graph_only | 1.0 | None | True |
| relation_synthesis | hybrid | 1.0 | None | True |
| relation_synthesis | hybrid_semantic | 1.0 | None | True |
| relation_synthesis | adaptive | 1.0 | None | True |
| claim_reconciliation | no_graph | 0.0 | 0.0 | False |
| claim_reconciliation | one_hop | 1.0 | 0.0 | True |
| claim_reconciliation | vector_only | 1.0 | 0.0 | True |
| claim_reconciliation | paths_only | 1.0 | 0.0 | True |
| claim_reconciliation | graph_only | 1.0 | 1.0 | True |
| claim_reconciliation | hybrid | 1.0 | 1.0 | True |
| claim_reconciliation | hybrid_semantic | 1.0 | 1.0 | True |
| claim_reconciliation | adaptive | 1.0 | 1.0 | True |
| ontology_typing | no_graph | 0.0 | None | False |
| ontology_typing | one_hop | 1.0 | None | True |
| ontology_typing | vector_only | 1.0 | None | True |
| ontology_typing | paths_only | 0.0 | None | False |
| ontology_typing | graph_only | 1.0 | None | True |
| ontology_typing | hybrid | 1.0 | None | True |
| ontology_typing | hybrid_semantic | 1.0 | None | True |
| ontology_typing | adaptive | 1.0 | None | True |
| temporal_updates | no_graph | 0.0 | None | False |
| temporal_updates | one_hop | 1.0 | None | True |
| temporal_updates | vector_only | 1.0 | None | True |
| temporal_updates | paths_only | 0.5 | None | False |
| temporal_updates | graph_only | 1.0 | None | True |
| temporal_updates | hybrid | 1.0 | None | True |
| temporal_updates | hybrid_semantic | 1.0 | None | True |
| temporal_updates | adaptive | 1.0 | None | True |
| contradiction_handling | no_graph | 0.0 | 0.0 | False |
| contradiction_handling | one_hop | 1.0 | 0.0 | True |
| contradiction_handling | vector_only | 1.0 | 0.0 | True |
| contradiction_handling | paths_only | 1.0 | 0.0 | True |
| contradiction_handling | graph_only | 1.0 | 1.0 | True |
| contradiction_handling | hybrid | 1.0 | 1.0 | True |
| contradiction_handling | hybrid_semantic | 1.0 | 1.0 | True |
| contradiction_handling | adaptive | 1.0 | 1.0 | True |
| scientific_knowledge | no_graph | 0.0 | 0.0 | False |
| scientific_knowledge | one_hop | 1.0 | 0.0 | True |
| scientific_knowledge | vector_only | 1.0 | 0.0 | True |
| scientific_knowledge | paths_only | 1.0 | 0.0 | True |
| scientific_knowledge | graph_only | 1.0 | 1.0 | True |
| scientific_knowledge | hybrid | 0.8 | 1.0 | False |
| scientific_knowledge | hybrid_semantic | 0.8 | 1.0 | False |
| scientific_knowledge | adaptive | 1.0 | 1.0 | True |
