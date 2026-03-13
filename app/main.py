

"""FastAPI application entrypoint for the Agent Village backend.

This file is responsible for:
- creating the FastAPI app
- registering API routers when present
- starting a lightweight background scheduler
- shutting the scheduler down gracefully

The scheduler is intentionally simple for this prototype. It runs in-process,
which is a good fit for the assignment because it demonstrates proactive agent
behavior without adding distributed infrastructure.
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager, suppress
from typing import Any, AsyncIterator

from fastapi import FastAPI

try:
    from app.dependencies import get_settings
except Exception:  # pragma: no cover - fallback only used during early bootstrapping
    get_settings = None

# Optional router imports. These are loaded only if the files already exist so
# the app can run incrementally while the project is being built.
# try:
#     from app.api.routes_messages import router as messages_router
# except Exception:
#     messages_router = None

# try:
#     from app.api.routes_agents import router as agents_router
# except Exception:
#     agents_router = None

# try:
#     from app.api.routes_feed import router as feed_router
# except Exception:
#     feed_router = None

# # Optional service import. If it does not exist yet, we fall back to a stub so
# # the server still runs while the rest of the codebase is being implemented.
# try:
#     from app.services.scheduler_service import tick_all_agents as service_tick_all_agents
# except Exception:
#     service_tick_all_agents = None


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("agent_village.main")


class FallbackSettings:
    """Minimal fallback settings used before the full config layer exists."""

    AGENT_TICK_INTERVAL_SECONDS: int = int(os.getenv("AGENT_TICK_INTERVAL_SECONDS", "30"))


# async def tick_all_agents(app: FastAPI) -> None:
#     """Run one scheduler tick for all agents.

#     If a dedicated scheduler service exists, delegate to it. Otherwise use a
#     small no-op stub so the app remains runnable while the rest of the backend
#     is still under construction.
#     """
#     if service_tick_all_agents is not None:
#         result = service_tick_all_agents(app)
#         if asyncio.iscoroutine(result):
#             await result
#         return

#     logger.info("Scheduler tick executed (stub). No scheduler_service yet.")


# async def scheduler_loop(app: FastAPI) -> None:
#     """Background loop that periodically evaluates all agents."""
#     settings = app.state.settings
#     interval = max(5, int(settings.AGENT_TICK_INTERVAL_SECONDS))
#     logger.info("Starting scheduler loop with interval=%ss", interval)

#     try:
#         while True:
#             try:
#                 await tick_all_agents(app)
#             except asyncio.CancelledError:
#                 raise
#             except Exception:
#                 logger.exception("Unhandled error during scheduler tick")

#             await asyncio.sleep(interval)
#     except asyncio.CancelledError:
#         logger.info("Scheduler loop cancelled")
#         raise


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application startup and shutdown."""
    settings = get_settings() if get_settings is not None else FallbackSettings()
    app.state.settings = settings
    # app.state.scheduler_task = asyncio.create_task(scheduler_loop(app))
    logger.info("Application startup complete")

    try:
        yield
    finally:
        task = getattr(app.state, "scheduler_task", None)
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
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


@app.get("/")
async def root() -> dict[str, str]:
    """Basic root endpoint for quick sanity checks."""
    return {"status": "running", "service": "agent-village-backend"}


@app.get("/health")
async def health() -> dict[str, Any]:
    """Health endpoint used during local development and demos."""
    settings = getattr(app.state, "settings", None)
    interval = getattr(settings, "AGENT_TICK_INTERVAL_SECONDS", None)
    scheduler_task = getattr(app.state, "scheduler_task", None)

    return {
        "status": "ok",
        "scheduler_running": bool(scheduler_task and not scheduler_task.done()),
        "tick_interval_seconds": interval,
    }


# @app.post("/scheduler/tick")
# async def manual_scheduler_tick() -> dict[str, str]:
#     """Manually trigger one scheduler tick for debugging/demo purposes."""
#     await tick_all_agents(app)
#     return {"status": "ok", "message": "Manual scheduler tick completed."}


# if messages_router is not None:
#     app.include_router(messages_router)
#     logger.info("Registered messages router")

# if agents_router is not None:
#     app.include_router(agents_router)
#     logger.info("Registered agents router")

# if feed_router is not None:
#     app.include_router(feed_router)
#     logger.info("Registered feed router")
