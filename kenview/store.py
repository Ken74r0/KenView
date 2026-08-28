import json
import os
import keyring
from pathlib import Path

APP_NAME = "KenView"
SERVICE_NAME = "KenView"

class Store:
    def __init__(self):
        self.app_data = Path(os.getenv("APPDATA", os.path.expanduser("~/.config"))) / APP_NAME
        self.app_data.mkdir(parents=True, exist_ok=True)
        self.settings_path = self.app_data / "settings.json"
        self.settings = self._load_settings()

    def _load_settings(self):
        if self.settings_path.exists():
            try:
                with open(self.settings_path, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "base_url": "https://api.openai.com/v1",
            "reference_filename": "",
            "reference_text": "",
            "deepgram_api_key": ""
        }

    def save(self):
        with open(self.settings_path, "w") as f:
            json.dump(self.settings, f, indent=4)

    def get_api_key(self):
        return keyring.get_password(SERVICE_NAME, "llm_api_key") or ""

    def set_api_key(self, key):
        keyring.set_password(SERVICE_NAME, "llm_api_key", key)

    def get(self, key, default=None):
        return self.settings.get(key, default)

    def set(self, key, value):
        self.settings[key] = value
        self.save()
