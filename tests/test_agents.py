"""Tests for agent CRUD and bootstrap personality.

Verifies:
- List agents endpoint
- Get single agent
- Create agent triggers LLM personality bootstrap
- Update agent
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from tests.conftest import ALL_AGENTS, LUNA, make_mock_db, make_mock_llm


class TestListAgents:
    def test_list_returns_all_agents(self, client):
        resp = client.get("/agents")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == len(ALL_AGENTS)
        names = {a["name"] for a in data}
        assert "Luna" in names
        assert "Bolt" in names


class TestGetAgent:
    def test_get_existing_agent(self, client):
        resp = client.get(f"/agents/{LUNA['id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Luna"
        assert data["bio"] == LUNA["bio"]

    def test_get_nonexistent_agent_returns_404(self, client):
        resp = client.get("/agents/nonexistent-id")
        assert resp.status_code == 404


class TestCreateAgent:
    def test_create_agent_with_name_only_triggers_bootstrap(self, client, mock_llm):
        """When only a name is provided, LLM should bootstrap personality."""
        mock_llm.generate_text = AsyncMock(
            return_value='{"bio": "A fiery spirit", "visitor_bio": "Welcome!", '
            '"status": "Warming up", "showcase_emoji": "🔥", '
            '"accent_color": "#ff4500", '
            '"first_diary_entry": "Just arrived in the village!"}'
        )
        resp = client.post("/agents", json={"name": "Ember"})
        assert resp.status_code == 201
        # LLM should have been called to bootstrap
        mock_llm.generate_text.assert_called_once()

    def test_create_agent_with_bio_skips_bootstrap(self, client, mock_llm):
        """When bio is provided, LLM bootstrap should be skipped."""
        resp = client.post(
            "/agents",
            json={"name": "Frost", "bio": "An icy observer of the world."},
        )
        assert resp.status_code == 201
        mock_llm.generate_text.assert_not_called()

    def test_created_agent_has_api_key(self, client, mock_llm):
        mock_llm.generate_text = AsyncMock(return_value='{}')
        resp = client.post("/agents", json={"name": "Nova"})
        assert resp.status_code == 201
        data = resp.json()
        assert "api_key" in data
        assert data["api_key"].startswith("agent-")


class TestUpdateAgent:
    def test_update_agent_status(self, client):
        resp = client.patch(
            f"/agents/{LUNA['id']}",
            json={"status": "Sleeping under the stars"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "Sleeping under the stars"

    def test_update_with_no_fields_returns_400(self, client):
        resp = client.patch(f"/agents/{LUNA['id']}", json={})
        assert resp.status_code == 400
