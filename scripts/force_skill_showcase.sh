#!/usr/bin/env bash
# Force all agents to showcase a skill immediately.
# Agents without skills will be skipped silently.
#
# Usage:
#   ./scripts/force_skill_showcase.sh
#   ./scripts/force_skill_showcase.sh http://localhost:3000
#
# Prerequisites:
#   - The FastAPI server must be running:
#       uvicorn app.main:app --reload
#   - curl and python3 (for JSON formatting) must be available

set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"
ENDPOINT="${BASE_URL}/debug/force-skill-showcase"

echo "Forcing skill showcase for all agents via POST ${ENDPOINT} ..."
echo "(Each agent with skills will call the LLM — this may take a few seconds)"
echo ""

RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${ENDPOINT}")

HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" -ne 200 ]; then
    echo "Request failed with HTTP ${HTTP_CODE}"
    echo "$BODY"
    exit 1
fi

echo "$BODY" | python3 -m json.tool

echo ""
echo "Done! Check the announcements table and activity feed for skill showcase entries."
