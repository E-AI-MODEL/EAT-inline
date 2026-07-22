"""Minimal reference parser for EAT Inline 0.3.1."""

from __future__ import annotations

from dataclasses import dataclass, asdict
import re
from typing import Iterable

VERSION = "0.3.1"
IDENTIFIER = r"[A-Za-z_][A-Za-z0-9_]*"
REFERENCE_RE = re.compile(rf"@@EAT (?P<type>{IDENTIFIER}):(?P<key>{IDENTIFIER})@@")
TLDR_RE = re.compile(r"@@EAT tldr:\r?\n(?P<content>.*?)\r?\n@@", re.DOTALL)

CORE_TYPES = {
    "person",
    "organisation",
    "location",
    "document",
    "project",
    "event",
    "concept",
}

EXTENDED_TYPES = {
    "product",
    "system",
    "dataset",
    "publication",
    "website",
    "course",
    "team",
    "policy",
    "law",
    "method",
}


@dataclass(frozen=True)
class Reference:
    type: str
    key: str
    raw: str
    start: int
    end: int
    status: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class TldrBlock:
    content: str
    raw: str
    start: int
    end: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def registry_status(type_name: str) -> str:
    if type_name in CORE_TYPES:
        return "valid-core"
    if type_name in EXTENDED_TYPES:
        return "valid-extended"
    return "valid-extension"


def parse_references(text: str) -> list[Reference]:
    return [
        Reference(
            type=match.group("type"),
            key=match.group("key"),
            raw=match.group(0),
            start=match.start(),
            end=match.end(),
            status=registry_status(match.group("type")),
        )
        for match in REFERENCE_RE.finditer(text)
    ]


def parse_tldr_blocks(text: str) -> list[TldrBlock]:
    return [
        TldrBlock(
            content=match.group("content"),
            raw=match.group(0),
            start=match.start(),
            end=match.end(),
        )
        for match in TLDR_RE.finditer(text)
    ]


def parse(text: str) -> dict[str, object]:
    return {
        "version": VERSION,
        "references": [item.to_dict() for item in parse_references(text)],
        "tldr": [item.to_dict() for item in parse_tldr_blocks(text)],
    }


def validate_reference(value: str) -> tuple[bool, str]:
    if REFERENCE_RE.fullmatch(value):
        return True, "valid"
    if not value.startswith("@@EAT "):
        return False, "E001 incomplete_opening_marker"
    if not value.endswith("@@"):
        return False, "E006 missing_closing_marker"
    body = value[6:-2]
    if ":" not in body:
        return False, "E003 missing_separator"
    type_name, key = body.split(":", 1)
    if not type_name:
        return False, "E002 missing_type"
    if not key:
        return False, "E004 missing_key"
    if not re.fullmatch(IDENTIFIER, type_name) or not re.fullmatch(IDENTIFIER, key):
        return False, "E005 invalid_identifier"
    return False, "E005 invalid_identifier"


def validate_many(values: Iterable[str]) -> list[tuple[bool, str]]:
    return [validate_reference(value) for value in values]
