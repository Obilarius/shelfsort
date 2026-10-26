"""Plan items shared by import and audit."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .i18n import tr
from .matcher import Match
from .parse import Parsed, companion_target, companions


@dataclass
class Op:
    kind: str  # "move" | "rename_dir" | "delete_dir"
    src: Path
    dst: Path | None = None


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

    def set_video_move(self, video: Path, target: Path) -> None:
        self.target = target
        if video == target and video.name == target.name:
            return
        self.ops.append(Op("move", video, target))
        for c in companions(video):
            self.ops.append(Op("move", c, companion_target(c, video, target)))


def finalize(items: list[PlanItem]) -> list[PlanItem]:
    """Flag duplicate targets and preselect what is safe."""
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
        it.selected = it.status == "ok" and bool(it.ops) and it.kind != "empty"
    return items
