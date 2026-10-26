"""Plex naming rules: sanitizing and building folder/file names."""
from __future__ import annotations

import re

ID_RE = re.compile(r"\s*\{(tmdb|tvdb|imdb)-([^}]+)\}", re.IGNORECASE)
SEASON_DIR_RE = re.compile(r"^(?:season|staffel)\s*0*(\d+)$", re.IGNORECASE)
YEAR_SUFFIX_RE = re.compile(r"\s*\((\d{4})\)\s*$")

# Folder names that already follow the scheme and are left alone by the audit.
VALID_MOVIE_DIR = re.compile(r"^.+ \(\d{4}\) \{tmdb-\d+\}$")
VALID_SHOW_DIR = re.compile(r"^.+ \{tmdb-\d+\}$")

_ILLEGAL = re.compile(r'[<>"/\\|?*\x00-\x1f]')
MAX_TITLE = 120


def sanitize(name: str) -> str:
    """Make a title safe for Windows paths. 'F1: Der Film' -> 'F1 - Der Film'."""
    name = re.sub(r"\s*:\s*", " - ", name)
    name = _ILLEGAL.sub("", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name.rstrip(". ")


def folder_id(name: str) -> tuple[str, str] | None:
    m = ID_RE.search(name)
    return (m.group(1).lower(), m.group(2)) if m else None


def tmdb_id_of(name: str) -> int | None:
    fid = folder_id(name)
    if fid and fid[0] == "tmdb" and fid[1].isdigit():
        return int(fid[1])
    return None


def strip_ids(name: str) -> str:
    return ID_RE.sub("", name).strip()


def title_of(name: str) -> str:
    """Folder name without IDs and trailing '(year)'."""
    return YEAR_SUFFIX_RE.sub("", strip_ids(name)).strip()


def movie_name(title: str, year: int | None) -> str:
    t = sanitize(title)
    return f"{t} ({year})" if year else t


def movie_folder(title: str, year: int | None, tmdb_id: int) -> str:
    return f"{movie_name(title, year)} {{tmdb-{tmdb_id}}}"


def show_folder(title: str, tmdb_id: int) -> str:
    return f"{sanitize(title)} {{tmdb-{tmdb_id}}}"


def season_folder(n: int) -> str:
    return f"Season {n:02d}"


def episode_code(season: int, episodes: list[int]) -> str:
    code = f"S{season:02d}E{episodes[0]:02d}"
    if len(episodes) > 1 and episodes[-1] != episodes[0]:
        code += f"-E{episodes[-1]:02d}"
    return code


def episode_name(show: str, season: int, episodes: list[int], title: str | None = None) -> str:
    name = f"{sanitize(show)} - {episode_code(season, episodes)}"
    if title:
        t = sanitize(title)[:MAX_TITLE].rstrip(". ")
        if t:
            name += f" - {t}"
    return name
