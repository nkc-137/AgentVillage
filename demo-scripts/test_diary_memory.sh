#!/usr/bin/env bash
# Tests that diary entries reference stored memories
# Usage: ./demo-scripts/test_diary_memory.sh

set -e
BASE_URL="${BASE_URL:-http://localhost:8000}"

# Get Ember's ID
EMBER_ID=$(curl -s "$BASE_URL/agents" | python3 -c "
import sys, json
agents = json.load(sys.stdin)
for a in agents:
    if a['name'] == 'Ember':
        print(a['id'])
        break
")

if [ -z "$EMBER_ID" ]; then
    echo "ERROR: Ember not found. Create Ember first."
    exit 1
fi

echo "Ember ID: $EMBER_ID"
echo ""

echo "=== Step 1: Send personal info as owner ==="
RESPONSE=$(curl -s -X POST "$BASE_URL/agents/$EMBER_ID/message" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "owner-1", "message": "My favorite color is blue and I love pizza"}')

echo "$RESPONSE" | python3 -c "
import sys, json
r = json.load(sys.stdin)
print(f\"Trust context: {r['trust_context']}\")
print(f\"Memory written: {r['memory_written']}\")
print(f\"Response: {r['response'][:100]}...\")
"

echo ""
echo "=== Step 2: Wait 2 seconds for DB writes to settle ==="
sleep 2

echo ""
echo "=== Step 3: Force diary entry ==="
DIARY_RESPONSE=$(curl -s -X POST "$BASE_URL/debug/force-diary")

echo "$DIARY_RESPONSE" | python3 -c "
import sys, json
r = json.load(sys.stdin)
for result in r.get('results', []):
    if result.get('agent') == 'Ember':
        print(f\"Agent: {result['agent']}\")
        print(f\"Status: {result['status']}\")
        print(f\"Activity log entries: {result.get('activity_log_entries', 'N/A')}\")
        print(f\"Activity log: {result.get('activity_log', 'N/A')}\")
        break
"

echo ""
echo "=== Step 4: Check Ember's latest diary entry ==="
curl -s "$BASE_URL/feed/agent/$EMBER_ID?limit=3" | python3 -c "
import sys, json
items = json.load(sys.stdin)
for item in items:
    if item.get('type') == 'diary_entry':
        print(f\"Diary: {item.get('text', 'N/A')}\")
        print(f\"Time: {item.get('created_at', 'N/A')}\")
        break
" 2>/dev/null || echo "(Feed endpoint may not support agent filter)"

echo ""
echo "=== Done ==="
