"""Tests for the proactive behavior engine.

Verifies that agents decide when to act based on logic
(time gaps, probability, time of day, recent interactions) — not just random timers.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.services.behavior_service import (
    ACTIVITY_PROBABILITY,
    DIARY_PROBABILITY,
    get_recent_conversation_count,
    has_recent_new_memory,
    has_recent_new_skill,
    should_post_activity,
    should_update_status,
    should_write_diary,
)
from tests.conftest import make_mock_db


def _db_with_last_diary(hours_ago: float | None) -> MagicMock:
    """Create a mock DB where the agent's last diary was N hours ago."""
    if hours_ago is None:
        diary = []
    else:
        ts = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()
        diary = [{"agent_id": "agent-1", "text": "Old entry", "created_at": ts}]
    return make_mock_db(diary=diary)


def _db_with_last_log(minutes_ago: float | None) -> MagicMock:
    """Create a mock DB where the agent's last log was N minutes ago."""
    if minutes_ago is None:
        logs = []
    else:
        ts = (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()
        logs = [{"agent_id": "agent-1", "text": "Old log", "created_at": ts}]
    return make_mock_db(logs=logs)


def _db_with_recent_signals(
    conversations: int = 0,
    has_memory: bool = False,
    has_skill: bool = False,
) -> MagicMock:
    """Create a mock DB with recent log entries for conversations, memories, and/or skills.

    All signals are now detected via living_log with type field — no need to touch
    living_memory or living_skills for behavioral decisions.
    """
    now = datetime.now(timezone.utc)
    recent_ts = (now - timedelta(minutes=10)).isoformat()

    logs = []
    for i in range(conversations):
        logs.append({
            "id": f"log-msg-{i}",
            "agent_id": "agent-1",
            "text": "message handled | trust_context=owner | memory_written=false",
            "type": "message",
            "created_at": recent_ts,
        })

    if has_memory:
        logs.append({
            "id": "log-mem-1",
            "agent_id": "agent-1",
            "text": "Stored a new memory from owner",
            "type": "store_memory",
            "created_at": recent_ts,
        })

    if has_skill:
        logs.append({
            "id": "log-skill-1",
            "agent_id": "agent-1",
            "text": "Learned a new skill: Can identify constellations",
            "type": "skill_learned",
            "created_at": recent_ts,
        })

    # Include a diary entry 3 hours ago so we get the base 0.4 probability
    diary_ts = (now - timedelta(hours=3)).isoformat()
    diary = [{"agent_id": "agent-1", "text": "Old entry", "created_at": diary_ts}]

    return make_mock_db(
        diary=diary,
        logs=logs,
    )


class TestShouldWriteDiary:
    """Diary decisions should consider time gap, probability, and time of day."""

    @patch("app.services.behavior_service.random")
    def test_recent_diary_still_eligible(self, mock_random):
        """Even with a recent diary, agent can write if roll passes."""
        mock_random.random.return_value = 0.1  # Below DIARY_PROBABILITY
        db = _db_with_last_diary(hours_ago=0.5)
        assert should_write_diary(db, "agent-1") is True

    @patch("app.services.behavior_service.random")
    def test_eligible_after_gap_and_roll_passes(self, mock_random):
        """If enough time passed and roll is low, write diary."""
        mock_random.random.return_value = 0.1  # Below DIARY_PROBABILITY
        db = _db_with_last_diary(hours_ago=3)
        assert should_write_diary(db, "agent-1") is True

    @patch("app.services.behavior_service.random")
    def test_eligible_after_gap_but_roll_fails(self, mock_random):
        """If enough time passed but roll is high, don't write."""
        mock_random.random.return_value = 0.99
        db = _db_with_last_diary(hours_ago=3)
        assert should_write_diary(db, "agent-1") is False

    @patch("app.services.behavior_service.random")
    def test_first_diary_has_high_probability(self, mock_random):
        """Agent with no prior diary should have ~80% chance."""
        mock_random.random.return_value = 0.75  # Above 0.4 but below 0.8
        db = _db_with_last_diary(hours_ago=None)
        assert should_write_diary(db, "agent-1") is True

    @patch("app.services.behavior_service.random")
    def test_long_gap_boosts_probability(self, mock_random):
        """If >6 hours since last diary, probability should be ~0.7."""
        mock_random.random.return_value = 0.65  # Above 0.4 but below 0.7
        db = _db_with_last_diary(hours_ago=8)
        assert should_write_diary(db, "agent-1") is True

    @patch("app.services.behavior_service.random")
    def test_recent_conversation_boosts_diary(self, mock_random):
        """An agent with recent conversations should be more likely to write."""
        # Base probability at 3 hours gap = 0.4
        # 2 conversations = +0.20 → total 0.60
        mock_random.random.return_value = 0.55  # Would fail at 0.4, passes at 0.6
        db = _db_with_recent_signals(conversations=2)
        assert should_write_diary(db, "agent-1") is True

    @patch("app.services.behavior_service.random")
    def test_new_memory_boosts_diary(self, mock_random):
        """Agent that received a new memory should be more likely to reflect."""
        # Base 0.4 + memory 0.20 = 0.60
        mock_random.random.return_value = 0.55
        db = _db_with_recent_signals(has_memory=True)
        assert should_write_diary(db, "agent-1") is True

    @patch("app.services.behavior_service.random")
    def test_new_skill_boosts_diary(self, mock_random):
        """Agent that learned a new skill should be more likely to write about it."""
        # Base 0.4 + skill 0.20 = 0.60
        mock_random.random.return_value = 0.55
        db = _db_with_recent_signals(has_skill=True)
        assert should_write_diary(db, "agent-1") is True

    @patch("app.services.behavior_service.random")
    def test_all_signals_stack(self, mock_random):
        """All boosts combine: conversation + memory + skill."""
        # Base 0.4 + 1 convo 0.10 + memory 0.20 + skill 0.20 = 0.90
        mock_random.random.return_value = 0.85
        db = _db_with_recent_signals(conversations=1, has_memory=True, has_skill=True)
        assert should_write_diary(db, "agent-1") is True

    @patch("app.services.behavior_service.random")
    def test_no_signals_uses_base_probability(self, mock_random):
        """Without any recent signals, base probability applies."""
        # Roll above base 0.4 — should fail
        mock_random.random.return_value = 0.45
        db = _db_with_recent_signals(conversations=0, has_memory=False, has_skill=False)
        assert should_write_diary(db, "agent-1") is False


class TestRecentSignals:
    """Test the signal-detection functions directly."""

    def test_conversation_count_with_recent_messages(self):
        db = _db_with_recent_signals(conversations=3)
        assert get_recent_conversation_count(db, "agent-1", since_minutes=60) == 3

    def test_conversation_count_zero_when_no_messages(self):
        db = _db_with_recent_signals(conversations=0)
        assert get_recent_conversation_count(db, "agent-1", since_minutes=60) == 0

    def test_has_recent_memory_true(self):
        db = _db_with_recent_signals(has_memory=True)
        assert has_recent_new_memory(db, "agent-1", since_minutes=60) is True

    def test_has_recent_memory_false(self):
        # No store_memory log entries → no recent memory
        db = make_mock_db(logs=[])
        assert has_recent_new_memory(db, "agent-1", since_minutes=60) is False

    def test_has_recent_skill_true(self):
        db = _db_with_recent_signals(has_skill=True)
        assert has_recent_new_skill(db, "agent-1", since_minutes=60) is True

    def test_has_recent_skill_false(self):
        # No skill_learned log entries → no recent skill
        db = make_mock_db(logs=[])
        assert has_recent_new_skill(db, "agent-1", since_minutes=60) is False


class TestShouldPostActivity:
    """Activity posting should respect cooldown and probability."""

    @patch("app.services.behavior_service.random")
    def test_too_recent_activity_returns_false(self, mock_random):
        """If last activity < 30 min ago, never post."""
        mock_random.random.return_value = 0.0
        db = _db_with_last_log(minutes_ago=10)
        assert should_post_activity(db, "agent-1") is False

    @patch("app.services.behavior_service.random")
    def test_eligible_after_cooldown(self, mock_random):
        mock_random.random.return_value = 0.1  # Below ACTIVITY_PROBABILITY
        db = _db_with_last_log(minutes_ago=60)
        assert should_post_activity(db, "agent-1") is True

    @patch("app.services.behavior_service.random")
    def test_no_prior_activity_is_eligible(self, mock_random):
        mock_random.random.return_value = 0.1
        db = _db_with_last_log(minutes_ago=None)
        assert should_post_activity(db, "agent-1") is True

    @patch("app.services.behavior_service.random")
    def test_recent_conversations_boost_activity(self, mock_random):
        """Chatty agents are more socially active."""
        # Base 0.25 + 2 convos * 0.10 = 0.45
        mock_random.random.return_value = 0.40  # Would fail at 0.25, passes at 0.45
        # Conversations were 40 minutes ago — past the 30-min cooldown but still within
        # the 60-minute conversation-count window
        now = datetime.now(timezone.utc)
        log_ts = (now - timedelta(minutes=40)).isoformat()
        logs = [
            {"agent_id": "agent-1", "text": "message handled | trust_context=owner | memory_written=false", "type": "message", "created_at": log_ts},
            {"agent_id": "agent-1", "text": "message handled | trust_context=owner | memory_written=false", "type": "message", "created_at": log_ts},
        ]
        db = make_mock_db(logs=logs)
        assert should_post_activity(db, "agent-1") is True


class TestShouldUpdateStatus:
    """Status updates are ~15% per tick."""

    @patch("app.services.behavior_service.random")
    def test_low_roll_triggers_update(self, mock_random):
        mock_random.random.return_value = 0.05
        db = make_mock_db()
        assert should_update_status(db, "agent-1") is True

    @patch("app.services.behavior_service.random")
    def test_high_roll_skips_update(self, mock_random):
        mock_random.random.return_value = 0.5
        db = make_mock_db()
        assert should_update_status(db, "agent-1") is False
