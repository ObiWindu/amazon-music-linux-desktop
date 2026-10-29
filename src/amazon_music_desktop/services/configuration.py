"""Application configuration management.

Stores validated settings in the user's XDG config directory. Never stores
credentials, cookies, tokens, or DRM license data.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

APP_NAME = "amazon-music-desktop"
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / APP_NAME
CONFIG_FILE = CONFIG_DIR / "config.json"
PROFILE_DIR = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))) / APP_NAME
CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))) / APP_NAME
LOG_DIR = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / APP_NAME / "logs"

REGION_URLS: dict[str, str] = {
    "fr": "https://music.amazon.fr/",
    "us": "https://music.amazon.com/",
    "uk": "https://music.amazon.co.uk/",
    "de": "https://music.amazon.de/",
}

REGION_LABELS: dict[str, str] = {
    "fr": "France",
    "us": "United States",
    "uk": "United Kingdom",
    "de": "Germany",
}


@dataclass
class AppConfig:
    region: str = "fr"
    homepage_url: str = "https://music.amazon.fr/"
    window_width: int = 1280
    window_height: int = 800
    window_x: int | None = None
    window_y: int | None = None
    theme: str = "system"  # system | light | dark
    tray_enabled: bool = True
    minimize_to_tray: bool = True
    media_keys_enabled: bool = True
    diagnostics_verbosity: str = "info"  # info | debug
    developer_diagnostics: bool = False
    download_dir: str | None = None
    last_url: str | None = None

    def validate(self) -> AppConfig:
        if self.region not in REGION_URLS:
            self.region = "fr"
        if not self.homepage_url or not self.homepage_url.startswith("https://"):
            self.homepage_url = REGION_URLS.get(self.region, REGION_URLS["fr"])
        # keep region/homepage consistent when region changed but url is a default
        if self.homepage_url in REGION_URLS.values() and self.region in REGION_URLS:
            self.homepage_url = REGION_URLS[self.region]
        self.window_width = max(self.window_width, 640)
        self.window_height = max(self.window_height, 480)
        if self.theme not in {"system", "light", "dark"}:
            self.theme = "system"
        if self.diagnostics_verbosity not in {"info", "debug"}:
            self.diagnostics_verbosity = "info"
        return self

    @classmethod
    def default(cls) -> AppConfig:
        cfg = cls()
        cfg.validate()
        return cfg

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AppConfig:
        cfg = cls()
        for key, val in data.items():
            if hasattr(cfg, key):
                setattr(cfg, key, val)
        return cfg.validate()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ConfigService:
    def __init__(self, config_file: Path = CONFIG_FILE):
        self.config_file = config_file
        self._config: AppConfig = AppConfig.default()

    @property
    def config(self) -> AppConfig:
        return self._config

    def load(self) -> AppConfig:
        if not self.config_file.exists():
            self._config = AppConfig.default()
            self.save()
            return self._config
        try:
            raw = self.config_file.read_text(encoding="utf-8")
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise TypeError("config is not an object")
            self._config = AppConfig.from_dict(data)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            # preserve a diagnostic copy
            try:
                backup = self.config_file.with_suffix(".json.corrupt")
                if self.config_file.exists():
                    self.config_file.replace(backup)
            except OSError:
                pass
            self._config = AppConfig.default()
            self.save()
        return self._config

    def save(self) -> None:
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        self.config_file.write_text(
            json.dumps(self._config.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        try:
            os.chmod(self.config_file, 0o600)
        except OSError:
            pass

    def reset(self) -> AppConfig:
        self._config = AppConfig.default()
        self.save()
        return self._config

    def region_url(self, region: str | None = None) -> str:
        r = region or self._config.region
        if r in REGION_URLS:
            return REGION_URLS[r]
        return self._config.homepage_url

    def set_region(self, region: str) -> None:
        if region not in REGION_URLS:
            raise ValueError(f"unknown region: {region}")
        self._config.region = region
        self._config.homepage_url = REGION_URLS[region]
        self.save()


def ensure_dirs() -> None:
    for d in (CONFIG_DIR, PROFILE_DIR, CACHE_DIR, LOG_DIR):
        d.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(d, 0o700)
        except OSError:
            pass
    # profile subdirs
    (PROFILE_DIR / "profile").mkdir(parents=True, exist_ok=True)
    (PROFILE_DIR / "cache").mkdir(parents=True, exist_ok=True)
    (CACHE_DIR).mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(PROFILE_DIR / "profile", 0o700)
        os.chmod(PROFILE_DIR / "cache", 0o700)
    except OSError:
        pass
