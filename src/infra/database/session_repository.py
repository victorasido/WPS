import sqlite3
import json
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_BLOB_KEYS = frozenset({"doc_bytes", "sign_bytes", "modified_docx"})


class SessionManager:
    """
    Manages user sessions with a Hybrid Storage strategy:

    ┌─────────────────────────────────────────────────────┐
    │  MEMORY (fast, ~ns access)                          │
    │    _meta_cache[user_id] = {keyword, zones, ...}    │
    ├─────────────────────────────────────────────────────┤
    │  SQLite (durable, disk I/O)                        │
    │    BLOB columns: doc_bytes, sign_bytes, modified   │
    │    Written ONLY when blobs actually change          │
    └─────────────────────────────────────────────────────┘

    Keuntungan:
    - State-machine transitions (keyword, zones, selected) = instant (memori)
    - File BLOB tetap di disk → tahan crash/restart container
    - update_session() tanpa blob = hanya update metadata JSON (ringan)
    - update_session() dengan blob = tulis BLOB ke SQLite (sekali saja)
    """

    def __init__(self, db_path: str = "data/sessions.db"):
        self.db_path = db_path
        self._active_users: set = set()
        self._meta_cache: dict = {}          # user_id → metadata dict (non-blob)
        self._init_db()

    # ── Schema ───────────────────────────────────────────────────────────────

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

    # ── Write: document upload ───────────────────────────────────────────────

    def set_document(self, user_id: int, doc_bytes: bytes, doc_name: str,
                     doc_type: str, chat_id: int, preview_mode: bool = False):
        """
        Simpan dokumen baru. Selalu tulis BLOB ke SQLite (harus persist).
        Update memory cache untuk metadata.
        """
        metadata = {
            "doc_name":     doc_name,
            "doc_type":     doc_type,
            "preview_mode": preview_mode,
            "chat_id":      chat_id,
        }
        # Hot-write memory cache
        self._meta_cache[user_id] = metadata.copy()

        # Cold-write BLOB ke SQLite
        with self._get_conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO sessions (user_id, metadata, doc_bytes, last_updated)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """, (user_id, json.dumps(metadata), doc_bytes))
            conn.commit()

    # ── Read ─────────────────────────────────────────────────────────────────

    def get_session(self, user_id: int) -> Optional[dict]:
        """
        Hot path: metadata dari memory cache, blobs dari SQLite (1 query ringkas).
        Cold path (bot restart): load semua dari SQLite, populate cache.
        """
        if user_id in self._meta_cache:
            # Metadata dari cache (super cepat), ambil only blobs dari DB
            meta = self._meta_cache[user_id].copy()
            with self._get_conn() as conn:
                cursor = conn.execute(
                    "SELECT doc_bytes, sign_bytes, modified_docx FROM sessions WHERE user_id = ?",
                    (user_id,)
                )
                row = cursor.fetchone()
                if not row:
                    # Row hilang (misal manual delete DB) — bersihkan cache
                    self._meta_cache.pop(user_id, None)
                    return None
                meta["doc_bytes"]     = row[0]
                meta["sign_bytes"]    = row[1]
                meta["modified_docx"] = row[2]
            return meta

        # Cold start: load dari SQLite, populate cache
        with self._get_conn() as conn:
            cursor = conn.execute(
                "SELECT metadata, doc_bytes, sign_bytes, modified_docx FROM sessions WHERE user_id = ?",
                (user_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None

            meta = json.loads(row[0])
            self._meta_cache[user_id] = meta.copy()  # seed cache

            session = meta.copy()
            session["doc_bytes"]     = row[1]
            session["sign_bytes"]    = row[2]
            session["modified_docx"] = row[3]
            return session

    # ── Update ───────────────────────────────────────────────────────────────

    def update_session(self, user_id: int, **kwargs):
        """
        Hybrid update:
        - Metadata kwargs (keyword, zones, selected...) → memory cache (instant)
          + lightweight metadata-only SQL UPDATE (tanpa BLOB rewrite)
        - BLOB kwargs (sign_bytes, modified_docx...) → tulis BLOB ke SQLite
          (hanya kalau ada perubahan blob)
        """
        if user_id not in self._meta_cache:
            # Cold start: seed cache dulu
            session = self.get_session(user_id)
            if not session:
                return

        # Pisahkan blob vs metadata
        blob_updates  = {k: v for k, v in kwargs.items() if k in _BLOB_KEYS}
        meta_updates  = {k: v for k, v in kwargs.items() if k not in _BLOB_KEYS}

        # Selalu update memory cache untuk metadata
        self._meta_cache[user_id].update(meta_updates)
        clean_meta = dict(self._meta_cache[user_id])  # snapshot for SQLite

        if blob_updates:
            # Ada blob baru → tulis semua ke SQLite (query berat, tapi jarang)
            with self._get_conn() as conn:
                # Ambil blob yang tidak berubah dari SQLite
                cursor = conn.execute(
                    "SELECT doc_bytes, sign_bytes, modified_docx FROM sessions WHERE user_id = ?",
                    (user_id,)
                )
                row = cursor.fetchone() or (None, None, None)

                doc_bytes     = blob_updates.get("doc_bytes",     row[0])
                sign_bytes    = blob_updates.get("sign_bytes",    row[1])
                modified_docx = blob_updates.get("modified_docx", row[2])

                conn.execute("""
                    UPDATE sessions
                    SET metadata = ?, doc_bytes = ?, sign_bytes = ?,
                        modified_docx = ?, last_updated = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                """, (json.dumps(clean_meta), doc_bytes, sign_bytes, modified_docx, user_id))
                conn.commit()
        else:
            # Tidak ada blob baru → hanya update metadata JSON (super ringan!)
            with self._get_conn() as conn:
                conn.execute("""
                    UPDATE sessions
                    SET metadata = ?, last_updated = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                """, (json.dumps(clean_meta), user_id))
                conn.commit()

    # ── Delete ───────────────────────────────────────────────────────────────

    def clear_session(self, user_id: int):
        self._meta_cache.pop(user_id, None)
        with self._get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            conn.commit()

    # ── Active User Lock ─────────────────────────────────────────────────────

    def add_active_user(self, user_id: int):
        self._active_users.add(user_id)

    def remove_active_user(self, user_id: int):
        self._active_users.discard(user_id)

    def is_active(self, user_id: int) -> bool:
        return user_id in self._active_users


# Singleton instance with default path
session_manager = SessionManager()
