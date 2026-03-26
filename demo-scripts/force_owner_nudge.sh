#!/usr/bin/env bash
# Force all agents with owners to send a nudge to their owner
BASE_URL="${BASE_URL:-http://localhost:8000}"
echo "=== Forcing owner nudges for all agents ==="
curl -s -X POST "$BASE_URL/debug/force-owner-nudge" | python3 -m json.tool
