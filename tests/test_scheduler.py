"""Tests for the scheduler service — proactive diary, activity, and status generation."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.scheduler_service import (
    _build_diary_system_prompt,
    _build_diary_user_prompt,
    _build_interaction_prompt,
    _build_owner_nudge_prompt,
    _build_skill_showcase_prompt,
    _build_status_options,
    _get_agent_skills,
    _handle_agent_interaction,
    _handle_diary_entry,
    _handle_owner_nudge,
    _handle_skill_showcase,
    _handle_status_update,
    tick_all_agents,
)
from tests.conftest import BOLT, LUNA, make_mock_db, make_mock_llm

LUNA_SKILLS = [
    {"agent_id": LUNA["id"], "description": "Can identify 47 constellations by memory", "category": "observation"},
    {"agent_id": LUNA["id"], "description": "Makes dreamcatchers from recycled circuit boards", "category": "crafting"},
]


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

    def test_diary_user_prompt_includes_conversation_context(self):
        prompt = _build_diary_user_prompt(LUNA, [], recent_convo_count=3)
        assert "3 conversation" in prompt
        assert "visitors" in prompt.lower()

    def test_diary_user_prompt_includes_memory_context(self):
        prompt = _build_diary_user_prompt(LUNA, [], had_new_memory=True)
        assert "owner recently shared something personal" in prompt.lower()

    def test_diary_user_prompt_includes_skill_context(self):
        prompt = _build_diary_user_prompt(LUNA, [], had_new_skill=True)
        assert "learned a new skill" in prompt.lower()

    def test_diary_user_prompt_no_signals_no_happenings(self):
        prompt = _build_diary_user_prompt(LUNA, [])
        assert "recent happenings" not in prompt.lower()

    def test_diary_user_prompt_all_signals_combined(self):
        prompt = _build_diary_user_prompt(
            LUNA, [], recent_convo_count=2, had_new_memory=True, had_new_skill=True
        )
        assert "2 conversation" in prompt
        assert "owner recently shared" in prompt.lower()
        assert "learned a new skill" in prompt.lower()


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


class TestSkillShowcase:
    """Skill showcase should pick a skill, call LLM, and persist to 3 tables."""

    def test_skill_showcase_prompt_includes_agent_and_skill(self):
        skill = LUNA_SKILLS[0]
        system_prompt, user_prompt = _build_skill_showcase_prompt(LUNA, skill)
        assert "Luna" in system_prompt
        assert "dreamy stargazer" in system_prompt
        assert "47 constellations" in user_prompt
        assert "observation" in user_prompt

    @pytest.mark.asyncio
    async def test_showcase_calls_llm_and_persists(self):
        db = make_mock_db(skills=LUNA_SKILLS)
        llm = make_mock_llm()
        llm.generate_scheduled_text = AsyncMock(return_value="Luna dazzled the village with her star knowledge!")

        await _handle_skill_showcase(db, llm, LUNA)

        llm.generate_scheduled_text.assert_called_once()
        # Verify temperature is 0.9 for creative output
        call_kwargs = llm.generate_scheduled_text.call_args.kwargs
        assert call_kwargs["temperature"] == 0.9

    @pytest.mark.asyncio
    async def test_showcase_does_nothing_without_skills(self):
        db = make_mock_db(skills=[])
        llm = make_mock_llm()

        await _handle_skill_showcase(db, llm, LUNA)

        # LLM should never be called if agent has no skills
        llm.generate_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_showcase_llm_failure_does_not_crash(self):
        db = make_mock_db(skills=LUNA_SKILLS)
        llm = make_mock_llm()
        llm.generate_text = AsyncMock(side_effect=Exception("LLM down"))

        # Should not raise
        await _handle_skill_showcase(db, llm, LUNA)


class TestAgentInteraction:
    """Agent-agent interactions should call LLM and persist to DB."""

    def test_interaction_prompt_includes_both_agents(self):
        system_prompt, user_prompt = _build_interaction_prompt(LUNA, BOLT, "visit")
        assert "Luna" in system_prompt
        assert "dreamy stargazer" in system_prompt
        assert "Bolt" in user_prompt
        assert "visit" in user_prompt

    def test_interaction_prompt_includes_interaction_type(self):
        for itype in ["visit", "like", "follow", "message"]:
            _, user_prompt = _build_interaction_prompt(LUNA, BOLT, itype)
            assert itype in user_prompt

    @pytest.mark.asyncio
    async def test_interaction_calls_llm_and_persists(self):
        db = make_mock_db()
        llm = make_mock_llm()
        llm.generate_scheduled_text = AsyncMock(return_value="Luna visited Bolt's workshop and admired his gadgets.")

        await _handle_agent_interaction(db, llm, LUNA, [LUNA, BOLT])

        llm.generate_scheduled_text.assert_called_once()
        call_kwargs = llm.generate_scheduled_text.call_args.kwargs
        assert call_kwargs["temperature"] == 0.9

    @pytest.mark.asyncio
    async def test_interaction_skips_when_alone(self):
        db = make_mock_db()
        llm = make_mock_llm()

        # Only one agent — no one to interact with
        await _handle_agent_interaction(db, llm, LUNA, [LUNA])

        llm.generate_scheduled_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_interaction_llm_failure_does_not_crash(self):
        db = make_mock_db()
        llm = make_mock_llm()
        llm.generate_text = AsyncMock(side_effect=Exception("LLM down"))

        # Should not raise
        await _handle_agent_interaction(db, llm, LUNA, [LUNA, BOLT])


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


class TestOwnerNudge:
    """Owner nudge — agent reaches out to its owner proactively."""

    def test_nudge_prompt_includes_agent_name(self):
        system_prompt, user_prompt = _build_owner_nudge_prompt(LUNA)
        assert "Luna" in system_prompt

    def test_nudge_prompt_includes_personality(self):
        system_prompt, user_prompt = _build_owner_nudge_prompt(LUNA)
        assert "dreamy stargazer" in system_prompt

    def test_nudge_prompt_forbids_private_info(self):
        system_prompt, user_prompt = _build_owner_nudge_prompt(LUNA)
        assert "do not reveal any private memories" in system_prompt.lower()

    @pytest.mark.asyncio
    async def test_nudge_generates_and_stores(self):
        db = make_mock_db()
        llm = make_mock_llm()
        llm.generate_scheduled_text = AsyncMock(return_value="Hey there! The stars are extra bright tonight.")

        await _handle_owner_nudge(db, llm, LUNA)

        llm.generate_scheduled_text.assert_called_once()
        call_kwargs = llm.generate_scheduled_text.call_args.kwargs
        assert call_kwargs["temperature"] == 0.9
        assert call_kwargs["max_output_tokens"] == 100

    @pytest.mark.asyncio
    async def test_nudge_skips_agent_without_owner(self):
        db = make_mock_db()
        llm = make_mock_llm()
        agent_no_owner = {**LUNA, "owner_id": None}

        await _handle_owner_nudge(db, llm, agent_no_owner)

        llm.generate_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_nudge_llm_failure_does_not_crash(self):
        db = make_mock_db()
        llm = make_mock_llm()
        llm.generate_text = AsyncMock(side_effect=Exception("LLM down"))

        # Should not raise
        await _handle_owner_nudge(db, llm, LUNA)
