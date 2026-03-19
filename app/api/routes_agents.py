from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from supabase import Client

from app.dependencies import supabase_dependency

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


class AgentCreateRequest(AgentBase):
    api_key: str | None = Field(
        default=None,
        description="Optional agent API key. If omitted, a UUID-based key is generated.",
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


@router.post("", response_model=AgentResponse, status_code=201)
def create_agent(
    request: AgentCreateRequest,
    db: Client = Depends(supabase_dependency),
) -> dict[str, Any]:
    payload = request.model_dump(exclude_none=True)
    payload["api_key"] = payload.get("api_key") or f"agent-{uuid4()}"

    result = db.table("living_agents").insert(payload).execute()
    created = _fetch_one(result)
    if not created:
        raise HTTPException(status_code=500, detail="Agent creation failed")
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


@router.patch("/{agent_id}", response_model=AgentResponse)
def update_agent(
    agent_id: str,
    request: AgentUpdateRequest,
    db: Client = Depends(supabase_dependency),
) -> dict[str, Any]:
    updates = request.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields provided for update")

    result = db.table("living_agents").update(updates).eq("id", agent_id).execute()
    updated = _fetch_one(result)
    if not updated:
        raise HTTPException(status_code=404, detail="Agent not found")
    return updated
