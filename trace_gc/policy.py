"""Immutable policy identity. Publication mode is application-owned configuration."""
from __future__ import annotations
from typing import Any
from .catalog import Catalog
from .errors import require

def find_policy(catalog: Catalog, version: str) -> str:
    matches = [r["id"] for r in catalog.all("policy") if r["body"]["version"] == version]
    require(len(matches) == 1, "POLICY_IDENTITY", "exactly one immutable policy per version required")
    return matches[0]

def create_policy(catalog: Catalog, *, version: str, scope: str, population: str,
                  mode: str = "ANALYSIS_ONLY", allowed_modes: list[str] | None = None,
                  maximum_risk: str = "R5") -> str:
    from .plans import REQUIRED_CHECKS
    return catalog.put("policy", {"version": version, "mode": mode, "security_scope": scope,
        "population": population, "allowed_modes": allowed_modes or ["SYNTHETIC"],
        "maximum_risk": maximum_risk, "qualification_metric": "ERRORS_PER_ACCEPTED_ACTION",
        "required_checks": sorted(REQUIRED_CHECKS)})
