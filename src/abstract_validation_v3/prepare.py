"""Prepare first-page source views only; never open or produce model predictions."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

from .adapters import read_native_page
from .common import data_root, external_output, read, resolve_source, write_once, file_digest, safe_id


def _bytes_once(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream: stream.write(data)
    except FileExistsError:
        if path.is_symlink() or path.read_bytes() != data:
            raise ValueError("immutable_source_view_conflict") from None


def prepare(rows: list[dict], root: Path, out: Path, *, dpi: int = 120) -> list[dict]:
    import fitz
    out = external_output(out)
    if not out.is_relative_to(root.resolve()):
        raise ValueError("source_views_must_remain_under_authorized_data_root")
    prepared = []
    seen = set()
    for row in rows:
        sid = safe_id(row["id"])
        if sid in seen: raise ValueError("duplicate_source_identity")
        seen.add(sid)
        source = resolve_source(root, row["source_path"])
        page = read_native_page(source)
        folder = out / sid
        with fitz.open(stream=source.read_bytes(), filetype="pdf") as document:
            single = fitz.open()
            try:
                single.insert_pdf(document, from_page=0, to_page=0)
                page_bytes = single.tobytes(no_new_id=True)
            finally:
                single.close()
            image = document[0].get_pixmap(dpi=dpi).tobytes("png")
        if hashlib.sha256(page_bytes).hexdigest() != page["page_sha256"]:
            raise ValueError("first_page_serialization_not_reproducible")
        _bytes_once(folder / "page.pdf", page_bytes)
        _bytes_once(folder / "page.png", image)
        write_once(folder / "lines.json", page["native_lines"])
        prepared.append({"id": sid, "work_id": row["work_id"], "source_path": row["source_path"],
                         "source_sha256": page["source_sha256"], "page_sha256": page["page_sha256"],
                         "image_sha256": hashlib.sha256(image).hexdigest(),
                         "native_lines_sha256": file_digest(folder / "lines.json"), "render_dpi": dpi,
                         "page_path": (folder/"page.pdf").relative_to(root).as_posix(),
                         "image_path": (folder/"page.png").relative_to(root).as_posix(),
                         "lines_path": (folder/"lines.json").relative_to(root).as_posix(),
                         "physical_page": 1, "pymupdf_version": page["pymupdf_version"]})
    write_once(out / "source_manifest.json", prepared)
    return prepared


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-root", type=Path)
    p.add_argument("--manifest", required=True, type=Path, help="external JSON list: id, work_id, source_path")
    p.add_argument("--out", required=True, type=Path)
    a = p.parse_args()
    result = prepare(read(a.manifest), data_root(a.data_root), a.out)
    print(json.dumps({"sources_prepared": len(result), "predictions_opened": False, "source_review": "required_next"}))


if __name__ == "__main__": main()
