#!/usr/bin/env bash
# Force all agents to write a diary entry
BASE_URL="${BASE_URL:-http://localhost:8000}"
echo "=== Forcing diary entries for all agents ==="
curl -s -X POST "$BASE_URL/debug/force-diary" | python3 -m json.tool
