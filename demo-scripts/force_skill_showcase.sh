#!/usr/bin/env bash
# Force all agents to demonstrate a skill
BASE_URL="${BASE_URL:-http://localhost:8000}"
echo "=== Forcing skill showcase for all agents ==="
curl -s -X POST "$BASE_URL/debug/force-skill-showcase" | python3 -m json.tool
