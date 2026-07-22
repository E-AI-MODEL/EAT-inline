#!/usr/bin/env python3
"""Check repository text for version drift and retired terminology."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".md", ".txt", ".py", ".toml", ".json", ".yml", ".yaml", ".abnf"}
REQUIRED = ("Hans Visser", "EAI Analyse & Advies", "0.3.2")
FORBIDDEN = (
    "Nick Milo",
    "Nick_Milo",
    "wikilink",
    "wiki link",
    "[[",
    "@@EAT tldr:",
    "TLDR block",
    "research baseline",
)
EXCLUDED = {ROOT / "scripts" / "check_docs.py"}


def iter_text_files():
    for path in ROOT.rglob("*"):
        if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES and path not in EXCLUDED:
            if ".git" not in path.parts and "benchmark/results" not in path.as_posix():
                yield path


def main() -> int:
    files = list(iter_text_files())
    combined = "\n".join(path.read_text(encoding="utf-8") for path in files)
    errors: list[str] = []

    for required in REQUIRED:
        if required not in combined:
            errors.append(f"required text missing: {required}")

    for path in files:
        text = path.read_text(encoding="utf-8")
        lowered = text.lower()
        for forbidden in FORBIDDEN:
            if forbidden.lower() in lowered:
                errors.append(f"retired term {forbidden!r} found in {path.relative_to(ROOT)}")

    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    if 'version = "0.3.2"' not in pyproject:
        errors.append("pyproject version is not 0.3.2")
    if "0.3.2" not in readme:
        errors.append("README does not mention version 0.3.2")
    if "EAT Inline has one construct" not in readme:
        errors.append("README does not declare the single-construct core")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(f"Documentation checks passed across {len(files)} text files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
