class SessionManager:
    """
    Manages user sessions and active processing locks.
    Currently uses in-memory storage, but creates a clean boundary
    for future migrations to Redis or databases.
    """
    
    def __init__(self):
        self._user_sessions = {}
        self._active_users = set()

    def set_document(self, user_id: int, doc_bytes: bytes, doc_name: str, doc_type: str, chat_id: int, preview_mode: bool = False):
        self._user_sessions[user_id] = {
            "doc_bytes": doc_bytes,
            "doc_name": doc_name,
            "doc_type": doc_type,
            "preview_mode": preview_mode,
            "chat_id": chat_id,
        }

    def get_session(self, user_id: int) -> dict:
        return self._user_sessions.get(user_id)

    def update_session(self, user_id: int, **kwargs):
        if user_id in self._user_sessions:
            self._user_sessions[user_id].update(kwargs)

    def clear_session(self, user_id: int):
        self._user_sessions.pop(user_id, None)

    def add_active_user(self, user_id: int):
        self._active_users.add(user_id)

    def remove_active_user(self, user_id: int):
        self._active_users.discard(user_id)

    def is_active(self, user_id: int) -> bool:
        return user_id in self._active_users

# Singleton instance
session_manager = SessionManager()
