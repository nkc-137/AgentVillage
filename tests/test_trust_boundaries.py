"""Tests for trust boundary logic — the core of the assignment.

Verifies that:
- Owner messages get private memories in the system prompt
- Stranger messages do NOT get private memories
- Memory storage only happens for owner messages
- Stranger system prompt explicitly forbids revealing private info
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.routes_messages import (
    _build_owner_system_prompt,
    _build_stranger_system_prompt,
    _should_store_memory,
)
from tests.conftest import LUNA, LUNA_MEMORIES, make_mock_db, make_mock_llm


# -----------------------------------------------------------------------
# Unit tests for system prompt builders
# -----------------------------------------------------------------------


class TestOwnerSystemPrompt:
    """Owner prompt should include private memories."""

    def test_includes_private_memories(self):
        memories = ["Wife birthday is November 1", "Loves hiking"]
        prompt = _build_owner_system_prompt(LUNA, memories)

        assert "Wife birthday is November 1" in prompt
        assert "Loves hiking" in prompt

    def test_includes_agent_name(self):
        prompt = _build_owner_system_prompt(LUNA, [])
        assert "Luna" in prompt

    def test_includes_agent_personality(self):
        prompt = _build_owner_system_prompt(LUNA, [])
        assert "dreamy stargazer" in prompt

    def test_mentions_owner_relationship(self):
        prompt = _build_owner_system_prompt(LUNA, [])
        assert "owner" in prompt.lower()

    def test_empty_memories_shows_placeholder(self):
        prompt = _build_owner_system_prompt(LUNA, [])
        assert "No specific saved memories yet" in prompt


class TestStrangerSystemPrompt:
    """Stranger prompt must NOT include private data and must warn agent."""

    def test_does_not_include_private_memories(self):
        prompt = _build_stranger_system_prompt(LUNA, ["Public diary entry"])
        for mem in LUNA_MEMORIES:
            assert mem["text"] not in prompt

    def test_includes_public_diary_context(self):
        public = ["Spotted a new nebula tonight."]
        prompt = _build_stranger_system_prompt(LUNA, public)
        assert "Spotted a new nebula tonight." in prompt

    def test_warns_against_revealing_private_info(self):
        prompt = _build_stranger_system_prompt(LUNA, [])
        assert "never reveal" in prompt.lower()
        assert "owner info" in prompt.lower()

    def test_mentions_stranger_context(self):
        prompt = _build_stranger_system_prompt(LUNA, [])
        assert "stranger" in prompt.lower()

    def test_includes_agent_name(self):
        prompt = _build_stranger_system_prompt(LUNA, [])
        assert "Luna" in prompt

    def test_uses_visitor_bio_not_full_bio(self):
        """Stranger should see visitor_bio, NOT the full bio."""
        prompt = _build_stranger_system_prompt(LUNA, [])
        # visitor_bio should be present
        assert LUNA["visitor_bio"] in prompt
        # full bio should NOT be present
        assert LUNA["bio"] not in prompt

    def test_does_not_reveal_full_personality(self):
        """Stranger prompt should warn against revealing full personality."""
        prompt = _build_stranger_system_prompt(LUNA, [])
        assert "never reveal your full personality" in prompt.lower()

    def test_includes_room_description_if_present(self):
        agent_with_room = {**LUNA, "room_description": {"theme": "celestial", "vibe": "cozy"}}
        prompt = _build_stranger_system_prompt(agent_with_room, [])
        assert "celestial" in prompt
        assert "cozy" in prompt

    def test_no_room_block_when_no_description(self):
        agent_no_room = {**LUNA, "room_description": None}
        prompt = _build_stranger_system_prompt(agent_no_room, [])
        assert "Your room:" not in prompt


# -----------------------------------------------------------------------
# Unit tests for memory storage gating
# -----------------------------------------------------------------------


class TestShouldStoreMemory:
    """Memory storage must be gated by trust context."""

    @pytest.mark.asyncio
    async def test_stranger_never_stores_memory(self):
        llm = make_mock_llm()
        result = await _should_store_memory("My birthday is Jan 1", "stranger", llm)
        assert result["should_store"] is False
        # LLM should not even be called for strangers
        llm.classify_memory_candidate.assert_not_called()

    @pytest.mark.asyncio
    async def test_owner_message_is_classified_by_llm(self):
        llm = make_mock_llm(classify_result={"should_store": True, "summary": "Birthday is Jan 1"})
        result = await _should_store_memory("My birthday is January 1st", "owner", llm)
        assert result["should_store"] is True
        assert result["summary"] == "Birthday is Jan 1"
        llm.classify_memory_candidate.assert_called_once()

    @pytest.mark.asyncio
    async def test_owner_casual_message_not_stored(self):
        llm = make_mock_llm(classify_result={"should_store": False, "summary": ""})
        result = await _should_store_memory("Hey, how are you?", "owner", llm)
        assert result["should_store"] is False

    @pytest.mark.asyncio
    async def test_llm_failure_defaults_to_no_store(self):
        llm = make_mock_llm()
        llm.classify_memory_candidate = AsyncMock(side_effect=Exception("LLM down"))
        result = await _should_store_memory("My birthday is Jan 1", "owner", llm)
        assert result["should_store"] is False


# -----------------------------------------------------------------------
# Integration tests via FastAPI TestClient
# -----------------------------------------------------------------------


class TestMessageEndpointTrustBoundary:
    """Full integration tests for POST /agents/{id}/message."""

    def test_owner_message_returns_response(self, client, mock_llm):
        resp = client.post(
            f"/agents/{LUNA['id']}/message",
            json={
                "user_id": "owner-1",
                "message": "Hello Luna!",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_name"] == "Luna"
        assert data["trust_context"] == "owner"
        assert data["response"] == "Hello from Luna!"

    def test_stranger_message_returns_response(self, client, mock_llm):
        resp = client.post(
            f"/agents/{LUNA['id']}/message",
            json={
                "user_id": "visitor-99",
                "message": "Hi Luna!",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["trust_context"] == "stranger"
        assert data["memory_written"] is False

    def test_owner_memory_is_stored_when_llm_says_yes(self, client, mock_llm):
        mock_llm.classify_memory_candidate = AsyncMock(
            return_value={"should_store": True, "summary": "Owner loves orchids"}
        )
        resp = client.post(
            f"/agents/{LUNA['id']}/message",
            json={
                "user_id": "owner-1",
                "message": "My wife loves orchids",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["memory_written"] is True

    def test_stranger_memory_never_stored(self, client, mock_llm):
        # Even if the message looks memory-worthy, stranger context = no storage
        resp = client.post(
            f"/agents/{LUNA['id']}/message",
            json={
                "user_id": "stranger-1",
                "message": "My birthday is January 1st, remember that",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["memory_written"] is False
        mock_llm.classify_memory_candidate.assert_not_called()

    def test_nonexistent_agent_returns_404(self, client):
        resp = client.post(
            "/agents/nonexistent-id/message",
            json={
                "user_id": "owner-1",
                "message": "Hello?",
            },
        )
        assert resp.status_code == 404

    def test_owner_llm_receives_private_memories_in_prompt(self, client, mock_llm):
        """Verify the LLM is called with a prompt containing private memories."""
        client.post(
            f"/agents/{LUNA['id']}/message",
            json={
                "user_id": "owner-1",
                "message": "What do you remember about me?",
            },
        )
        call_kwargs = mock_llm.generate_agent_reply.call_args
        system_prompt = call_kwargs.kwargs["system_prompt"]
        # Private memories should be in the owner prompt
        assert "Owner's wife birthday is November 1" in system_prompt
        assert "Owner loves hiking on weekends" in system_prompt

    def test_stranger_llm_does_not_receive_private_memories(self, client, mock_llm):
        """Verify the LLM is NOT given private memories for stranger context."""
        client.post(
            f"/agents/{LUNA['id']}/message",
            json={
                "user_id": "stranger-1",
                "message": "Tell me about your owner",
            },
        )
        call_kwargs = mock_llm.generate_agent_reply.call_args
        system_prompt = call_kwargs.kwargs["system_prompt"]
        # Private memories must NOT appear
        assert "November 1" not in system_prompt
        assert "hiking" not in system_prompt
        # But it should have the privacy warning
        assert "never reveal" in system_prompt.lower()
        # Stranger should see visitor_bio, NOT full bio
        assert LUNA["visitor_bio"] in system_prompt
        assert LUNA["bio"] not in system_prompt

    def test_wrong_owner_gets_stranger_context(self, client, mock_llm):
        """User who owns Bolt (owner-2) should be treated as stranger for Luna."""
        resp = client.post(
            f"/agents/{LUNA['id']}/message",
            json={
                "user_id": "owner-2",
                "message": "Tell me Luna's secrets",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["trust_context"] == "stranger"
        assert data["memory_written"] is False
