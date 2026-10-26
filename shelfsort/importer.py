"""Planning the import of downloaded releases into the Plex library."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from .library import Library, localized
from .matcher import find_movie, find_show, movie_by_id, norm, show_by_id
from .naming import episode_name, movie_folder, movie_name, show_folder
from .parse import is_video, parse_release, walk_videos
from .plan import Override, PlanItem, finalize
from .plex_sync import is_placeholder

ProgressFn = Callable[[str, int, int], None]
# (show folder, TMDB id, language) -> episode list in the order Plex uses / will use for that show
EpisodeSource = Callable[..., "list | None"]


def release_dir(video: Path, root: Path) -> Path | None:
    rel = video.relative_to(root)
    return root / rel.parts[0] if len(rel.parts) > 1 else None


def build_import_plan(root: Path, tmdb, lib: Library, min_bytes: int,
                      progress: ProgressFn | None = None, plex_eps: EpisodeSource | None = None) -> list[PlanItem]:
    videos = walk_videos(root, min_bytes)
    items: list[PlanItem] = []
    for i, v in enumerate(videos):
        if progress:
            progress(f"Erkenne {v.name}", i, len(videos))
        items.append(plan_import(v, root, tmdb, lib, plex_eps=plex_eps))
    return finalize(items)


def plan_import(video: Path, root: Path, tmdb, lib: Library, override: Override | None = None,
                plex_eps: EpisodeSource | None = None, target: Path | None = None) -> PlanItem:
    """target: library folder chosen by the user; None = where the movie/show already is, else the default."""
    parsed = parse_release(video)
    kind = ("movie" if override.kind == "movie" else "episode") if override else parsed.kind
    item = PlanItem(kind=kind, source=video, group=str(video), parsed=parsed,
                    dialog_kind="movie" if kind == "movie" else "show")
    item.replan = lambda ov: finalize([plan_import(video, root, tmdb, lib, ov, plex_eps, target)])
    item.retarget = lambda t: finalize([plan_import(video, root, tmdb, lib, override, plex_eps, t)])
    item.cleanup = release_dir(video, root)
    try:
        if kind == "movie":
            _plan_movie(item, video, tmdb, lib, override, target)
        else:
            _plan_episode(item, video, tmdb, lib, override, plex_eps, target)
    except Exception as e:  # network errors etc. - keep the row, show the reason
        item.status, item.note = "error", str(e)
    if item.target and (r := lib.root_of(item.target)):
        item.library = lib.title(r)
    return item


def _in_language(match, by_id, tmdb, language: str | None):
    """The match with title/overview in the target library's language (e.g. English for an OV library)."""
    t = localized(tmdb, language)
    if t is tmdb:
        return match
    other = by_id(t, match.tmdb_id)
    if not other:
        return match
    other.confident = match.confident
    return other


def _existing(found: Path | None, target: Path | None, lib: Library) -> tuple[Path | None, Path | None]:
    """(folder to use, folder in another library). A chosen target library wins over an existing folder."""
    if found and target and lib.root_of(found) != target:
        return None, found
    return found, None


def _find_any(find, tmdb, p):
    """First confident match over the parsed title and its fallbacks, else the first match at all."""
    first = None
    for title in p.titles():
        m = find(tmdb, title, p.year)
        if m and m.confident:
            return m
        first = first or m
    return first


def _plan_movie(item: PlanItem, video: Path, tmdb, lib: Library, ov: Override | None,
                target: Path | None = None) -> None:
    p = item.parsed
    match = movie_by_id(tmdb, ov.tmdb_id) if ov else _find_any(find_movie, tmdb, p)
    if not match:
        item.status, item.note = "review", f"Kein TMDB-Treffer für „{p.title}“ – Doppelklick zum Suchen"
        return
    existing, elsewhere = _existing(lib.movie_by_id.get(match.tmdb_id), target, lib)
    root = lib.root_of(existing) if existing else (target or lib.movies_root)
    match = _in_language(match, movie_by_id, tmdb, lib.language_of(root))
    item.match = match
    folder = existing or root / movie_folder(match.title, match.year, match.tmdb_id)
    name = movie_name(match.title, match.year) + (f" - pt{p.part}" if p.part else "")
    item.set_video_move(video, folder / (name + video.suffix.lower()))

    if not (match.confident or ov):
        item.status = "review"
        item.add_note("Treffer unsicher – bitte prüfen")
    if elsewhere:
        item.status = "review"
        item.add_note(f"Film liegt schon in Bibliothek „{lib.title(lib.root_of(elsewhere))}“")
    elif existing:
        others = [f.name for f in existing.iterdir() if f.is_file() and is_video(f)]
        if others:
            item.status = "review"
            item.add_note(f"Film schon vorhanden: {', '.join(others)}")
    else:
        similar = lib.movie_by_title.get(norm(match.title))
        if similar:
            item.status = "review"
            item.add_note(f"Ähnlicher Ordner vorhanden: {similar[0].name}")
    if item.target.exists():
        item.status = "conflict"
        item.add_note("Ziel existiert bereits")


def _plan_episode(item: PlanItem, video: Path, tmdb, lib: Library, ov: Override | None,
                  plex_eps: EpisodeSource | None = None, target: Path | None = None) -> None:
    p = item.parsed
    season = ov.season if ov and ov.season is not None else p.season
    episodes = ov.episodes if ov and ov.episodes else p.episodes
    match = show_by_id(tmdb, ov.tmdb_id) if ov else _find_any(find_show, tmdb, p)
    if not match:
        item.status, item.note = "review", f"Keine Serie „{p.title}“ bei TMDB – Doppelklick zum Suchen"
        return
    item.match = match
    if season is None or not episodes:
        item.status, item.note = "review", "Staffel/Folge nicht erkannt – Doppelklick zum Eintragen"
        return

    existing, elsewhere = _existing(lib.show_by_id.get(match.tmdb_id), target, lib)
    root = lib.root_of(existing) if existing else (target or lib.tv_root)
    language = lib.language_of(root)
    match = _in_language(match, show_by_id, tmdb, language)
    tmdb = localized(tmdb, language)  # episode titles below in the library's language too
    item.match = match
    show_dir = existing or root / show_folder(match.title, match.tmdb_id)
    # Shows Plex already knows: titles come from the Plex list in the show's chosen ordering
    # (e.g. TheTVDB "BBC iPlayer"), so the name matches what Plex shows for this number.
    # New shows too: Plex will number them by the library's default ordering once imported.
    in_plex = plex_eps(show_dir, match.tmdb_id, language) if plex_eps else None
    if in_plex:
        by_num = {(e.season, e.episode): e for e in in_plex}

        def title_of(n):
            e = by_num.get((season, n))
            return None if e is None or is_placeholder(e.title) else e.title

        first = by_num.get((season, episodes[0]))
        item.episode_info = first.info() if first else None
    else:
        def title_of(n):
            return tmdb.episode_title(match.tmdb_id, season, n)

        item.episode_info = tmdb.episode(match.tmdb_id, season, episodes[0])
    t1 = title_of(episodes[0])
    title = t1
    if len(episodes) > 1 and episodes[-1] != episodes[0]:
        t2 = title_of(episodes[-1])
        title = f"{t1} & {t2}" if t1 and t2 else t1
    name = episode_name(lib.display_name(show_dir), season, episodes, title)
    item.set_video_move(video, lib.season_dir(show_dir, season) / (name + video.suffix.lower()))

    if not (match.confident or ov):
        item.status = "review"
        item.add_note("Serien-Treffer unsicher – bitte prüfen")
    if elsewhere:
        item.status = "review"
        item.add_note(f"Serie liegt schon in Bibliothek „{lib.title(lib.root_of(elsewhere))}“ – "
                      f"Folge käme in einen zweiten Serienordner")
    elif not existing:
        item.add_note("Neue Serie")
    if in_plex:
        item.add_note("Titel laut Plex-Reihenfolge")
    if t1 is None:
        item.status = "review"
        item.add_note("Folge in Plex-Reihenfolge unbekannt – Nummer prüfen" if in_plex
                      else "Folge nicht bei TMDB (andere Reihenfolge?) – ohne Titel")
    if item.target.exists():
        item.status = "conflict"
        item.add_note("Ziel existiert bereits")
