"""Build source-hashed, query-independent fields from a prepared page-one manifest."""
from __future__ import annotations
import argparse
import time
from pathlib import Path
from trace_gc.pdf_source_parallel_v4 import source_lines,digest_value
from .common import child,data_root,digest,read,write_once
from .retrieval import extract_fields


def build_fields(root: Path, manifest: dict, output: Path, *, title_reviews=None, ocr_caches=None) -> dict:
    import fitz
    started=time.perf_counter(); fields=[]; ids=set()
    for row in manifest['pdfs']:
        sid=row['sample_id']
        if sid in ids:raise ValueError('duplicate_field_document_id')
        ids.add(sid)
        if row.get('physical_page')!=1:raise ValueError('retrieval_fields_require_first_physical_page')
        for key in ('source','page','image','native'):
            if digest(child(root,row[key+'_relative']))!=row[key+'_sha256']:
                raise ValueError('field_source_hash_mismatch')
        with fitz.open(child(root,row['page_relative'])) as pdf:
            native=source_lines(pdf[0]);page_size=[pdf[0].rect.width,pdf[0].rect.height]
        fields.append(extract_fields(sid,native,page_size=page_size,source_sha256=row['source_sha256'],page_sha256=row['page_sha256'],image_sha256=row['image_sha256'],
                                     reviewed_title=(title_reviews or {}).get(sid),ocr_cache=(ocr_caches or {}).get(sid)))
    result={'fields':fields,'fields_sha256':digest_value(fields),'field_count':len(fields),
            'unsearchable_ids':[x['id'] for x in fields if not x['searchable']], 'query_independent':True,
            'runtime_seconds':time.perf_counter()-started,'new_paid_api_calls':0,'production_graph_writes':0}
    write_once(output,result)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--data-root');p.add_argument('--manifest',required=True)
    p.add_argument('--title-reviews');p.add_argument('--ocr-caches');p.add_argument('--output',required=True)
    a=p.parse_args();root=data_root(a.data_root)
    build_fields(root,read(child(root,a.manifest)),child(root,a.output),
                 title_reviews=read(child(root,a.title_reviews)) if a.title_reviews else None,
                 ocr_caches=read(child(root,a.ocr_caches)) if a.ocr_caches else None)
    return 0


if __name__=='__main__':raise SystemExit(main())
