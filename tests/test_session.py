import pytest
import sqlite3
import json

def test_session_init(session_mgr, temp_db):
    """Test if database is initialized correctly."""
    assert session_mgr.db_path == temp_db
    conn = sqlite3.connect(temp_db)
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'")
    assert cursor.fetchone() is not None

def test_set_get_document(session_mgr, mock_pdf_bytes):
    """Test setting and getting a document."""
    user_id = 123
    session_mgr.set_document(user_id, mock_pdf_bytes, "test.pdf", "pdf", 456)
    
    session = session_mgr.get_session(user_id)
    assert session is not None
    assert session["doc_name"] == "test.pdf"
    assert session["doc_type"] == "pdf"
    assert session["chat_id"] == 456
    assert session["doc_bytes"] == mock_pdf_bytes

def test_update_session(session_mgr, mock_pdf_bytes, mock_sign_bytes):
    """Test updating a session with new data and BLOBs."""
    user_id = 123
    session_mgr.set_document(user_id, mock_pdf_bytes, "test.pdf", "pdf", 456)
    
    session_mgr.update_session(user_id, sign_bytes=mock_sign_bytes, keyword="Signer")
    
    session = session_mgr.get_session(user_id)
    assert session["sign_bytes"] == mock_sign_bytes
    assert session["keyword"] == "Signer"
    assert session["doc_bytes"] == mock_pdf_bytes  # Still there

def test_clear_session(session_mgr, mock_pdf_bytes):
    """Test clearing a session."""
    user_id = 123
    session_mgr.set_document(user_id, mock_pdf_bytes, "test.pdf", "pdf", 456)
    session_mgr.clear_session(user_id)
    
    assert session_mgr.get_session(user_id) is None

def test_active_users(session_mgr):
    """Test in-memory active user locking."""
    user_id = 789
    assert not session_mgr.is_active(user_id)
    
    session_mgr.add_active_user(user_id)
    assert session_mgr.is_active(user_id)
    
    session_mgr.remove_active_user(user_id)
    assert not session_mgr.is_active(user_id)
