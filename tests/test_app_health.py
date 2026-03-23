"""Tests for app-level endpoints (health, root, force-diary, force-skill-showcase, force-interactions)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from tests.conftest import LUNA, make_mock_db, make_mock_llm


class TestRootEndpoint:
    def test_root_returns_running(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "running"
        assert data["service"] == "agent-village-backend"


class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "scheduler_running" in data
        assert "tick_interval_seconds" in data


class TestForceDiaryEndpoint:
    def test_force_diary_triggers_for_all_agents(self, client, mock_db, mock_llm):
        with (
            patch("app.main.get_supabase_client", return_value=mock_db),
            patch("app.main.get_llm_service", return_value=mock_llm),
        ):
            resp = client.post("/debug/force-diary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "results" in data
        assert len(data["results"]) >= 1
        for result in data["results"]:
            assert result["status"] == "ok"


class TestForceSkillShowcaseEndpoint:
    def test_force_skill_showcase_triggers_for_all_agents(self, client, mock_db, mock_llm):
        with (
            patch("app.main.get_supabase_client", return_value=mock_db),
            patch("app.main.get_llm_service", return_value=mock_llm),
        ):
            resp = client.post("/debug/force-skill-showcase")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "results" in data
        assert len(data["results"]) >= 1
        for result in data["results"]:
            assert result["status"] == "ok"


class TestForceInteractionsEndpoint:
    def test_force_interactions_triggers_for_all_agents(self, client, mock_db, mock_llm):
        with (
            patch("app.main.get_supabase_client", return_value=mock_db),
            patch("app.main.get_llm_service", return_value=mock_llm),
        ):
            resp = client.post("/debug/force-interactions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "results" in data
        assert len(data["results"]) >= 2
        for result in data["results"]:
            assert result["status"] == "ok"
