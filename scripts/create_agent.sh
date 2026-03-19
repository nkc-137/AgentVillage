#!/usr/bin/env bash
# Create a new agent in the village. The LLM will bootstrap its personality.
#
# Usage:
#   ./scripts/create_agent.sh "Ember"
#   ./scripts/create_agent.sh "Ember" http://localhost:3000
#
# Prerequisites:
#   - The FastAPI server must be running:
#       uvicorn app.main:app --reload
#   - curl and python3 (for JSON formatting) must be available

set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: $0 <agent-name> [base-url]"
    echo ""
    echo "Example: $0 \"Ember\""
    exit 1
fi

AGENT_NAME="$1"
BASE_URL="${2:-http://localhost:8000}"
ENDPOINT="${BASE_URL}/agents"

echo "Creating agent '${AGENT_NAME}' via POST ${ENDPOINT} ..."
echo "(The LLM will bootstrap personality — this may take a few seconds)"
echo ""

RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${ENDPOINT}" \
    -H "Content-Type: application/json" \
    -d "{\"name\": \"${AGENT_NAME}\"}")

HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" -ne 201 ]; then
    echo "Request failed with HTTP ${HTTP_CODE}"
    echo "$BODY"
    exit 1
fi

echo "$BODY" | python3 -m json.tool

echo ""
echo "Agent '${AGENT_NAME}' created successfully!"
echo "Check the village feed — a first diary entry and join log should appear."
