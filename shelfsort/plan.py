"""Plan items shared by import and audit."""
from __future__ import annotations

import functools
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .i18n import tr
from .matcher import Match
from .parse import Parsed, companion_target, companions


class ScanCancelled(Exception):
    """The user stopped an import scan or library check; raised from the progress callback."""


@dataclass
class Op:
    kind: str  # "move" | "rename_dir" | "delete_dir" | "write" (new small file, e.g. .nfo)
    src: Path
    dst: Path | None = None
    text: str = ""  # content for "write"


@dataclass
class Override:
    """Manual choice from the match dialog."""
    kind: str  # "movie" | "show"
    tmdb_id: int
    season: int | None = None
    episodes: list[int] | None = None


@dataclass
class PlanItem:
    kind: str  # movie | episode | show_dir | empty
    source: Path
    group: str
    target: Path | None = None
    status: str = "ok"  # ok | review | conflict | error | done
    note: str = ""
    match: Match | None = None
    parsed: Parsed | None = None
    ops: list[Op] = field(default_factory=list)
    selected: bool = False
    cleanup: Path | None = None  # import: release folder to trash afterwards
    # Re-plan with a manual match; returns the replacement items for this group.
    replan: Callable[[Override], list["PlanItem"]] | None = None
    dialog_kind: str = "movie"  # what the match dialog searches for
    library: str = ""  # title of the library the target lies in
    # Import only: re-plan into another library of the same kind (local root folder)
    retarget: Callable[[Path], list["PlanItem"]] | None = None
    episode_info: dict | None = None  # TMDB episode (name, overview, still_path) for the details panel

    def add_note(self, text: str) -> None:
        self.note = f"{self.note} · {text}" if self.note else text

    def add_nfo(self, path: Path, kind: str, tmdb_id: int) -> None:
        """Kodi .nfo with the TMDB link, if the scheme wants one and there is none yet."""
        from . import naming
        if naming.scheme.nfo and not path.exists() and not any(o.kind == "write" and o.dst == path for o in self.ops):
            self.ops.append(Op("write", path, path, naming.nfo_text(kind, tmdb_id)))

    def set_video_move(self, video: Path, target: Path) -> None:
        self.target = target
        if video == target and video.name == target.name:
            return
        self.ops.append(Op("move", video, target))
        for c in companions(video):
            self.ops.append(Op("move", c, companion_target(c, video, target)))


MAX_PATH = 259  # Windows without long path support


@functools.cache
def long_paths_enabled() -> bool:
    """Windows handles paths over 260 characters only with this switched on (Linux/macOS always)."""
    if sys.platform != "win32":
        return True
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\FileSystem") as k:
            return winreg.QueryValueEx(k, "LongPathsEnabled")[0] == 1
    except OSError:
        return False


def too_long(it: PlanItem) -> int:
    """Length of the longest target path if Windows can't handle it, else 0."""
    if long_paths_enabled():
        return 0
    longest = max((len(str(o.dst)) for o in it.ops if o.dst is not None), default=0)
    return longest if longest > MAX_PATH else 0


def finalize(items: list[PlanItem]) -> list[PlanItem]:
    """Flag duplicate targets and over-long paths, preselect what is safe."""
    seen: dict[str, PlanItem] = {}
    for it in items:
        if it.target is None or not it.ops:
            continue
        key = str(it.target).lower()
        if key in seen:
            for x in (seen[key], it):
                x.status = "conflict"
                x.add_note(tr("Mehrere Dateien mit gleichem Ziel"))
        else:
            seen[key] = it
    for it in items:
        if n := too_long(it):
            it.status = "conflict"
            it.add_note(tr("Pfad zu lang ({n} Zeichen, Windows erlaubt {max}) – Titel kürzen oder lange Pfade "
                           "in Windows einschalten", n=n, max=MAX_PATH))
    for it in items:
        it.selected = it.status == "ok" and bool(it.ops) and it.kind != "empty"
    return items
