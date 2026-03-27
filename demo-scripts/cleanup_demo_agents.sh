#!/usr/bin/env bash
# Deletes demo agents: Ember and Orion

BASE_URL="${BASE_URL:-http://localhost:8000}"

echo "=== Deleting Ember ==="
curl -s -X DELETE "$BASE_URL/agents/Ember" | python3 -m json.tool

echo ""
echo "=== Deleting Orion ==="
curl -s -X DELETE "$BASE_URL/agents/Orion" | python3 -m json.tool

echo ""
echo "=== Done ==="
