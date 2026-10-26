"""Settings stored in %APPDATA%\\ShelfSort\\config.json (outside the repo - holds API keys)."""
from __future__ import annotations

import json
import os
import shutil
from dataclasses import asdict, dataclass, fields
from pathlib import Path

_APPDATA = Path(os.environ.get("APPDATA", Path.home()))
CONFIG_PATH = _APPDATA / "ShelfSort" / "config.json"
_OLD_CONFIG_PATH = _APPDATA / "plex-renamer" / "config.json"  # before the rename to ShelfSort


@dataclass
class Config:
    tmdb_key: str = ""
    language: str = "de-DE"
    plex_url: str = "http://localhost:32400"
    plex_token: str = ""
    movies_root: str = ""
    tv_root: str = ""
    min_video_mb: int = 100
    last_import_dir: str = ""

    @classmethod
    def load(cls) -> "Config":
        if not CONFIG_PATH.exists() and _OLD_CONFIG_PATH.exists():
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(_OLD_CONFIG_PATH, CONFIG_PATH)
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    def save(self) -> None:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")

    @property
    def roots(self) -> list[Path]:
        return [Path(self.movies_root), Path(self.tv_root)]
