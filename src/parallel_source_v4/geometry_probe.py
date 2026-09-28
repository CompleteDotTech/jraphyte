"""Replay authorized cached native lines; diagnostic only, never qualification.

No PDF extraction, model call, graph write, or substitute dataset. The output
contains IDs, hashes, reasons and scores, never cached paper prose. Final native
re-extraction through the bounded extraction harness remains a separate gate.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import time

from trace_gc.pdf_source_parallel_v4 import validate_lines
from trace_gc.pdf_structure_parallel_v4 import assess_document, verify_assessment
from trace_gc.pdf_geometry_parallel_v4 import VERSION
from .adapters import grobid_assess, mineru_document, olmocr_assess
from .common import REPO, child, data_root, digest, method_hashes, write_once
from .extraction import METHODS, _cache
from .metrics import score_case, summary


def run(root: Path, prior: Path, output: Path, case_ids: list[str] | None = None) -> dict:
    inputs = {}
    def read(path):
        payload = path.read_bytes()
        inputs[path.relative_to(root).as_posix()] = hashlib.sha256(payload).hexdigest()
        return json.loads(payload)

    hashes = method_hashes()
    # This isolated pre-runtime-integration base predates recursive hash closure.
    # Explicitly bind the new helper as well as the existing method inventory.
    relative = "trace_gc/pdf_geometry_parallel_v4.py"
    hashes[relative] = digest(REPO/relative)
    labels = read(root/"validation_expanded200/labels.json")
    if len(labels) != 200 or set(labels) != {f"f{i:03}" for i in range(1, 201)}:
        raise ValueError("expected_authorized_200_case_labels")
    ids = sorted(labels) if case_ids is None else case_ids
    if not ids or len(set(ids)) != len(ids) or any(sid not in labels for sid in ids):
        raise ValueError("invalid_probe_case_ids")
    previous = read(prior/"results.json")
    before = {method: {row["id"]: row for row in previous["details"][method]} for method in METHODS}
    details = {method: [] for method in METHODS}
    changes = {method: [] for method in METHODS}
    started = time.perf_counter()
    for index, sid in enumerate(ids, 1):
        saved = read(prior/"assessments/parallel_structure_v4"/f"{sid}.json")
        verify_assessment(saved)
        kwargs = {key: saved[key] for key in ("page_size", "source_sha256", "page_sha256")}
        kwargs["native_lines"] = validate_lines(read(prior/"native"/f"{sid}.json"), kwargs["page_size"])
        caches = {name: read(_cache(root, name, sid)) for name in ("docling", "grobid", "mineru", "olmocr")}
        doc = read(_cache(root, "docling", sid, ".document.json"))
        field = caches["grobid"].get("text", "") if caches["grobid"].get("status") == "success" else ""
        for name, raw in caches.items():
            if raw.get("page_sha256") and raw["page_sha256"] != kwargs["page_sha256"]:
                raise ValueError("cached_converter_page_binding_mismatch")
        for method in METHODS:
            if method == "parallel_structure_v4":
                pred = assess_document(doc, **kwargs, scholarly_abstract=field, conversion_status=caches["docling"].get("status", "error"))
            elif method == "parallel_grobid_v4":
                pred = grobid_assess(caches["grobid"], doc, **kwargs)
            elif method == "parallel_mineru_v4":
                pred = assess_document(mineru_document(caches["mineru"], kwargs["page_size"]), **kwargs,
                                       scholarly_abstract=field, conversion_status=caches["mineru"].get("status", "error"))
            else:
                pred = olmocr_assess(caches["olmocr"], **kwargs, scholarly_abstract=field)
            verify_assessment(pred)
            row = score_case(sid, pred, labels[sid])
            details[method].append(row)
            old = before[method][sid]
            keys = ("predicted", "proposed", "reasons", "precision", "recall", "boundary_and_98_match")
            if any(old.get(key) != row.get(key) for key in keys):
                changes[method].append({"id": sid, "before": {key: old.get(key) for key in keys},
                                        "after": {key: row.get(key) for key in keys}})
        print(json.dumps({"completed_cases": index, "total_cases": len(ids), "id": sid}), flush=True)
    for relative, expected in inputs.items():
        if digest(child(root, relative)) != expected:
            raise ValueError("probe_input_changed_during_run")
    for relative, expected in hashes.items():
        if digest(REPO/relative) != expected:
            raise ValueError("probe_code_changed_during_run")
    result = {"schema_version": 1, "status": "CACHED_NATIVE_GEOMETRY_DIAGNOSTIC_NOT_VALIDATION",
              "geometry_version": VERSION, "cases": len(ids), "assessments": len(ids)*len(METHODS),
              "case_ids": ids, "baseline_run": prior.relative_to(root).as_posix(),
              "method_hashes": hashes, "input_hashes": inputs,
              "elapsed_seconds": time.perf_counter()-started,
              "new_paid_api_calls": 0, "production_graph_writes": 0,
              "summaries": {method: summary(rows) for method, rows in details.items()},
              "details": details, "changes": changes,
              "limits": ["Native extraction was not rerun; cached source metadata is not a fresh PDF-byte verification.",
                         "Already examined 200-case regression, not unseen or independently source-reviewed validation.",
                         "Historical alphanumeric scores do not certify notation or independently reviewed boundaries.",
                         "Final integrated bounded-runtime native replay and preservation gate remain outstanding."]}
    write_once(output, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--run", default="validation_v3_private/parallel-v4-regression-rerun-20260927-220439")
    parser.add_argument("--output", required=True, help="New relative JSON path under the authorized data root")
    parser.add_argument("--cases", nargs="+")
    args = parser.parse_args()
    root = data_root(args.data_root)
    output = child(root, args.output)
    if output.exists():
        raise ValueError("probe_output_must_be_new")
    result = run(root, child(root, args.run), output, args.cases)
    print(json.dumps({"status": result["status"], "cases": result["cases"], "assessments": result["assessments"]}))


if __name__ == "__main__":
    main()
