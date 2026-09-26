#!/usr/bin/env python3
"""Create a source-release ZIP with a complete, nonrecursive byte manifest."""
from __future__ import annotations
import argparse
import hashlib
import json
import zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
RELEASE="0.4.0"


def included(path: Path) -> bool:
    rel=path.relative_to(ROOT)
    name=path.name.lower()
    if name==".env" or (name.startswith(".env.") and name!=".env.example"):
        return False
    return (path.is_file() and not any(part in {"__pycache__",".git",".venv","build"} or part.endswith(".egg-info") for part in rel.parts)
            and (rel.parts[0]!="dist" or path.name==f"trace_gc-{RELEASE}-py3-none-any.whl")
            and not path.name.endswith((".pyc",".pyo",".sqlite3",".sqlite3-wal",".sqlite3-shm")))


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=ROOT.parent/(ROOT.name+".zip"))
    args=parser.parse_args();target=args.output.resolve()
    if target.is_relative_to(ROOT):parser.error("ZIP output must be outside the project directory")
    entries=[]
    for path in sorted(ROOT.rglob("*")):
        if included(path) and path!=ROOT/"MANIFEST.json":
            data=path.read_bytes();entries.append({"path":path.relative_to(ROOT).as_posix(),"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()})
    manifest={"release":RELEASE,"hash_algorithm":"SHA-256","manifest_self_excluded":True,"file_count":len(entries),"files":entries}
    (ROOT/"MANIFEST.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    with zipfile.ZipFile(target,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for path in sorted(ROOT.rglob("*")):
            if included(path):archive.write(path,ROOT.name+"/"+path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None:raise RuntimeError("ZIP CRC integrity failure")
        for item in entries:
            data=archive.read(ROOT.name+"/"+item["path"])
            if len(data)!=item["bytes"] or hashlib.sha256(data).hexdigest()!=item["sha256"]:
                raise RuntimeError("Manifest mismatch: "+item["path"])
    result={"status":"PASS","path":str(target),"files_in_zip":len(entries)+1,"bytes":target.stat().st_size,"sha256":hashlib.sha256(target.read_bytes()).hexdigest()}
    target.with_suffix(target.suffix+".sha256").write_text(result["sha256"]+"  "+target.name+"\n",encoding="ascii")
    print(json.dumps(result,indent=2))

if __name__=="__main__":main()
