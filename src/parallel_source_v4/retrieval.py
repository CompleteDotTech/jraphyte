"""Query-independent fields and separately measured local candidate/rerank stages.

No known target enters candidate generation. OCR/review fields aid discovery only;
none authorizes an abstract request or a graph write.
"""
from __future__ import annotations

import argparse
import math
import os
import re
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Callable, Sequence
from trace_gc.pdf_source_parallel_v4 import (SourceGeometry, canonical, digest_value, locate, normalize,
    style, validate_lines, validate_source_spans, verify_source_geometry_policy)
from trace_gc.pdf_structure_parallel_v4 import (METADATA_START, VERSION as ASSESSMENT_VERSION,
    _author_like, _boundary_evidence, _compose_section_spans, _role_rejected, verify_assessment,
    verify_interior_footnote_exclusion)
from .adapters import conversion_state
from .common import child, data_root, digest, read, write_once
from .metrics import ranking_metrics

BOILERPLATE = re.compile(r"^(?:graphical\s+abstract|abstract|highlights?|key\s+points|contents|table\s+of\s+contents|executive\s+summary|cover|original\s+article|research\s+article|introduction)\s*[.:]?$", re.I)
TITLE_POLICY_VERSION = "native-title-runs-v2"
AFFILIATION_WORD = re.compile(r"\b(?:university|laboratory|department|institute|academy|school|college)\b", re.I)
INSTITUTION_TITLE_START = re.compile(r"^(?:University|Department|Institute|School|Laboratory|College)\s+(?!(?:of|for|at)\b)\S+.*:\s+\S+", re.I)


def _title_like(text: str) -> bool:
    text = normalize(text)
    metadata = METADATA_START.match(text) and not INSTITUTION_TITLE_START.match(text)
    return bool(12 <= len(text) <= 600 and not BOILERPLATE.fullmatch(text) and
                not metadata and not _author_like(text) and
                not re.search(r"@|arXiv:|^(?:preprint|draft version|running title|prepared for)\b", text, re.I) and
                len(re.findall(r"(?<!\b[A-Z])[.!?]\s+[A-Z]", text)) < 2)


def _title_runs(block: list[dict]) -> list[list[dict]]:
    """Keep source lines intact when small leading metadata shares a PDF block.

    PDF text blocks are layout artifacts: a classification line can be grouped
    with a larger title. Split only at a visible style and role boundary, and
    retain the original line IDs for the candidate provenance.
    """
    if len(block) < 2:
        return [block]
    prefix = 0
    while prefix < len(block)-1 and METADATA_START.match(normalize(block[prefix]["text"])):
        prefix += 1
    if not prefix:
        return [block]
    metadata_size = max(style(line).get("size", 0) for line in block[:prefix])
    following_size = style(block[prefix]).get("size", 0)
    if not metadata_size or following_size < metadata_size * 1.25:
        return [block]
    title_end = prefix+1
    while title_end < len(block) and style(block[title_end]).get("size", 0) >= following_size*.85:
        title_end += 1
    if not _title_like(" ".join(line["text"] for line in block[prefix:title_end])):
        return [block]
    runs = [block[:prefix], block[prefix:title_end]]
    if title_end < len(block):
        runs.append(block[title_end:])
    return runs


def _affiliation_linked_author(block: dict, following: dict | None) -> bool:
    """Require both small inline markers and a following marked affiliation."""
    if not following or len(block["lines"]) != 1:
        return False
    line = block["lines"][0]
    spans = line.get("spans", [])
    main_size = style(line).get("size", 0)
    if not main_size:
        return False
    small = [normalize(s.get("text", "")) for s in spans
             if s.get("size", main_size) <= .75 * main_size]
    markers = [s.lstrip(",").casefold() for s in small if re.fullmatch(r"[a-z]|,?\d{1,2}", s, re.I)]
    next_text = following["text"]
    marker = re.match(r"^([a-z]|\d{1,2})(?=[A-Z][a-z]+|\s+(?:Department|University|Institute|School|Laboratory|College)\b)", next_text)
    return (len(markers) >= 2 and marker is not None and
            marker.group(1).casefold() in markers and
            bool(AFFILIATION_WORD.search(next_text[:80])))


def verify_source_bound_assessment(assessment: dict, native: list[dict], *, page_size: list,
                                   source_sha256: str, page_sha256: str,
                                   source_geometry: SourceGeometry | None = None) -> None:
    """Verify the seal, source identity and unique native span for any assessment state."""
    if not isinstance(assessment,dict):
        raise ValueError("abstract_assessment_record_required")
    verify_assessment(assessment)
    if (assessment.get("schema_version") != 3 or
            assessment.get("extractor_version") != ASSESSMENT_VERSION or
            assessment.get("status") not in {"complete","partial","absent","uncertain","error","truncated"} or
            type(assessment.get("proposal")) is not bool):
        raise ValueError("unsupported_abstract_assessment_version_or_state")
    if (assessment.get("source_sha256") != source_sha256 or
            assessment.get("page_sha256") != page_sha256 or
            assessment.get("physical_page") != 1 or
            assessment.get("page_size") != page_size):
        raise ValueError("abstract_field_source_mismatch")
    verify_source_geometry_policy(assessment.get("source_geometry_policy"), source_geometry,
                                  source_sha256=source_sha256,native_sha256=digest_value(native))
    if "interior_footnote_exclusion" in assessment:
        # Replays the unique unsplit parent and exact source-owned deletion;
        # arbitrary rewritten text or caller-supplied joiners are not accepted.
        verify_interior_footnote_exclusion(assessment, native, source_geometry=source_geometry)
        return
    if not assessment.get("proposal"):
        return
    if (assessment.get("status") != "complete" or
            assessment.get("complete_candidate") is not True or
            assessment.get("transcription") != "native_pdf" or
            not assessment.get("spans") or
            not assessment.get("closing_boundary")):
        raise ValueError("abstract_field_requires_complete_native_proposal")
    try:
        validate_source_spans(assessment["spans"],native)
    except (KeyError,TypeError,ValueError) as exc:
        raise ValueError("abstract_field_native_spans_mismatch") from exc
    if "\n".join(span["text"] for span in assessment["spans"]) != assessment.get("text"):
        raise ValueError("abstract_field_text_not_source_spans")
    alignment = assessment.get("source_alignment")
    if isinstance(alignment, dict) and alignment.get("method") == "source_owned_monotone_paragraph_groups":
        _verify_source_owned_paragraph_groups(assessment, native, source_geometry)
        return
    relocated=locate(assessment["text"],native,source_geometry=source_geometry)
    saved_positions=[(str(s["line_id"]),s["start"],s["end"]) for s in assessment["spans"]]
    located_positions=[(str(s["line_id"]),s["start"],s["end"]) for s in relocated["spans"]]
    if relocated["status"] != "located" or saved_positions != located_positions:
        raise ValueError("abstract_field_spans_not_unique_or_current")


def _verify_source_owned_paragraph_groups(assessment: dict, native: list[dict],
                                          source_geometry: SourceGeometry | None) -> None:
    """Replay each source-owned paragraph when another PDF column interleaves native lines."""
    if source_geometry is None:
        raise ValueError("abstract_paragraph_groups_require_pdf_geometry")
    refs = assessment.get("region_refs")
    ownership = assessment.get("region_ownership")
    proof = assessment.get("source_alignment")
    groups = proof.get("paragraph_groups") if isinstance(proof, dict) else None
    if (not isinstance(refs, list) or len(refs) < 2 or len(refs) != len(set(refs)) or
            not isinstance(ownership, list) or not isinstance(groups, list) or
            len(groups) != len(refs) or proof.get("status") != "located" or
            proof.get("column_change") is not False):
        raise ValueError("abstract_paragraph_group_proof_invalid")
    included = [entry for entry in ownership if isinstance(entry, dict) and
                entry.get("decision") == "included"]
    if [entry.get("ref") for entry in included] != refs:
        raise ValueError("abstract_paragraph_group_ownership_mismatch")
    current_entries = []
    for ref, entry, group in zip(refs, included, groups):
        spans = entry.get("source_spans")
        if (not isinstance(spans, list) or not spans or not isinstance(group, dict) or
                group.get("ref") != ref):
            raise ValueError("abstract_paragraph_group_source_missing")
        try:
            validate_source_spans(spans, native)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("abstract_paragraph_group_source_mismatch") from exc
        replay = locate("\n".join(span["text"] for span in spans), native,
                        source_geometry=source_geometry)
        positions = lambda source: [(str(span["line_id"]), span["start"], span["end"])
                                    for span in source]
        if (replay["status"] != "located" or replay.get("column_change") or
                positions(replay["spans"]) != positions(spans)):
            raise ValueError("abstract_paragraph_group_not_unique_or_current")
        saved = entry.get("source_alignment")
        if not isinstance(saved, dict) or saved != {
                key: value for key, value in replay.items() if key not in {"text", "spans"}}:
            raise ValueError("abstract_paragraph_group_alignment_changed")
        current_entries.append({**entry, "source_alignment": replay})
    composed = _compose_section_spans({"alignment_failure": None, "refs": refs,
        "ownership": current_entries, "text": assessment["text"]}, native)
    positions = lambda source: [(str(span["line_id"]), span["start"], span["end"])
                                for span in source]
    if (composed is None or positions(composed["spans"]) != positions(assessment["spans"]) or
            composed["text"] != assessment["text"] or
            [group["ref"] for group in composed["paragraph_groups"]] != refs or
            [group["bbox"] for group in composed["paragraph_groups"]] !=
            [group.get("bbox") for group in groups]):
        raise ValueError("abstract_paragraph_groups_not_source_owned")
    boundary = assessment.get("closing_boundary")
    if (not isinstance(boundary, dict) or
            boundary.get("kind") not in {"metadata_or_nonabstract_region", "body_section"} or
            boundary.get("ref") in refs or not boundary.get("source_spans") or
            boundary.get("source_location") != "located"):
        raise ValueError("abstract_paragraph_group_closure_missing")
    try:
        validate_source_spans(boundary["source_spans"], native)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("abstract_paragraph_group_closure_mismatch") from exc
    last = composed["paragraph_groups"][-1]["bbox"]
    closure_spans = boundary["source_spans"]
    first_boundary_y = min(span["bbox"][1] for span in closure_spans)
    if first_boundary_y < last[3] - 2:
        raise ValueError("abstract_paragraph_group_closure_before_abstract")
    label = boundary.get("label", "")
    box = [min(span["bbox"][0] for span in closure_spans), first_boundary_y,
           max(span["bbox"][2] for span in closure_spans),
           max(span["bbox"][3] for span in closure_spans)]
    width = min(box[2] - box[0], last[2] - last[0])
    horizontal_overlap = max(0, min(box[2], last[2]) - max(box[0], last[0]))
    source_text = " ".join(span["text"] for span in closure_spans)
    scope = boundary.get("source_text_scope", "whole_region")
    if (not isinstance(label, str) or not label.strip() or
            scope not in {"whole_region", "metadata_label", "legal_footer_statement"} or
            (scope == "whole_region" and
             normalize(source_text)[:120] != normalize(label)[:120]) or
            (scope != "whole_region" and not normalize(label).startswith(normalize(source_text))) or
            width <= 0 or horizontal_overlap < .8 * width):
        raise ValueError("abstract_paragraph_group_closure_not_source_owned")
    region_boxes = boundary.get("region_boxes") or [box]
    region = {"text": source_text if scope == "whole_region" else label,
              "boxes": region_boxes, "bbox": [min(b[0] for b in region_boxes),
              min(b[1] for b in region_boxes), max(b[2] for b in region_boxes),
              max(b[3] for b in region_boxes)], "ref": boundary["ref"],
              "tree_order": boundary.get("tree_order", 0)}
    replay = _boundary_evidence(region, native, boundary["kind"], source_geometry)
    if (replay.get("source_location") != "located" or
            [(str(s["line_id"]), s["start"], s["end"]) for s in replay["source_spans"]] !=
            [(str(s["line_id"]), s["start"], s["end"]) for s in closure_spans] or
            replay.get("source_text_scope") != scope):
        raise ValueError("abstract_paragraph_group_closure_policy_changed")
    closure_ids = {str(span["line_id"]) for span in closure_spans}
    for line in native:
        line_box = line["bbox"]
        if (str(line["id"]) not in closure_ids and line["text"].strip() and
                line_box[1] >= last[3] - 2 and line_box[3] <= first_boundary_y + 2 and
                max(0, min(line_box[2], last[2]) - max(line_box[0], last[0])) >=
                .8 * min(line_box[2] - line_box[0], last[2] - last[0])):
            raise ValueError("abstract_paragraph_group_unowned_trailing_line")
    if boundary["kind"] == "metadata_or_nonabstract_region" and not _role_rejected(label):
        raise ValueError("abstract_paragraph_group_metadata_closure_not_role_bounded")


def extract_fields(case_id: str, native: list[dict], *, page_size: list,
                   source_sha256: str, page_sha256: str, image_sha256: str | None = None,
                   abstract_assessment: dict | None = None, reviewed_title: dict | None = None,
                   ocr_cache: dict | None = None,
                   source_geometry: SourceGeometry | None = None) -> dict:
    native=validate_lines(native,page_size)
    groups = defaultdict(list)
    for line in native:
        groups[line.get("block_id", str(line["id"]))].append(line)
    blocks = []
    for source_block in groups.values():
        source_block.sort(key=lambda x: (x["bbox"][1], x["bbox"][0]))
        for block in _title_runs(source_block):
            text = normalize(" ".join(x["text"] for x in block))
            weights = [(style(x), len(canonical(x["text"]))) for x in block]
            total = sum(n for s, n in weights if s)
            size = sum(s.get("size", 0)*n for s, n in weights)/total if total else 0
            blocks.append({"text": text, "size": size, "y": min(x["bbox"][1] for x in block),
                           "line_ids": [x["id"] for x in block], "lines": block})
    blocks.sort(key=lambda x: x["y"])
    result = {"id": case_id, "source_sha256": source_sha256, "page_sha256": page_sha256,
              "physical_page": 1, "title": "", "abstract": "", "body": "\n".join(x["text"] for x in native),
              "field_provenance": {}, "retrieval_only": True, "eligible_for_jev": False}
    non_title_roles = set()
    for i, block in enumerate(blocks[:-1]):
        if _affiliation_linked_author(block, blocks[i+1]):
            non_title_roles.update((i,i+1))
    eligible = [b for i,b in enumerate(blocks) if i not in non_title_roles and _title_like(b["text"])]
    if eligible:
        # Unlike v2, a boilerplate heading cannot win merely by being largest;
        # title candidates below 45% of the page remain available.
        winner = max(eligible, key=lambda b: (b["size"], -b["y"]))
        result["title"] = winner["text"]
        result["field_provenance"]["title"] = {"kind": "native_title_candidate", "line_ids": winner["line_ids"],
                                                 "source_reviewed": False, "policy_version": TITLE_POLICY_VERSION,
                                                 "source_line_spans": [
                                                     {"line_id": line["id"], "bbox": line["bbox"],
                                                      "spans": [{k: span[k] for k in ("start", "end", "bbox", "font", "size") if k in span}
                                                                for span in line.get("spans", [])]}
                                                     for line in winner["lines"]]}
    if reviewed_title:
        if (reviewed_title.get("source_sha256") != source_sha256 or reviewed_title.get("page_sha256") != page_sha256 or
                reviewed_title.get("image_sha256") != image_sha256 or not image_sha256 or
                reviewed_title.get("reviewer_kind") not in {"human", "assistant"} or not reviewed_title.get("reviewer") or
                reviewed_title.get("source_reviewed") is not True or not _title_like(reviewed_title.get("text", ""))):
            raise ValueError("reviewed_title_missing_source_binding")
        result["title"] = reviewed_title["text"]
        result["field_provenance"]["title"] = {"kind": "source_image_reviewed_title", "reviewer_kind": reviewed_title["reviewer_kind"],
                                                    "reviewer": reviewed_title["reviewer"], "receipt_sha256": digest_value(reviewed_title)}
    if ocr_cache:
        if ocr_cache.get("source_sha256") != source_sha256 or ocr_cache.get("page_sha256") != page_sha256:
            raise ValueError("ocr_fields_not_bound_to_source")
        if conversion_state(ocr_cache) == "success":
            text = ocr_cache.get("raw_text", "")
            if not result["body"].strip():
                result["body"] = text
                result["field_provenance"]["body"] = {"kind": "local_ocr_candidate", "source_reviewed": False,
                                                      "cache_sha256": digest_value(ocr_cache), "coordinate_source": "not_supplied"}
            if not result["title"] and _title_like(ocr_cache.get("title", "")):
                result["title"] = ocr_cache["title"]
                result["field_provenance"]["title"] = {"kind": "local_ocr_title_candidate", "source_reviewed": False}
    if abstract_assessment is not None:
        verify_source_bound_assessment(abstract_assessment,native,page_size=page_size,
                                       source_sha256=source_sha256,page_sha256=page_sha256,
                                       source_geometry=source_geometry)
    if abstract_assessment and abstract_assessment.get("proposal"):
        result["abstract"] = abstract_assessment["text"]
        result["field_provenance"]["abstract"] = {"kind": "source_located_selector_proposal", "source_reviewed": False,
                                                 "assessment_sha256": abstract_assessment["assessment_sha256"]}
    result["searchable"] = any(result[k].strip() for k in ("title", "abstract", "body"))
    result["field_state"] = "candidate_fields" if result["searchable"] else "needs_local_ocr_or_source_review"
    result["fields_sha256"] = digest_value(result)
    return result


def tokens(text: str) -> list[str]:
    return re.findall(r"\w+", text.casefold())


class BM25:
    """Deterministic local BM25 index. Empty fields do not receive padding hits."""
    def __init__(self, values: dict[str, str], *, k1=1.2, b=.75):
        if not 0 <= b <= 1 or k1 <= 0:
            raise ValueError("invalid_bm25_parameters")
        self.ids = sorted(values)
        self.tf = {k: Counter(tokens(values[k])) for k in self.ids}
        self.lengths = {k: sum(v.values()) for k, v in self.tf.items()}
        self.average = sum(self.lengths.values())/len(self.ids) if self.ids else 0
        self.df = Counter(t for value in self.tf.values() for t in value)
        self.k1, self.b = k1, b

    def scores(self, query: str) -> dict[str, float]:
        output = {}
        for key in self.ids:
            score = 0.0
            for term in set(tokens(query)):
                frequency = self.tf[key][term]
                if not frequency or not self.average:
                    continue
                idf = math.log(1+(len(self.ids)-self.df[term]+.5)/(self.df[term]+.5))
                denominator = frequency+self.k1*(1-self.b+self.b*self.lengths[key]/self.average)
                score += idf*frequency*(self.k1+1)/denominator
            output[key] = score
        return output

    def rank(self, query: str) -> list[str]:
        return ordered_scores(self.scores(query))


def ordered_scores(scores: dict[str, float]) -> list[str]:
    if any(not math.isfinite(v) for v in scores.values()):
        raise ValueError("nonfinite_retrieval_score")
    return sorted((k for k, v in scores.items() if v > 0), key=lambda k: (-scores[k], k))


def candidate_pool(bm25f: Sequence[str], specter2: Sequence[str], bm25_page: Sequence[str], *, k=50) -> list[str]:
    """Union includes full-page lexical candidates; deliberately no target input."""
    if not isinstance(k, int) or k <= 0:
        raise ValueError("invalid_candidate_depth")
    output, seen = [], set()
    for ranking in (bm25f, specter2, bm25_page):
        if len(ranking) != len(set(ranking)):
            raise ValueError("duplicate_id_in_candidate_ranking")
        for key in ranking[:k]:
            if key not in seen:
                seen.add(key)
                output.append(key)
    return output


def rerank_pool(query: str, fields: dict[str, dict], pool: list[str], scorer: Callable) -> list[str]:
    if len(pool) != len(set(pool)) or any(k not in fields for k in pool):
        raise ValueError("invalid_candidate_pool")
    pairs = [(query, "\n".join(fields[k].get(f, "") for f in ("title", "abstract", "body"))) for k in pool]
    scores = list(scorer(pairs)) if pairs else []
    if len(scores) != len(pool) or any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in scores):
        raise ValueError("reranker_score_contract_failed")
    return [pool[i] for i in sorted(range(len(pool)), key=lambda i: (-scores[i], i))]


def local_cross_encoder(model_directory: Path, expected_files: dict) -> Callable:
    model_directory = Path(model_directory).resolve()
    if not model_directory.is_dir() or not expected_files:
        raise ValueError("pinned_local_model_directory_and_hashes_required")
    actual_files={p.relative_to(model_directory).as_posix() for p in model_directory.rglob("*") if p.is_file()}
    if set(expected_files)!=actual_files:
        raise ValueError("local_model_manifest_must_cover_entire_snapshot")
    if any(p.is_symlink() for p in model_directory.rglob("*")):
        raise ValueError("local_model_symlinks_not_allowed")
    if any(Path(name).suffix.lower() in {".py", ".bin", ".pt", ".pth", ".pkl", ".pickle", ".ckpt"} for name in actual_files):
        raise ValueError("local_model_executable_or_pickle_weights_not_allowed")
    if "config.json" not in actual_files or not any(name.endswith(".safetensors") for name in actual_files):
        raise ValueError("local_safetensors_snapshot_required")
    if not ({"tokenizer.json", "vocab.txt", "spiece.model"} & actual_files):
        raise ValueError("local_tokenizer_required")
    configuration=read(model_directory/"config.json")
    if configuration.get("auto_map") or configuration.get("num_labels", len(configuration.get("id2label", {}))) != 1:
        raise ValueError("local_single_logit_no_remote_code_model_required")
    for relative, sha in expected_files.items():
        if digest(child(model_directory, relative)) != sha:
            raise ValueError("local_model_hash_mismatch")
    # Fail closed instead of silently downloading missing model files.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    from sentence_transformers import CrossEncoder
    model = CrossEncoder(str(model_directory), device="cpu", local_files_only=True, trust_remote_code=False, token=False)
    def score(pairs):
        return [float(x) for x in model.predict(pairs, show_progress_bar=False)]
    score.offline_receipt={"model_file_hashes":dict(expected_files),"local_files_only":True}
    return score


def normalize_queries(value) -> list[dict]:
    """Accept published target->text maps and the frozen query_id/text schema."""
    if isinstance(value, dict):
        if "queries" in value:
            value=value["queries"]
        elif all(isinstance(text,str) for text in value.values()):
            value=[{"id":f"mapped-{i:04d}","query":text,"target_id":target}
                   for i,(target,text) in enumerate(sorted(value.items()))]
        else:
            raise ValueError("unsupported_query_mapping")
    if not isinstance(value,list):raise ValueError("expected_query_list")
    output=[]
    for row in value:
        if "query" in row and "text" in row and row["query"]!=row["text"]:
            raise ValueError("conflicting_query_text_aliases")
        if "id" in row and "query_id" in row and str(row["id"])!=str(row["query_id"]):
            raise ValueError("conflicting_query_identifier_aliases")
        key=row.get("id",row.get("query_id"));text=row.get("query",row.get("text"));target=row.get("target_id")
        if key is None or not isinstance(text,str) or not text.strip() or not isinstance(target,str) or not target:
            raise ValueError("query_identifier_text_and_target_required")
        output.append({"id":str(key),"query":text,"target_id":target})
    return output


def evaluate(fields: list[dict], queries: list[dict], *, dense_cache: dict | None = None,
             scorer: Callable | None = None, k=50, page_channel: bool = True) -> dict:
    if type(page_channel) is not bool:
        raise ValueError('page_channel_requires_boolean')
    if (dense_cache is not None and dense_cache.get('binding_version')=='ranking-inputs-v2' and
            isinstance(queries,dict) and 'queries' not in queries):
        raise ValueError('v2_dense_cache_requires_explicit_query_identifiers')
    queries=normalize_queries(queries)
    ranking_inputs=[{'id':q['id'],'query':q['query']} for q in queries]
    ranking_inputs_sha256=digest_value(ranking_inputs)
    evaluation_labels_sha256=digest_value([{'id':q['id'],'target_id':q['target_id']} for q in queries])
    total_start=time.perf_counter()
    ids = [x["id"] for x in fields]
    if len(ids) != len(set(ids)) or len(queries) != len({str(q["id"]) for q in queries}):
        raise ValueError("duplicate_document_or_query_id")
    by_id = {x["id"]: x for x in fields}
    fingerprint = digest_value(fields)
    dense_binding='not_run'
    if dense_cache is not None:
        if dense_cache.get("fields_sha256") != fingerprint:
            raise ValueError("dense_embeddings_stale_after_field_changes")
        if dense_cache.get('binding_version') not in (None,'ranking-inputs-v2'):
            raise ValueError('unsupported_dense_cache_binding_version')
        if dense_cache.get('binding_version')=='ranking-inputs-v2':
            query_bound=dense_cache.get('ranking_inputs_sha256')==ranking_inputs_sha256
            dense_binding='ranking_inputs_only_v2'
            if (dense_cache.get('ranking_sha256')!=digest_value(dense_cache.get('rankings')) or
                    dense_cache.get('document_ids_sha256')!=digest_value(ids) or
                    dense_cache.get('query_ids_sha256')!=digest_value([q['id'] for q in queries]) or
                    dense_cache.get('target_ids_used_for_ranking') is not False or
                    not isinstance(dense_cache.get('top_k'),int) or dense_cache['top_k']<k):
                raise ValueError('dense_cache_ranking_provenance_invalid')
        else:
            query_bound=dense_cache.get('queries_sha256')==digest_value(queries)
            dense_binding='legacy_target_bound_v1'
        if (not query_bound or dense_cache.get("channel") != "specter2" or
                not re.fullmatch(r"[a-f0-9]{40}", dense_cache.get("model_revision", "")) or
                set(dense_cache.get("rankings", {})) != {str(q["id"]) for q in queries}):
            raise ValueError("dense_cache_query_or_model_binding_invalid")
    indexes = {field: BM25({k: x.get(field, "") for k, x in by_id.items()}) for field in ("title", "abstract", "body")}
    whole = BM25({k: "\n".join(x.get(f, "") for f in ("title", "abstract", "body")) for k, x in by_id.items()}) if page_channel else None
    pools, rankings, candidate_receipts = {}, {}, {}
    stage_hits={'field_weighted_bm25_parallel_v4':0,'specter2':0,'bm25_page':0,'union':0}
    before = time.perf_counter()
    index_seconds=before-total_start
    candidate_seconds=rerank_seconds=0.0
    for q in queries:
        # Only query text/id, never target_id, flows into ranking code.
        candidate_start=time.perf_counter()
        qid, text = str(q["id"]), q["query"]
        components = {field: index.scores(text) for field, index in indexes.items()}
        field_scores = {key: 3*components["title"][key]+2*components["abstract"][key]+.25*components["body"][key] for key in by_id}
        lexical, page = ordered_scores(field_scores), whole.rank(text) if whole is not None else []
        dense = dense_cache.get("rankings", {}).get(qid, []) if dense_cache else []
        if len(dense)!=len(set(dense)) or any(key not in by_id for key in dense):
            raise ValueError("dense_cache_contains_unknown_document")
        pool = candidate_pool(lexical, dense, page, k=k)
        target=q['target_id']
        stage_hits['field_weighted_bm25_parallel_v4']+=target in lexical[:k]
        if dense_cache is not None:stage_hits['specter2']+=target in dense[:k]
        stage_hits['bm25_page']+=target in page[:k]
        stage_hits['union']+=target in pool
        pools[qid] = pool
        candidate_seconds+=time.perf_counter()-candidate_start
        rerank_start=time.perf_counter()
        rankings[qid] = rerank_pool(text, by_id, pool, scorer) if scorer else pool
        rerank_seconds+=time.perf_counter()-rerank_start if scorer else 0.0
        candidate_receipts[qid] = {"field_weighted_bm25_parallel_v4_topk": lexical[:k], "specter2_topk": dense[:k], "bm25_page_topk": page[:k],
                                   "pool": pool, "pool_sha256": digest_value(pool)}
    result = ranking_metrics(rankings, pools, queries)
    stage_metrics={name:({'status':'NOT_RUN'} if (name=='specter2' and dense_cache is None or name=='bm25_page' and not page_channel) else
                         {'status':'MEASURED','hits':hits,'queries':len(queries),
                          'recall':hits/len(queries) if queries else None})
                   for name,hits in stage_hits.items()}
    result.update(fields_sha256=fingerprint, fields_count=len(fields), searchable_fields=sum(bool(x.get("searchable", True)) for x in fields),
                  ranking_inputs_sha256=ranking_inputs_sha256,evaluation_labels_sha256=evaluation_labels_sha256,
                  dense_cache_binding=dense_binding,ranking_outputs_sha256=digest_value(rankings),
                  dense_cache_sha256=digest_value(dense_cache) if dense_cache is not None else None,
                  candidate_depth=k,candidate_stage_metrics=stage_metrics,page_channel_enabled=page_channel,
                  stage="supplied_scorer" if scorer else "candidate_order_only_not_reranked",
                  dense_stage="supplied_bound_cache" if dense_cache else "not_run",
                  runtime_seconds=time.perf_counter()-total_start, index_seconds=index_seconds, candidate_seconds=candidate_seconds, rerank_seconds=rerank_seconds,
                  new_paid_api_calls=0 if scorer is None or getattr(scorer,"offline_receipt",None) else None,
                  measured_api_spend_usd=0 if scorer is None or getattr(scorer,"offline_receipt",None) else None,
                  candidates=candidate_receipts)
    return result


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-root", required=True)
    p.add_argument("--fields", required=True)
    p.add_argument("--queries", required=True)
    p.add_argument("--dense-cache")
    p.add_argument("--model-directory")
    p.add_argument("--model-manifest")
    p.add_argument("--output", required=True)
    a = p.parse_args()
    root = data_root(a.data_root)
    values = read(child(root, a.fields))
    fields = values["fields"] if isinstance(values, dict) else values
    query_values = read(child(root, a.queries))
    queries = query_values["queries"] if isinstance(query_values, dict) else query_values
    if bool(a.model_directory) != bool(a.model_manifest):
        p.error("--model-directory and --model-manifest must be supplied together")
    # All snapshot files are pinned; the revision is provenance, not an inferred proof.
    model_manifest=read(child(root,a.model_manifest)) if a.model_directory else None
    if model_manifest and not re.fullmatch(r"[a-f0-9]{40}", model_manifest.get("model_revision", "")):
        p.error("model manifest requires a 40-hex model_revision")
    scorer = local_cross_encoder(Path(a.model_directory), model_manifest["files"]) if a.model_directory else None
    result = evaluate(fields, queries, dense_cache=read(child(root, a.dense_cache)) if a.dense_cache else None, scorer=scorer)
    if model_manifest:
        result["model"]={"revision":model_manifest["model_revision"],"manifest_sha256":digest_value(model_manifest),"local_files_only":True}
        result["stage"]="local_cross_encoder"
    write_once(child(root, a.output), result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
