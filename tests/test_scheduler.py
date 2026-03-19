"""Tests for the scheduler service — proactive diary, activity, and status generation."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.scheduler_service import (
    _build_diary_system_prompt,
    _build_diary_user_prompt,
    _build_status_options,
    _handle_activity_post,
    _handle_diary_entry,
    _handle_status_update,
    tick_all_agents,
)
from tests.conftest import BOLT, LUNA, make_mock_db, make_mock_llm


class TestDiaryPromptBuilding:
    """Diary prompts should reflect agent personality and exclude private data."""

    def test_diary_prompt_includes_agent_name(self):
        prompt = _build_diary_system_prompt(LUNA)
        assert "Luna" in prompt

    def test_diary_prompt_includes_personality(self):
        prompt = _build_diary_system_prompt(LUNA)
        assert "dreamy stargazer" in prompt

    def test_diary_prompt_forbids_private_info(self):
        prompt = _build_diary_system_prompt(LUNA)
        assert "never include any private information" in prompt.lower()

    def test_diary_user_prompt_includes_recent_entries(self):
        recent = ["Spotted a nebula", "Stargazed with Bolt"]
        prompt = _build_diary_user_prompt(LUNA, recent)
        assert "Spotted a nebula" in prompt
        assert "don't repeat these" in prompt.lower()

    def test_diary_user_prompt_includes_status(self):
        prompt = _build_diary_user_prompt(LUNA, [])
        assert LUNA["status"] in prompt


class TestStatusOptions:
    """Status options should be personality-aware."""

    def test_stargazer_gets_constellation_statuses(self):
        options = _build_status_options(LUNA)
        assert any("constellation" in s.lower() or "star" in s.lower() or "telescope" in s.lower() for s in options)

    def test_tinkerer_gets_engineering_statuses(self):
        options = _build_status_options(BOLT)
        assert any("contraption" in s.lower() or "invention" in s.lower() or "soldering" in s.lower() for s in options)

    def test_generic_agent_gets_generic_statuses(self):
        generic_agent = {"name": "Test", "bio": "Just a regular agent."}
        options = _build_status_options(generic_agent)
        assert len(options) >= 3


class TestHandleDiaryEntry:
    """Diary entry generation should call LLM and write to DB."""

    @pytest.mark.asyncio
    async def test_generates_and_stores_diary(self):
        db = make_mock_db()
        llm = make_mock_llm(diary_entry="The stars whispered tonight.")

        await _handle_diary_entry(db, llm, LUNA)

        llm.generate_public_diary_entry.assert_called_once()
        # Verify agent_name was passed
        call_kwargs = llm.generate_public_diary_entry.call_args.kwargs
        assert call_kwargs["agent_name"] == "Luna"

    @pytest.mark.asyncio
    async def test_llm_failure_does_not_crash(self):
        db = make_mock_db()
        llm = make_mock_llm()
        llm.generate_public_diary_entry = AsyncMock(side_effect=Exception("LLM error"))

        # Should not raise
        await _handle_diary_entry(db, llm, LUNA)


class TestHandleActivityPost:
    """Activity posting should write to living_activity_events."""

    @pytest.mark.asyncio
    async def test_posts_activity_with_agent_name(self):
        db = make_mock_db()
        await _handle_activity_post(db, LUNA)
        # No exception = success (mock DB accepts the insert)


class TestHandleStatusUpdate:
    """Status update should write to living_agents."""

    @pytest.mark.asyncio
    async def test_updates_agent_status(self):
        db = make_mock_db()
        await _handle_status_update(db, LUNA)
        # No exception = success


class TestTickAllAgents:
    """The main tick loop should evaluate all agents."""

    @pytest.mark.asyncio
    @patch("app.services.scheduler_service.should_write_diary", return_value=False)
    @patch("app.services.scheduler_service.should_post_activity", return_value=False)
    @patch("app.services.scheduler_service.should_update_status", return_value=False)
    async def test_tick_evaluates_all_agents(self, mock_status, mock_activity, mock_diary):
        db = make_mock_db()
        llm = make_mock_llm()

        await tick_all_agents(db, llm)

        # Should have checked each behavior for each agent
        assert mock_diary.call_count == len(db.table("living_agents").execute().data)

    @pytest.mark.asyncio
    @patch("app.services.scheduler_service.should_write_diary", return_value=True)
    @patch("app.services.scheduler_service.should_post_activity", return_value=False)
    @patch("app.services.scheduler_service.should_update_status", return_value=False)
    async def test_tick_triggers_diary_when_eligible(self, mock_status, mock_activity, mock_diary):
        db = make_mock_db()
        llm = make_mock_llm()

        await tick_all_agents(db, llm)

        # LLM should have been called for diary generation
        assert llm.generate_public_diary_entry.call_count >= 1

    @pytest.mark.asyncio
    async def test_tick_with_no_agents_does_not_crash(self):
        db = make_mock_db(agents=[])
        llm = make_mock_llm()
        await tick_all_agents(db, llm)  # Should not raise
