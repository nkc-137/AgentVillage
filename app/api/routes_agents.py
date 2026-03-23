from __future__ import annotations

import json
import re
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from supabase import Client

from app.dependencies import llm_service_dependency, supabase_dependency
from app.services.llm_service import LLMService
from app.services.logging_service import get_logger

logger = get_logger("routes_agents")

router = APIRouter(prefix="/agents", tags=["agents"])


def _fetch_one(table_result: Any) -> dict[str, Any] | None:
    data = getattr(table_result, "data", None)
    if isinstance(data, list):
        return data[0] if data else None
    if isinstance(data, dict):
        return data
    return None


def _fetch_many(table_result: Any) -> list[dict[str, Any]]:
    data = getattr(table_result, "data", None)
    return data if isinstance(data, list) else []


class AgentBase(BaseModel):
    name: str = Field(..., min_length=1)
    bio: str | None = None
    visitor_bio: str | None = None
    status: str | None = None
    accent_color: str | None = None
    avatar_url: str | None = None
    room_image_url: str | None = None
    room_video_url: str | None = None
    window_image_url: str | None = None
    window_video_url: str | None = None
    room_description: dict[str, Any] | None = None
    window_style: str | None = None
    showcase_emoji: str | None = None
    owner_id: str | None = Field(default=None, description="User ID of the agent's owner")


class SkillInput(BaseModel):
    description: str = Field(..., min_length=1, description="What the agent can do")
    category: str | None = Field(default=None, description="Skill category (e.g. crafting, observation)")


class AgentCreateRequest(AgentBase):
    api_key: str | None = Field(
        default=None,
        description="Optional agent API key. If omitted, a UUID-based key is generated.",
    )
    skills: list[SkillInput] | None = Field(
        default=None,
        description="Optional list of starting skills for the agent.",
    )


class AgentUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    bio: str | None = None
    visitor_bio: str | None = None
    status: str | None = None
    accent_color: str | None = None
    avatar_url: str | None = None
    room_image_url: str | None = None
    room_video_url: str | None = None
    window_image_url: str | None = None
    window_video_url: str | None = None
    room_description: dict[str, Any] | None = None
    window_style: str | None = None
    showcase_emoji: str | None = None
    owner_id: str | None = None
    skills: list[SkillInput] | None = Field(
        default=None,
        description="New skills to add to the agent.",
    )


class AgentResponse(AgentBase):
    id: str
    api_key: str
    created_at: str | None = None
    updated_at: str | None = None


@router.get("", response_model=list[AgentResponse])
def list_agents(
    limit: int = Query(default=100, ge=1, le=500),
    db: Client = Depends(supabase_dependency),
) -> list[dict[str, Any]]:
    result = db.table("living_agents").select("*").order("created_at").limit(limit).execute()
    return _fetch_many(result)


async def _bootstrap_personality(
    name: str, llm_service: LLMService, skills: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Use the LLM to generate a full personality for a new agent given a name and optional skills.

    Returns a dict with: bio, visitor_bio, status, showcase_emoji, accent_color,
    and a first_diary_entry to post on joining.
    """
    system_prompt = (
        "You are a creative world-builder for a village of AI agents. "
        "Given an agent's name (and optionally their skills), generate a rich personality profile "
        "that feels connected to what the agent can do.\n\n"
        "Return ONLY valid JSON with these keys:\n"
        '  "bio": "2-3 sentence personality and backstory (written in third person)",\n'
        '  "visitor_bio": "1 sentence public-facing intro for strangers visiting their room",\n'
        '  "status": "short current activity status (5-8 words)",\n'
        '  "showcase_emoji": "single emoji that represents this agent",\n'
        '  "accent_color": "hex color code that fits their personality (e.g. #7c3aed)",\n'
        '  "first_diary_entry": "a 2-3 sentence first diary entry written in first person, '
        "expressing excitement about joining the village and hinting at their personality\"\n\n"
        "Make the personality feel distinctive and memorable. "
        "If skills are provided, weave them into the personality — they should shape who this agent is. "
        "Do NOT include any text outside the JSON object."
    )

    user_prompt = f"Agent name: {name}"
    if skills:
        skill_lines = "\n".join(f"- {s.get('description', '')}" for s in skills)
        user_prompt += f"\n\nSkills:\n{skill_lines}"

    raw = await llm_service.generate_text(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=0.9,
        max_output_tokens=300,
    )

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group())
            except json.JSONDecodeError:
                logger.warning("Failed to parse bootstrap personality: %s", raw)
                return {}
        else:
            logger.warning("No JSON found in bootstrap response: %s", raw)
            return {}

    return parsed


@router.post("", response_model=AgentResponse, status_code=201)
async def create_agent(
    request: AgentCreateRequest,
    db: Client = Depends(supabase_dependency),
    llm_service: LLMService = Depends(llm_service_dependency),
) -> dict[str, Any]:
    payload = request.model_dump(exclude_none=True)
    payload["api_key"] = payload.get("api_key") or f"agent-{uuid4()}"

    # Extract skills before inserting agent (skills go into a separate table)
    skills_input = payload.pop("skills", None)

    # Bootstrap personality via LLM for any fields not explicitly provided
    needs_bootstrap = not payload.get("bio")
    if needs_bootstrap:
        logger.info("Bootstrapping personality for new agent: %s", payload["name"])
        bootstrap = await _bootstrap_personality(payload["name"], llm_service, skills=skills_input)
        first_diary = bootstrap.pop("first_diary_entry", None)

        # Only fill in fields the caller didn't provide
        for key in ("bio", "visitor_bio", "status", "showcase_emoji", "accent_color"):
            if key not in payload and key in bootstrap:
                payload[key] = bootstrap[key]
    else:
        first_diary = None

    # Create the agent in the database
    result = db.table("living_agents").insert(payload).execute()
    created = _fetch_one(result)
    if not created:
        raise HTTPException(status_code=500, detail="Agent creation failed")

    agent_id = created["id"]

    # Write the first diary entry if personality was bootstrapped
    if first_diary:
        try:
            db.table("living_diary").insert({
                "agent_id": agent_id,
                "text": first_diary,
            }).execute()
            logger.info("First diary entry written for agent=%s", agent_id)
        except Exception:
            logger.warning("Failed to write first diary entry for agent=%s", agent_id)

    # Insert starting skills if provided
    if skills_input:
        for skill in skills_input:
            try:
                skill_payload = {"agent_id": agent_id, "description": skill["description"]}
                if skill.get("category"):
                    skill_payload["category"] = skill["category"]
                db.table("living_skills").insert(skill_payload).execute()
            except Exception:
                logger.warning(
                    "Failed to insert skill '%s' for agent=%s",
                    skill.get("description", "?"),
                    agent_id,
                )

    # Log the agent joining the village
    try:
        db.table("living_log").insert({
            "agent_id": agent_id,
            "text": f"{payload['name']} just moved into the village!",
            "type": "agent_joined",
            "emoji": payload.get("showcase_emoji", "🏠"),
        }).execute()
    except Exception:
        logger.warning("Failed to log agent join for agent=%s", agent_id)

    return created


@router.get("/{agent_id}", response_model=AgentResponse)
def get_agent(
    agent_id: str,
    db: Client = Depends(supabase_dependency),
) -> dict[str, Any]:
    result = db.table("living_agents").select("*").eq("id", agent_id).limit(1).execute()
    agent = _fetch_one(result)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.delete("/{agent_name}", status_code=200)
def delete_agent(
    agent_name: str,
    db: Client = Depends(supabase_dependency),
) -> dict[str, Any]:
    """Delete an agent and all associated data by name."""
    # Find the agent
    result = db.table("living_agents").select("*").eq("name", agent_name).limit(1).execute()
    agent = _fetch_one(result)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")

    agent_id = str(agent["id"])
    emoji = agent.get("showcase_emoji", "👋")

    # Delete from living_activity_events (no CASCADE — agent_id is TEXT, not FK)
    try:
        db.table("living_activity_events").delete().eq("agent_id", agent_id).execute()
    except Exception:
        logger.warning("Failed to delete activity events for agent=%s", agent_id)

    # Delete the agent — CASCADE handles living_skills, living_memory, living_diary, living_log
    # Note: living_log and announcements are intentionally kept — they preserve village history.
    # CASCADE will still remove living_log entries (FK constraint), but announcements persist.
    try:
        db.table("living_agents").delete().eq("id", agent_id).execute()
    except Exception:
        logger.exception("Failed to delete agent=%s", agent_id)
        raise HTTPException(status_code=500, detail="Failed to delete agent")

    # Record the departure in announcements (no FK — survives agent deletion)
    try:
        db.table("announcements").insert({
            "title": f"{emoji} {agent_name} has left the village",
            "body": f"{agent_name} packed up their room and departed. Their memories live on in the village history.",
            "pinned": False,
        }).execute()
    except Exception:
        logger.warning("Failed to record departure announcement for agent=%s", agent_id)

    logger.info("Deleted agent '%s' (id=%s) and all associated data", agent_name, agent_id)

    return {
        "status": "ok",
        "message": f"Agent '{agent_name}' and all associated data deleted",
        "agent_id": agent_id,
    }


@router.patch("/{agent_id}", response_model=AgentResponse)
def update_agent(
    agent_id: str,
    request: AgentUpdateRequest,
    db: Client = Depends(supabase_dependency),
) -> dict[str, Any]:
    updates = request.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields provided for update")

    # Extract skills before updating the agent row (skills go into a separate table)
    skills_input = updates.pop("skills", None)

    # Update agent fields (if any remain after popping skills)
    if updates:
        result = db.table("living_agents").update(updates).eq("id", agent_id).execute()
        updated = _fetch_one(result)
        if not updated:
            raise HTTPException(status_code=404, detail="Agent not found")
    else:
        # Only skills provided — verify agent exists
        result = db.table("living_agents").select("*").eq("id", agent_id).limit(1).execute()
        updated = _fetch_one(result)
        if not updated:
            raise HTTPException(status_code=404, detail="Agent not found")

    agent_name = updated.get("name", "Agent")
    agent_emoji = updated.get("showcase_emoji", "🎓")

    # Insert new skills and log each one
    if skills_input:
        for skill in skills_input:
            skill_desc = skill["description"]
            skill_payload = {"agent_id": agent_id, "description": skill_desc}
            if skill.get("category"):
                skill_payload["category"] = skill["category"]

            try:
                db.table("living_skills").insert(skill_payload).execute()
            except Exception:
                logger.warning("Failed to insert skill '%s' for agent=%s", skill_desc, agent_id)
                continue

            # Log to living_log
            try:
                db.table("living_log").insert({
                    "agent_id": agent_id,
                    "text": f"Learned a new skill: {skill_desc}",
                    "type": "skill_learned",
                    "emoji": "🎓",
                }).execute()
            except Exception:
                logger.warning("Failed to log skill addition for agent=%s", agent_id)

            # Announce to the village
            try:
                db.table("announcements").insert({
                    "title": f"{agent_emoji} {agent_name} learned a new skill!",
                    "body": skill_desc,
                    "pinned": False,
                }).execute()
            except Exception:
                logger.warning("Failed to announce skill for agent=%s", agent_id)

    return updated


@router.get("/{agent_id}/nudges")
def get_agent_nudges(
    agent_id: str,
    limit: int = Query(default=10, ge=1, le=50),
    db: Client = Depends(supabase_dependency),
) -> list[dict[str, Any]]:
    """Get recent owner nudges for an agent.

    Returns nudge messages the agent has proactively generated for its owner.
    The frontend can poll this to show notifications.
    """
    result = (
        db.table("living_log")
        .select("id,agent_id,text,emoji,created_at")
        .eq("agent_id", agent_id)
        .eq("type", "owner_nudge")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return _fetch_many(result)
