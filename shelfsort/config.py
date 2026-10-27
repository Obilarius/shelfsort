"""Settings stored in %APPDATA%\\ShelfSort\\config.json (outside the repo - holds API keys)."""
from __future__ import annotations

import json
import logging
import os
import shutil
import sys
import uuid
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from .i18n import N_, tr
from .plex import LibraryMap

# Windows: %APPDATA%, Linux: $XDG_CONFIG_HOME or ~/.config, macOS: ~/Library/Application Support
if os.name == "nt":
    _APPDATA = Path(os.environ.get("APPDATA", Path.home()))
elif sys.platform == "darwin":
    _APPDATA = Path.home() / "Library" / "Application Support"
else:
    _APPDATA = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
CONFIG_PATH = _APPDATA / "ShelfSort" / "config.json"
_OLD_CONFIG_PATH = _APPDATA / "plex-renamer" / "config.json"  # before the rename to ShelfSort

KINDS = {"movie": N_("Filme"), "show": N_("Serien")}  # German values are also saved as default titles

# languages offered for titles/descriptions (TMDB and Plex language codes)
METADATA_LANGUAGES = [
    ("de-DE", N_("Deutsch")), ("en-US", N_("Englisch (USA)")), ("en-GB", N_("Englisch (UK)")),
    ("fr-FR", N_("Französisch")), ("es-ES", N_("Spanisch")), ("it-IT", N_("Italienisch")),
    ("nl-NL", N_("Niederländisch")), ("pl-PL", N_("Polnisch")), ("pt-BR", N_("Portugiesisch (Brasilien)")),
    ("sv-SE", N_("Schwedisch")), ("da-DK", N_("Dänisch")), ("nb-NO", N_("Norwegisch")),
    ("fi-FI", N_("Finnisch")), ("cs-CZ", N_("Tschechisch")), ("tr-TR", N_("Türkisch")),
    ("ja-JP", N_("Japanisch")),
]


def language_name(code: str) -> str:
    name = dict(METADATA_LANGUAGES).get(code)
    return tr(name) if name else code


@dataclass
class LibraryConfig:
    """One library ShelfSort manages - a local folder, optionally tied to a Plex library."""
    kind: str  # "movie" | "show"
    title: str
    local_root: str
    section_key: str = ""  # Plex library
    server_root: str = ""  # the same folder as the Plex server sees it
    default: bool = False  # new imports of this kind go here
    language: str = ""  # titles for this library (e.g. "en-US" for an OV library); "" = Config.language

    @property
    def path(self) -> Path:
        return Path(self.local_root)

    def map(self) -> LibraryMap:
        return LibraryMap(self.path, self.section_key or None, self.server_root or None)


@dataclass
class Config:
    tmdb_key: str = ""
    app_language: str = ""  # user interface; "" = system language
    language: str = "de-DE"  # metadata: titles/descriptions from TMDB and Plex
    plex_url: str = "http://localhost:32400"
    plex_token: str = ""
    min_video_mb: int = 100
    last_import_dir: str = ""
    client_id: str = ""  # identifies this ShelfSort installation at plex.tv
    plex_server_name: str = ""
    libraries: list[dict] = field(default_factory=list)  # LibraryConfig as dicts
    check_updates: bool = True  # ask GitHub once a day for a newer release
    last_update_check: float = 0.0
    skipped_version: str = ""  # "Skip this version"
    # naming scheme for new names (see naming.Scheme); defaults = Plex
    naming_ids: str = "plex"
    naming_show_year: bool = False
    naming_season: str = "Season"
    naming_episode_titles: bool = True
    naming_nfo: bool = False
    # before multiple libraries (read once, then moved into `libraries`)
    movies_root: str = ""
    tv_root: str = ""
    movies_section: str = ""
    movies_server_root: str = ""
    tv_section: str = ""
    tv_server_root: str = ""

    @classmethod
    def load(cls) -> "Config":
        if not CONFIG_PATH.exists() and _OLD_CONFIG_PATH.exists():
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(_OLD_CONFIG_PATH, CONFIG_PATH)
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return cls()
        except (OSError, ValueError) as e:  # damaged file: start with defaults, but say so
            logging.getLogger("shelfsort").error("Settings %s unreadable, using defaults: %s", CONFIG_PATH, e)
            return cls()
        known = {f.name for f in fields(cls)}
        cfg = cls(**{k: v for k, v in data.items() if k in known})
        cfg._migrate()
        return cfg

    def _migrate(self) -> None:
        if self.libraries:
            return
        for kind, root, section, server in (("movie", self.movies_root, self.movies_section, self.movies_server_root),
                                            ("show", self.tv_root, self.tv_section, self.tv_server_root)):
            if root:
                self.libraries.append(asdict(LibraryConfig(kind, KINDS[kind], root, section, server, True)))
        self.movies_root = self.tv_root = self.movies_section = self.movies_server_root = ""
        self.tv_section = self.tv_server_root = ""

    def save(self) -> None:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")

    # --- libraries ---

    @property
    def libs(self) -> list[LibraryConfig]:
        known = {f.name for f in fields(LibraryConfig)}
        return [LibraryConfig(**{k: v for k, v in d.items() if k in known}) for d in self.libraries]

    def set_libs(self, libs: list[LibraryConfig]) -> None:
        self.libraries = [asdict(lib) for lib in libs]

    def libs_of(self, kind: str) -> list[LibraryConfig]:
        return [lib for lib in self.libs if lib.kind == kind]

    def default_lib(self, kind: str) -> LibraryConfig | None:
        libs = self.libs_of(kind)
        return next((lib for lib in libs if lib.default), libs[0] if libs else None)

    @property
    def is_set_up(self) -> bool:
        return bool(self.tmdb_key and self.default_lib("movie") and self.default_lib("show"))

    @property
    def roots(self) -> list[Path]:
        return [lib.path for lib in self.libs]

    def library_maps(self) -> list[LibraryMap]:
        return [lib.map() for lib in self.libs]

    def ensure_client_id(self) -> str:
        if not self.client_id:
            self.client_id = str(uuid.uuid4())
            self.save()
        return self.client_id
