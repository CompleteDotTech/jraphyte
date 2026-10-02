"""Document-scope PDF page lineage on immutable source snapshots."""
from copy import deepcopy


def extend(schemas):
    source = schemas["source"]
    h = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
    s = {"type": "string", "minLength": 1}
    lineage = {
        "type": "object",
        "properties": {
            "version": {"const": "reviewed-native-pdf-page-v1"},
            "raw_document_sha256": h,
            "physical_page": {"type": "integer", "minimum": 1},
            "render_dpi": {"const": 144},
            "page_png_sha256": h,
            "native_text_sha256": h,
            "start": {"type": "integer", "minimum": 0},
            "end": {"type": "integer", "minimum": 1},
            "reviewer": s,
            "reviewer_kind": {"enum": ["assistant", "human"]},
            "reviewed_at": {"type": "string", "format": "date-time"},
            "checks": {"type": "object", "properties": {key: {"const": True} for key in
                ("source_identity", "reading_order", "boundaries", "notation")},
                "required": ["source_identity", "reading_order", "boundaries", "notation"],
                "additionalProperties": False},
        },
        "required": ["version", "raw_document_sha256", "physical_page", "render_dpi", "page_png_sha256",
            "native_text_sha256", "start", "end", "reviewer", "reviewer_kind", "reviewed_at", "checks"],
        "additionalProperties": False,
    }
    source["properties"]["page_lineage"] = deepcopy(lineage)
    source.setdefault("allOf", []).append({
        "if": {"properties": {"representation": {"const": "reviewed-native-pdf-page-v1"}}},
        "then": {"required": ["page_lineage"]},
        "else": {"not": {"required": ["page_lineage"]}},
    })
