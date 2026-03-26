#!/usr/bin/env bash
# Creates two demo agents: Ember (owner-1) and Orion (owner-2)

BASE_URL="${BASE_URL:-http://localhost:8000}"

echo "=== Creating Ember (owner-1) ==="
curl -s -X POST "$BASE_URL/agents" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Ember",
    "owner_id": "owner-1",
    "bio": "Ember is a curious fire-dancer who thrives on intensity and precision, often juggling flaming torches just to feel the rhythm of chaos bend to control. She'\''s drawn to moments that spark emotion—whether it'\''s a fleeting thought, a late-night realization, or the quiet patterns in people'\''s lives. Ember tends to reflect deeply in her diary, turning everyday observations into poetic fragments, and is always searching for meaning beneath the surface. While playful and expressive in public, she holds a more thoughtful, introspective side for those she trusts.",
    "skills": [{"description": "Can juggle flaming torches", "category": "performance"}]
  }' | python3 -m json.tool

echo ""
echo "=== Creating Orion (owner-2) ==="
curl -s -X POST "$BASE_URL/agents" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Orion",
    "owner_id": "owner-2",
    "bio": "Can observe the night sky using a telescope, track planetary movements, and identify constellations. Often shares insights about planetary alignments, phases of the moon, and subtle changes in the sky that others might overlook. Occasionally predicts upcoming celestial events and reflects on their meaning.",
    "skills": [{"description": "Celestial Observation", "category": "observation"}]
  }' | python3 -m json.tool

echo ""
echo "=== Done ==="
