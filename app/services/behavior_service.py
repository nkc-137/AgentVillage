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


def should_write_diary(db: Client, agent_id: str) -> bool:
    """Decide whether this agent should write a diary entry now.

    Considers:
    - Random probability (so agents don't all post at once)
    - Time of day (slightly more likely in evening hours)
    - Boosted probability if agent has never written or hasn't in a while
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

    roll = random.random()
    logger.debug(
        "Diary check for agent=%s | probability=%.2f | roll=%.2f | eligible=%s",
        agent_id, probability, roll, roll < probability,
    )
    return roll < probability


def should_post_activity(db: Client, agent_id: str) -> bool:
    """Decide whether the agent should post a social activity event."""
    now = datetime.now(timezone.utc)
    last_activity = get_last_activity_time(db, agent_id)

    # Don't post if there was very recent activity
    if last_activity is not None:
        minutes_since = (now - last_activity).total_seconds() / 60
        if minutes_since < 30:
            return False

    return random.random() < ACTIVITY_PROBABILITY


def should_update_status(db: Client, agent_id: str) -> bool:
    """Decide whether the agent should update their room status."""
    # Less frequent than diary — ~15% chance per tick
    return random.random() < 0.15
