"""Reproducible synthetic GraphRAG ablations and actual pipeline wiring checks.

The semantic oracle deliberately depends on known fixture relevance. These runs
measure retrieval mechanics and controlled context-to-decision changes, not model
accuracy, scientific validity, calibrated probabilities, or production cost.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import time
from ..budget import RunBudget
from ..canonical import digest, write
from ..compiler import now
from ..demo import limits
from ..policy import create_policy
from .contracts import VERSION, RetrievalBudget, query, item_id
from .evaluation import UPSTREAM_ABLATIONS, DOWNSTREAM_ABLATIONS, retrieval_metrics, efficiency_metrics
from .fixtures import corpus, demo_access, SCOPE
from .planner import RetrievalPlanner, UpstreamGraphRAG
from .reranker import JevReranker
from .scenarios import synthetic_response
from .service import GraphRAGQueryService

CASES = [
    {"id": "entity_alignment", "task": "IDENTITY", "text": "Acme and Acme Holdings are aliases of the same organization.",
     "focus": ["Acme"], "gold_edges": ["e-alias"], "gold_entities": ["Acme", "Acme-Holdings"]},
    {"id": "relation_synthesis", "task": "ASSERTION", "text": "What indirect ownership path connects Acme through Bar to Foo?",
     "focus": ["Acme"], "gold_edges": ["e-owns", "e-path"], "gold_entities": ["Acme", "Bar", "Foo"], "gold_paths": [["e-owns", "e-path"]]},
    {"id": "claim_reconciliation", "task": "CLAIM_RECONCILIATION", "text": "Intervention X improves outcome Y in population P: compare supporting and refuting claims.",
     "focus": ["$claim"], "gold_edges": ["e-support", "e-refute"], "gold_entities": ["Paper-A", "Paper-B", "$claim"], "gold_conflicts": [["e-refute", "e-support"]]},
    {"id": "ontology_typing", "task": "ONTOLOGY", "text": "Organization is a subtype of Entity; retrieve the type hierarchy.",
     "focus": ["Organization"], "gold_edges": ["e-ontology"], "gold_entities": ["Organization", "Entity"], "query": {"ontology_scope": ["Organization", "Entity"]}},
    {"id": "temporal_updates", "task": "TEMPORAL", "text": "How did Foo change from subsidiary of Baz to subsidiary of Acme in March 2024?",
     "focus": ["Foo"], "gold_edges": ["e-old", "e-new"], "gold_entities": ["Foo", "Baz", "Acme"], "query": {"include_historical": True, "include_superseded": True}},
    {"id": "contradiction_handling", "task": "CLAIM_RECONCILIATION", "text": "Find the conflicting support and refutation for intervention X outcome Y.",
     "focus": ["$claim"], "gold_edges": ["e-support", "e-refute"], "gold_entities": ["Paper-A", "Paper-B"], "gold_conflicts": [["e-refute", "e-support"]]},
    {"id": "scientific_knowledge", "task": "SCIENTIFIC", "text": "Compare the randomized method, Dataset P, replication and conflicting evidence in Papers A, B and C.",
     "focus": ["Paper-A", "Paper-B", "$claim"], "gold_edges": ["e-support", "e-refute", "e-replicate", "e-method", "e-dataset"],
     "gold_entities": ["Paper-A", "Paper-B", "Paper-C", "Method-randomized", "Dataset-P"], "gold_conflicts": [["e-refute", "e-support"]]},
]
RUN = "synthetic-graphrag-ablation"
POLICY = "graphrag-benchmark-review-v1"
POPULATION = "fabricated-context-oracle-not-qualified"


def resolved_case(case, fixture):
    result = deepcopy(case)
    for field in ("focus", "gold_entities"):
        result[field] = [fixture["claim_id"] if x == "$claim" else x for x in case[field]]
    return result


def gold(case, fixture):
    grades = {}
    for edge in case["gold_edges"]:
        grades[item_id("EDGE", edge)] = 2
        grades[item_id("EVIDENCE", fixture["evidence"][edge])] = 2
    for entity in case["gold_entities"]:
        grades[item_id("NODE", entity)] = 1
    paths = []
    for members in case.get("gold_paths", []):
        ref = digest(list(min(tuple(members), tuple(reversed(members)))))
        paths.append(item_id("PATH", ref, members))
        grades[paths[-1]] = 3
    conflicts = []
    for members in case.get("gold_conflicts", []):
        conflicts.append(item_id("CONFLICT", digest(sorted(members)), sorted(members)))
        grades[conflicts[-1]] = 3
    expected = {"entity": case["gold_entities"], "evidence": [fixture["evidence"][x] for x in case["gold_edges"]],
                "path": paths, "contradiction": conflicts, "provenance": []}
    return grades, expected


def has_relevant_context(items, case, fixture):
    """Explicit controlled oracle: all labeled edge sources or graph edges visible."""
    edges = {e for i in items for e in i["assertion_ids"]}
    evidence = {e for i in items for e in i["evidence_ids"]}
    return all(edge in edges or fixture["evidence"][edge] in evidence for edge in case["gold_edges"])


def add_benchmark_candidate(fixture, case):
    c = fixture["catalog"]
    claim = c.claim(case["text"])
    source = c.source("benchmark-source", case["id"], "SYNTHETIC TASK DESCRIPTION, NOT REAL EVIDENCE: "+case["text"], scope=SCOPE)
    evidence = c.evidence(source)
    fixture["adapter"].source_status[source] = {"active": True, "permission": "READ", "tombstone": False, "epoch": 1, "updated_at": now()}
    snapshot = c.get(fixture["snapshot_id"], "graph-snapshot")
    snapshot["graph_version"] = 3
    snapshot["nodes"].update({"benchmark-source": "Document", claim: "Claim"})
    snapshot["source_epochs"][source] = 1
    snapshot_id = c.put("graph-snapshot", snapshot)
    fixture["adapter"].snapshot_ids.append(snapshot_id)
    candidate = c.candidate(id_="benchmark:"+case["id"], run_id=RUN, claim_id=claim, evidence_ids=[evidence],
        assertion={"subject": "benchmark-source", "predicate": "supports", "object": claim, "qualifiers": {}})
    fixture["retriever"].set_access_policy(demo_access(c, snapshot_id))
    create_policy(c, version=POLICY, scope=SCOPE, population=POPULATION, mode="REVIEWED", allowed_modes=["SYNTHETIC"])
    return candidate, source


class FixedPlanner(RetrievalPlanner):
    def __init__(self, case, configuration, source):
        super().__init__()
        self.case, self.configuration, self.source = case, configuration, source
    def plan(self, catalog, **kwargs):
        ref = super().plan(catalog, **kwargs)
        body = catalog.get(ref, "retrieval-plan")
        body["known_entities"] = sorted(self.case["focus"])
        hop = self.configuration.get("hop_limit", 1)
        body["steps"] = [{"strategy": x, "max_hops": hop} for x in self.configuration["retrieval_strategy"]]
        return catalog.put("retrieval-plan", body)
    def request(self, catalog, plan_id, **kwargs):
        kwargs.update(self.case.get("query", {}))
        kwargs.update({k: v for k, v in self.configuration.items() if k not in {"retrieval_strategy", "hop_limit"}})
        if self.configuration["retrieval_strategy"] == ["SOURCE", "EVIDENCE"]:
            kwargs["source_scope"] = [self.source]  # No graph-assisted source lookup in this ablation.
        return super().request(catalog, plan_id, **kwargs)


class AdaptiveCasePlanner(RetrievalPlanner):
    def __init__(self, case):
        super().__init__()
        self.case = case
    def plan(self, catalog, **kwargs):
        kwargs["known_entities"] = self.case["focus"]
        return super().plan(catalog, **kwargs)
    def request(self, catalog, plan_id, **kwargs):
        kwargs.update(self.case.get("query", {}))
        return super().request(catalog, plan_id, **kwargs)


def run_benchmark(output: str | Path | None=None):
    rows = []
    dataset_hash = digest({"cases": CASES, "fixture": "retrieval-fixture-schema-v1", "label_origin": "HAND_AUTHORED_SYNTHETIC"})
    with tempfile.TemporaryDirectory(prefix="trace-graphrag-benchmark-") as directory:
        for case_template in CASES:
            for configuration_name, configuration in UPSTREAM_ABLATIONS.items():
                fixture = corpus()
                c, r = fixture["catalog"], fixture["retriever"]
                case = resolved_case(case_template, fixture)
                candidate, source = add_benchmark_candidate(fixture, case)
                grades, expected = gold(case, fixture)
                adaptive = configuration_name == "adaptive"
                planner = AdaptiveCasePlanner(case) if adaptive else FixedPlanner(case, configuration, source)
                elapsed = {"model_ms": 0.0, "packs": 0}
                def callback(pack_id):
                    started = time.monotonic()
                    pack = c.get(pack_id, "pack")
                    items = [i for ctx in pack["state"]["graph_context"] for i in ctx["items"]]
                    is_relevance = pack["questions"][0]["task"] == "GRAPH_RELEVANCE"
                    # The relevance-only oracle is fixed, explicitly synthetic and
                    # intentionally does not claim to model Jev's ranking quality.
                    label = "RELEVANT" if is_relevance else "SUPPORTS" if has_relevant_context(items, case, fixture) else "INSUFFICIENT"
                    result = synthetic_response(c, pack_id, label)
                    elapsed["model_ms"] += (time.monotonic()-started)*1000
                    elapsed["packs"] += 1
                    return result
                budget = RunBudget(Path(directory)/(case["id"]+"-"+configuration_name+".sqlite3"), RUN, limits())
                try:
                    started = time.monotonic()
                    run = UpstreamGraphRAG(r, planner).run(candidate_id=candidate, execute=callback, run_budget=budget,
                        policy_version=POLICY, population=POPULATION, question_type=case["task"],
                        budget=RetrievalBudget(maximum_tokens=12000, maximum_latency_ms=10000, maximum_rounds=5 if adaptive else 1),
                        reranker=JevReranker(callback) if configuration_name == "hybrid_semantic" else None)
                    duration = (time.monotonic()-started)*1000
                finally:
                    budget.close()
                result = c.get(run.result_ids[-1], "retrieval-result")
                context = c.get(result["graph_context_id"], "graph-context")
                items = context["items"]
                metrics = retrieval_metrics([i["id"] for i in items], grades, k=10, items=items, expected=expected)
                lineages = [c.get(c.get(x, "retrieval-result")["lineage_id"], "retrieval-lineage") for x in run.result_ids]
                packs = [r["body"] for r in c.all("pack")]
                tokens = sum(p["budget"]["state_tokens"]+sum(p["budget"]["question_tokens"].values()) for p in packs)
                efficiency = efficiency_metrics(lineages, jev_latency_ms=elapsed["model_ms"], total_synthesis_latency_ms=duration,
                    tokens_supplied_to_jev=tokens, resolved_candidates=int(bool(c.get(run.batch_id, "resolution-batch")["selected_ids"])))
                row = {"role": "upstream", "case": case["id"], "configuration": configuration_name, "metrics": metrics,
                    "efficiency": efficiency, "result_status": result["status"], "stop_reason": run.stop_reason,
                    "synthetic_analysis_selected": bool(c.get(run.batch_id, "resolution-batch")["selected_ids"]),
                    "semantic_packs": elapsed["packs"], "model_judgments": "FABRICATED_CONTEXT_ORACLE",
                    "graph_version": context["graph_version"], "retrieval_fingerprint": context["retrieval_fingerprint"],
                    "embedding_version": context["embedding_version"], "policy_outcome": c.get(run.evaluation_id, "evaluation")["outcome"],
                    "real_synthesis_accuracy": None, "production_qualified": False}
                c.put("retrieval-evaluation", {"version": VERSION, "dataset_hash": dataset_hash, "split": "SYNTHETIC_SMOKE",
                    "label_origin": "HAND_AUTHORED_FIXTURE_RELEVANCE", "metrics": {**metrics, **efficiency},
                    "configuration": configuration, "result_ids": run.result_ids, "production_qualified": False, "created_at": now()})
                rows.append(row)
            for name, configuration in DOWNSTREAM_ABLATIONS.items():
                fixture = corpus()
                case = resolved_case(case_template, fixture)
                params = {**case.get("query", {}), **configuration}
                methods = params.pop("retrieval_strategy")
                result = GraphRAGQueryService(fixture["retriever"]).query(query(requesting_component="downstream-benchmark",
                    security_scope=SCOPE, focus_entities=case["focus"], text=case["text"], strategies=methods,
                    budget=RetrievalBudget(maximum_tokens=12000, maximum_latency_ms=10000), **params))
                answer = result["context"]
                grades, expected = gold(case, fixture)
                items = answer["items"]
                rows.append({"role": "downstream", "case": case["id"], "configuration": name,
                    "metrics": retrieval_metrics([i["id"] for i in items], grades, k=10, items=items, expected=expected),
                    "canonical_citations": len(answer["citations"]), "warnings": answer["warnings"],
                    "graph_version": answer["graph_version"], "production_qualified": False})
    report = {"status": "PASS", "dataset_hash": dataset_hash, "created_at": now(), "cases": len(CASES),
        "upstream_configurations": list(UPSTREAM_ABLATIONS), "downstream_configurations": list(DOWNSTREAM_ABLATIONS),
        "runs": len(rows), "results": rows, "provider_calls": 0, "production_graph_writes": 0,
        "real_model_accuracy": None, "heldout_production_results": None,
        "interpretation": "Synthetic retrieval/pipeline wiring only. The semantic oracle sees fixture relevance; its decisions are not an unbiased model evaluation. No claim that GraphRAG improves real synthesis is established.",
        "cost_units": "Logical work; monetary cost is unmeasured.", "tokens": "Conservative UTF-8 byte estimates, not billed provider tokens."}
    if output:
        target = Path(output)
        target.mkdir(parents=True, exist_ok=True)
        write(target/"dataset.json", {"dataset_hash": dataset_hash, "cases": CASES, "label_origin": "HAND_AUTHORED_SYNTHETIC"})
        write(target/"benchmark_results.json", report)
        lines = ["# GraphRAG synthetic benchmark", "", report["interpretation"], "",
            f"{report['runs']} actual runs: 7 cases × (8 upstream + 5 downstream).", "",
            "| Case | Configuration | Evidence recall | Contradiction recall | Synthetic selection |",
            "|---|---|---:|---:|---|"]
        for row in rows:
            if row["role"] == "upstream":
                lines.append(f"| {row['case']} | {row['configuration']} | {row['metrics']['evidence_recall']} | {row['metrics']['contradiction_recall']} | {row['synthetic_analysis_selected']} |")
        (target/"benchmark_summary.md").write_text("\n".join(lines)+"\n")
    return report

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run_benchmark(args.output)
    print(json.dumps({k: report[k] for k in ("status", "cases", "runs", "provider_calls", "production_graph_writes", "interpretation")}, indent=2))
