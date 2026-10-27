"""Comparing the quality of two copies of the same movie, from what their names tell."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from guessit import guessit

from .i18n import tr

RESOLUTION = {"2160p": 4, "4320p": 5, "1080p": 3, "1080i": 3, "720p": 2, "576p": 1, "576i": 1, "480p": 1, "480i": 1}
SOURCE = {"ultra hd blu-ray": 5, "blu-ray": 4, "web": 3, "hd-dvd": 3, "hdtv": 2, "dvd": 1, "tv": 1, "vhs": 0}


@dataclass
class Quality:
    resolution: int | None  # rank, see RESOLUTION
    source: int | None  # rank, see SOURCE (remux and WEB-DL above rips)
    size: int
    label: str  # "2160p Blu-ray Remux, 58.1 GB"


def _first(v):
    return v[0] if isinstance(v, list) and v else v


def quality_of(path: Path) -> Quality:
    try:
        info = dict(guessit(path.name))
    except Exception:
        info = {}
    res_name = str(_first(info.get("screen_size")) or "")
    src_name = str(_first(info.get("source")) or "")
    other = info.get("other") or []
    other = other if isinstance(other, list) else [other]
    source = SOURCE.get(src_name.lower())
    if source is not None:
        # a remux keeps the disc's quality, a rip re-encodes it: half steps inside the same source
        source = source + (0.5 if "Remux" in other else 0) - (0.25 if "Rip" in other else 0)
    try:
        size = path.stat().st_size
    except OSError:
        size = 0
    parts = [p for p in (res_name, src_name, "Remux" if "Remux" in other else "") if p]
    parts.append(f"{size / 1024 ** 3:.1f} GB")
    return Quality(RESOLUTION.get(res_name.lower()), source, size, " ".join(parts[:-1]) + (", " if parts[:-1] else "") + parts[-1])


def compare(new: Quality, old: Quality) -> tuple[int | None, str]:
    """(1 new is better, -1 worse, 0 same, None unknown) and a note for the table."""
    for attr in ("resolution", "source"):
        a, b = getattr(new, attr), getattr(old, attr)
        if a is not None and b is not None and a != b:
            verdict = 1 if a > b else -1
            break
    else:
        known = new.resolution is not None and old.resolution is not None
        verdict = 0 if known and new.source is not None and old.source is not None else None
    if verdict == 1:
        note = tr("Bessere Qualität: {new} statt {old}", new=new.label, old=old.label)
    elif verdict == -1:
        note = tr("Vorhandene Datei ist besser: {old} statt {new}", new=new.label, old=old.label)
    elif verdict == 0:
        note = tr("Gleiche Qualität: {new} / vorhanden {old}", new=new.label, old=old.label)
    else:
        note = tr("Qualität der vorhandenen Datei unbekannt: neu {new}, vorhanden {old}", new=new.label, old=old.label)
    return verdict, note
