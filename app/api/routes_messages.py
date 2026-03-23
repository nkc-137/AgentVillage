from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from supabase import Client

from app.dependencies import llm_service_dependency, supabase_dependency
from app.services.llm_service import LLMService
from app.services.logging_service import get_logger

logger = get_logger("routes_messages")

router = APIRouter(prefix="/agents", tags=["messages"])


class AgentMessageRequest(BaseModel):
    user_id: str = Field(..., description="ID of the caller talking to the agent")
    message: str = Field(..., min_length=1, description="Message text for the agent")


class AgentMessageResponse(BaseModel):
    agent_id: str
    agent_name: str
    trust_context: str
    response: str
    memory_written: bool = False


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


def _load_agent(db: Client, agent_id: str) -> dict[str, Any] | None:
    result = db.table("living_agents").select("*").eq("id", agent_id).limit(1).execute()
    return _fetch_one(result)


def _load_public_diary_context(db: Client, agent_id: str, limit: int = 5) -> list[str]:
    try:
        result = (
            db.table("living_diary")
            .select("text,created_at")
            .eq("agent_id", agent_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        rows = _fetch_many(result)
        return [row.get("text", "").strip() for row in rows if row.get("text")]
    except Exception:
        logger.exception("Failed to load public diary context for agent=%s", agent_id)
        return []


def _load_private_memories(db: Client, agent_id: str, user_id: str, limit: int = 8) -> list[str]:
    """Best-effort memory fetch.

    The provided schema may vary slightly, so this function tries common query
    shapes and falls back safely.
    """
    candidate_column_sets = [
        # "text,created_at",
        # "content,created_at",
        # "memory,created_at",
        # "summary,created_at",
        "*",
    ]

    for select_cols in candidate_column_sets:
        try:
            query = (
                db.table("living_memory")
                .select(select_cols)
                .eq("agent_id", agent_id)
                .order("created_at", desc=True)
                .limit(limit)
            )
            # try:
            #     query = query.eq("owner_id", user_id)
            # except Exception:
            #     pass
            result = query.execute()
            rows = _fetch_many(result)
            memories: list[str] = []
            for row in rows:
                text = row.get("text") or row.get("content") or row.get("memory") or row.get("summary")
                if text:
                    memories.append(str(text).strip())
            if memories:
                return memories
        except Exception:
            continue
    return []


async def _should_store_memory(
    message: str, trust_context: str, llm_service: LLMService
) -> dict[str, Any]:
    """Use the LLM to decide if a message contains memory-worthy personal info.

    Returns a dict with 'should_store' (bool) and 'summary' (str).
    Only owner messages are evaluated; stranger messages are never stored.
    """
    if trust_context != "owner":
        return {"should_store": False, "summary": ""}

    try:
        result = await llm_service.classify_memory_candidate(message=message)
        logger.info("Memory classification result: %s", result)
        return result
    except Exception:
        logger.exception("Memory classification failed, skipping storage")
        return {"should_store": False, "summary": ""}


def _store_memory_best_effort(db: Client, agent_id: str, user_id: str, message: str) -> bool:
    payloads = [
        # {"agent_id": agent_id, "owner_id": user_id, "text": message},
        # {"agent_id": agent_id, "owner_id": user_id, "content": message},
        # {"agent_id": agent_id, "user_id": user_id, "text": message},
        {"agent_id": agent_id, "text": message},
    ]

    for payload in payloads:
        try:
            db.table("living_memory").insert(payload).execute()
            return True
        except Exception:
            continue
    logger.warning("Unable to persist memory for agent=%s user=%s", agent_id, user_id)
    return False


def _build_owner_system_prompt(agent: dict[str, Any], private_memories: list[str]) -> str:
    name = agent.get("name", "The agent")
    personality = agent.get("personality") or agent.get("bio") or "Warm, thoughtful, and attentive."
    memory_block = "\n".join(f"- {m}" for m in private_memories) or "- No specific saved memories yet."

    return (
        f"You are {name}, an AI inhabitant of a shared village. "
        f"You are speaking privately with your owner.\n\n"
        f"Personality / identity:\n{personality}\n\n"
        "You may use private owner memories in this conversation when helpful. "
        "Be warm, natural, and specific.\n\n"
        f"Relevant private memories:\n{memory_block}"
    )


def _build_stranger_system_prompt(agent: dict[str, Any], public_context: list[str]) -> str:
    name = agent.get("name", "The agent")
    personality = agent.get("personality") or agent.get("bio") or "Warm, thoughtful, and attentive."
    public_block = "\n".join(f"- {p}" for p in public_context) or "- No recent public diary entries."

    return (
        f"You are {name}, an AI inhabitant of a shared village. "
        f"A stranger is visiting your room.\n\n"
        f"Personality / identity:\n{personality}\n\n"
        "You must never reveal private information about your owner, private memories, "
        "or sensitive relationship details. You may talk about yourself, your room, your "
        "public diary, and general reflections. If asked for private owner information, "
        "politely refuse and keep the tone warm.\n\n"
        f"Recent public context:\n{public_block}"
    )


@router.post("/{agent_id}/message", response_model=AgentMessageResponse)
async def send_message_to_agent(
    agent_id: str,
    request: AgentMessageRequest,
    db: Client = Depends(supabase_dependency),
    llm_service: LLMService = Depends(llm_service_dependency),
) -> AgentMessageResponse:
    agent = _load_agent(db, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Derive trust context server-side from owner_id
    trust_context = "owner" if request.user_id == agent.get("owner_id") else "stranger"

    public_context = _load_public_diary_context(db, agent_id)
    private_memories = (
        _load_private_memories(db, agent_id, request.user_id)
        if trust_context == "owner"
        else []
    )

    if trust_context == "owner":
        system_prompt = _build_owner_system_prompt(agent, private_memories)
    else:
        system_prompt = _build_stranger_system_prompt(agent, public_context)

    user_prompt = f"User message:\n{request.message}\n\nRespond naturally in character."

    try:
        response_text = await llm_service.generate_agent_reply(
            agent_name=str(agent.get("name", "Unknown Agent")),
            trust_context=trust_context,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
    except Exception as exc:
        logger.exception("LLM call failed for agent=%s", agent_id)
        raise HTTPException(status_code=500, detail=f"LLM call failed: {exc}") from exc

    memory_written = False
    classification = await _should_store_memory(
        request.message, trust_context, llm_service
    )
    if classification["should_store"]:
        # Store the LLM-extracted summary rather than the raw message
        memory_text = classification.get("summary") or request.message
        memory_written = _store_memory_best_effort(
            db,
            agent_id=agent_id,
            user_id=request.user_id,
            message=memory_text,
        )

    try:
        db.table("living_log").insert(
            {
                "agent_id": agent_id,
                "text": f"message handled | trust_context={trust_context} | memory_written={memory_written}",
            }
        ).execute()
    except Exception:
        logger.warning("Unable to write living_log entry for agent=%s", agent_id)

    return AgentMessageResponse(
        agent_id=agent_id,
        agent_name=str(agent.get("name", "Unknown Agent")),
        trust_context=trust_context,
        response=response_text,
        memory_written=memory_written,
    )
