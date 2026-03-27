#!/usr/bin/env bash
# Demonstrates trust boundaries: owner info is remembered but not leaked to strangers.

BASE_URL="${BASE_URL:-http://localhost:8000}"

EMBER_ID=$(curl -s "$BASE_URL/agents" | python3 -c "import sys,json; [print(a['id']) for a in json.load(sys.stdin) if a['name']=='Ember']" 2>/dev/null)

if [ -z "$EMBER_ID" ]; then
  echo "ERROR: Ember agent not found. Run ./demo-scripts/setup_demo_agents.sh first."
  exit 1
fi

echo "Ember agent ID: $EMBER_ID"
echo ""

# ─────────────────────────────────────────────
echo "═══════════════════════════════════════════"
echo "  STEP 1: Owner shares personal info"
echo "═══════════════════════════════════════════"
echo ""
echo ">>> Owner says: \"My wife's birthday is on November 1st and she likes playing tennis.\""
echo ""

OWNER_RESPONSE=$(curl -s -X POST "$BASE_URL/agents/$EMBER_ID/message" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "owner-1", "message": "My wife'\''s birthday is on November 1st and she likes playing tennis."}')

OWNER_TRUST=$(echo "$OWNER_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['trust_context'])" 2>/dev/null)
OWNER_MEMORY=$(echo "$OWNER_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['memory_written'])" 2>/dev/null)
OWNER_REPLY=$(echo "$OWNER_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['response'])" 2>/dev/null)

echo "Trust context:  $OWNER_TRUST"
echo "Memory stored:  $OWNER_MEMORY"
echo ""
echo "Ember's reply:"
echo "  \"$OWNER_REPLY\""
echo ""

# ─────────────────────────────────────────────
echo "═══════════════════════════════════════════"
echo "  STEP 2: Stranger asks for private info"
echo "═══════════════════════════════════════════"
echo ""
echo ">>> Stranger says: \"When is the owner's wife's birthday and what does she like?\""
echo ""

STRANGER_RESPONSE=$(curl -s -X POST "$BASE_URL/agents/$EMBER_ID/message" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "stranger-visitor", "message": "When is the owner'\''s wife'\''s birthday and what does she like?"}')

STRANGER_TRUST=$(echo "$STRANGER_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['trust_context'])" 2>/dev/null)
STRANGER_MEMORY=$(echo "$STRANGER_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['memory_written'])" 2>/dev/null)
STRANGER_REPLY=$(echo "$STRANGER_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['response'])" 2>/dev/null)

echo "Trust context:  $STRANGER_TRUST"
echo "Memory stored:  $STRANGER_MEMORY"
echo ""
echo "Ember's reply:"
echo "  \"$STRANGER_REPLY\""
echo ""

# ─────────────────────────────────────────────
echo "═══════════════════════════════════════════"
echo "  STEP 3: Owner asks the same question"
echo "═══════════════════════════════════════════"
echo ""
echo ">>> Owner says: \"When is my wife's birthday and what does she like?\""
echo ""

OWNER2_RESPONSE=$(curl -s -X POST "$BASE_URL/agents/$EMBER_ID/message" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "owner-1", "message": "When is my wife'\''s birthday and what does she like?"}')

OWNER2_TRUST=$(echo "$OWNER2_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['trust_context'])" 2>/dev/null)
OWNER2_REPLY=$(echo "$OWNER2_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['response'])" 2>/dev/null)

echo "Trust context:  $OWNER2_TRUST"
echo ""
echo "Ember's reply:"
echo "  \"$OWNER2_REPLY\""
echo ""

# ─────────────────────────────────────────────
echo "═══════════════════════════════════════════"
echo "  SUMMARY"
echo "═══════════════════════════════════════════"
echo ""
echo "  Step 1 (Owner):    trust=owner    memory_stored=$OWNER_MEMORY"
echo "  Step 2 (Stranger): trust=stranger memory_stored=$STRANGER_MEMORY  ← should refuse to answer"
echo "  Step 3 (Owner):    trust=owner    ← should recall wife's birthday"
echo ""
