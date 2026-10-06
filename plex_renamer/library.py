"""Index of the existing Plex library folders."""
from __future__ import annotations

from pathlib import Path

from .matcher import norm
from .naming import SEASON_DIR_RE, season_folder, strip_ids, title_of, tmdb_id_of


def list_dirs(root: Path) -> list[Path]:
    if not root.is_dir():
        raise FileNotFoundError(f"Bibliotheksordner nicht erreichbar: {root}")
    return sorted((d for d in root.iterdir() if d.is_dir() and not d.name.startswith(".")),
                  key=lambda d: d.name.lower())


class Library:
    def __init__(self, movies_root: Path, tv_root: Path):
        self.movies_root = movies_root
        self.tv_root = tv_root
        self.movie_by_id: dict[int, Path] = {}
        self.movie_by_title: dict[str, list[Path]] = {}
        self.show_by_id: dict[int, Path] = {}
        self.show_by_title: dict[str, list[Path]] = {}
        self.refresh()

    def refresh(self) -> None:
        self.movie_by_id.clear(); self.movie_by_title.clear()
        self.show_by_id.clear(); self.show_by_title.clear()
        for d in list_dirs(self.movies_root):
            if (i := tmdb_id_of(d.name)) is not None:
                self.movie_by_id[i] = d
            self.movie_by_title.setdefault(norm(title_of(d.name)), []).append(d)
        for d in list_dirs(self.tv_root):
            if (i := tmdb_id_of(d.name)) is not None:
                self.show_by_id[i] = d
            self.show_by_title.setdefault(norm(title_of(d.name)), []).append(d)

    @staticmethod
    def display_name(show_dir: Path) -> str:
        return strip_ids(show_dir.name)

    @staticmethod
    def season_dir(show_dir: Path, n: int) -> Path:
        """Existing 'Season 05'/'Staffel 5' folder, else the default name."""
        if show_dir.is_dir():
            for c in show_dir.iterdir():
                m = SEASON_DIR_RE.match(c.name)
                if c.is_dir() and m and int(m.group(1)) == n:
                    return c
        return show_dir / season_folder(n)
