"""Checking the existing Plex library for names that should be fixed."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from guessit import guessit

from .importer import ProgressFn
from .library import Library, list_dirs
from .matcher import find_movie, find_show, movie_by_id, show_by_id
from .naming import (SEASON_DIR_RE, VALID_MOVIE_DIR, VALID_SHOW_DIR, YEAR_SUFFIX_RE, episode_code, episode_name,
                     movie_folder, movie_name, show_folder, strip_ids, title_of, tmdb_id_of)
from .parse import (RELEASE_JUNK, current_episode_title, episode_numbers, has_video, parse_release,
                    walk_videos)
from .plan import Op, Override, PlanItem, finalize
from .plex_sync import PlexCatalog, PlexEpisode, find_by_title, is_placeholder, season_offsets

_LOOSE_CODE = re.compile(r"S\d{1,3}E[\d,.]+(?:-?E\d+)*\s*-\s*", re.IGNORECASE)


@dataclass
class AuditOptions:
    movies: bool = True
    shows: bool = True
    empty: bool = True
    episode_titles: bool = False  # also replace episode titles with the TMDB/Plex ones
    plex_sync: bool = False  # renumber episodes to match the show's ordering in Plex


def build_audit_plan(tmdb, lib: Library, opts: AuditOptions,
                     progress: ProgressFn | None = None, catalog: PlexCatalog | None = None,
                     only_shows: set[Path] | None = None) -> list[PlanItem]:
    """only_shows: check just these show folders (e.g. after changing their ordering in Plex)."""
    plex_shows = {}
    if opts.shows and opts.plex_sync and catalog:
        plex_shows = catalog.shows(lib.tv_root, progress)
    jobs = []
    if (opts.movies or opts.empty) and only_shows is None:
        jobs += [(d, audit_movie_dir) for d in list_dirs(lib.movies_root)]
    if opts.shows or opts.empty:
        wanted = {str(p).lower() for p in only_shows} if only_shows is not None else None
        jobs += [(d, audit_show_dir) for d in list_dirs(lib.tv_root) if wanted is None or str(d).lower() in wanted]
    items: list[PlanItem] = []
    for i, (d, fn) in enumerate(jobs):
        if progress:
            progress(f"Prüfe {d.parent.name}\\{d.name}", i, len(jobs))
        try:
            if fn is audit_show_dir and str(d).lower() in plex_shows:
                eps = catalog.load_episodes(plex_shows[str(d).lower()])
                items += audit_show_dir(d, tmdb, lib, opts, plex_eps=eps)
                continue
            items += fn(d, tmdb, lib, opts)
        except Exception as e:
            items.append(PlanItem("movie" if fn is audit_movie_dir else "show_dir", d, str(d),
                                  status="error", note=str(e)))
    return finalize([it for it in items if it.ops or it.status != "ok"])


def _dir_stats(d: Path) -> str:
    count, size = 0, 0
    for dirpath, _, files in os.walk(d):
        for f in files:
            count += 1
            try:
                size += (Path(dirpath) / f).stat().st_size
            except OSError:
                pass
    return "leer" if count == 0 else f"{count} Datei(en), {size / 1024 / 1024:.1f} MB, kein Video"


def empty_item(d: Path, group: str) -> PlanItem:
    return PlanItem("empty", d, group, status="review", note=_dir_stats(d), ops=[Op("delete_dir", d)])


def _guess_title_year(name: str, kind: str = "movie") -> tuple[str, int | None]:
    """Title/year from a library folder name.

    Clean names ('10 Cloverfield Lane', 'Blade Runner 2049 (2017)') are used as they are -
    guessit would read '10' as an episode or '2049' as S20E49. Only release-style names
    ('Some.Movie.2016.German.1080p...') go through guessit.
    """
    clean = strip_ids(name)
    if not RELEASE_JUNK.search(clean.replace(".", " ")) and not ("." in clean and " " not in clean):
        m = YEAR_SUFFIX_RE.search(clean)
        return title_of(clean), (int(m.group(1)) if m else None)
    try:
        info = dict(guessit(clean, {"type": kind}))
    except Exception:
        info = {}
    title = info.get("title") or title_of(clean)
    year = info.get("year")
    return (title[0] if isinstance(title, list) else title), (year[0] if isinstance(year, list) else year)


# --- movies -------------------------------------------------------------------------------

def audit_movie_dir(d: Path, tmdb, lib: Library, opts: AuditOptions,
                    override: Override | None = None) -> list[PlanItem]:
    group = str(d)
    videos = walk_videos(d)
    if not videos:
        return [empty_item(d, group)] if opts.empty and not has_video(d) else []
    if not opts.movies:
        return []

    item = PlanItem("movie", d, group, dialog_kind="movie")
    item.replan = lambda ov: finalize(audit_movie_dir(d, tmdb, lib, opts, ov))
    main = [v for v in videos if v.parent == d] or videos
    parts = {v: parse_release(v).part for v in main}
    if len(main) > 1 and not all(parts.values()):
        item.status, item.note = "review", f"{len(main)} Videodateien im Ordner – manuell prüfen"
        return [item]

    if VALID_MOVIE_DIR.match(d.name) and not override:
        new_dir_name, base = d.name, strip_ids(d.name)
    else:
        fid = tmdb_id_of(d.name)
        if override or fid:
            match = movie_by_id(tmdb, override.tmdb_id if override else fid)
        else:
            title, year = _guess_title_year(d.name)
            if not year:
                p = parse_release(main[0])
                year = p.year
            match = find_movie(tmdb, title, year)
        if not match:
            item.status, item.note = "review", "Kein TMDB-Treffer – Doppelklick zum Suchen"
            return [item]
        item.match = match
        new_dir_name = movie_folder(match.title, match.year, match.tmdb_id)
        base = movie_name(match.title, match.year)
        if not (override or fid or match.confident):
            item.status = "review"
            item.add_note("Treffer unsicher – bitte prüfen")

    new_dir = d.parent / new_dir_name
    if new_dir_name != d.name:
        if new_dir.exists() and new_dir_name.lower() != d.name.lower():
            item.status = "conflict"
            item.add_note(f"Zielordner existiert bereits: {new_dir_name}")
        item.ops.append(Op("rename_dir", d, new_dir))
        item.add_note("Ordner umbenennen")

    final_name = None
    for v in main:
        name = base + (f" - pt{parts[v]}" if parts[v] else "") + v.suffix.lower()
        final_name = final_name or name
        before = len(item.ops)
        item.set_video_move(v, d / name)
        if len(item.ops) > before:
            item.add_note("Datei umbenennen")
    item.target = new_dir / final_name
    return [item]


# --- shows --------------------------------------------------------------------------------

def audit_show_dir(d: Path, tmdb, lib: Library, opts: AuditOptions,
                   override: Override | None = None, plex_eps: list[PlexEpisode] | None = None) -> list[PlanItem]:
    group = str(d)
    videos = walk_videos(d)
    if not videos:
        return [empty_item(d, group)] if opts.empty and not has_video(d) else []

    items: list[PlanItem] = []
    if opts.empty:
        for c in sorted(d.iterdir()):
            if c.is_dir() and not c.name.startswith(".") and not has_video(c):
                items.append(empty_item(c, group))
    if not opts.shows:
        return items

    def replan(ov: Override) -> list[PlanItem]:
        return finalize(audit_show_dir(d, tmdb, lib, opts, ov, plex_eps))

    show_id = tmdb_id_of(d.name)
    display = strip_ids(d.name)
    if override or not VALID_SHOW_DIR.match(d.name):
        dir_item = PlanItem("show_dir", d, group, replan=replan, dialog_kind="show")
        if override or show_id:
            match = show_by_id(tmdb, override.tmdb_id if override else show_id)
        else:
            match = find_show(tmdb, *_guess_title_year(d.name, "episode"))
        if not match:
            dir_item.status, dir_item.note = "review", "Keine Serie bei TMDB – Doppelklick zum Suchen"
        else:
            dir_item.match = match
            show_id = match.tmdb_id
            new_name = show_folder(match.title, match.tmdb_id)
            dir_item.target = d.parent / new_name
            if new_name != d.name:
                dir_item.ops.append(Op("rename_dir", d, dir_item.target))
                dir_item.note = "Serienordner umbenennen"
                if dir_item.target.exists() and new_name.lower() != d.name.lower():
                    dir_item.status = "conflict"
                    dir_item.add_note("Zielordner existiert bereits")
            if not (override or tmdb_id_of(d.name) or match.confident):
                dir_item.status = "review"
                dir_item.add_note("Treffer unsicher – bitte prüfen")
            if dir_item.status == "ok":
                display = strip_ids(new_name)
        items.append(dir_item)

    season_dirs: dict[int, Path] = {}
    for c in d.iterdir():
        m = SEASON_DIR_RE.match(c.name)
        if c.is_dir() and m:
            season_dirs.setdefault(int(m.group(1)), c)
    plex_by_num = {(e.season, e.episode): e for e in plex_eps or []}
    offsets: dict[int, int] = {}
    if plex_eps:
        known = [(n[0], n[1][0], t) for v in videos
                 if (n := episode_numbers(v.name)) and (t := loose_episode_title(v.stem))]
        offsets = season_offsets(known, plex_eps)

    for v in videos:
        nums = episode_numbers(v.name)
        it = PlanItem("episode", v, group, replan=replan, dialog_kind="show")
        title = loose_episode_title(v.stem) if plex_eps else current_episode_title(v.stem)
        if title and is_placeholder(title):
            title = None  # "Episode 3" is not a title

        # multi-episode files (S01E01-E02) are left to the structural check
        if plex_eps and not (nums and len(nums[1]) > 1):
            at = plex_by_num.get((nums[0], nums[1][0])) if nums else None
            if title and not (at and at.score(title) >= 0.999):
                near = (nums[0], nums[1][0] + offsets.get(nums[0], 0)) if nums else None
                hit, score = find_by_title(plex_eps, title, near)
                if hit is None and at and at.score(title) >= 0.85:
                    hit, score = at, at.score(title)  # close enough where it is, nothing better
                if hit is not None and nums and hit.season != nums[0] and score < 0.99:
                    hit = None  # jumping to another season needs a practically exact title
                if hit is not None and hit is not at:
                    old = episode_code(*nums) if nums else "ohne Nummer"
                    nums = (hit.season, [hit.episode])
                    at = hit
                    it.add_note(f"Plex-Abgleich: {old} → {episode_code(*nums)} („{hit.title}“)")
                    if score < 0.9:
                        it.status = "review"
                # No match anywhere: usually just a different translation of the title - the number
                # is left alone (only a title that clearly belongs to another episode moves a file).
            if nums and at and not is_placeholder(at.title) and (opts.episode_titles or not title):
                title = at.title

        if not nums:
            # no clean SxxEyy (e.g. "S07E05,5") and no Plex hint - flag it, never guess a rename
            it.status, it.note = "review", "Keine eindeutige SxxEyy-Nummer – manuell prüfen"
            items.append(it)
            continue
        season, eps = nums
        if not plex_eps and show_id and (opts.episode_titles or not title):
            title = tmdb.episode_title(show_id, season, eps[0]) or title
        season_dir = season_dirs.get(season) or d / Library.season_dir(d, season).name
        it.set_video_move(v, season_dir / (episode_name(display, season, eps, title) + v.suffix.lower()))
        if it.ops:
            if not it.note:
                it.note = "Staffelordner falsch" if v.parent != season_dir else "Dateiname"
            items.append(it)

    # A target occupied by a file that is not moving away would overwrite nothing - but it can't work either.
    # Plex keys episodes by number, not by file name: two files with S07E07 clash even if titled differently.
    moving = {str(op.src).lower() for it in items for op in it.ops if op.kind == "move"}
    staying: dict[tuple[int, int], Path] = {}
    for v in videos:
        n = episode_numbers(v.name)
        if n and str(v).lower() not in moving:
            staying[(n[0], n[1][0])] = v
    for it in items:
        if it.kind != "episode" or not it.ops or not it.target:
            continue
        n = episode_numbers(it.target.name)
        blocker = staying.get((n[0], n[1][0])) if n else None
        if blocker is not None and blocker != it.source:
            it.status = "conflict"
            it.add_note(f"{episode_code(*n)} ist schon belegt durch „{blocker.name}“ (wird nicht verschoben)")
    return items


def loose_episode_title(stem: str) -> str | None:
    """Title even after odd numbers like 'S07E05,5 - Die Schneemänner'."""
    t = current_episode_title(stem)
    if t:
        return t
    m = _LOOSE_CODE.search(stem)
    return stem[m.end():].strip() or None if m else None
