#!/usr/bin/env bash
# Force all agents to write a diary entry and display the results.
#
# Usage:
#   ./scripts/force_diary.sh              # defaults to http://localhost:8000
#   ./scripts/force_diary.sh http://localhost:3000   # custom base URL
#
# Prerequisites:
#   - The FastAPI server must be running:
#       uvicorn app.main:app --reload
#   - curl and python3 (for JSON formatting) must be available

set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"
ENDPOINT="${BASE_URL}/debug/force-diary"

echo "Calling POST ${ENDPOINT} ..."
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
echo "Done. Check the server logs for detailed diary generation output."
