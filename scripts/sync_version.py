#!/usr/bin/env python3
"""Keep every version string in the repo equal to the one in pyproject.toml.

pyproject.toml is the single source of truth. This script stamps its version into:
  - server.json: the top-level "version" and every packages[] entry with registryType "pypi"
  - gemini-extension.json: "version"
  - manifest.json: the top-level "version" (Claude Desktop / MCPB)
  - diffbot_mcp/__init__.py: __version__

The JSON files are edited in place, one "version" value at a time, so hand-written
formatting (indentation, inline arrays, key order) survives untouched.

Usage:
  python scripts/sync_version.py          # rewrite the files to match pyproject.toml
  python scripts/sync_version.py --check  # exit 1 if any file disagrees (used in CI)
  python scripts/sync_version.py --print  # print the pyproject.toml version
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Iterator, NamedTuple

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ModuleNotFoundError:
        sys.exit("needs Python 3.11+, or `pip install tomli` on 3.10")

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
SERVER_JSON = ROOT / "server.json"
GEMINI_JSON = ROOT / "gemini-extension.json"
MANIFEST_JSON = ROOT / "manifest.json"
INIT_PY = ROOT / "diffbot_mcp" / "__init__.py"

# Matches one "version": "..." pair; group 2 is the value, which is what we rewrite.
JSON_VERSION_RE = re.compile(r'("version"\s*:\s*")([^"\\]*)(")')
INIT_VERSION_RE = re.compile(r'^__version__ = "([^"]*)"$', re.MULTILINE)


class Slot(NamedTuple):
    """One "version" value in a JSON file, in document order."""

    label: str  # where it is, for error messages
    value: str  # what it says now
    stamp: bool  # whether it must equal the pyproject.toml version


def pyproject_version() -> str:
    with PYPROJECT.open("rb") as f:
        return tomllib.load(f)["project"]["version"]


def walk_version_keys(node: object, path: str = "") -> Iterator[tuple[str, str]]:
    """Yield (json path, value) for every string "version" key, in document order."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "version" and isinstance(value, str):
                yield f"{path}.version", value
            else:
                yield from walk_version_keys(value, f"{path}.{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from walk_version_keys(value, f"{path}[{i}]")


def server_slots(data: dict) -> tuple[list[Slot], list[str]]:
    """Slots for server.json: the top-level version plus the pypi packages[] entries."""
    packages = data.get("packages") or []
    pypi_paths = {
        f".packages[{i}].version" for i, pkg in enumerate(packages) if pkg.get("registryType") == "pypi"
    }
    problems = [] if pypi_paths else ["server.json has no packages[] entry with registryType 'pypi'"]
    slots = [
        Slot(f"server.json {path.lstrip('.')}", value, path == ".version" or path in pypi_paths)
        for path, value in walk_version_keys(data)
    ]
    return slots, problems


def gemini_slots(data: dict) -> list[Slot]:
    return [
        Slot(f"gemini-extension.json {path.lstrip('.')}", value, path == ".version")
        for path, value in walk_version_keys(data)
    ]


def manifest_slots(data: dict) -> list[Slot]:
    return [
        Slot(f"manifest.json {path.lstrip('.')}", value, path == ".version")
        for path, value in walk_version_keys(data)
    ]


def stamp_json(path: Path, slots: list[Slot], version: str, write: bool) -> list[str]:
    """Report slots that disagree with `version`; when `write`, rewrite just those values."""
    text = path.read_text(encoding="utf-8")
    matches = list(JSON_VERSION_RE.finditer(text))
    if [m.group(2) for m in matches] != [s.value for s in slots]:
        sys.exit(
            f"{path.name}: the \"version\" keys in the file text do not line up with the parsed JSON; "
            "edit the version by hand"
        )

    problems = []
    edits = []
    for match, slot in zip(matches, slots):
        if slot.stamp and slot.value != version:
            problems.append(f"{slot.label} is {slot.value!r}")
            edits.append(match)
    if write and edits:
        for match in reversed(edits):  # back to front so earlier offsets stay valid
            text = text[: match.start(2)] + version + text[match.end(2) :]
        path.write_text(text, encoding="utf-8")
    return problems


def stamp_init(version: str, write: bool) -> list[str]:
    text = INIT_PY.read_text(encoding="utf-8")
    match = INIT_VERSION_RE.search(text)
    if match is None:
        return ["diffbot_mcp/__init__.py has no __version__ line"]
    if match.group(1) == version:
        return []
    if write:
        INIT_PY.write_text(INIT_VERSION_RE.sub(f'__version__ = "{version}"', text, count=1), encoding="utf-8")
    return [f"diffbot_mcp/__init__.py __version__ is {match.group(1)!r}"]


def sync(version: str, write: bool) -> list[str]:
    server = json.loads(SERVER_JSON.read_text(encoding="utf-8"))
    slots, problems = server_slots(server)
    problems += stamp_json(SERVER_JSON, slots, version, write)

    gemini = json.loads(GEMINI_JSON.read_text(encoding="utf-8"))
    problems += stamp_json(GEMINI_JSON, gemini_slots(gemini), version, write)

    manifest = json.loads(MANIFEST_JSON.read_text(encoding="utf-8"))
    problems += stamp_json(MANIFEST_JSON, manifest_slots(manifest), version, write)

    problems += stamp_init(version, write)
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="fail if any file disagrees with pyproject.toml")
    mode.add_argument("--print", action="store_true", help="print the pyproject.toml version and exit")
    args = parser.parse_args()

    version = pyproject_version()
    if args.print:
        print(version)
        return 0

    problems = sync(version, write=not args.check)
    if not problems:
        print(f"All versions match {version}" if args.check else f"Already in sync at {version}")
        return 0

    if args.check:
        print(f"Version mismatch, pyproject.toml says {version}:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        print("Run: python scripts/sync_version.py", file=sys.stderr)
        return 1

    print(f"Stamped {version} into:")
    for problem in problems:
        print(f"  - fixed: {problem}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
