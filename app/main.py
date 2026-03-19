"""FastAPI application entrypoint for the Agent Village backend.

This file is responsible for:
- creating the FastAPI app
- registering API routers when present
- starting the APScheduler-based background scheduler
- shutting the scheduler down gracefully
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

try:
    from app.dependencies import (
        get_llm_service,
        get_settings,
        get_supabase_client,
    )
except Exception:  # pragma: no cover
    get_settings = None
    get_supabase_client = None
    get_llm_service = None

# Optional router imports — loaded only if the files already exist so the app
# can run incrementally while the project is being built.
try:
    from app.api.routes_messages import router as messages_router
except Exception:
    messages_router = None

try:
    from app.api.routes_agents import router as agents_router
except Exception:
    agents_router = None

try:
    from app.api.routes_feed import router as feed_router
except Exception:
    feed_router = None

# Scheduler service
try:
    from app.services.scheduler_service import (
        _handle_diary_entry,
        start_scheduler,
        stop_scheduler,
    )
except Exception:
    _handle_diary_entry = None
    start_scheduler = None
    stop_scheduler = None


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("agent_village.main")


class FallbackSettings:
    """Minimal fallback settings used before the full config layer exists."""

    AGENT_TICK_INTERVAL_SECONDS: int = int(os.getenv("AGENT_TICK_INTERVAL_SECONDS", "60"))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application startup and shutdown."""
    settings = get_settings() if get_settings is not None else FallbackSettings()
    app.state.settings = settings

    # Start the background scheduler
    scheduler = None
    if start_scheduler is not None and get_supabase_client is not None and get_llm_service is not None:
        try:
            db = get_supabase_client()
            llm = get_llm_service()
            interval = max(30, int(settings.AGENT_TICK_INTERVAL_SECONDS))
            scheduler = start_scheduler(db, llm, interval_seconds=interval)
            app.state.scheduler = scheduler
            logger.info("Background scheduler started (interval=%ds)", interval)
        except Exception:
            logger.exception("Failed to start scheduler — app will run without proactive behavior")
    else:
        logger.warning("Scheduler dependencies not available — running without proactive behavior")

    logger.info("Application startup complete")

    try:
        yield
    finally:
        if stop_scheduler is not None:
            stop_scheduler()
        logger.info("Application shutdown complete")


app = FastAPI(
    title="Agent Village Backend",
    description=(
        "Backend prototype for trust-aware AI agents that maintain private "
        "owner relationships while participating safely in a public shared world."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root() -> dict[str, str]:
    """Basic root endpoint for quick sanity checks."""
    return {"status": "running", "service": "agent-village-backend"}


@app.get("/health")
async def health() -> dict[str, Any]:
    """Health endpoint used during local development and demos."""
    settings = getattr(app.state, "settings", None)
    interval = getattr(settings, "AGENT_TICK_INTERVAL_SECONDS", None)
    scheduler = getattr(app.state, "scheduler", None)

    return {
        "status": "ok",
        "scheduler_running": bool(scheduler and scheduler.running),
        "tick_interval_seconds": interval,
    }



@app.post("/debug/force-diary")
async def force_diary_entries() -> dict[str, Any]:
    """Force ALL agents to write a diary entry immediately. Testing only."""
    if (
        _handle_diary_entry is None
        or get_supabase_client is None
        or get_llm_service is None
    ):
        return {"status": "error", "message": "Dependencies not available"}

    from app.services.behavior_service import get_all_agents

    db = get_supabase_client()
    llm = get_llm_service()
    agents = get_all_agents(db)

    if not agents:
        return {"status": "error", "message": "No agents found in database"}

    results: list[dict[str, str]] = []
    for agent in agents:
        agent_id = str(agent["id"])
        agent_name = agent.get("name", "Agent")
        try:
            await _handle_diary_entry(db, llm, agent)
            results.append({"agent": agent_name, "status": "ok"})
        except Exception as exc:
            logger.exception("Force diary failed for agent=%s", agent_id)
            results.append({"agent": agent_name, "status": f"error: {exc}"})

    return {
        "status": "ok",
        "message": f"Forced diary entries for {len(agents)} agents",
        "results": results,
    }


# Register routers
if messages_router is not None:
    app.include_router(messages_router)
    logger.info("Registered messages router")

if agents_router is not None:
    app.include_router(agents_router)
    logger.info("Registered agents router")

if feed_router is not None:
    app.include_router(feed_router)
    logger.info("Registered feed router")
