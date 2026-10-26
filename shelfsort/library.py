"""Index of the existing library folders (all movie and show libraries ShelfSort manages)."""
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
    """movies_root/tv_root are the defaults for new imports; movie_roots/show_roots are all libraries.

    Existing movies/shows are found in any library, so new episodes join their show wherever it lives.
    """

    def __init__(self, movies_root: Path, tv_root: Path,
                 movie_roots: list[Path] | None = None, show_roots: list[Path] | None = None,
                 titles: dict[str, str] | None = None, languages: dict[str, str] | None = None):
        self.movies_root = movies_root
        self.tv_root = tv_root
        self.movie_roots = movie_roots or [movies_root]
        self.show_roots = show_roots or [tv_root]
        self.titles = titles or {}  # str(root).lower() -> library title, for notes
        self.languages = languages or {}  # str(root).lower() -> title language of the library
        self.movie_by_id: dict[int, Path] = {}
        self.movie_by_title: dict[str, list[Path]] = {}
        self.show_by_id: dict[int, Path] = {}
        self.show_by_title: dict[str, list[Path]] = {}
        self.refresh()

    @classmethod
    def from_config(cls, cfg) -> "Library":
        movie, show = cfg.default_lib("movie"), cfg.default_lib("show")
        if not movie or not show:
            raise RuntimeError("Bitte zuerst eine Filme- und eine Serien-Bibliothek einrichten (Menü „Einrichten …“).")
        return cls(movie.path, show.path, [lib.path for lib in cfg.libs_of("movie")],
                   [lib.path for lib in cfg.libs_of("show")],
                   {str(lib.path).lower(): lib.title for lib in cfg.libs},
                   {str(lib.path).lower(): lib.language or cfg.language for lib in cfg.libs})

    def refresh(self) -> None:
        self.movie_by_id.clear(); self.movie_by_title.clear()
        self.show_by_id.clear(); self.show_by_title.clear()
        for root in self.movie_roots:
            for d in list_dirs(root):
                if (i := tmdb_id_of(d.name)) is not None:
                    self.movie_by_id.setdefault(i, d)
                self.movie_by_title.setdefault(norm(title_of(d.name)), []).append(d)
        for root in self.show_roots:
            for d in list_dirs(root):
                if (i := tmdb_id_of(d.name)) is not None:
                    self.show_by_id.setdefault(i, d)
                self.show_by_title.setdefault(norm(title_of(d.name)), []).append(d)

    @property
    def all_roots(self) -> list[Path]:
        return [*self.movie_roots, *self.show_roots]

    def root_of(self, path: Path) -> Path | None:
        return next((r for r in self.all_roots if r == path or r in path.parents), None)

    def title(self, root: Path) -> str:
        return self.titles.get(str(root).lower(), root.name)

    def language_of(self, path: Path | None) -> str | None:
        """Title language of the library a path lies in (None: use the client's default)."""
        root = self.root_of(path) if path else None
        return self.languages.get(str(root).lower()) if root else None

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


def localized(tmdb, language: str | None):
    """TMDB client for a library's language (test doubles without languages are used as they are)."""
    fn = getattr(tmdb, "for_language", None)
    return fn(language) if fn and language else tmdb
