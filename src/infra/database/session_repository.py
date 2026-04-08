import sqlite3
import json
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class SessionManager:
    """
    Manages user sessions using SQLite for persistence.
    Stores metadata in JSON and large document/signature files as BLOBs.
    """
    
    def __init__(self, db_path: str = "data/sessions.db"):
        self.db_path = db_path
        self._active_users = set()  # Locks remain in-memory (short-lived)
        self._init_db()

    def _init_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    user_id INTEGER PRIMARY KEY,
                    metadata TEXT,
                    doc_bytes BLOB,
                    sign_bytes BLOB,
                    modified_docx BLOB,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def _get_conn(self):
        return sqlite3.connect(self.db_path)

    def set_document(self, user_id: int, doc_bytes: bytes, doc_name: str, doc_type: str, chat_id: int, preview_mode: bool = False):
        metadata = {
            "doc_name": doc_name,
            "doc_type": doc_type,
            "preview_mode": preview_mode,
            "chat_id": chat_id,
        }
        with self._get_conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO sessions (user_id, metadata, doc_bytes, last_updated)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """, (user_id, json.dumps(metadata), doc_bytes))
            conn.commit()

    def get_session(self, user_id: int) -> Optional[dict]:
        with self._get_conn() as conn:
            cursor = conn.execute(
                "SELECT metadata, doc_bytes, sign_bytes, modified_docx FROM sessions WHERE user_id = ?",
                (user_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            
            session = json.loads(row[0])
            session["doc_bytes"] = row[1]
            session["sign_bytes"] = row[2]
            session["modified_docx"] = row[3]
            return session

    def update_session(self, user_id: int, **kwargs):
        session = self.get_session(user_id)
        if not session:
            return

        # Separate bytes from metadata for efficient storage
        doc_bytes = kwargs.pop("doc_bytes", session.get("doc_bytes"))
        sign_bytes = kwargs.pop("sign_bytes", session.get("sign_bytes"))
        modified_docx = kwargs.pop("modified_docx", session.get("modified_docx"))
        
        # Merge other metadata
        for k, v in kwargs.items():
            session[k] = v
            
        # Clean session from bytes before saving metadata JSON
        clean_metadata = {k: v for k, v in session.items() if k not in ["doc_bytes", "sign_bytes", "modified_docx"]}
        
        with self._get_conn() as conn:
            conn.execute("""
                UPDATE sessions 
                SET metadata = ?, doc_bytes = ?, sign_bytes = ?, modified_docx = ?, last_updated = CURRENT_TIMESTAMP
                WHERE user_id = ?
            """, (json.dumps(clean_metadata), doc_bytes, sign_bytes, modified_docx, user_id))
            conn.commit()

    def clear_session(self, user_id: int):
        with self._get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            conn.commit()

    def add_active_user(self, user_id: int):
        self._active_users.add(user_id)

    def remove_active_user(self, user_id: int):
        self._active_users.discard(user_id)

    def is_active(self, user_id: int) -> bool:
        return user_id in self._active_users

# Singleton instance with default path
session_manager = SessionManager()
