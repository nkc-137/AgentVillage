#!/usr/bin/env bash
# Delete an agent and all associated data (skills, memories, diary, logs, activities).
#
# Usage:
#   ./scripts/delete_agent.sh "Chopper"
#   ./scripts/delete_agent.sh "Chopper" http://localhost:3000
#
# Prerequisites:
#   - The FastAPI server must be running:
#       uvicorn app.main:app --reload
#   - curl and python3 (for JSON formatting) must be available

set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: $0 <agent-name> [base-url]"
    echo ""
    echo "Example: $0 \"Chopper\""
    exit 1
fi

AGENT_NAME="$1"
BASE_URL="${2:-http://localhost:8000}"
# URL-encode the agent name for the path
ENCODED_NAME=$(python3 -c "import urllib.parse; print(urllib.parse.quote('${AGENT_NAME}'))")
ENDPOINT="${BASE_URL}/agents/${ENCODED_NAME}"

echo "Deleting agent '${AGENT_NAME}' via DELETE ${ENDPOINT} ..."
echo ""

RESPONSE=$(curl -s -w "\n%{http_code}" -X DELETE "${ENDPOINT}")

HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" -ne 200 ]; then
    echo "Request failed with HTTP ${HTTP_CODE}"
    echo "$BODY"
    exit 1
fi

echo "$BODY" | python3 -m json.tool

echo ""
echo "Agent '${AGENT_NAME}' deleted successfully!"
