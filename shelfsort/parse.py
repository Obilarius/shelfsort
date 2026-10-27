"""Finding video files and parsing release names."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from guessit import guessit

VIDEO_EXT = {".mkv", ".mp4", ".avi", ".m4v", ".mov", ".wmv", ".ts", ".m2ts", ".mpg", ".mpeg", ".webm"}
SUB_EXT = {".srt", ".ass", ".ssa", ".sub", ".idx", ".vtt", ".sup"}
# Plex extras folders (and sample folders) - never treated as main content. Plus names releases
# use for the same thing. Not "specials": in a show that is season 0.
EXTRAS_DIRS = {
    "behind the scenes", "deleted scenes", "featurettes", "interviews", "scenes",
    "shorts", "trailers", "other", "extras", "sample", "samples",
    "bonus", "bonus features", "special features", "making of", "featurette", "trailer",
}
# Plex extras next to the movie: "Arrival (2016)-trailer.mkv"
_EXTRA_SUFFIX_RE = re.compile(r"-(behindthescenes|deleted|featurette|interview|scene|short|trailer|other)$",
                              re.IGNORECASE)
# Editions worth keeping apart (guessit knows most of them; "Final Cut" and friends it misses)
_EDITIONS = {
    "director's cut": "Director's Cut", "extended": "Extended", "unrated": "Unrated", "uncut": "Uncut",
    "theatrical": "Theatrical", "remastered": "Remastered", "imax": "IMAX", "special": "Special Edition",
    "final cut": "Final Cut", "ultimate cut": "Ultimate Cut", "alternative cut": "Alternative Cut",
}
_EDITION_RE = re.compile(r"(?<![a-z])(final|ultimate|alternative)[ ._-]cut(?![a-z])", re.IGNORECASE)

_SAMPLE_RE = re.compile(r"(?:^|[\W_])sample(?:[\W_]|$)", re.IGNORECASE)
# Odd numbers like "S07E05,5" are rejected instead of misread; "S01E02.1080p" is a normal episode.
EP_RE = re.compile(r"(?<![a-z0-9])s(\d{1,3})[ ._-]?e(\d{1,4})((?:[ ._]?-?[ ._]?e\d{1,4})*)(?!\d|[,.]\d(?![\da-z]))",
                   re.IGNORECASE)
RELEASE_JUNK = re.compile(
    r"\b(480p|576p|720p|1080p|2160p|x264|x265|h\.?264|h\.?265|hevc|web(-?dl|rip)?|bluray|bdrip|"
    r"german|dl|aac|ac3|dts|eac3|hdr|dv)\b",
    re.IGNORECASE,
)


@dataclass
class Parsed:
    kind: str  # "movie" | "episode"
    title: str = ""
    year: int | None = None
    season: int | None = None
    episodes: list[int] = field(default_factory=list)
    part: int | None = None
    edition: str | None = None  # "Director's Cut", "3D", "Extended 3D" (movies only)
    # other readings to try if `title` finds nothing ("abc-show" -> "show", folder "Show.S03E02…")
    alt_titles: list[str] = field(default_factory=list)

    def titles(self) -> list[str]:
        return [t for t in dict.fromkeys([self.title, *self.alt_titles]) if t]


def _raise(err: OSError) -> None:
    # A folder we cannot read must never look "empty" (it might get deleted).
    raise err


def is_video(p: Path) -> bool:
    return p.suffix.lower() in VIDEO_EXT


def is_sample(p: Path) -> bool:
    return bool(_SAMPLE_RE.search(p.stem)) or p.parent.name.lower() in ("sample", "samples")


def is_extra(p: Path) -> bool:
    """Plex local extra like 'Arrival (2016)-trailer.mkv'."""
    return bool(_EXTRA_SUFFIX_RE.search(p.stem))


def walk_videos(root: Path, min_bytes: int = 0, skip_extras: bool = True) -> list[Path]:
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, onerror=_raise):
        dirnames[:] = sorted(
            d for d in dirnames
            if not d.startswith(".") and not (skip_extras and d.lower() in EXTRAS_DIRS)
        )
        for f in sorted(filenames):
            p = Path(dirpath) / f
            if not is_video(p) or is_sample(p) or (skip_extras and is_extra(p)):
                continue
            if min_bytes and p.stat().st_size < min_bytes:
                continue
            out.append(p)
    return out


def has_video(root: Path) -> bool:
    """Any video file at all (including extras/samples)."""
    for _, _, filenames in os.walk(root, onerror=_raise):
        if any(Path(f).suffix.lower() in VIDEO_EXT for f in filenames):
            return True
    return False


def episode_numbers(name: str) -> tuple[int, list[int]] | None:
    m = EP_RE.search(name)
    if not m:
        return None
    eps = [int(m.group(2))] + [int(x) for x in re.findall(r"e(\d{1,4})", m.group(3), re.IGNORECASE)]
    return int(m.group(1)), eps


def current_episode_title(stem: str) -> str | None:
    """Title part after 'SxxEyy' in an existing file name, if it looks like a real title."""
    m = EP_RE.search(stem)
    if not m:
        return None
    rest = stem[m.end():].strip(" -._")
    if not rest:
        return None
    if RELEASE_JUNK.search(rest.replace(".", " ")):
        info = _guess(stem)
        t = info.get("episode_title")
        return t if isinstance(t, str) else None
    if " " not in rest and "." in rest and max(len(t) for t in rest.split(".")) > 2:
        rest = rest.replace(".", " ")  # "Die.Wechseljahre" but not "S.A.R.A.H"
    return rest


def _guess(s: str) -> dict:
    try:
        return dict(guessit(s))
    except Exception:
        return {}


def _first(v):
    return v[0] if isinstance(v, list) and v else v


def _edition(info: dict, name: str) -> str | None:
    """Edition of a movie release: guessit's edition, 'Final Cut' & co. and 3D."""
    found = []
    for e in info.get("edition") or []:
        if (label := _EDITIONS.get(str(e).lower())) and label not in found:
            found.append(label)
    if not isinstance(info.get("edition"), list) and (label := _EDITIONS.get(str(info.get("edition", "")).lower())):
        found = [label]
    if (m := _EDITION_RE.search(name)) and (label := _EDITIONS.get(f"{m.group(1).lower()} cut")) not in found:
        found.append(label)
    other = info.get("other") or []
    if "3D" in (other if isinstance(other, list) else [other]):
        found.append("3D")
    return " ".join(found) or None


def edition_in(path: Path) -> str | None:
    """Edition of an existing movie file: Plex tag '{edition-…}' or what the release name says."""
    m = re.search(r"\{edition-([^}]+)\}", path.name, re.IGNORECASE)
    return m.group(1).strip() if m else parse_release(path).edition


def parse_release(path: Path) -> Parsed:
    info = _guess(path.name)
    parent = _guess(path.parent.name + path.suffix)
    if not info.get("title"):
        info = {**parent, **{k: v for k, v in info.items() if v}}

    title = str(_first(info.get("title")) or "")
    alts = []
    # guessit reads "Spider-Man.2002…" as group "Spider" + title "Man": glue it back together
    group = _first(info.get("release_group"))
    plain = re.sub(r"[._]", " ", path.name.lower())
    if group and title and plain.startswith(f"{group}-{title}".lower()):
        alts.append(title)
        title = f"{group}-{title}"
    # Fallbacks: obfuscated scene files put the group in front ("abc-show.s03e02…"),
    # while the release folder usually carries the clean name ("Show.S03E02…-ABC").
    # all lower case only, so "Spider-Man" never turns into "Man"
    if title == title.lower() and (m := re.match(r"^[a-z0-9]{2,8}-(.+)$", title)):
        alts.append(m.group(1))
    if parent_title := _first(parent.get("title")):
        alts.append(str(parent_title))
    year = _first(info.get("year")) or _first(parent.get("year"))
    part = _first(info.get("part")) or _first(info.get("cd"))
    if info.get("type") == "episode":
        season = _first(info.get("season"))
        ep = info.get("episode")
        episodes = ep if isinstance(ep, list) else ([ep] if ep is not None else [])
        nums = episode_numbers(path.name)
        if season is None and nums:
            season, episodes = nums
        # "Blade.Runner.1982.The.Final.Cut": no season, no episode, but a year - that is a movie
        if season is not None or episodes or not year:
            return Parsed("episode", title, year, season, [int(e) for e in episodes], part, alt_titles=alts)
    return Parsed("movie", title, year, part=part, edition=_edition(info, path.name), alt_titles=alts)


def companions(video: Path) -> list[Path]:
    """Subtitle files next to the video sharing its name (Film.de.forced.srt)."""
    stem = video.stem.lower() + "."
    try:
        entries = list(video.parent.iterdir())
    except OSError:
        return []
    return sorted(
        p for p in entries
        if p != video and p.suffix.lower() in SUB_EXT and p.name.lower().startswith(stem) and p.is_file()
    )


def companion_target(comp: Path, video: Path, new_video: Path) -> Path:
    rest = comp.name[len(video.stem):]
    return new_video.parent / (new_video.stem + rest)
