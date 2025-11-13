"""Pytest configuration and fixtures."""

import pytest
import asyncio
import os

# Set test environment variables
os.environ["LOG_LEVEL"] = "ERROR"  # Reduce log noise during tests
os.environ["HEADLESS"] = "true"  # Always run headless in tests

@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
def mock_openai_key(monkeypatch):
    """Mock OpenAI API key for tests."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key-12345")
    return "sk-test-key-12345"

