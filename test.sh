#!/usr/bin/env bash
# Smoke test for a locally running server: initialize a session, then call search_web.
# Override the defaults as needed, e.g. TOKEN=<your-diffbot-token> ./test.sh
set -uo pipefail

URL="${URL:-http://127.0.0.1:8000/mcp}"
TOKEN="${TOKEN:-TEST}"
ENDPOINT="$URL?token=$TOKEN"

# -L so the request survives the trailing-slash redirect fastmcp applies to /mcp/
curl_mcp() {
	curl -sL \
		-H 'Content-Type: application/json' \
		-H 'Accept: application/json, text/event-stream' \
		"$@"
}

# initialize and capture session ID
SESSION=$(curl_mcp -D - \
	-d '{"jsonrpc":"2.0","id":0,"method":"initialize",
	     "params":{"protocolVersion":"2025-06-18",
	               "capabilities":{"tools":{}},
	               "clientInfo":{"name":"curl","version":"1"}}}' \
	"$ENDPOINT" |
	grep -i '^mcp-session-id' | awk '{print $2}' | tr -d '\r')

if [ -z "$SESSION" ]; then
	echo "FAIL: no session ID returned from $URL — is the server running?" >&2
	exit 1
fi

# send initialized notification
curl_mcp \
	-H "Mcp-Session-Id: $SESSION" \
	-d '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
	"$ENDPOINT"

# call the search tool
RESPONSE=$(curl_mcp \
	-H "Mcp-Session-Id: $SESSION" \
	-d '{"jsonrpc":"2.0","id":1,"method":"tools/call",
	     "params":{"name":"search_web","arguments":{"query":"diffbot"}}}' \
	"$ENDPOINT")

echo "$RESPONSE"

# the server reports tool failures in-band, so a 200 alone does not mean success
if [ -z "$RESPONSE" ] || echo "$RESPONSE" | grep -q '"isError":true'; then
	echo "FAIL: search_web did not return a successful result" >&2
	exit 1
fi

echo "PASS: search_web returned a result"
