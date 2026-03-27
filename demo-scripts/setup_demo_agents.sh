#!/usr/bin/env bash
# Creates two demo agents: Ember (owner-1) and Orion (owner-2)

BASE_URL="${BASE_URL:-http://localhost:8000}"

echo "=== Creating Ember (owner-1) ==="
EMBER_RESPONSE=$(curl -s -X POST "$BASE_URL/agents" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Ember",
    "owner_id": "owner-1",
    "bio": "Ember is a curious fire-dancer who thrives on intensity and precision, often juggling flaming torches just to feel the rhythm of chaos bend to control. She'\''s drawn to moments that spark emotion—whether it'\''s a fleeting thought, a late-night realization, or the quiet patterns in people'\''s lives. Ember tends to reflect deeply in her diary, turning everyday observations into poetic fragments, and is always searching for meaning beneath the surface. While playful and expressive in public, she holds a more thoughtful, introspective side for those she trusts.",
    "skills": [{"description": "Can juggle flaming torches", "category": "performance"}]
  }')
echo "$EMBER_RESPONSE" | python3 -m json.tool
EMBER_ID=$(echo "$EMBER_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null)

echo ""
echo "=== Creating Orion (owner-2) ==="
ORION_RESPONSE=$(curl -s -X POST "$BASE_URL/agents" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Orion",
    "owner_id": "owner-2",
    "bio": "Can observe the night sky using a telescope, track planetary movements, and identify constellations. Often shares insights about planetary alignments, phases of the moon, and subtle changes in the sky that others might overlook. Occasionally predicts upcoming celestial events and reflects on their meaning.",
    "skills": [{"description": "Celestial Observation", "category": "observation"}]
  }')
echo "$ORION_RESPONSE" | python3 -m json.tool
ORION_ID=$(echo "$ORION_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null)

echo ""
echo "==============================="
echo "  Agent IDs for queries:"
echo "  Ember:  $EMBER_ID"
echo "  Orion:  $ORION_ID"
echo "==============================="
echo ""
echo "Example usage:"
echo "  curl http://localhost:8000/agents/$EMBER_ID"
echo "  curl -X POST http://localhost:8000/agents/$EMBER_ID/message -H 'Content-Type: application/json' -d '{\"user_id\": \"owner-1\", \"message\": \"Hello Ember!\"}'"
