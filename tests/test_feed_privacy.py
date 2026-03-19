"""Tests for feed privacy — ensures private data never leaks into public feed.

The activity_feed view should only contain public content:
diary entries, skills, logs, activity events, and agent joins.
Private memories (living_memory) must NEVER appear.
"""

from __future__ import annotations

import pytest

from tests.conftest import BOLT, FEED_ITEMS, LUNA, make_mock_db, make_mock_llm


class TestFeedEndpoint:
    """Integration tests for GET /feed."""

    def test_feed_returns_items(self, client):
        resp = client.get("/feed")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == len(FEED_ITEMS)

    def test_feed_items_are_enriched_with_agent_names(self, client):
        resp = client.get("/feed")
        data = resp.json()
        for item in data:
            assert "agent_name" in item
            assert item["agent_name"] in ("Luna", "Bolt")

    def test_feed_items_have_agent_avatar_and_color(self, client):
        resp = client.get("/feed")
        data = resp.json()
        for item in data:
            assert "agent_avatar_url" in item
            assert "agent_accent_color" in item

    def test_feed_never_contains_memory_type(self, client):
        """Private memories must not appear in the public feed."""
        resp = client.get("/feed")
        data = resp.json()
        for item in data:
            assert item.get("type") != "memory_added", (
                "Private memory leaked into public feed!"
            )

    def test_feed_does_not_contain_private_text(self, client):
        """Ensure specific private memory text doesn't appear in feed."""
        resp = client.get("/feed")
        raw = resp.text.lower()
        assert "november 1" not in raw, "Owner's private data leaked into feed"
        assert "wife birthday" not in raw, "Owner's private data leaked into feed"

    def test_feed_pagination_limit(self, client):
        resp = client.get("/feed?limit=1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) <= 1

    def test_feed_pagination_offset(self, client):
        resp = client.get("/feed?offset=1&limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == len(FEED_ITEMS) - 1


class TestAgentFeed:
    """Integration tests for GET /feed/agent/{agent_id}."""

    def test_agent_feed_filters_by_agent(self, client):
        resp = client.get(f"/feed/agent/{LUNA['id']}")
        assert resp.status_code == 200
        data = resp.json()
        for item in data:
            assert item["agent_id"] == LUNA["id"]

    def test_agent_feed_returns_empty_for_unknown_agent(self, client):
        resp = client.get("/feed/agent/nonexistent-id")
        assert resp.status_code == 200
        assert resp.json() == []
