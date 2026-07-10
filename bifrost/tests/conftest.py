import tempfile
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _temp_db(monkeypatch):
    """Override DB_DIR and DB_PATH to a temp directory for test isolation."""
    tmp = Path(tempfile.mkdtemp())
    monkeypatch.setattr("companion.db.DB_DIR", tmp)
    monkeypatch.setattr("companion.db.DB_PATH", tmp / "test_bifrost.db")
