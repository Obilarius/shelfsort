"""Episode lists exactly as Plex numbers them (respecting each show's chosen episode ordering).

The local server only knows episodes that have a file. Plex's metadata provider returns the full
list for the show's ordering (e.g. TheTVDB "BBC iPlayer"), so files can be renumbered to match.
"""
from __future__ import annotations

import difflib
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

import requests

from .i18n import N_, tr
from .matcher import norm
from .naming import episode_code
from .plex import LibraryMap, Plex

log = logging.getLogger("shelfsort")
PROVIDER = "https://metadata.provider.plex.tv/library/metadata"
_PAREN = re.compile(r"\s*[\(\[][^)\]]*[\)\]]")
_PLACEHOLDER = re.compile(r"^(episode|folge)\s*\d+$", re.IGNORECASE)

# The library-wide setting uses older names: "aired" is TheTVDB, not TMDB.
LIBRARY_ORDERING = {"aired": "tvdbAiring", "dvd": "tvdbDvd", "absolute": "tvdbAbsolute", "tmdbAiring": "tmdbAiring"}
ORDERING_LABELS = {"tmdbAiring": N_("TMDB (Ausstrahlung)"), "tvdbAiring": N_("TheTVDB (Ausstrahlung)"),
                   "tvdbDvd": N_("TheTVDB (DVD)"), "tvdbAbsolute": N_("TheTVDB (Absolut)"),
                   "tvdbDisney": N_("TheTVDB (Disney+)"), "tvdbBbcIPlayer": N_("TheTVDB (BBC iPlayer)")}
# Release from a streaming service -> the ordering Plex has for it (Disney+ numbers Bluey differently)
SERVICE_ORDERING = {"Disney+": "tvdbDisney", "BBC iPlayer": "tvdbBbcIPlayer"}
# Shows Plex doesn't know yet have no list of offered orderings - try these
DEFAULT_ORDERINGS = ["tmdbAiring", "tvdbAiring", "tvdbDvd", "tvdbDisney", "tvdbBbcIPlayer"]


@dataclass
class PlexEpisode:
    season: int
    episode: int
    title: str
    alt_titles: list[str] = field(default_factory=list)  # e.g. English, for files named "The Star Beast"
    summary: str = ""
    thumb: str | None = None  # full image URL
    air_date: str = ""
    guid: str = ""  # same episode across orderings
    duration: int = 0  # seconds, as the metadata service has it (whole minutes)

    def info(self) -> dict:
        """Same shape as a TMDB episode, for the details panel."""
        return {"name": self.title, "overview": self.summary, "still_url": self.thumb, "air_date": self.air_date,
                "season_number": self.season, "episode_number": self.episode, "source": "Plex"}

    def score(self, title: str) -> float:
        return max((similar(title, t) for t in [self.title, *self.alt_titles] if not is_placeholder(t)),
                   default=0.0)


@dataclass
class PlexShow:
    title: str
    rating_key: str
    guid: str
    ordering: str  # effective ordering (own setting or library default)
    local_dir: Path
    own_ordering: str | None = None  # None: follows the library default
    options: list[tuple[str, str]] = field(default_factory=list)  # (value, label) Plex offers for this show
    episodes: list[PlexEpisode] = field(default_factory=list)
    year: int | None = None

    @property
    def name(self) -> str:
        """Title with year, so two shows of the same name (Doctor Who 2005 and 2023) can be told apart."""
        return f"{self.title} ({self.year})" if self.year else self.title

    def label(self, value: str) -> str:
        return dict(self.options).get(value) or (tr(ORDERING_LABELS[value]) if value in ORDERING_LABELS else value)


@dataclass
class OrderingOption:
    value: str
    label: str
    in_flow: list[str] = field(default_factory=list)  # "S00E05 Die letzte Botschaft → S12E09"
    still_special: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)  # specials the ordering doesn't list at all


@dataclass
class SpecialsReport:
    show: PlexShow
    specials: list[str]  # titles in season 0 with the current ordering
    options: list[OrderingOption]
    no_file: int = 0  # specials without a file in the show's folder

    @property
    def best(self) -> OrderingOption | None:
        good = [o for o in self.options if o.in_flow]
        return max(good, key=lambda o: (len(o.in_flow), -len(o.missing))) if good else None


class ProviderError(RuntimeError):
    """Plex's metadata service failed. It is unofficial - callers fall back instead of failing."""


def clean_title(t: str) -> str:
    """'Die Schneemänner (Christmas Special)' -> 'Die Schneemänner'."""
    return _PAREN.sub("", t or "").strip()


def similar(a: str, b: str) -> float:
    """0..1 similarity of two episode titles (ignores case, umlaut spelling, '(Special)' suffixes)."""
    na, nb = norm(clean_title(a)), norm(clean_title(b))
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    # "Weihnachtsspecial 2012 - Die Schneemänner" vs "Die Schneemänner" - but not "Monster"
    # inside "Götter und Monster": the contained title must be long enough to be telling.
    if min(len(na), len(nb)) >= 10 and (na in nb or nb in na):
        return 0.95
    return difflib.SequenceMatcher(None, na, nb).ratio()


def is_placeholder(title: str) -> bool:
    return not title or bool(_PLACEHOLDER.match(title.strip()))


def _parse_enum(enum: str) -> list[tuple[str, str]]:
    """'":Library default|tmdbAiring:The Movie Database (Aired)|…' -> [(value, label)] without the default."""
    out = []
    for part in (enum or "").split("|"):
        value, _, label = part.partition(":")
        if value:
            out.append((value, tr(ORDERING_LABELS[value]) if value in ORDERING_LABELS else label))
    return out


class PlexCatalog:
    """Plex episode lists for the show libraries ShelfSort manages.

    show_libs: local folder + Plex library + server path of each TV library (from the setup). A
    library without section key is found by its folder name (older configs).
    """

    def __init__(self, plex: Plex, language: str = "de-DE", show_libs: list[LibraryMap] | None = None):
        self.plex = plex
        self.show_libs = show_libs or []
        self.lang = language.split("-")[0]
        self.s = requests.Session()
        self.s.headers.update({"X-Plex-Token": plex.token, "Accept": "application/json",
                               "X-Plex-Language": self.lang})
        self._lists: dict[tuple[str, str], list[PlexEpisode]] = {}
        self._season_keys: dict[tuple[str, str], dict[int, str]] = {}
        self._seasons: dict[tuple[str, str, int], list[PlexEpisode]] = {}
        self._sections: list[dict] | None = None

    def _provider(self, path: str, ordering: str | None, language: str | None = None) -> list[dict]:
        params = {"episodeOrder": ordering} if ordering else {}
        headers = {"X-Plex-Language": language} if language else {}
        # The provider pages at 20 items by default - seasons with 22 episodes would lose the last two.
        items: list[dict] = []
        while True:
            try:
                r = self.s.get(f"{PROVIDER}/{path}", headers=headers, timeout=20,
                               params={**params, "X-Plex-Container-Start": len(items), "X-Plex-Container-Size": 100})
                r.raise_for_status()
                mc = r.json().get("MediaContainer", {})
            except (requests.RequestException, ValueError) as e:
                raise ProviderError(tr("Plex-Metadatendienst nicht erreichbar oder verändert ({error})", error=e)) from e
            page = mc.get("Metadata", [])
            items += page
            if not page or len(items) >= int(mc.get("totalSize") or 0):
                return items

    def _section(self, lib: LibraryMap) -> dict:
        if self._sections is None:
            self._sections = self.plex.sections()
        if lib.section_key:  # chosen in the setup wizard
            section = next((s for s in self._sections if s["key"] == lib.section_key), None)
        else:  # older configs: library whose folder has the same name
            name = lib.local_root.name.lower()
            section = next((s for s in self._sections
                            if s["type"] == "show" and any(Plex._basename(l) == name for l in s["locations"])), None)
        if not section:
            raise RuntimeError(tr("Keine Plex-Serienbibliothek für „{root}“ gefunden – bitte im "
                                  "Einrichtungsassistenten zuordnen.", root=lib.local_root))
        return section

    @staticmethod
    def _bases(lib: LibraryMap, section: dict) -> list[str]:
        """Server-side folders whose content lives under the library's local folder."""
        roots = [lib.server_root] if lib.server_root else section["locations"]
        return [r.replace("\\", "/").rstrip("/") for r in roots]

    def library_ordering(self, lib: LibraryMap | None = None) -> str:
        """Ordering a show gets in this library unless it has its own setting."""
        lib = lib or (self.show_libs[0] if self.show_libs else None)
        if lib is None:
            return "tvdbAiring"
        section = self._section(lib)
        lib_value = next((p.get("value") for p in self.plex._get(f"/library/sections/{section['key']}/prefs")
                          .get("MediaContainer", {}).get("Setting", []) if p.get("id") == "showOrdering"), None)
        return LIBRARY_ORDERING.get(lib_value or "", "tvdbAiring")

    def match_show(self, tmdb_id: int) -> str | None:
        """Plex guid of a show that is not in the library yet, found by its TMDB id."""
        r = self.s.get(f"{PROVIDER}/matches", params={"type": 2, "guid": f"tmdb://{tmdb_id}"}, timeout=20)
        r.raise_for_status()
        hits = r.json().get("MediaContainer", {}).get("Metadata", [])
        guid = hits[0].get("guid", "") if hits else ""
        return guid if guid.startswith("plex://show/") else None

    def shows(self, progress=None) -> dict[str, PlexShow]:
        """Plex-matched shows of all managed show libraries, keyed by lower-case local folder."""
        out: dict[str, PlexShow] = {}
        for lib in self.show_libs:
            out.update(self._library_shows(lib, progress))
        return out

    def _library_shows(self, lib: LibraryMap, progress=None) -> dict[str, PlexShow]:
        section = self._section(lib)
        default_order = self.library_ordering(lib)
        items = [s for s in self.plex._get(f"/library/sections/{section['key']}/all")
                 .get("MediaContainer", {}).get("Metadata", [])
                 if str(s.get("guid", "")).startswith("plex://show/")]  # matched by the Plex agent

        def load(s):
            return s, self.plex._get(f"/library/metadata/{s['ratingKey']}",
                                     includePreferences=1)["MediaContainer"]["Metadata"][0]

        out: dict[str, PlexShow] = {}
        with ThreadPoolExecutor(8) as pool:
            results = pool.map(load, items)
            for i, s in enumerate(items):
                if progress:
                    try:
                        progress(f"Plex: {s.get('title')}", i, len(items))
                    except BaseException:
                        pool.shutdown(wait=False, cancel_futures=True)  # don't fetch the rest first
                        raise
                s, meta = next(results)
                pref = next((p for p in meta.get("Preferences", {}).get("Setting", [])
                             if p.get("id") == "showOrdering"), {})
                own = meta.get("showOrdering") or pref.get("value") or None
                for loc in meta.get("Location", []):
                    path = loc["path"].replace("\\", "/").rstrip("/")
                    for base in self._bases(lib, section):
                        if path.lower().startswith(base.lower() + "/"):
                            local = lib.local_root.joinpath(*path[len(base) + 1:].split("/"))
                            out[str(local).lower()] = PlexShow(
                                s.get("title", ""), s["ratingKey"], s["guid"], own or default_order, local,
                                own, _parse_enum(pref.get("enumValues", "")), year=s.get("year"))
        return out

    def episode_list(self, show: PlexShow, ordering: str, languages: list[str] | None = None) -> list[PlexEpisode]:
        """All episodes of a show in a given ordering (cached)."""
        langs = languages or ([self.lang] + (["en"] if self.lang != "en" else []))
        key = (show.guid, ordering, ",".join(langs))
        if key in self._lists:
            return self._lists[key]
        pid = show.guid.rsplit("/", 1)[-1]
        by_num: dict[tuple[int, int], PlexEpisode] = {}
        for lang in langs:
            seasons = [s for s in self._provider(f"{pid}/children", ordering, lang) if s.get("index") is not None]
            with ThreadPoolExecutor(6) as pool:
                children = list(pool.map(lambda s: self._provider(f"{s['ratingKey']}/children", ordering, lang),
                                         seasons))
            for season, eps in zip(seasons, children):
                for e in eps:
                    if e.get("index") is None:
                        continue
                    num = (int(season["index"]), int(e["index"]))
                    title = e.get("title") or ""
                    if num not in by_num:
                        by_num[num] = PlexEpisode(*num, title, summary=e.get("summary") or "", thumb=e.get("thumb"),
                                                  air_date=e.get("originallyAvailableAt") or "",
                                                  guid=e.get("guid") or "", duration=(e.get("duration") or 0) // 1000)
                    elif title and title != by_num[num].title:
                        by_num[num].alt_titles.append(title)
        result = sorted(by_num.values(), key=lambda e: (e.season, e.episode))
        self._lists[key] = result
        return result

    def season_episodes(self, show: PlexShow, ordering: str, season: int) -> list[PlexEpisode]:
        """One season of an ordering - cheaper than the whole list when only a few seasons matter."""
        key = (show.guid, ordering, season)
        if key not in self._seasons:
            pid = show.guid.rsplit("/", 1)[-1]
            if (show.guid, ordering) not in self._season_keys:
                self._season_keys[(show.guid, ordering)] = {
                    int(s["index"]): s["ratingKey"] for s in self._provider(f"{pid}/children", ordering, self.lang)
                    if s.get("index") is not None}
            rk = self._season_keys[(show.guid, ordering)].get(season)
            eps = self._provider(f"{rk}/children", ordering, self.lang) if rk else []
            self._seasons[key] = [PlexEpisode(season, int(e["index"]), e.get("title") or "", guid=e.get("guid") or "",
                                              duration=(e.get("duration") or 0) // 1000)
                                  for e in eps if e.get("index") is not None]
        return self._seasons[key]

    def alternatives(self, show: PlexShow) -> list[tuple[str, str]]:
        """Orderings other than the show's own that files may be numbered by (absolute: one big season, left out)."""
        options = show.options or [(v, show.label(v)) for v in DEFAULT_ORDERINGS]
        return [(v, label) for v, label in options if v not in (show.ordering, "tvdbAbsolute")]

    def file_durations(self, show: PlexShow) -> dict[tuple[int, int], int]:
        """Length in seconds of the file behind each episode number, as the server measured it."""
        out = {}
        for e in self.plex._get(f"/library/metadata/{show.rating_key}/allLeaves").get("MediaContainer", {}) \
                .get("Metadata", []):
            media = e.get("Media") or []
            if e.get("parentIndex") is not None and e.get("index") is not None and media and media[0].get("duration"):
                out[(int(e["parentIndex"]), int(e["index"]))] = int(media[0]["duration"]) // 1000
        return out

    def ordering_hints(self, show: PlexShow,
                       current: list[PlexEpisode]) -> dict[int, list[tuple[str, str, list[PlexEpisode]]]]:
        """Seasons whose file lengths fit another ordering clearly better than the show's own:
        {season: [(ordering, label, that season's episodes in it), best first]}."""
        # Only where episode lengths differ can a different order show at all (Bluey: 7 min, one 8, one 28)
        varied = set()
        for s in {e.season for e in current}:
            d = [e.duration for e in current if e.season == s and e.duration]
            if d and max(d) - min(d) >= 60:
                varied.add(s)
        if not varied:
            return {}
        files = {k: v for k, v in self.file_durations(show).items() if k[0] in varied}
        others: dict[str, tuple[str, list[PlexEpisode]]] = {}
        for value, label in self.alternatives(show):
            eps = [e for s in sorted({k[0] for k in files}) for e in self.season_episodes(show, value, s)]
            if eps:
                others[value] = (label, eps)
        fit = ordering_fit(files, current, {v: eps for v, (_, eps) in others.items()})
        return {s: [(v, others[v][0], [e for e in others[v][1] if e.season == s]) for v in values]
                for s, values in fit.items()}

    def load_episodes(self, show: PlexShow, language: str | None = None) -> list[PlexEpisode]:
        """Episodes in the show's ordering; titles in `language` (the library's), English as a second set."""
        lang = (language or self.lang).split("-")[0]
        langs = [lang] + (["en"] if lang != "en" else [])
        show.episodes = self.episode_list(show, show.ordering, langs)
        return show.episodes

    # --- specials check ---

    def specials_report(self, show: PlexShow) -> SpecialsReport | None:
        """Which orderings move the show's specials (season 0) into the regular seasons?"""
        current = self.episode_list(show, show.ordering, [self.lang])
        specials = [e for e in current if e.season == 0]
        if not specials:
            return None
        have = self.special_files(show)

        def name(sp: PlexEpisode) -> str:
            text = f"{episode_code(0, [sp.episode])} {sp.title}"
            return text if have is None or sp.episode in have else f"{text}  {tr('(keine Datei)')}"

        options = []
        for value, label in show.options:
            if value == show.ordering or value == "tvdbAbsolute":  # absolute = one big season, no help
                continue
            other = {e.guid: e for e in self.episode_list(show, value, [self.lang]) if e.guid}
            if not other:
                continue  # ordering not available for this show
            opt = OrderingOption(value, label)
            for sp in specials:
                e = other.get(sp.guid)
                if e is None:
                    opt.missing.append(name(sp))
                elif e.season == 0:
                    opt.still_special.append(name(sp))
                else:
                    opt.in_flow.append(f"{name(sp)}  →  {episode_code(e.season, [e.episode])}")
            options.append(opt)
        no_file = 0 if have is None else sum(sp.episode not in have for sp in specials)
        return SpecialsReport(show, [name(sp) for sp in specials], options, no_file)

    def special_files(self, show: PlexShow) -> set[int] | None:
        """Season 0 episode numbers the server has a file for, in the show's current ordering (None: unknown)."""
        try:
            seasons = self.plex._get(f"/library/metadata/{show.rating_key}/children").get("MediaContainer", {})
            season0 = next((s for s in seasons.get("Metadata", []) if s.get("index") == 0), None)
            if not season0:
                return set()
            eps = self.plex._get(f"/library/metadata/{season0['ratingKey']}/children").get("MediaContainer", {})
            return {int(e["index"]) for e in eps.get("Metadata", []) if e.get("index") is not None}
        except Exception as e:
            log.warning("Specials of %s on the server not readable: %s", show.name, e)
            return None

    def set_ordering(self, show: PlexShow, value: str) -> None:
        """Change the show's episode ordering in Plex and refresh its metadata."""
        self.plex._put(f"/library/metadata/{show.rating_key}/prefs", showOrdering=value)
        self.plex._put(f"/library/metadata/{show.rating_key}/refresh")
        show.own_ordering = show.ordering = value
        show.episodes = []


def specials_overview(catalog: PlexCatalog, progress=None) -> tuple[list[SpecialsReport], list[str]]:
    """Specials report for every show that has specials; returns (reports, errors)."""
    shows = catalog.shows()
    reports, errors = [], []
    with ThreadPoolExecutor(4) as pool:
        futures = {pool.submit(catalog.specials_report, s): s for s in shows.values()}
        for i, f in enumerate(as_completed(futures)):
            show = futures[f]
            if progress:
                try:
                    progress(f"Specials: {show.name}", i, len(futures))
                except BaseException:
                    pool.shutdown(wait=False, cancel_futures=True)
                    raise
            try:
                if r := f.result():
                    reports.append(r)
            except ProviderError as e:
                if not any(isinstance(x, ProviderError) for x in errors):
                    errors.append(e)  # one message if the service is down, not one per show
            except Exception as e:
                errors.append(f"{show.name}: {e}")
    return sorted(reports, key=lambda r: r.show.name.lower()), [str(e) for e in errors]


def ordering_fit(files: dict[tuple[int, int], int], current: list[PlexEpisode], others: dict[str, list[PlexEpisode]],
                 gap: int = 60, margin: int = 15) -> dict[int, list[str]]:
    """Seasons whose file lengths fit other orderings clearly better: {season: [ordering, best first]}.

    Only numbers where the two orderings put different episodes of clearly different length (`gap` seconds)
    count, and the file has to be clearly closer (`margin`) to one of them. Both lengths come from the
    show's own list where it has the episode - TMDB and TheTVDB give the same episode different lengths.
    Metadata lengths are whole minutes, so one such number proves little: it takes two, and none speaking
    for the show's own ordering.
    """
    cur = {(e.season, e.episode): e for e in current}
    by_guid = {e.guid: e for e in current if e.guid}
    found: dict[int, list[tuple[int, str]]] = {}
    for value, eps in others.items():
        alt = {(e.season, e.episode): e for e in eps}
        votes: dict[int, list[int]] = {}  # season -> [for the other ordering, for the show's own]
        for key, f in files.items():
            here, there = cur.get(key), alt.get(key)
            if not here or not there or there.guid == here.guid or there.guid not in by_guid:
                continue  # same episode, or one the show's list doesn't know (TMDB ids): nothing to compare
            c, a = here.duration, by_guid[there.guid].duration
            if not c or not a or abs(c - a) < gap:
                continue
            v = votes.setdefault(key[0], [0, 0])
            if abs(f - a) + margin <= abs(f - c):
                v[0] += 1
            elif abs(f - c) + margin <= abs(f - a):
                v[1] += 1
        for season, (yes, no) in votes.items():
            if yes >= 2 and no == 0:
                found.setdefault(season, []).append((yes, value))
    return {s: [v for _, v in sorted(c, key=lambda x: -x[0])] for s, c in found.items()}


class PlexEpisodeSource:
    """Lazy 'show -> Plex episode list' lookup for the import (loaded once per scan, on first use).

    Shows already in the library use their ordering in Plex. New shows are looked up by TMDB id
    and use the library's default ordering - the numbering Plex will apply once they are imported
    (TMDB often counts differently, e.g. Bluey S03E49 is a special there).
    """

    def __init__(self, catalog: PlexCatalog):
        self.catalog = catalog
        self._shows: dict[str, PlexShow] | None = None
        self._new: dict[int, PlexShow | None] = {}
        self._default = "tvdbAiring"
        self.error: str | None = None

    def is_new(self, show_dir: Path) -> bool:
        return self._shows is not None and str(show_dir).lower() not in self._shows

    def _show(self, show_dir: Path, tmdb_id: int | None) -> PlexShow | None:
        if self._shows is None:
            try:
                self._shows = self.catalog.shows()
                self._default = self.catalog.library_ordering()  # default TV library
            except Exception as e:  # Plex down -> import falls back to TMDB
                self._shows, self.error = {}, str(e)
                log.warning("Plex show list not available, episode titles from TMDB: %s", e)
                return None
        show = self._shows.get(str(show_dir).lower())
        if not show and tmdb_id is not None:
            if tmdb_id not in self._new:
                try:
                    guid = self.catalog.match_show(tmdb_id)
                except Exception as e:
                    guid, self.error = None, str(e)
                    log.warning("Plex match for tmdb-%s failed: %s", tmdb_id, e)
                self._new[tmdb_id] = PlexShow("", "", guid, self._default, show_dir) if guid else None
            show = self._new[tmdb_id]
        return show

    def __call__(self, show_dir: Path, tmdb_id: int | None = None,
                 language: str | None = None) -> list[PlexEpisode] | None:
        show = self._show(show_dir, tmdb_id)
        if not show:
            return None
        try:
            return self.catalog.load_episodes(show, language)
        except Exception as e:
            self.error = str(e)
            log.warning("Plex episode list for %s failed: %s", show_dir.name, e)
            return None


    def orderings(self, show_dir: Path, tmdb_id: int | None = None,
                  language: str | None = None) -> list[tuple[str, str, list[PlexEpisode]]]:
        """The other orderings Plex has for the show: (value, label, episodes) - to spot numbers that differ."""
        show = self._show(show_dir, tmdb_id)
        if not show:
            return []
        lang = (language or self.catalog.lang).split("-")[0]
        out = []
        for value, label in self.catalog.alternatives(show):
            try:
                eps = self.catalog.episode_list(show, value, [lang])
            except Exception as e:
                log.warning("Plex ordering %s for %s not available: %s", value, show_dir.name, e)
                continue
            if eps:
                out.append((value, label, eps))
        return out


def find_by_title(episodes: list[PlexEpisode], title: str, near: tuple[int, int] | None = None,
                  min_score: float = 0.85) -> tuple[PlexEpisode | None, float]:
    """Best episode for a title.

    Equally good candidates (two-parters, or Plex giving parts 1 and 2 the same name) are decided by
    the distance to `near` - the number the file would have with its season's usual offset.
    Returns None if nothing is close enough or the tie can't be broken.
    """
    scored = [(round(e.score(title), 2), e) for e in episodes]
    scored = [x for x in scored if x[0] >= min_score]
    if not scored:
        return None, 0.0
    top = max(s for s, _ in scored)
    tops = [e for s, e in scored if s >= top - 0.02]
    if len(tops) == 1:
        return tops[0], top
    if not near:
        return None, top

    def dist(e):
        return (0 if e.season == near[0] else 1000) + abs(e.episode - near[1])

    tops.sort(key=dist)
    if dist(tops[0]) == dist(tops[1]):
        return None, top
    return tops[0], top


def season_offsets(files: list[tuple[int, int, str]], episodes: list[PlexEpisode]) -> dict[int, int]:
    """Typical shift per season from clear title matches: (season, episode, title) -> {season: delta}."""
    deltas: dict[int, list[int]] = {}
    for season, ep, title in files:
        hit, _ = find_by_title(episodes, title, min_score=0.95)
        if hit and hit.season == season:
            deltas.setdefault(season, []).append(hit.episode - ep)
    out = {}
    for season, ds in deltas.items():
        common = max(set(ds), key=ds.count)
        if ds.count(common) >= 2:
            out[season] = common
    return out


def catalog_for(cfg) -> PlexCatalog:
    """Catalog for the configured server and all TV libraries (default library first)."""
    libs = sorted(cfg.libs_of("show"), key=lambda lib: not lib.default)
    return PlexCatalog(Plex(cfg.plex_url, cfg.plex_token), cfg.language, [lib.map() for lib in libs])
