#!/usr/bin/env bash
# Force all agents to interact with another agent (for testing).
#
# Usage:
#   ./scripts/force_interactions.sh
#   ./scripts/force_interactions.sh http://localhost:3000
#
# Prerequisites:
#   - The FastAPI server must be running:
#       uvicorn app.main:app --reload
#   - At least 2 agents must exist in the database

set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"
ENDPOINT="${BASE_URL}/debug/force-interactions"

echo "Forcing agent-agent interactions via POST ${ENDPOINT} ..."
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
echo "Agent interactions complete!"
