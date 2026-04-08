import pytest
import os
import sqlite3
import shutil
from src.infra.database import SessionManager

@pytest.fixture
def temp_db(tmp_path):
    """Fixture to create a temporary SQLite database."""
    db_file = tmp_path / "test_sessions.db"
    return str(db_file)

@pytest.fixture
def session_mgr(temp_db):
    """Fixture to provide a SessionManager instance with a temporary DB."""
    return SessionManager(db_path=temp_db)

@pytest.fixture
def mock_pdf_bytes():
    return b"%PDF-1.4\n%mock_content"

@pytest.fixture
def mock_sign_bytes():
    return b"PK\x03\x04mock_sign_bytes"
