#!/usr/bin/env bash
# Force all agents to interact with another agent
BASE_URL="${BASE_URL:-http://localhost:8000}"
echo "=== Forcing agent-agent interactions ==="
curl -s -X POST "$BASE_URL/debug/force-interactions" | python3 -m json.tool
