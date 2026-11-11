#!/usr/bin/env python3
"""Print the one-click install links in the README.

The README badges are generated, not hand-written: the client deeplinks embed a
base64 or url-encoded copy of the server config, so editing them by hand is how
they end up pointing at stale JSON. Change a config below, run this script, and
paste the output over the badge block in README.md.

    python3 scripts/install_links.py            # markdown for the README
    python3 scripts/install_links.py --decode    # each link with its decoded JSON

Link formats (both documented, both survive GitHub's markdown sanitizer, which
strips the raw cursor:// and vscode: schemes):
  Cursor   https://cursor.com/install-mcp?name=$NAME&config=$BASE64_CONFIG
           https://cursor.com/docs/mcp/install-links
  VS Code  https://vscode.dev/redirect?url=<urlencoded vscode:mcp/install?$JSON>
           https://code.visualstudio.com/docs/copilot/guides/mcp-developer-guide

No token belongs in a link: the hosted remote signs the user in over OAuth, and
the local server reads DIFFBOT_API_TOKEN, DIFFBOT_TOKEN, or ~/.diffbot/credentials.
"""

import argparse
import base64
import json
from urllib.parse import quote

NAME = "diffbot-mcp"
REMOTE_URL = "https://mcp.diffbot.com/mcp"

# Cursor takes the single server config object, without the mcpServers wrapper.
CURSOR_REMOTE = {"url": REMOTE_URL}
CURSOR_LOCAL = {"type": "stdio", "command": "uvx", "args": [NAME]}

# VS Code takes the same object with the server name inside it.
VSCODE_REMOTE = {"name": NAME, "type": "http", "url": REMOTE_URL}
VSCODE_LOCAL = {"name": NAME, "type": "stdio", "command": "uvx", "args": [NAME]}


def dumps(config: dict) -> str:
    """JSON.stringify: no whitespace, so the encoded payload matches the clients' docs."""
    return json.dumps(config, separators=(",", ":"))


def cursor_link(config: dict) -> str:
    payload = base64.b64encode(dumps(config).encode()).decode()
    return f"https://cursor.com/install-mcp?name={NAME}&config={payload}"


def vscode_link(config: dict, insiders: bool = False) -> str:
    scheme = "vscode-insiders" if insiders else "vscode"
    host = "insiders.vscode.dev" if insiders else "vscode.dev"
    # The wrapper url-encodes the whole vscode: URL once, which is the same
    # encodeURIComponent the docs apply to the JSON in the bare scheme link.
    return f"https://{host}/redirect?url={quote(f'{scheme}:mcp/install?{dumps(config)}', safe='')}"


LINKS = [
    ("Cursor, hosted server", cursor_link(CURSOR_REMOTE), CURSOR_REMOTE),
    ("Cursor, local server", cursor_link(CURSOR_LOCAL), CURSOR_LOCAL),
    ("VS Code, hosted server", vscode_link(VSCODE_REMOTE), VSCODE_REMOTE),
    ("VS Code, local server", vscode_link(VSCODE_LOCAL), VSCODE_LOCAL),
    ("VS Code Insiders, hosted server", vscode_link(VSCODE_REMOTE, insiders=True), VSCODE_REMOTE),
]

MARKDOWN = """[![Install in Cursor](https://cursor.com/deeplink/mcp-install-dark.svg)]({cursor_remote})
[![Install in VS Code](https://img.shields.io/badge/VS_Code-Install_Diffbot-0098FF?style=flat-square&logo=visualstudiocode&logoColor=white)]({vscode_remote})

One click adds the hosted server and signs you in with a Diffbot account, no token to paste.
For the local `uvx diffbot-mcp` server instead: [Cursor]({cursor_local}) · [VS Code]({vscode_local}).
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decode", action="store_true", help="print each link with its decoded JSON")
    args = parser.parse_args()

    if args.decode:
        for label, link, config in LINKS:
            print(f"{label}\n  {link}\n  {dumps(config)}\n")
        return

    print(MARKDOWN.format(
        cursor_remote=cursor_link(CURSOR_REMOTE),
        cursor_local=cursor_link(CURSOR_LOCAL),
        vscode_remote=vscode_link(VSCODE_REMOTE),
        vscode_local=vscode_link(VSCODE_LOCAL),
    ), end="")


if __name__ == "__main__":
    main()
