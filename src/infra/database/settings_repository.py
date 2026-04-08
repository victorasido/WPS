import json
import os

class SettingsRepository:
    def __init__(self):
        data_dir = os.getenv("DATA_DIR")
        if data_dir:
            self.app_dir = data_dir
        else:
            self.app_dir = os.path.join(os.getenv("APPDATA", os.path.expanduser("~")), "WordSigner")
        self.default_settings = {
            "confidence_threshold": 0.4,
            "signature_width_inches": 1.5,
            "auto_open_pdf": True,
            "dark_mode": False,
        }
        self._ensure_dir()
        
    def _ensure_dir(self):
        os.makedirs(self.app_dir, exist_ok=True)
        
    def _load_json(self, filename: str) -> dict:
        path = os.path.join(self.app_dir, filename)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_json(self, filename: str, data: dict):
        path = os.path.join(self.app_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    # ── Preset TTD ──
    def save_preset(self, sig_path: str):
        data = self._load_json("preset.json")
        data["signature_path"] = sig_path
        self._save_json("preset.json", data)

    def load_preset(self) -> str | None:
        data = self._load_json("preset.json")
        path = data.get("signature_path")
        return path if path and os.path.exists(path) else None

    # ── Settings ──
    def save_settings(self, settings: dict):
        self._save_json("settings.json", settings)

    def load_settings(self) -> dict:
        defaults = self.default_settings.copy()
        saved = self._load_json("settings.json")
        defaults.update(saved)
        return defaults
