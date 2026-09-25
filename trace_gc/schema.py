"""Offline-only schema registry: never resolve untrusted remote $refs."""
from __future__ import annotations
from functools import lru_cache
from pathlib import Path
from typing import Any
from jsonschema import Draft202012Validator, FormatChecker
from .canonical import load
from .errors import ContractError, require

ROOT = Path(__file__).resolve().parents[1]

@lru_cache(maxsize=64)
def validator(name: str) -> Draft202012Validator:
    require(name.replace("-", "").replace("_", "").isalnum(), "SCHEMA_NAME", "invalid name")
    path = ROOT / "schemas" / "runtime" / f"{name}.schema.json"
    if not path.is_file():
        path = Path(__file__).resolve().parent / "data" / "schemas" / f"{name}.schema.json"
    require(path.is_file(), "SCHEMA_NAME", name)
    schema = load(path)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())

def validate(name: str, value: Any) -> None:
    error = next(validator(name).iter_errors(value), None)
    if error:
        raise ContractError("SCHEMA_ERROR", error.message, path=f"{name}/" + "/".join(map(str, error.absolute_path)))
