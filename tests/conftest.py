"""
Shared fixtures for the whole test suite.

Why this lives in conftest.py rather than being duplicated per test file:
app.config.settings and the SQLAlchemy engine built from it are both
created once, at first import, and cached in sys.modules for the life of
the process. Two test files each building their own TestClient(app) with
different DATABASE_URL env vars would silently share the *first* one's
engine anyway (the second import is a no-op cache hit) -- so giving every
file its own fixture doesn't actually give it isolation, it just hides
that they're already sharing state. One session-scoped fixture makes
that sharing explicit instead of accidental.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["DATABASE_URL"] = "sqlite:///./test_ct200.db"
os.environ["TINYDB_PATH"] = "./test_tinydb_generations.json"
os.environ["LLM_PROVIDER"] = "mock"

import pytest
from fastapi.testclient import TestClient

_TEST_FILES = ("test_ct200.db", "test_tinydb_generations.json")


@pytest.fixture(scope="session")
def client():
    for f in _TEST_FILES:
        if os.path.exists(f):
            os.remove(f)
    from app.main import app
    with TestClient(app) as c:
        yield c
    for f in _TEST_FILES:
        if os.path.exists(f):
            os.remove(f)
