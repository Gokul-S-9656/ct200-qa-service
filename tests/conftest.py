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


def _remove_test_files() -> None:
    for f in _TEST_FILES:
        if os.path.exists(f):
            try:
                os.remove(f)
            except PermissionError:
                # Belt-and-suspenders: dispose_engine()/nosql.close() in
                # the fixture below should already have released these
                # on every platform. If a handle is still somehow open
                # (e.g. an OS-level antivirus scan holding the file, or a
                # future contributor adding a code path that opens the
                # db without going through get_db()), this shouldn't
                # fail the whole test run over cleanup -- the next run
                # wipes it anyway.
                pass


@pytest.fixture(scope="session")
def client():
    _remove_test_files()
    from app.database import dispose_engine
    from app.main import app
    from app import nosql

    with TestClient(app) as c:
        yield c

    dispose_engine()
    nosql.close()
    _remove_test_files()
