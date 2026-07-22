"""Minimal reference parser for EAT Inline 0.3.2."""

from __future__ import annotations

from dataclasses import dataclass, asdict
import re
from typing import Iterable

VERSION = "0.3.2"
IDENTIFIER = r"[A-Za-z_][A-Za-z0-9_]*"
REFERENCE_RE = re.compile(rf"@@EAT (?P<type>{IDENTIFIER}):(?P<key>{IDENTIFIER})@@")


@dataclass(frozen=True)
class Reference:
    type: str
    key: str
    raw: str
    start: int
    end: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def parse_references(text: str) -> list[Reference]:
    """Extract all syntactically valid EAT Inline references from text."""
    return [
        Reference(
            type=match.group("type"),
            key=match.group("key"),
            raw=match.group(0),
            start=match.start(),
            end=match.end(),
        )
        for match in REFERENCE_RE.finditer(text)
    ]


def parse(text: str) -> dict[str, object]:
    """Return a small, storage-neutral representation of written references."""
    return {
        "version": VERSION,
        "references": [item.to_dict() for item in parse_references(text)],
    }


def validate_reference(value: str) -> tuple[bool, str]:
    """Validate one complete reference.

    Diagnostic labels are implementation conveniences, not part of the core
    EAT Inline syntax.
    """
    if REFERENCE_RE.fullmatch(value):
        return True, "valid"
    if not value.startswith("@@EAT "):
        return False, "incomplete_opening_marker"
    if not value.endswith("@@"):
        return False, "missing_closing_marker"
    body = value[6:-2]
    if ":" not in body:
        return False, "missing_separator"
    type_name, key = body.split(":", 1)
    if not type_name:
        return False, "missing_type"
    if not key:
        return False, "missing_key"
    return False, "invalid_identifier"


def validate_many(values: Iterable[str]) -> list[tuple[bool, str]]:
    return [validate_reference(value) for value in values]
