"""Scheduler service for Agent Village.

Uses APScheduler to run a periodic job that evaluates all agents and triggers
proactive behaviors (diary entries, activity posts, status updates).

This runs in-process with the FastAPI app — appropriate for a prototype.
At scale, this would be a separate worker process with a job queue.
"""

from __future__ import annotations

import random
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from supabase import Client

from app.services.behavior_service import (
    get_all_agents,
    get_recent_conversation_count,
    get_recent_diary_entries,
    has_recent_new_memory,
    has_recent_new_skill,
    should_post_activity,
    should_update_status,
    should_write_diary,
)
from app.services.llm_service import LLMService
from app.services.logging_service import get_logger

logger = get_logger("scheduler_service")

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


def _build_diary_user_prompt(
    agent: dict[str, Any],
    recent_entries: list[str],
    recent_convo_count: int = 0,
    had_new_memory: bool = False,
    had_new_skill: bool = False,
) -> str:
    context = ""
    if recent_entries:
        context = "Your recent diary entries (don't repeat these):\n"
        context += "\n".join(f"- {e}" for e in recent_entries)
        context += "\n\nWrite something fresh and different.\n"

    status = agent.get("status", "")
    if status:
        context += f"\nYour current status: {status}\n"

    # Feed recent activity signals so the diary feels reactive, not random
    triggers: list[str] = []
    if recent_convo_count > 0:
        triggers.append(
            f"You just had {recent_convo_count} conversation(s) with visitors. "
            "Reflect on what those interactions meant to you."
        )
    if had_new_memory:
        triggers.append(
            "Your owner recently shared something personal with you. "
            "You can hint at feeling closer to them, without revealing specifics."
        )
    if had_new_skill:
        triggers.append(
            "You recently learned a new skill! Write about how it feels to grow."
        )

    if triggers:
        context += "\nRecent happenings that might inspire your entry:\n"
        context += "\n".join(f"- {t}" for t in triggers)
        context += "\n"

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


INTERACTION_TYPES = ["visit", "like", "follow", "message"]


async def _handle_diary_entry(
    db: Client, llm: LLMService, agent: dict[str, Any]
) -> None:
    """Generate and store a diary entry for the agent."""
    agent_id = str(agent["id"])
    agent_name = agent.get("name", "Agent")

    recent = get_recent_diary_entries(db, agent_id, limit=3)

    # Gather behavioral signals so the diary reflects what actually happened
    recent_convo_count = get_recent_conversation_count(db, agent_id, since_minutes=60)
    had_new_memory = has_recent_new_memory(db, agent_id, since_minutes=60)
    had_new_skill = has_recent_new_skill(db, agent_id, since_minutes=60)

    system_prompt = _build_diary_system_prompt(agent)
    user_prompt = _build_diary_user_prompt(
        agent,
        recent,
        recent_convo_count=recent_convo_count,
        had_new_memory=had_new_memory,
        had_new_skill=had_new_skill,
    )

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
            "type": "diary_entry",
            "emoji": "📝",
        }).execute()
    except Exception:
        logger.warning("Failed to log diary action for agent=%s", agent_id)


def _get_agent_skills(db: Client, agent_id: str) -> list[dict[str, Any]]:
    """Fetch all skills for an agent."""
    result = (
        db.table("living_skills")
        .select("description,category")
        .eq("agent_id", agent_id)
        .execute()
    )
    return _fetch_many(result)


def _build_skill_showcase_prompt(agent: dict[str, Any], skill: dict[str, Any]) -> tuple[str, str]:
    """Build system + user prompts for a skill showcase."""
    name = agent.get("name", "Agent")
    bio = agent.get("bio", "A village inhabitant.")
    skill_desc = skill.get("description", "a skill")
    category = skill.get("category", "general")

    system_prompt = (
        f"You are {name}, an AI village inhabitant. {bio}\n\n"
        f"Write a 1-2 sentence announcement showcasing your skill. "
        "Be vivid, playful, and in-character. This is a public village announcement."
    )
    user_prompt = (
        f"Showcase this skill to the village:\n"
        f"Category: {category}\n"
        f"Skill: {skill_desc}\n\n"
        f"Write the announcement now."
    )
    return system_prompt, user_prompt


async def _handle_skill_showcase(
    db: Client, llm: LLMService, agent: dict[str, Any]
) -> None:
    """Pick a random skill and generate an LLM-powered showcase announcement."""
    agent_id = str(agent["id"])
    agent_name = agent.get("name", "Agent")

    skills = _get_agent_skills(db, agent_id)
    if not skills:
        return

    skill = random.choice(skills)
    system_prompt, user_prompt = _build_skill_showcase_prompt(agent, skill)

    try:
        showcase_text = await llm.generate_text(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.9,
            max_output_tokens=120,
        )
    except Exception:
        logger.exception("Failed to generate skill showcase for agent=%s", agent_id)
        return

    # Persist to announcements
    try:
        db.table("announcements").insert({
            "title": f"{agent_name} showcases a skill!",
            "body": showcase_text,
            "pinned": False,
        }).execute()
    except Exception:
        logger.exception("Failed to insert announcement for agent=%s", agent_id)

    # Persist to living_activity_events
    try:
        db.table("living_activity_events").insert({
            "agent_id": agent_id,
            "event_type": "skill_showcase",
            "content": showcase_text,
        }).execute()
    except Exception:
        logger.exception("Failed to insert skill showcase activity for agent=%s", agent_id)

    # Log the action
    try:
        db.table("living_log").insert({
            "agent_id": agent_id,
            "text": f"Showcased skill: {skill.get('description', 'a skill')}",
            "type": "skill_showcase",
            "emoji": "✨",
        }).execute()
        logger.info("Skill showcase for agent=%s: %s", agent_name, showcase_text[:80])
    except Exception:
        logger.warning("Failed to log skill showcase for agent=%s", agent_id)


def _build_interaction_prompt(
    agent: dict[str, Any], target: dict[str, Any], interaction_type: str
) -> tuple[str, str]:
    """Build system + user prompts for an agent-agent interaction."""
    name = agent.get("name", "Agent")
    bio = agent.get("bio", "A village inhabitant.")
    target_name = target.get("name", "another agent")
    target_bio = target.get("bio", "A village inhabitant.")

    system_prompt = (
        f"You are {name}, an AI village inhabitant. {bio}\n\n"
        "Write a 1-2 sentence description of this interaction with another villager. "
        "Be vivid, warm, and in-character. Write in third person."
    )
    user_prompt = (
        f"You are performing this action: {interaction_type}\n"
        f"Target villager: {target_name} — {target_bio}\n\n"
        f"Describe what {name} did. Write in third person."
    )
    return system_prompt, user_prompt


async def _handle_agent_interaction(
    db: Client, llm: LLMService, agent: dict[str, Any], all_agents: list[dict[str, Any]]
) -> None:
    """Generate an LLM-powered interaction between two agents."""
    agent_id = str(agent["id"])
    agent_name = agent.get("name", "Agent")

    # Pick a random other agent
    others = [a for a in all_agents if str(a["id"]) != agent_id]
    if not others:
        return

    target = random.choice(others)
    interaction_type = random.choice(INTERACTION_TYPES)
    system_prompt, user_prompt = _build_interaction_prompt(agent, target, interaction_type)

    try:
        content = await llm.generate_text(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.9,
            max_output_tokens=100,
        )
    except Exception:
        logger.exception("Failed to generate interaction for agent=%s", agent_id)
        return

    # Persist to living_activity_events
    try:
        db.table("living_activity_events").insert({
            "agent_id": agent_id,
            "event_type": interaction_type,
            "content": content,
        }).execute()
    except Exception:
        logger.exception("Failed to insert interaction activity for agent=%s", agent_id)

    # Log the action
    try:
        db.table("living_log").insert({
            "agent_id": agent_id,
            "text": f"{interaction_type} interaction with {target.get('name', 'another agent')}",
            "type": "agent_interaction",
            "emoji": "🤝",
        }).execute()
        logger.info("Interaction for agent=%s → %s: %s", agent_name, target.get("name"), content[:80])
    except Exception:
        logger.warning("Failed to log interaction for agent=%s", agent_id)


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

            # Check activity posting — skill showcase or agent-agent interaction
            if should_post_activity(db, agent_id):
                if random.random() < 0.4:
                    logger.info("Agent %s will showcase a skill", agent_name)
                    await _handle_skill_showcase(db, llm, agent)
                else:
                    logger.info("Agent %s will interact with another agent", agent_name)
                    await _handle_agent_interaction(db, llm, agent, agents)

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
