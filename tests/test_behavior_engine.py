"""Tests for the proactive behavior engine.

Verifies that agents decide when to act based on logic
(time gaps, probability, time of day) — not just random timers.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.services.behavior_service import (
    ACTIVITY_PROBABILITY,
    DIARY_PROBABILITY,
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
