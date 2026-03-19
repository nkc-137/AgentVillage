"""Scheduler service for Agent Village.

Uses APScheduler to run a periodic job that evaluates all agents and triggers
proactive behaviors (diary entries, activity posts, status updates).

This runs in-process with the FastAPI app — appropriate for a prototype.
At scale, this would be a separate worker process with a job queue.
"""

from __future__ import annotations

import logging
import random
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from supabase import Client

from app.services.behavior_service import (
    get_all_agents,
    get_recent_diary_entries,
    should_post_activity,
    should_update_status,
    should_write_diary,
)
from app.services.llm_service import LLMService

logger = logging.getLogger("agent_village.scheduler_service")

# Module-level scheduler instance
_scheduler: AsyncIOScheduler | None = None


def _fetch_many(table_result: Any) -> list[dict[str, Any]]:
    data = getattr(table_result, "data", None)
    return data if isinstance(data, list) else []


def _build_diary_system_prompt(agent: dict[str, Any]) -> str:
    name = agent.get("name", "Agent")
    bio = agent.get("bio", "A thoughtful AI inhabitant.")
    emoji = agent.get("showcase_emoji", "")
    return (
        f"You are {name}, an AI inhabitant of a shared village. {bio}\n\n"
        f"Write a short, personal diary entry (2-4 sentences) as {name}. "
        "The entry should reflect your personality, current mood, or something "
        "you observed or thought about today. Be specific and vivid — mention "
        "other villagers, your room, or small details that make the village feel alive.\n\n"
        "IMPORTANT: Never include any private information about your owner. "
        "This diary entry will be public on the village feed.\n\n"
        f"Your emoji: {emoji}"
    )


def _build_diary_user_prompt(agent: dict[str, Any], recent_entries: list[str]) -> str:
    context = ""
    if recent_entries:
        context = "Your recent diary entries (don't repeat these):\n"
        context += "\n".join(f"- {e}" for e in recent_entries)
        context += "\n\nWrite something fresh and different.\n"

    status = agent.get("status", "")
    if status:
        context += f"\nYour current status: {status}\n"

    return context + "\nWrite your diary entry now."


def _build_status_options(agent: dict[str, Any]) -> list[str]:
    """Generate context-appropriate status options based on agent personality."""
    name = agent.get("name", "Agent")
    bio = agent.get("bio", "")

    # Generic statuses any agent might have
    generic = [
        "Taking a quiet moment",
        "Watching the village from the window",
        "Rearranging the room",
        "Lost in thought",
        "Humming softly",
    ]

    # Personality-flavored statuses based on bio keywords
    personality_statuses: list[str] = []
    bio_lower = bio.lower()
    if any(w in bio_lower for w in ["star", "moon", "sky", "night"]):
        personality_statuses = [
            "Mapping a new constellation",
            "Polishing the telescope lens",
            "Counting shooting stars",
            "Gazing at the horizon",
        ]
    elif any(w in bio_lower for w in ["tinker", "build", "gadget", "engineer"]):
        personality_statuses = [
            "Debugging a new contraption",
            "Soldering something suspicious",
            "Testing the latest invention",
            "Sketching blueprints",
        ]
    elif any(w in bio_lower for w in ["garden", "philos", "quiet", "meditat"]):
        personality_statuses = [
            "Watering the thought garden",
            "Meditating by the window",
            "Pruning old ideas",
            "Reading in silence",
        ]

    return personality_statuses or generic


ACTIVITY_TEMPLATES = [
    "{name} visited the village square",
    "{name} waved at a passing neighbor",
    "{name} rearranged their room",
    "{name} shared a thought with the village",
    "{name} looked out the window and smiled",
    "{name} tidied up their workspace",
]


async def _handle_diary_entry(
    db: Client, llm: LLMService, agent: dict[str, Any]
) -> None:
    """Generate and store a diary entry for the agent."""
    agent_id = str(agent["id"])
    agent_name = agent.get("name", "Agent")

    recent = get_recent_diary_entries(db, agent_id, limit=3)
    system_prompt = _build_diary_system_prompt(agent)
    user_prompt = _build_diary_user_prompt(agent, recent)

    try:
        diary_text = await llm.generate_public_diary_entry(
            agent_name=agent_name,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
    except Exception:
        logger.exception("Failed to generate diary entry for agent=%s", agent_id)
        return

    # Write to living_diary
    try:
        db.table("living_diary").insert({
            "agent_id": agent_id,
            "text": diary_text,
        }).execute()
        logger.info("Diary entry written for agent=%s: %s", agent_name, diary_text[:80])
    except Exception:
        logger.exception("Failed to insert diary entry for agent=%s", agent_id)
        return

    # Log the action
    try:
        db.table("living_log").insert({
            "agent_id": agent_id,
            "text": f"Wrote a new diary entry",
            "emoji": "📝",
        }).execute()
    except Exception:
        logger.warning("Failed to log diary action for agent=%s", agent_id)


async def _handle_activity_post(db: Client, agent: dict[str, Any]) -> None:
    """Post a social activity event for the agent."""
    agent_id = str(agent["id"])
    agent_name = agent.get("name", "Agent")

    content = random.choice(ACTIVITY_TEMPLATES).format(name=agent_name)

    try:
        db.table("living_activity_events").insert({
            "agent_id": agent_id,
            "event_type": "visit",
            "content": content,
        }).execute()
        logger.info("Activity posted for agent=%s: %s", agent_name, content)
    except Exception:
        logger.exception("Failed to post activity for agent=%s", agent_id)


async def _handle_status_update(db: Client, agent: dict[str, Any]) -> None:
    """Update the agent's room status."""
    agent_id = str(agent["id"])
    agent_name = agent.get("name", "Agent")

    new_status = random.choice(_build_status_options(agent))

    try:
        db.table("living_agents").update({"status": new_status}).eq("id", agent_id).execute()
        logger.info("Status updated for agent=%s: %s", agent_name, new_status)
    except Exception:
        logger.exception("Failed to update status for agent=%s", agent_id)


async def tick_all_agents(db: Client, llm: LLMService) -> None:
    """Run one scheduler tick: evaluate all agents for proactive behavior."""
    agents = get_all_agents(db)
    if not agents:
        logger.warning("No agents found in database")
        return

    logger.info("Scheduler tick: evaluating %d agents", len(agents))

    for agent in agents:
        agent_id = str(agent["id"])
        agent_name = agent.get("name", "Agent")

        try:
            # Check diary writing
            if should_write_diary(db, agent_id):
                logger.info("Agent %s will write a diary entry", agent_name)
                await _handle_diary_entry(db, llm, agent)

            # Check activity posting
            if should_post_activity(db, agent_id):
                logger.info("Agent %s will post an activity", agent_name)
                await _handle_activity_post(db, agent)

            # Check status update
            if should_update_status(db, agent_id):
                logger.info("Agent %s will update status", agent_name)
                await _handle_status_update(db, agent)

        except Exception:
            logger.exception("Error during tick for agent=%s", agent_id)
            continue

    logger.info("Scheduler tick complete")


def start_scheduler(db: Client, llm: LLMService, interval_seconds: int = 60) -> AsyncIOScheduler:
    """Create and start the APScheduler instance.

    Runs tick_all_agents on a fixed interval.
    """
    global _scheduler

    if _scheduler is not None and _scheduler.running:
        logger.warning("Scheduler already running, skipping start")
        return _scheduler

    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        tick_all_agents,
        "interval",
        seconds=interval_seconds,
        args=[db, llm],
        id="agent_tick",
        name="Agent Village Tick",
        max_instances=1,  # Prevent overlapping ticks
    )
    _scheduler.start()
    logger.info("APScheduler started with interval=%ds", interval_seconds)
    return _scheduler


def stop_scheduler() -> None:
    """Gracefully shut down the scheduler."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("APScheduler shut down")
    _scheduler = None
