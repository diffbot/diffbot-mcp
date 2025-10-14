# initialize and capture session ID
SESSION=$(curl -sD - \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":0,"method":"initialize",
       "params":{"protocolVersion":"2025-06-18",
                 "capabilities":{"tools":{}},
                 "clientInfo":{"name":"curl","version":"1"}}}' \
  http://127.0.0.1:8000/mcp/?token=TEST |
  grep -i mcp-session-id | awk '{print $2}' | tr -d '\r')

# send initialized notification
curl -s \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -H "Mcp-Session-Id: $SESSION" \
  -d '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
  http://127.0.0.1:8000/mcp/?token=TEST

# call the search tool
curl -s \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -H "Mcp-Session-Id: $SESSION" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call",
       "params":{"name":"search_web","arguments":{"query":"diffbot"}}}' \
  http://127.0.0.1:8000/mcp/?token=TEST