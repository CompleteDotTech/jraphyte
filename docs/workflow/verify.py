"""Check documentation links, source coverage, Mermaid copies and rendered receipts.

Run with --refresh-map after reviewing changed code to deliberately refresh the
module-to-chapter inventory. This does not execute application code or tests.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import struct
from pathlib import Path
from urllib.parse import unquote

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
INDEX = json.loads((HERE / "diagram-index.json").read_text(encoding="utf-8"))
CHAPTERS = {int(d["id"][:2]): d["id"] for d in INDEX["diagrams"]}
CORE = {
    "__init__": [1, 12], "__main__": [12], "adapter": [3], "backend": [4, 5],
    "budget": [12], "canonical": [2, 5], "catalog": [2], "cli": [12],
    "compiler": [2, 7], "conformance": [11], "constraints": [3, 4],
    "demo": [1, 11], "errors": [2, 12], "ledger": [5], "legacy": [4, 11],
    "plans": [4, 5], "policy": [4], "programs": [2, 3], "qualification": [4],
    "references": [2, 5], "replay": [5], "resolver": [3], "schema": [2],
    "trust": [4], "validation": [5, 11],
}
RETRIEVAL = {
    "__init__": [6, 7, 8], "benchmark": [6, 11], "budget": [6, 12],
    "contracts": [6], "evaluation": [6, 11], "fixtures": [6, 11],
    "integration": [2, 7, 8], "items": [6, 8], "planner": [7],
    "reranker": [6, 7], "scenarios": [1, 7, 8, 11], "security": [6, 8],
    "service": [6, 8], "store": [6, 8], "strategies": [6], "vector": [6],
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_paths() -> list[Path]:
    paths = []
    for directory in ("trace_gc", "src", "tools"):
        paths.extend((REPO / directory).rglob("*.py"))
    paths.append(REPO / "examples/graphrag/query_example.py")
    return sorted(paths)


def chapters_for(path: Path) -> list[int]:
    rel = path.relative_to(REPO)
    if rel.parts[0] == "src":
        return [9, 10]
    if rel.parts[0] == "tools":
        return [9, 10, 11] if path.stem == "public_fixtures_parallel_v4" else [11]
    if rel.parts[0] == "examples":
        return [8]
    if "retrieval" in rel.parts:
        return RETRIEVAL[path.stem]
    if path.stem.startswith("pdf_"):
        return [9, 10]
    return CORE[path.stem]


def refresh_map() -> None:
    entries = []
    for path in source_paths():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        description = (ast.get_docstring(tree) or "Module initialization or command forwarding.").split("\n\n")[0].replace("\n", " ")
        entries.append({
            "path": path.relative_to(REPO).as_posix(), "sha256": digest(path),
            "chapters": [CHAPTERS[n] for n in chapters_for(path)],
            "description": description,
            "top_level_symbols": [node.name for node in tree.body if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))],
        })
    (HERE / "source-map.json").write_text(json.dumps({
        "source_revision": INDEX["source_revision"],
        "scope": "Every active Python module under trace_gc, src and tools, plus the downstream query example. Archives and tests are not active workflow modules.",
        "files": entries,
    }, indent=2) + "\n", encoding="utf-8")
    lines = ["# Workflow source coverage", "", "[Atlas index](README.md) · [Machine-readable source hashes](source-map.json)", "",
             f"The atlas indexes **{len(entries)} active Python modules** at source revision `{INDEX['source_revision']}`. The table assigns every module to its explanatory chapters; it does not claim a separate diagram node for every helper function. The JSON also records each top-level class/function and exact file hash.", "",
             "Function-level explanations and test references live in the linked chapters. Archived releases remain historical context. The application runtime, optional research harnesses and release tooling remain distinct in the diagrams.", ""]
    for prefix, title in (("trace_gc/", "Runtime and retrieval"), ("src/", "Versioned research experiments"), ("tools/", "Validation and release tooling"), ("examples/", "Executable query example")):
        lines.extend([f"## {title}", "", "| Source module | Workflow chapters |", "| --- | --- |"])
        for item in entries:
            if not item["path"].startswith(prefix):
                continue
            links = " · ".join(f"[{int(ch[:2]):02d}]({ch}.md)" for ch in item["chapters"])
            lines.append(f"| [{item['path']}](../../{item['path']}) | {links} |")
        lines.append("")
    lines.extend(["## Keeping the inventory current", "",
                  "Run `python docs/workflow/verify.py` to verify file hashes, module coverage, local links, matching Mermaid blocks and image receipts. After reviewing a code change and updating the affected chapters/revision, use `--refresh-map` to explicitly accept a new source inventory. Regenerate changed figures with `render.mjs` before verification.", ""])
    (HERE / "SOURCE_MAP.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh-map", action="store_true")
    args = parser.parse_args()
    if args.refresh_map:
        refresh_map()
    errors = []
    inventory = json.loads((HERE / "source-map.json").read_text(encoding="utf-8"))
    expected = {p.relative_to(REPO).as_posix() for p in source_paths()}
    recorded = {item["path"] for item in inventory["files"]}
    if recorded != expected:
        errors.append("Source inventory has missing or extra paths.")
    if len(recorded) != len(inventory["files"]):
        errors.append("Source inventory has duplicate paths.")
    for item in inventory["files"]:
        path = REPO / item["path"]
        if not path.is_file() or digest(path) != item["sha256"]:
            errors.append(f"Source changed: {item['path']}")
        for chapter in item["chapters"]:
            if not (HERE / (chapter + ".md")).is_file():
                errors.append(f"Missing chapter for {item['path']}: {chapter}")

    indexed = {d["id"] for d in INDEX["diagrams"]}
    if {p.stem for p in HERE.glob("*.mmd")} != indexed:
        errors.append("Mermaid file set differs from diagram index.")
    for diagram in INDEX["diagrams"]:
        source = (HERE / (diagram["id"] + ".mmd")).read_text(encoding="utf-8").strip()
        md = (HERE / (diagram["id"] + ".md")).read_text(encoding="utf-8")
        blocks = re.findall(r"```mermaid\s*\n(.*?)```", md, re.S)
        if len(blocks) != 1 or blocks[0].strip() != source:
            errors.append(f"Mermaid block differs: {diagram['id']}")
        if "accTitle:" not in source or "accDescr:" not in source:
            errors.append(f"Accessibility metadata missing: {diagram['id']}")
        groups = set(re.findall(r"^\s*subgraph\s+(\w+)", source, re.M))
        nodes = set(re.findall(r"^\s*(\w+)\s*[\[({]", source, re.M))
        if groups & nodes:
            errors.append(f"Subgraph/node ID collision in {diagram['id']}: {sorted(groups & nodes)}")

    links_checked = 0
    for path in HERE.glob("*.md"):
        for target in re.findall(r"\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
            if re.match(r"https?://|mailto:|#", target):
                continue
            target_path, _, anchor = unquote(target).partition("#")
            resolved = (path.parent / target_path).resolve()
            links_checked += 1
            # verification.json is the receipt being produced by this command.
            if resolved == HERE / "verification.json":
                continue
            if not resolved.exists():
                errors.append(f"Broken link: {path.name} -> {target}")
            elif re.fullmatch(r"L\d+", anchor) and resolved.is_file():
                lines = len(resolved.read_text(encoding="utf-8").splitlines())
                if not 1 <= int(anchor[1:]) <= lines:
                    errors.append(f"Line anchor out of bounds: {path.name} -> {target}")

    manifest = json.loads((HERE / "render-manifest.json").read_text(encoding="utf-8"))
    if manifest["source_revision"] != INDEX["source_revision"] or inventory["source_revision"] != INDEX["source_revision"]:
        errors.append("Reviewed source revision differs across receipts.")
    expected_renders = {(d, t) for d in indexed for t in ("light", "dark")}
    if {(r["diagram"], r["theme"]) for r in manifest["renders"]} != expected_renders or len(manifest["renders"]) != len(expected_renders):
        errors.append("Expected exactly one light and dark render per diagram.")
    for render in manifest["renders"]:
        png = HERE / render["png"]
        svg = HERE / render["svg"]
        if not png.is_file() or not svg.is_file():
            errors.append(f"Missing rendered export: {render['diagram']}")
            continue
        data = png.read_bytes()
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            errors.append(f"Invalid PNG signature: {png.name}")
            continue
        width, height = struct.unpack(">II", data[16:24])
        if (width, height) != (render["width"], render["height"]) or min(width, height) < 3000:
            errors.append(f"PNG dimensions invalid or below HD target: {png.name}")
        if digest(png) != render["sha256"] or len(data) != render["bytes"]:
            errors.append(f"PNG receipt differs: {png.name}")
        if digest(HERE / (render["diagram"] + ".mmd")) != render["source_sha256"]:
            errors.append(f"Diagram changed after rendering: {render['diagram']}")
        if render["clipping_check"] != "PASS":
            errors.append(f"Clipping check failed: {png.name}")
    result = {"status": "FAIL" if errors else "PASS", "source_revision": INDEX["source_revision"],
              "active_modules": len(recorded), "chapters": len(indexed), "png_exports": len(manifest["renders"]),
              "svg_exports": len(manifest["renders"]), "local_links_checked": links_checked,
              "mermaid_blocks_match_sources": not any("Mermaid block" in e for e in errors),
              "runtime_tests_executed": False, "errors": errors}
    (HERE / "verification.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    raise SystemExit(bool(errors))


if __name__ == "__main__":
    main()
