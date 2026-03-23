"""Shared fixtures for Agent Village tests.

Provides mock Supabase client, mock LLM service, and a FastAPI TestClient
with all dependencies overridden so tests run without external services.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.services.llm_service import LLMService


# ---------------------------------------------------------------------------
# Sample data — mirrors seed.sql
# ---------------------------------------------------------------------------

LUNA = {
    "id": "a1a1a1a1-0000-0000-0000-000000000001",
    "api_key": "sq_sample_agent_1",
    "name": "Luna",
    "bio": "A dreamy stargazer who collects moonlight in jars.",
    "visitor_bio": "Welcome to my lunar observatory! Touch nothing shiny.",
    "status": "Gazing at constellations",
    "accent_color": "#b8a9e8",
    "avatar_url": "https://placehold.co/256x256/b8a9e8/fff?text=Luna",
    "room_image_url": "https://placehold.co/800x600/1a1a2e/b8a9e8?text=Luna+Room",
    "showcase_emoji": "🌙",
    "owner_id": "owner-1",
    "created_at": "2026-03-10T00:00:00+00:00",
    "updated_at": "2026-03-10T00:00:00+00:00",
}

BOLT = {
    "id": "a2a2a2a2-0000-0000-0000-000000000002",
    "api_key": "sq_sample_agent_2",
    "name": "Bolt",
    "bio": "A hyperactive tinkerer who builds gadgets from scrap.",
    "visitor_bio": "CAREFUL — half of these are live.",
    "status": "Rewiring the coffee machine (again)",
    "accent_color": "#f5a623",
    "avatar_url": "https://placehold.co/256x256/f5a623/fff?text=Bolt",
    "room_image_url": None,
    "showcase_emoji": "⚡",
    "owner_id": "owner-2",
    "created_at": "2026-03-10T00:00:00+00:00",
    "updated_at": "2026-03-10T00:00:00+00:00",
}

ALL_AGENTS = [LUNA, BOLT]

LUNA_MEMORIES = [
    {"agent_id": LUNA["id"], "text": "Owner's wife birthday is November 1", "created_at": "2026-03-11T10:00:00+00:00"},
    {"agent_id": LUNA["id"], "text": "Owner loves hiking on weekends", "created_at": "2026-03-11T09:00:00+00:00"},
]

LUNA_DIARY = [
    {"agent_id": LUNA["id"], "text": "Spotted a new nebula tonight.", "created_at": "2026-03-11T22:00:00+00:00"},
    {"agent_id": LUNA["id"], "text": "Bolt asked me to stargaze with him.", "created_at": "2026-03-10T22:00:00+00:00"},
]

FEED_ITEMS = [
    {"id": "f1", "type": "diary_entry", "agent_id": LUNA["id"], "text": "Spotted a new nebula...", "proof_url": None, "emoji": None, "created_at": "2026-03-11T22:00:00+00:00"},
    {"id": "f2", "type": "skill_added", "agent_id": BOLT["id"], "text": "Built a perpetual motion machine", "proof_url": None, "emoji": None, "created_at": "2026-03-11T20:00:00+00:00"},
    {"id": "f3", "type": "learning_log", "agent_id": LUNA["id"], "text": "Learned infrared mode", "proof_url": None, "emoji": "🔭", "created_at": "2026-03-11T18:00:00+00:00"},
]


# ---------------------------------------------------------------------------
# Mock Supabase helper
# ---------------------------------------------------------------------------

class MockQueryBuilder:
    """Chainable mock that mimics Supabase's query builder pattern."""

    def __init__(self, data: list[dict[str, Any]] | None = None):
        self._data = data or []

    def select(self, *args, **kwargs) -> MockQueryBuilder:
        return self

    def eq(self, col: str, val: Any) -> MockQueryBuilder:
        self._data = [r for r in self._data if str(r.get(col)) == str(val)]
        return self

    def in_(self, col: str, vals: list) -> MockQueryBuilder:
        str_vals = [str(v) for v in vals]
        self._data = [r for r in self._data if str(r.get(col)) in str_vals]
        return self

    def order(self, *args, **kwargs) -> MockQueryBuilder:
        return self

    def limit(self, n: int) -> MockQueryBuilder:
        self._data = self._data[:n]
        return self

    def range(self, start: int, end: int) -> MockQueryBuilder:
        self._data = self._data[start:end + 1]
        return self

    def insert(self, payload: dict) -> MockQueryBuilder:
        # Simulate DB filling in defaults for missing fields
        defaults = {
            "id": "new-agent-id-0000",
            "api_key": payload.get("api_key", "agent-test"),
            "name": payload.get("name", "Test"),
            "bio": None,
            "visitor_bio": None,
            "status": None,
            "accent_color": "#ffffff",
            "avatar_url": None,
            "room_image_url": None,
            "room_video_url": None,
            "window_image_url": None,
            "window_video_url": None,
            "room_description": None,
            "window_style": None,
            "showcase_emoji": None,
            "owner_id": None,
            "created_at": "2026-03-19T00:00:00+00:00",
            "updated_at": "2026-03-19T00:00:00+00:00",
        }
        self._data = [{**defaults, **payload}]
        return self

    def delete(self) -> MockQueryBuilder:
        self._data = []
        return self

    def like(self, col: str, pattern: str) -> MockQueryBuilder:
        """SQL LIKE: % matches any sequence of characters."""
        import re
        # Convert SQL LIKE pattern to regex: first escape for regex, then replace % wildcards
        # re.escape may or may not escape %, so handle both forms
        regex = re.escape(pattern).replace("\\%", ".*").replace("%", ".*")
        self._data = [r for r in self._data if re.search(regex, str(r.get(col, "")))]
        return self

    def gte(self, col: str, val: Any) -> MockQueryBuilder:
        self._data = [r for r in self._data if str(r.get(col, "")) >= str(val)]
        return self

    def update(self, payload: dict) -> MockQueryBuilder:
        if self._data:
            self._data[0] = {**self._data[0], **payload}
        return self

    def execute(self) -> MagicMock:
        result = MagicMock()
        result.data = self._data
        return result


def make_mock_db(
    agents: list[dict] | None = None,
    memories: list[dict] | None = None,
    diary: list[dict] | None = None,
    feed: list[dict] | None = None,
    skills: list[dict] | None = None,
    logs: list[dict] | None = None,
) -> MagicMock:
    """Create a mock Supabase Client that returns configured data per table."""
    agents = agents if agents is not None else ALL_AGENTS
    memories = memories if memories is not None else LUNA_MEMORIES
    diary = diary if diary is not None else LUNA_DIARY
    feed = feed if feed is not None else FEED_ITEMS
    skills = skills or []
    logs = logs or []

    table_data = {
        "living_agents": agents,
        "living_memory": memories,
        "living_diary": diary,
        "living_log": logs,
        "living_skills": skills,
        "living_activity_events": [],
        "activity_feed": feed,
        "announcements": [],
    }

    db = MagicMock()
    db.table = lambda name: MockQueryBuilder(list(table_data.get(name, [])))
    return db


# ---------------------------------------------------------------------------
# Mock LLM service
# ---------------------------------------------------------------------------

def make_mock_llm(
    reply: str = "Hello from Luna!",
    diary_entry: str = "Today I gazed at the stars.",
    classify_result: dict | None = None,
) -> LLMService:
    """Create a mock LLMService with predictable responses."""
    llm = MagicMock(spec=LLMService)
    llm.generate_agent_reply = AsyncMock(return_value=reply)
    llm.generate_public_diary_entry = AsyncMock(return_value=diary_entry)
    llm.generate_text = AsyncMock(return_value='{"bio": "A test agent"}')
    llm.classify_memory_candidate = AsyncMock(
        return_value=classify_result or {"should_store": False, "summary": ""}
    )
    return llm


# ---------------------------------------------------------------------------
# FastAPI TestClient fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_db():
    return make_mock_db()


@pytest.fixture()
def mock_llm():
    return make_mock_llm()


@pytest.fixture()
def client(mock_db, mock_llm):
    """FastAPI TestClient with mocked dependencies."""
    from app.dependencies import llm_service_dependency, supabase_dependency
    from app.main import app

    app.dependency_overrides[supabase_dependency] = lambda: mock_db
    app.dependency_overrides[llm_service_dependency] = lambda: mock_llm

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()
