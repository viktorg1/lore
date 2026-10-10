"""Request validation helpers and the one error type the API raises."""
from __future__ import annotations


class ApiError(Exception):
    """A failure that maps to an HTTP status and a message for the page."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def text_field(body: dict, key: str, *, required: bool = True, maxlen: int = 4096) -> str:
    v = body.get(key)
    if v is None or v == "":
        if required:
            raise ApiError(400, f"{key} is required")
        return ""
    if not isinstance(v, str) or "\0" in v or len(v) > maxlen:
        raise ApiError(400, f"bad {key}")
    return v.strip()


def number_field(body: dict, key: str, default, kind, lo, hi):
    v = body.get(key, default)
    try:
        v = kind(v)
    except (TypeError, ValueError):
        raise ApiError(400, f"{key} must be a number")
    if not lo <= v <= hi:
        raise ApiError(400, f"{key} must be between {lo} and {hi}")
    return v
