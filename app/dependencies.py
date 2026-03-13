

"""
Shared dependency providers for the FastAPI application.

This module centralizes creation of reusable clients (Supabase, OpenAI)
and configuration access so the rest of the application can import them
through FastAPI dependency injection.
"""

import os
from functools import lru_cache
from typing import Generator

from dotenv import load_dotenv
from supabase import create_client, Client
from openai import AsyncOpenAI

# Load environment variables from .env if present
load_dotenv()


class Settings:
    """Application configuration loaded from environment variables."""

    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_SERVICE_KEY: str = os.getenv("SUPABASE_SERVICE_KEY", "")

    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    AGENT_TICK_INTERVAL_SECONDS: int = int(os.getenv("AGENT_TICK_INTERVAL_SECONDS", "30"))


@lru_cache()
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()


@lru_cache()
def get_supabase_client() -> Client:
    """Create and cache the Supabase client."""
    settings = get_settings()

    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_KEY:
        raise RuntimeError("Supabase configuration is missing.")

    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)


@lru_cache()
def get_openai_client() -> AsyncOpenAI:
    """Create and cache the OpenAI async client."""
    settings = get_settings()

    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set.")

    return AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


def supabase_dependency() -> Generator[Client, None, None]:
    """
    FastAPI dependency for Supabase client.

    Example:
        async def route(client: Client = Depends(supabase_dependency)):
            ...
    """
    yield get_supabase_client()


def openai_dependency() -> Generator[AsyncOpenAI, None, None]:
    """
    FastAPI dependency for OpenAI client.
    """
    yield get_openai_client()