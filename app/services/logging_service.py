"""Centralized logging configuration for Agent Village.

Usage:
    from app.services.logging_service import get_logger

    logger = get_logger(__name__)
    logger.info("Something happened")

Call `setup_logging()` once at application startup (in main.py lifespan)
to configure the root logger format and level.
"""

from __future__ import annotations

import logging
import sys

LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
DEFAULT_LEVEL = logging.INFO
ROOT_LOGGER_NAME = "agent_village"

_initialized = False


def setup_logging(level: int = DEFAULT_LEVEL) -> None:
    """Configure logging for the entire application.

    Should be called once at startup. Safe to call multiple times —
    subsequent calls are no-ops.
    """
    global _initialized
    if _initialized:
        return

    root = logging.getLogger(ROOT_LOGGER_NAME)
    root.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))

    root.addHandler(handler)

    # Prevent duplicate logs from propagating to the root logger
    root.propagate = False

    _initialized = True


def get_logger(name: str) -> logging.Logger:
    """Return a logger under the agent_village namespace.

    Automatically prefixes with 'agent_village.' if not already present,
    so callers can pass __name__ or a short label.

    Examples:
        get_logger(__name__)           -> agent_village.app.services.llm_service
        get_logger("llm_service")      -> agent_village.llm_service
        get_logger("agent_village.x")  -> agent_village.x  (unchanged)
    """
    if name.startswith(ROOT_LOGGER_NAME):
        return logging.getLogger(name)
    return logging.getLogger(f"{ROOT_LOGGER_NAME}.{name}")
