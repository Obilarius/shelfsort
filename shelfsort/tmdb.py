"""Minimal TMDB client with in-memory cache."""
from __future__ import annotations

import re
import time

import requests

from .i18n import tr

PLACEHOLDER_TITLE = re.compile(r"^(episode|folge|episodio|épisode)\s*\d+$", re.IGNORECASE)


class TMDBError(Exception):
    pass


class TMDB:
    BASE = "https://api.themoviedb.org/3"

    def __init__(self, api_key: str, language: str = "de-DE", session: requests.Session | None = None):
        if not api_key:
            raise TMDBError(tr("Kein TMDB-API-Key hinterlegt (Einstellungen)."))
        self.s = session or requests.Session()
        self.key: str | None = api_key
        if len(api_key) > 40:  # v4 read access token
            self.s.headers["Authorization"] = f"Bearer {api_key}"
            self.key = None
        self.language = language
        self._cache: dict = {}  # keyed by path + params incl. language, so it can be shared
        self._api_key = api_key
        self._siblings: dict[str, "TMDB"] = {language: self}

    def for_language(self, language: str | None) -> "TMDB":
        """Same client in another language (e.g. for an OV library); shares session and cache."""
        if not language or language == self.language:
            return self
        if language not in self._siblings:
            other = TMDB(self._api_key, language, self.s)
            other._cache, other._siblings = self._cache, self._siblings
            self._siblings[language] = other
        return self._siblings[language]

    def get(self, path: str, **params):
        params = {k: v for k, v in params.items() if v is not None}
        params.setdefault("language", self.language)
        ck = (path, tuple(sorted(params.items())))
        if ck in self._cache:
            return self._cache[ck]
        if self.key:
            params["api_key"] = self.key
        for _ in range(5):
            r = self.s.get(self.BASE + path, params=params, timeout=20)
            if r.status_code != 429:
                break
            time.sleep(float(r.headers.get("Retry-After", 1)))
        if r.status_code == 401:
            raise TMDBError(tr("TMDB-API-Key ungültig."))
        if r.status_code == 404:
            data = None
        else:
            r.raise_for_status()
            data = r.json()
        self._cache[ck] = data
        return data

    def search_movie(self, query: str, year: int | None = None) -> list[dict]:
        return (self.get("/search/movie", query=query, year=year) or {}).get("results", [])

    def search_tv(self, query: str, year: int | None = None) -> list[dict]:
        return (self.get("/search/tv", query=query, first_air_date_year=year) or {}).get("results", [])

    def movie(self, tmdb_id: int) -> dict | None:
        return self.get(f"/movie/{tmdb_id}")

    def tv(self, tmdb_id: int) -> dict | None:
        return self.get(f"/tv/{tmdb_id}")

    def _episode_title(self, tv_id: int, season: int, episode: int, language: str) -> str | None:
        data = self.get(f"/tv/{tv_id}/season/{season}", language=language)
        for e in (data or {}).get("episodes", []):
            if e.get("episode_number") == episode:
                return (e.get("name") or "").strip() or None
        return None

    def episode(self, tv_id: int, season: int, episode: int) -> dict | None:
        """Episode details (name, overview, still_path, air_date) from the cached season data."""
        data = self.get(f"/tv/{tv_id}/season/{season}")
        ep = next((e for e in (data or {}).get("episodes", []) if e.get("episode_number") == episode), None)
        if ep and not ep.get("overview") and not self.language.lower().startswith("en"):
            en = self.get(f"/tv/{tv_id}/season/{season}", language="en-US")
            en_ep = next((e for e in (en or {}).get("episodes", []) if e.get("episode_number") == episode), {})
            ep = {**ep, "overview": en_ep.get("overview") or ""}
        return ep

    def episode_title(self, tv_id: int, season: int, episode: int) -> str | None:
        """Localized episode title, falling back to English when only a placeholder exists."""
        title = self._episode_title(tv_id, season, episode, self.language)
        if title and not PLACEHOLDER_TITLE.match(title):
            return title
        if not self.language.lower().startswith("en"):
            en = self._episode_title(tv_id, season, episode, "en-US")
            if en and not PLACEHOLDER_TITLE.match(en):
                return en
        return None
