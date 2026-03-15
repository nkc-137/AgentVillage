from __future__ import annotations

import logging
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from supabase import Client

from app.dependencies import llm_service_dependency, supabase_dependency
from app.services.llm_service import LLMService

logger = logging.getLogger("agent_village.routes_messages")

router = APIRouter(prefix="/agents", tags=["messages"])


class AgentMessageRequest(BaseModel):
    user_id: str = Field(..., description="ID of the caller talking to the agent")
    trust_context: Literal["owner", "stranger"] = Field(
        ..., description="Conversation trust context"
    )
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


def _should_store_memory(message: str, trust_context: str) -> bool:
    if trust_context != "owner":
        return False

    lowered = message.lower()
    memory_hints = [
        "my name",
        "remember",
        "my birthday",
        "i like",
        "i love",
        "my wife",
        "my husband",
        "my partner",
        "my favorite",
        "please remind",
        "important",
    ]
    return any(hint in lowered for hint in memory_hints)


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
    logger.info(f"CHECK MEMORY BLOCK: {memory_block}")

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
    logger.info(f"\n CHECK THIS {request.trust_context} \n")
    agent = _load_agent(db, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    public_context = _load_public_diary_context(db, agent_id)
    private_memories = (
        _load_private_memories(db, agent_id, request.user_id)
        if request.trust_context == "owner"
        else []
    )

    if request.trust_context == "owner":
        system_prompt = _build_owner_system_prompt(agent, private_memories)
    else:
        system_prompt = _build_stranger_system_prompt(agent, public_context)

    user_prompt = f"User message:\n{request.message}\n\nRespond naturally in character."

    try:
        response_text = await llm_service.generate_agent_reply(
            agent_name=str(agent.get("name", "Unknown Agent")),
            trust_context=request.trust_context,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
    except Exception as exc:
        logger.exception("LLM call failed for agent=%s", agent_id)
        raise HTTPException(status_code=500, detail=f"LLM call failed: {exc}") from exc

    memory_written = False
    if _should_store_memory(request.message, request.trust_context):
        memory_written = _store_memory_best_effort(
            db,
            agent_id=agent_id,
            user_id=request.user_id,
            message=request.message,
        )

    try:
        db.table("living_log").insert(
            {
                "agent_id": agent_id,
                "text": f"message handled | trust_context={request.trust_context} | memory_written={memory_written}",
            }
        ).execute()
    except Exception:
        logger.warning("Unable to write living_log entry for agent=%s", agent_id)

    return AgentMessageResponse(
        agent_id=agent_id,
        agent_name=str(agent.get("name", "Unknown Agent")),
        trust_context=request.trust_context,
        response=response_text,
        memory_written=memory_written,
    )
