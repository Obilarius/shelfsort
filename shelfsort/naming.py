"""Naming rules: sanitizing and building folder/file names in the chosen scheme.

The scheme (Plex, Jellyfin, Kodi or custom) only decides how new names are built. Reading names
always understands every style, so existing folders are recognised whatever scheme made them.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# {tmdb-123} (Plex), [tmdbid-123] / [tmdbid=123] (Jellyfin), also for tvdb/imdb
ID_RE = re.compile(r"\s*(?:\{(tmdb|tvdb|imdb)-([^}]+)\}|\[(tmdb|tvdb|imdb)id[-=]([^\]]+)\])", re.IGNORECASE)
SEASON_DIR_RE = re.compile(r"^(?:season|staffel)\s*0*(\d+)$", re.IGNORECASE)
YEAR_SUFFIX_RE = re.compile(r"\s*\((\d{4})\)\s*$")

_ILLEGAL = re.compile(r'[<>"/\\|?*\x00-\x1f]')
MAX_TITLE = 120


@dataclass(frozen=True)
class Scheme:
    ids: str = "plex"  # "plex" {tmdb-1} | "jellyfin" [tmdbid-1] | "none"
    show_year: bool = False  # "Show (2019) {tmdb-1}"
    season: str = "Season"  # word for season folders: "Season 01" / "Staffel 01"
    episode_titles: bool = True  # "Show - S01E01 - Title" or just "Show - S01E01"
    nfo: bool = False  # a .nfo with the TMDB link next to new movies and in new show folders (Kodi)


PRESETS = {
    "plex": Scheme(),
    "jellyfin": Scheme(ids="jellyfin", show_year=True),
    "kodi": Scheme(ids="none", show_year=True, nfo=True),
}
ID_STYLES = ("plex", "jellyfin", "none")
SEASON_WORDS = ("Season", "Staffel")

scheme = Scheme()


def set_scheme(new: Scheme) -> None:
    global scheme
    scheme = new


def scheme_from_config(cfg) -> Scheme:
    return Scheme(ids=cfg.naming_ids if cfg.naming_ids in ID_STYLES else "plex", show_year=cfg.naming_show_year,
                  season=cfg.naming_season if cfg.naming_season in SEASON_WORDS else "Season",
                  episode_titles=cfg.naming_episode_titles, nfo=cfg.naming_nfo)


def preset_of(s: Scheme) -> str:
    """'plex' / 'jellyfin' / 'kodi', or '' for a custom combination."""
    return next((name for name, p in PRESETS.items() if p == s), "")


def sanitize(name: str) -> str:
    """Make a title safe for Windows paths. 'F1: Der Film' -> 'F1 - Der Film'."""
    name = re.sub(r"\s*:\s*", " - ", name)
    name = _ILLEGAL.sub("", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name.rstrip(". ")


def folder_id(name: str) -> tuple[str, str] | None:
    m = ID_RE.search(name)
    if not m:
        return None
    kind, value = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
    return kind.lower(), value


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


def _id_tag(tmdb_id: int, s: Scheme) -> str:
    return {"plex": f" {{tmdb-{tmdb_id}}}", "jellyfin": f" [tmdbid-{tmdb_id}]"}.get(s.ids, "")


def movie_name(title: str, year: int | None) -> str:
    t = sanitize(title)
    return f"{t} ({year})" if year else t


def movie_folder(title: str, year: int | None, tmdb_id: int, s: Scheme | None = None) -> str:
    return movie_name(title, year) + _id_tag(tmdb_id, s or scheme)


def show_folder(title: str, tmdb_id: int, year: int | None = None, s: Scheme | None = None) -> str:
    s = s or scheme
    name = movie_name(title, year) if s.show_year else sanitize(title)
    return name + _id_tag(tmdb_id, s)


def season_folder(n: int, s: Scheme | None = None) -> str:
    return f"{(s or scheme).season} {n:02d}"


def episode_code(season: int, episodes: list[int]) -> str:
    code = f"S{season:02d}E{episodes[0]:02d}"
    if len(episodes) > 1 and episodes[-1] != episodes[0]:
        code += f"-E{episodes[-1]:02d}"
    return code


def episode_name(show: str, season: int, episodes: list[int], title: str | None = None,
                 s: Scheme | None = None) -> str:
    name = f"{sanitize(show)} - {episode_code(season, episodes)}"
    if title and (s or scheme).episode_titles:
        t = sanitize(title)[:MAX_TITLE].rstrip(". ")
        if t:
            name += f" - {t}"
    return name


def _tag_pattern(s: Scheme) -> str:
    return {"plex": r" \{tmdb-\d+\}", "jellyfin": r" \[tmdbid-\d+\]"}.get(s.ids, "")


def valid_movie_dir(name: str, s: Scheme | None = None) -> bool:
    """Already 'Title (Year)' plus the ID in the scheme's style - left alone by the library check."""
    s = s or scheme
    if s.ids == "none" and folder_id(name):
        return False  # an ID from another scheme is to be removed
    return re.fullmatch(r".+ \(\d{4}\)" + _tag_pattern(s), name) is not None


def valid_show_dir(name: str, s: Scheme | None = None) -> bool:
    s = s or scheme
    if s.ids == "none" and folder_id(name):
        return False
    # without show_year, a year that is already there is fine too (not worth renaming every show)
    year = r" \(\d{4}\)" if s.show_year else ""
    return re.fullmatch(r".+" + year + _tag_pattern(s), name) is not None


SHOW_NFO = "tvshow.nfo"


def nfo_text(kind: str, tmdb_id: int) -> str:
    """Kodi's 'URL only' .nfo: the scraper reads the link and knows exactly which title this is."""
    return f"https://www.themoviedb.org/{'movie' if kind == 'movie' else 'tv'}/{tmdb_id}\n"


def example(s: Scheme) -> list[str]:
    """Sample paths for the settings."""
    movie = movie_folder("Blade Runner 2049", 2017, 335984, s)
    show = show_folder("Severance", 95396, 2022, s)
    lines = [f"{movie}/{movie_name('Blade Runner 2049', 2017)}.mkv"]
    if s.nfo:
        lines.append(f"{movie}/{movie_name('Blade Runner 2049', 2017)}.nfo")
    lines.append(f"{show}/{season_folder(1, s)}/{episode_name(strip_ids(show), 1, [1], 'Good News About Hell', s)}.mkv")
    if s.nfo:
        lines.append(f"{show}/{SHOW_NFO}")
    return lines

