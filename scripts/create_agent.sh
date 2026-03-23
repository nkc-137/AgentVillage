#!/usr/bin/env bash
# Create a new agent in the village. The LLM will bootstrap its personality.
#
# Usage:
#   ./scripts/create_agent.sh "Ember"
#   ./scripts/create_agent.sh "Ember" --owner "owner-1"
#   ./scripts/create_agent.sh "Ember" --skill "Can juggle flaming torches"
#   ./scripts/create_agent.sh "Ember" --owner "owner-1" --skill "Can juggle flaming torches"
#   ./scripts/create_agent.sh "Ember" --owner "owner-1" --skill "Can juggle flaming torches" --url http://localhost:3000
#
# Prerequisites:
#   - The FastAPI server must be running:
#       uvicorn app.main:app --reload
#   - curl and python3 (for JSON formatting) must be available

set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: $0 <agent-name> [--owner <owner-id>] [--skill <skill-description>] [--url <base-url>]"
    echo ""
    echo "Examples:"
    echo "  $0 \"Ember\""
    echo "  $0 \"Ember\" --owner \"owner-1\""
    echo "  $0 \"Ember\" --skill \"Can juggle flaming torches\""
    echo "  $0 \"Ember\" --owner \"owner-1\" --skill \"Can juggle flaming torches\""
    exit 1
fi

AGENT_NAME="$1"
shift

OWNER_ID=""
SKILL=""
BASE_URL="http://localhost:8000"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --owner)
            OWNER_ID="$2"
            shift 2
            ;;
        --skill)
            SKILL="$2"
            shift 2
            ;;
        --url)
            BASE_URL="$2"
            shift 2
            ;;
        *)
            # Legacy positional: treat as base URL for backward compat
            BASE_URL="$1"
            shift
            ;;
    esac
done

ENDPOINT="${BASE_URL}/agents"

# Build JSON payload
PAYLOAD="{\"name\": \"${AGENT_NAME}\""

if [ -n "$OWNER_ID" ]; then
    PAYLOAD="${PAYLOAD}, \"owner_id\": \"${OWNER_ID}\""
fi

if [ -n "$SKILL" ]; then
    PAYLOAD="${PAYLOAD}, \"skills\": [{\"description\": \"${SKILL}\"}]"
fi

PAYLOAD="${PAYLOAD}}"

echo "Creating agent '${AGENT_NAME}' via POST ${ENDPOINT} ..."
[ -n "$OWNER_ID" ] && echo "  Owner: ${OWNER_ID}"
[ -n "$SKILL" ] && echo "  Skill: ${SKILL}"
echo "(The LLM will bootstrap personality — this may take a few seconds)"
echo ""

RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${ENDPOINT}" \
    -H "Content-Type: application/json" \
    -d "${PAYLOAD}")

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
