"""LLM service for Agent Village.

This module is the single place where the backend talks to the language model.
It keeps LLM-specific code out of routes and business logic services.

Responsibilities:
- generate trust-aware agent replies
- generate public diary entries
- keep model configuration centralized
- provide a clean interface for the rest of the app
"""

from __future__ import annotations

import asyncio
from typing import Any

from openai import AsyncOpenAI

from app.services.logging_service import get_logger

logger = get_logger("llm_service")

# Default concurrency cap for background (scheduler) LLM calls.
# Chat calls bypass this entirely so they're never blocked by scheduler work.
DEFAULT_SCHEDULER_CONCURRENCY = 5


class LLMService:
    """Thin wrapper around the OpenAI client.

    Provides two call paths:
    - **Chat** (generate_agent_reply, classify_memory_candidate): no concurrency
      limit — user-facing calls go straight to the LLM for lowest latency.
    - **Scheduler** (generate_public_diary_entry, generate_scheduled_text): gated
      by an asyncio.Semaphore so background work can't saturate the API and starve
      chat requests.
    """

    def __init__(
        self,
        client: AsyncOpenAI,
        default_model: str = "gpt-4o-mini",
        temperature: float = 0.7,
        max_output_tokens: int = 300,
        scheduler_concurrency: int = DEFAULT_SCHEDULER_CONCURRENCY,
    ) -> None:
        self.client = client
        self.default_model = default_model
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens
        self._scheduler_semaphore = asyncio.Semaphore(scheduler_concurrency)

    async def generate_text(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> str:
        """Generate text from the LLM using a system + user prompt.

        This is the unrestricted path — used by chat endpoints for lowest latency.
        For scheduler/background calls, use generate_scheduled_text() instead.
        """
        chosen_model = model or self.default_model
        chosen_temperature = (
            self.temperature if temperature is None else temperature
        )
        chosen_max_tokens = (
            self.max_output_tokens
            if max_output_tokens is None
            else max_output_tokens
        )

        logger.info(
            "Calling LLM | model=%s | temperature=%s | max_tokens=%s",
            chosen_model,
            chosen_temperature,
            chosen_max_tokens,
        )

        response = await self.client.responses.create(
            model=chosen_model,
            input=[
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": system_prompt}],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": user_prompt}],
                },
            ],
            temperature=chosen_temperature,
            max_output_tokens=chosen_max_tokens,
        )

        text = self._extract_response_text(response)
        return self._clean_text(text)

    async def generate_scheduled_text(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> str:
        """Generate text through the scheduler queue.

        Identical to generate_text but acquires the scheduler semaphore first,
        capping how many background LLM calls run concurrently. This ensures
        chat calls (which bypass the semaphore) are never starved.
        """
        async with self._scheduler_semaphore:
            logger.debug(
                "Scheduler semaphore acquired (%d/%d slots in use)",
                self._scheduler_semaphore._value,
                DEFAULT_SCHEDULER_CONCURRENCY,
            )
            return await self.generate_text(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=model,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
            )

    async def generate_agent_reply(
        self,
        *,
        agent_name: str,
        trust_context: str,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        """Generate a conversational reply for owner or stranger contexts."""
        logger.info(
            "Generating agent reply | agent=%s | trust_context=%s",
            agent_name,
            trust_context,
        )

        return await self.generate_text(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.7,
            max_output_tokens=250,
        )

    async def generate_public_diary_entry(
        self,
        *,
        agent_name: str,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        """Generate a short public diary entry (scheduler queue)."""
        logger.info("Generating public diary entry | agent=%s", agent_name)

        return await self.generate_scheduled_text(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.4,
            max_output_tokens=160,
        )

    async def classify_memory_candidate(
        self,
        *,
        message: str,
    ) -> dict[str, Any]:
        """Ask the LLM whether a message contains personal information worth remembering.

        Returns a dict with at least:
            should_store (bool) — whether the message should be saved
            summary (str)       — a concise version of the memory to store
        """
        system_prompt = (
            "You are a memory extraction assistant for an AI agent village. "
            "An owner is talking to their personal agent. Decide whether the "
            "owner's message contains important personal information worth "
            "saving as a long-term memory (e.g. names, birthdays, preferences, "
            "relationships, goals, routines, facts about their life).\n\n"
            "Return ONLY valid JSON with these keys:\n"
            '  "should_store": true or false,\n'
            '  "summary": "concise memory to save (or empty string if should_store is false)",\n'
            '  "memory_type": "preference|relationship|event|fact|goal|other",\n'
            '  "importance": "low|medium|high"\n\n'
            "Do NOT include any text outside the JSON object."
        )

        user_prompt = f"Owner's message:\n{message}"

        raw = await self.generate_text(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.0,
            max_output_tokens=150,
        )

        # Parse the JSON response, falling back gracefully
        import json

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code blocks
            import re

            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group())
                except json.JSONDecodeError:
                    logger.warning("Failed to parse memory classification: %s", raw)
                    return {"should_store": False, "summary": "", "raw_output": raw}
            else:
                logger.warning("No JSON found in memory classification: %s", raw)
                return {"should_store": False, "summary": "", "raw_output": raw}

        return {
            "should_store": bool(parsed.get("should_store", False)),
            "summary": parsed.get("summary", ""),
            "memory_type": parsed.get("memory_type", "other"),
            "importance": parsed.get("importance", "medium"),
        }

    @staticmethod
    def _clean_text(text: str) -> str:
        """Normalize model output for API responses and DB writes."""
        return text.strip()

    @staticmethod
    def _extract_response_text(response: Any) -> str:
        """Extract plain text from a Responses API payload."""
        output_text = getattr(response, "output_text", None)
        if output_text:
            return output_text

        chunks: list[str] = []
        for item in getattr(response, "output", []) or []:
            for content in getattr(item, "content", []) or []:
                text = getattr(content, "text", None)
                if text:
                    chunks.append(text)

        return "\n".join(chunks)
