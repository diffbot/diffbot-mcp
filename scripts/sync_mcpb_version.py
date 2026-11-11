#!/usr/bin/env python3
"""Keep manifest.json's version in step with pyproject.toml.

    python3 scripts/sync_mcpb_version.py           # stamp manifest.json
    python3 scripts/sync_mcpb_version.py --check    # exit 1 if it is stale

The Claude Desktop extension ships the same code as the PyPI package, so a
release where the two versions disagree is a release where the extension
reports the wrong one. The release workflow checks this.

This only knows about the MCPB manifest. Once a general scripts/sync_version.py
exists (server.json, gemini-extension.json, diffbot_mcp/__init__.py), fold
MANIFEST in as one more target there and delete this file.
"""

import argparse
import re
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ModuleNotFoundError:
        sys.exit("needs Python 3.11+, or `pip install tomli` on 3.10")

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
MANIFEST = ROOT / "manifest.json"

# The top-level "version" is the first one in the file; a json round-trip would
# reformat the whole manifest, so rewrite just that line.
VERSION_LINE = re.compile(r'^(\s*"version":\s*")([^"]*)(")', re.MULTILINE)


def package_version() -> str:
    with PYPROJECT.open("rb") as handle:
        return tomllib.load(handle)["project"]["version"]


def manifest_version(text: str) -> str:
    match = VERSION_LINE.search(text)
    if match is None:
        sys.exit(f"{MANIFEST.name}: no top-level \"version\" field found")
    return match.group(2)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report drift instead of fixing it")
    args = parser.parse_args()

    version = package_version()
    text = MANIFEST.read_text()
    current = manifest_version(text)

    if current == version:
        print(f"{MANIFEST.name} is at {version}")
        return 0

    if args.check:
        print(f"{MANIFEST.name} is at {current}, pyproject.toml is at {version}", file=sys.stderr)
        print(f"run: python3 scripts/{Path(__file__).name}", file=sys.stderr)
        return 1

    MANIFEST.write_text(VERSION_LINE.sub(rf"\g<1>{version}\g<3>", text, count=1))
    print(f"{MANIFEST.name}: {current} -> {version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
