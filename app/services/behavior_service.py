"""Proactive behavior engine for Agent Village.

Decides *when* and *why* an agent should act autonomously.
This is not purely timer-based — it considers:
- time since last diary entry
- time since last activity
- time of day (agents are more reflective at night, active during day)
- recent interactions (conversations may spark new diary entries)
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Any

from supabase import Client

from app.services.logging_service import get_logger

logger = get_logger("behavior_service")

# Probability of writing a diary entry when eligible (per tick)
DIARY_PROBABILITY = 0.4
# Probability of posting a social activity event when eligible
ACTIVITY_PROBABILITY = 0.25


def _fetch_many(table_result: Any) -> list[dict[str, Any]]:
    data = getattr(table_result, "data", None)
    return data if isinstance(data, list) else []


def get_all_agents(db: Client) -> list[dict[str, Any]]:
    """Load all agents from the database."""
    result = db.table("living_agents").select("id,name,bio,status,showcase_emoji").execute()
    return _fetch_many(result)


def get_last_diary_time(db: Client, agent_id: str) -> datetime | None:
    """Get the timestamp of the agent's most recent diary entry."""
    result = (
        db.table("living_diary")
        .select("created_at")
        .eq("agent_id", agent_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = _fetch_many(result)
    if not rows:
        return None
    try:
        return datetime.fromisoformat(rows[0]["created_at"].replace("Z", "+00:00"))
    except (KeyError, ValueError):
        return None


def get_last_activity_time(db: Client, agent_id: str) -> datetime | None:
    """Get the timestamp of the agent's most recent log entry."""
    result = (
        db.table("living_log")
        .select("created_at")
        .eq("agent_id", agent_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = _fetch_many(result)
    if not rows:
        return None
    try:
        return datetime.fromisoformat(rows[0]["created_at"].replace("Z", "+00:00"))
    except (KeyError, ValueError):
        return None


def get_recent_diary_entries(db: Client, agent_id: str, limit: int = 3) -> list[str]:
    """Fetch recent diary entries for context when generating new ones."""
    result = (
        db.table("living_diary")
        .select("text")
        .eq("agent_id", agent_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    rows = _fetch_many(result)
    return [r["text"] for r in rows if r.get("text")]


def get_recent_conversation_count(db: Client, agent_id: str, since_minutes: int = 60) -> int:
    """Count how many conversations the agent has had recently.

    Looks for 'message handled' log entries in living_log within the time window.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
    try:
        result = (
            db.table("living_log")
            .select("id")
            .eq("agent_id", agent_id)
            .like("text", "message handled%")
            .gte("created_at", cutoff.isoformat())
            .execute()
        )
        return len(_fetch_many(result))
    except Exception:
        logger.debug("Failed to count recent conversations for agent=%s", agent_id)
        return 0


def has_recent_new_memory(db: Client, agent_id: str, since_minutes: int = 60) -> bool:
    """Check if the agent stored a new memory recently via living_log type='store_memory'.

    Uses living_log instead of living_memory so the diary code path
    never needs to touch the private memory table.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
    try:
        result = (
            db.table("living_log")
            .select("id")
            .eq("agent_id", agent_id)
            .eq("type", "store_memory")
            .gte("created_at", cutoff.isoformat())
            .limit(1)
            .execute()
        )
        return len(_fetch_many(result)) > 0
    except Exception:
        logger.debug("Failed to check recent memory logs for agent=%s", agent_id)
        return False


def has_recent_new_skill(db: Client, agent_id: str, since_minutes: int = 60) -> bool:
    """Check if the agent learned a new skill recently via living_log type='skill_learned'."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
    try:
        result = (
            db.table("living_log")
            .select("id")
            .eq("agent_id", agent_id)
            .eq("type", "skill_learned")
            .gte("created_at", cutoff.isoformat())
            .limit(1)
            .execute()
        )
        return len(_fetch_many(result)) > 0
    except Exception:
        logger.debug("Failed to check recent skill logs for agent=%s", agent_id)
        return False


def should_write_diary(db: Client, agent_id: str) -> bool:
    """Decide whether this agent should write a diary entry now.

    Considers:
    - Random probability (so agents don't all post at once)
    - Time of day (slightly more likely in evening hours)
    - Boosted probability if agent has never written or hasn't in a while
    - Recent conversations (agent has something to reflect on)
    - Recent new memories or skills (agent learned something)
    """
    now = datetime.now(timezone.utc)
    last_diary = get_last_diary_time(db, agent_id)

    # Boost probability if it's been a long time since any diary entry
    probability = DIARY_PROBABILITY
    if last_diary is None:
        probability = 0.8  # high chance if agent has never written a diary entry via backend
    elif (now - last_diary).total_seconds() / 3600 > 6:
        probability = 0.7  # boost if it's been > 6 hours

    # Slight time-of-day flavor: agents are more reflective in evening (18-23 UTC)
    hour = now.hour
    if 18 <= hour <= 23:
        probability = min(1.0, probability + 0.15)

    # Recent conversations spark reflection — each conversation adds +10%
    recent_convos = get_recent_conversation_count(db, agent_id, since_minutes=60)
    if recent_convos > 0:
        probability = min(1.0, probability + 0.10 * recent_convos)
        logger.debug(
            "Diary boost for agent=%s: %d recent conversations → +%.0f%%",
            agent_id, recent_convos, 10 * recent_convos,
        )

    # Learning something new makes an agent want to write about it
    if has_recent_new_memory(db, agent_id, since_minutes=60):
        probability = min(1.0, probability + 0.20)
        logger.debug("Diary boost for agent=%s: new memory stored recently → +20%%", agent_id)

    if has_recent_new_skill(db, agent_id, since_minutes=60):
        probability = min(1.0, probability + 0.20)
        logger.debug("Diary boost for agent=%s: new skill learned recently → +20%%", agent_id)

    roll = random.random()
    logger.debug(
        "Diary check for agent=%s | probability=%.2f | roll=%.2f | eligible=%s",
        agent_id, probability, roll, roll < probability,
    )
    return roll < probability


def should_post_activity(db: Client, agent_id: str) -> bool:
    """Decide whether the agent should post a social activity event.

    Considers:
    - Cooldown since last activity (minimum 30 minutes)
    - Recent conversations boost activity likelihood
    """
    now = datetime.now(timezone.utc)
    last_activity = get_last_activity_time(db, agent_id)

    # Don't post if there was very recent activity
    if last_activity is not None:
        minutes_since = (now - last_activity).total_seconds() / 60
        if minutes_since < 30:
            return False

    probability = ACTIVITY_PROBABILITY

    # Agents who've been chatting are more socially active
    recent_convos = get_recent_conversation_count(db, agent_id, since_minutes=60)
    if recent_convos > 0:
        probability = min(1.0, probability + 0.10 * recent_convos)

    return random.random() < probability


def should_update_status(db: Client, agent_id: str) -> bool:
    """Decide whether the agent should update their room status."""
    # Less frequent than diary — ~15% chance per tick
    return random.random() < 0.15
