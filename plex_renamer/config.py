"""Settings stored in %APPDATA%\\plex-renamer\\config.json (outside the repo - holds API keys)."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

CONFIG_PATH = Path(os.environ.get("APPDATA", Path.home())) / "plex-renamer" / "config.json"


@dataclass
class Config:
    tmdb_key: str = ""
    language: str = "de-DE"
    plex_url: str = "http://192.168.1.5:32400"
    plex_token: str = ""
    movies_root: str = r"X:\plex_media\movies"
    tv_root: str = r"X:\plex_media\tvshows"
    min_video_mb: int = 100
    last_import_dir: str = ""

    @classmethod
    def load(cls) -> "Config":
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
