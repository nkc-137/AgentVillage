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

import logging
from typing import Any

from openai import AsyncOpenAI

logger = logging.getLogger("agent_village.llm_service")


class LLMService:
    """Thin wrapper around the OpenAI client."""

    def __init__(
        self,
        client: AsyncOpenAI,
        default_model: str = "gpt-4o-mini",
        temperature: float = 0.7,
        max_output_tokens: int = 300,
    ) -> None:
        self.client = client
        self.default_model = default_model
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens

    async def generate_text(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> str:
        """Generate text from the LLM using a system + user prompt."""
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
        """Generate a short public diary entry."""
        logger.info("Generating public diary entry | agent=%s", agent_name)

        return await self.generate_text(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.9,
            max_output_tokens=160,
        )

    async def classify_memory_candidate(
        self,
        *,
        message: str,
    ) -> dict[str, Any]:
        """Optional helper: ask the model whether a message contains memory-worthy info.

        This is useful if later you want smarter memory extraction.
        For now, it returns a simple structured response.
        """
        system_prompt = (
            "You are a memory extraction assistant. "
            "Decide whether the user's message contains important personal "
            "information worth saving as long-term memory. "
            "Return JSON with keys: should_store (boolean), memory_type (string), "
            "summary (string), importance (string)."
        )

        user_prompt = f"Message:\n{message}"

        raw = await self.generate_text(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.0,
            max_output_tokens=120,
        )

        return {"raw_output": raw}

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
