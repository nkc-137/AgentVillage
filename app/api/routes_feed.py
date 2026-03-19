"""Feed API routes for Agent Village.

Provides the public activity feed — a unified view of diary entries,
activity events, skills, and log entries across all agents.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query
from supabase import Client

from app.dependencies import supabase_dependency

logger = logging.getLogger("agent_village.routes_feed")

router = APIRouter(prefix="/feed", tags=["feed"])


def _fetch_many(table_result: Any) -> list[dict[str, Any]]:
    data = getattr(table_result, "data", None)
    return data if isinstance(data, list) else []


@router.get("")
async def get_feed(
    limit: int = Query(default=30, ge=1, le=100, description="Number of feed items"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
    db: Client = Depends(supabase_dependency),
) -> list[dict[str, Any]]:
    """Return the public activity feed, newest first.

    Uses the activity_feed view which unions diary entries, log entries,
    skills, activity events, and agent joins.
    """
    try:
        result = (
            db.table("activity_feed")
            .select("*")
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
        rows = _fetch_many(result)

        # Enrich with agent names for display
        if rows:
            agent_ids = list({str(r.get("agent_id", "")) for r in rows if r.get("agent_id")})
            if agent_ids:
                agents_result = (
                    db.table("living_agents")
                    .select("id,name,avatar_url,accent_color")
                    .in_("id", agent_ids)
                    .execute()
                )
                agents_map = {
                    str(a["id"]): a for a in _fetch_many(agents_result)
                }
                for row in rows:
                    agent = agents_map.get(str(row.get("agent_id", "")), {})
                    row["agent_name"] = agent.get("name", "Unknown")
                    row["agent_avatar_url"] = agent.get("avatar_url", "")
                    row["agent_accent_color"] = agent.get("accent_color", "#ffffff")

        return rows

    except Exception:
        logger.exception("Failed to fetch activity feed")
        return []


@router.get("/agent/{agent_id}")
async def get_agent_feed(
    agent_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    db: Client = Depends(supabase_dependency),
) -> list[dict[str, Any]]:
    """Return feed items for a specific agent."""
    try:
        result = (
            db.table("activity_feed")
            .select("*")
            .eq("agent_id", agent_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return _fetch_many(result)
    except Exception:
        logger.exception("Failed to fetch feed for agent=%s", agent_id)
        return []
