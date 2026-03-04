# preset_service.py
# Simpan & load preset TTD dan settings ke AppData\WordSigner\

import json
import os

APP_DIR = os.path.join(os.getenv("APPDATA", os.path.expanduser("~")), "WordSigner")


def _ensure_dir():
    os.makedirs(APP_DIR, exist_ok=True)


# ── Preset TTD ─────────────────────────────────────────────
def save_preset(sig_path: str):
    _ensure_dir()
    data = _load_json("preset.json")
    data["signature_path"] = sig_path
    _save_json("preset.json", data)


def load_preset():
    """Return path string jika ada & file masih exist, else None."""
    data = _load_json("preset.json")
    path = data.get("signature_path")
    return path if path and os.path.exists(path) else None


# ── Settings ───────────────────────────────────────────────
DEFAULT_SETTINGS = {
    "confidence_threshold": 0.4,
    "signature_width_inches": 1.5,
    "auto_open_pdf": True,
    "dark_mode": False,
}


def save_settings(settings: dict):
    _ensure_dir()
    _save_json("settings.json", settings)


def load_settings() -> dict:
    defaults = DEFAULT_SETTINGS.copy()
    saved = _load_json("settings.json")
    defaults.update(saved)
    return defaults


# ── Helpers ────────────────────────────────────────────────
def _load_json(filename: str) -> dict:
    path = os.path.join(APP_DIR, filename)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_json(filename: str, data: dict):
    path = os.path.join(APP_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
