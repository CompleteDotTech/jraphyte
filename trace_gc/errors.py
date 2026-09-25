"""Stable machine-readable failures at all public trust boundaries."""
from __future__ import annotations
from functools import wraps
from typing import Any, Callable

class ContractError(ValueError):
    def __init__(self, code: str, detail: str = "", *, path: str = ""):
        self.code, self.detail, self.path = code, detail, path
        super().__init__(f"{code}: {path + ': ' if path else ''}{detail}")
    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail, "path": self.path}

def require(condition: bool, code: str, detail: str = "", *, path: str = "") -> None:
    if not condition:
        raise ContractError(code, detail, path=path)

def boundary(function: Callable[..., Any]) -> Callable[..., Any]:
    """Normalize malformed inputs, without disguising programming/system failures."""
    @wraps(function)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        try:
            return function(*args, **kwargs)
        except ContractError:
            raise
        except (KeyError, TypeError, IndexError, AttributeError, OverflowError, UnicodeError) as exc:
            raise ContractError("MALFORMED_INPUT", str(exc)) from exc
    return wrapped
