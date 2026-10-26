"""Turning parsed titles into TMDB matches."""
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass


@dataclass
class Match:
    kind: str  # "movie" | "show"
    tmdb_id: int
    title: str
    year: int | None
    original_title: str = ""
    confident: bool = True
    # shown in the details panel so the user can check the match at a glance
    poster_path: str | None = None
    overview: str = ""
    vote_average: float = 0.0
    vote_count: int = 0
    date: str = ""

    def url(self) -> str:
        return f"https://www.themoviedb.org/{'movie' if self.kind == 'movie' else 'tv'}/{self.tmdb_id}"

    def label(self) -> str:
        y = f" ({self.year})" if self.year else ""
        return f"{self.title}{y}"


_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def norm(s: str) -> str:
    # German umlauts fold to their ASCII spelling first, so "Einöde" == "Einoede"
    s = (s or "").lower().translate(_UMLAUTS)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("&", "and")
    return re.sub(r"[^a-z0-9]", "", s)


def umlaut_variant(title: str) -> str | None:
    """'Der Hobbit Smaugs Einoede' -> 'Der Hobbit Smaugs Einöde' (only used as a second search)."""
    v = re.sub(r"(?<![qQ])ue", "ü", re.sub(r"oe", "ö", re.sub(r"ae", "ä", title)))
    v = re.sub(r"Ae", "Ä", re.sub(r"Oe", "Ö", re.sub(r"(?<![qQ])Ue", "Ü", v)))
    return v if v != title else None


def year_of(date: str | None) -> int | None:
    try:
        return int((date or "")[:4])
    except ValueError:
        return None


def _extras(r: dict, date_key: str) -> dict:
    return {"poster_path": r.get("poster_path"), "overview": r.get("overview") or "",
            "vote_average": r.get("vote_average") or 0.0, "vote_count": r.get("vote_count") or 0,
            "date": r.get(date_key) or ""}


def movie_match(r: dict, confident: bool = True) -> Match:
    return Match("movie", r["id"], r.get("title") or r.get("original_title") or "",
                 year_of(r.get("release_date")), r.get("original_title") or "", confident,
                 **_extras(r, "release_date"))


def show_match(r: dict, confident: bool = True) -> Match:
    return Match("show", r["id"], r.get("name") or r.get("original_name") or "",
                 year_of(r.get("first_air_date")), r.get("original_name") or "", confident,
                 **_extras(r, "first_air_date"))


def _votes(r: dict) -> int:
    return r.get("vote_count") or 0


def _pick(results: list[dict], title: str, year: int | None, date_key: str, name_keys: tuple[str, str]):
    q = norm(title)

    def exact(r):
        return q in {norm(r.get(k) or "") for k in name_keys}

    best, best_score = None, float("-inf")
    for i, r in enumerate(results[:10]):
        ry = year_of(r.get(date_key))
        score = 4 if exact(r) else 0
        if year and ry:
            score += 3 if ry == year else (1 if abs(ry - year) == 1 else -2)
        # popularity breaks ties between equal titles (max +1.5, never beats a year match)
        score += min(math.log10(_votes(r) + 1), 5) * 0.3
        score -= i * 0.1
        if score > best_score:
            best, best_score = r, score
    if best is None:
        return None, False

    by = year_of(best.get(date_key))
    if year:
        confident = exact(best) and (by is None or abs(by - year) <= 1)
    else:
        # Without a year: trust a unique title, or one that is far better known than its
        # namesakes ("Joker" 2019 vs. obscure films of the same name).
        others = [_votes(r) for r in results[:10] if r is not best and exact(r)]
        confident = exact(best) and (not others or _votes(best) >= 10 * max(max(others), 20))
    return best, confident


def _find(search, title: str, year: int | None, date_key: str, name_keys: tuple[str, str]):
    results = search(title, year)
    if not results and year:
        results = search(title)
    r, confident = _pick(results, title, year, date_key, name_keys)
    if not confident and (alt := umlaut_variant(title)):
        alt_results = search(alt, year) or (search(alt) if year else [])
        r2, c2 = _pick(alt_results, title, year, date_key, name_keys)
        if r2 is not None and (c2 or r is None):
            return r2, c2
    return r, confident


def find_movie(tmdb, title: str, year: int | None) -> Match | None:
    if not title:
        return None
    r, confident = _find(tmdb.search_movie, title, year, "release_date", ("title", "original_title"))
    return movie_match(r, confident) if r else None


def find_show(tmdb, title: str, year: int | None) -> Match | None:
    if not title:
        return None
    r, confident = _find(tmdb.search_tv, title, year, "first_air_date", ("name", "original_name"))
    return show_match(r, confident) if r else None


def movie_by_id(tmdb, tmdb_id: int) -> Match | None:
    d = tmdb.movie(tmdb_id)
    return movie_match(d) if d else None


def show_by_id(tmdb, tmdb_id: int) -> Match | None:
    d = tmdb.tv(tmdb_id)
    return show_match(d) if d else None
