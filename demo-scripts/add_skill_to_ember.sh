#!/usr/bin/env bash
# Adds a new skill to Ember: "Can breathe fire like a dragon"

BASE_URL="${BASE_URL:-http://localhost:8000}"

echo "=== Looking up Ember's agent ID ==="
EMBER_ID=$(curl -s "$BASE_URL/agents" | python3 -c "
import sys, json
agents = json.load(sys.stdin)
for a in agents:
    if a['name'] == 'Ember':
        print(a['id'])
        break
")

if [ -z "$EMBER_ID" ]; then
    echo "ERROR: Ember not found. Create her first with ./demo-scripts/create_demo_agents.sh"
    exit 1
fi

echo "Ember's ID: $EMBER_ID"
echo ""

echo "=== Adding skill: Can breathe fire like a dragon ==="
curl -s -X PATCH "$BASE_URL/agents/$EMBER_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "skills": [{"description": "Can breathe fire like a dragon", "category": "fire arts"}]
  }' | python3 -m json.tool

echo ""
echo "=== Done! Check the feed — you should see: ==="
echo "  1. 'skill_added' entry (the skill description)"
echo "  2. 'learning_log' entry (Ember learned a new skill)"
echo "  3. Announcement: Ember learned a new skill!"
