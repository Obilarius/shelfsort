"""Applying a plan: renaming, moving across drives, deleting, cleaning up."""
from __future__ import annotations

import os
import shutil
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from send2trash import send2trash

from .history import Journal
from .i18n import tr
from .parse import has_video, walk_videos
from .plan import PlanItem

CHUNK = 16 * 1024 * 1024


class Cancelled(Exception):
    pass


@dataclass
class TransferInfo:
    """Snapshot for the progress panel."""
    item_no: int  # 1-based position in this run
    item_count: int
    name: str
    file_done: int
    file_total: int
    all_done: int  # bytes copied across drives so far
    all_total: int


class Reporter:
    """Callbacks from the executor; the GUI forwards them to signals."""

    def __init__(self, log: Callable[[str], None] | None = None,
                 transfer: Callable[[TransferInfo], None] | None = None,
                 item_state: Callable[[PlanItem, str], None] | None = None,
                 cancel: threading.Event | None = None, journal: Journal | None = None):
        self.log = log or (lambda s: None)
        self.journal = journal or Journal()  # records every change for undo
        self.transfer = transfer or (lambda info: None)
        self.item_state = item_state or (lambda it, state: None)
        self.cancel = cancel or threading.Event()

    def check(self) -> None:
        if self.cancel.is_set():
            raise Cancelled()


def _same_file(a: Path, b: Path) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def _check_free(src: Path, dst: Path) -> None:
    if dst.exists() and not _same_file(src, dst):
        raise FileExistsError(tr("Ziel existiert bereits: {path}", path=dst))


def crosses_drive(src: Path, dst: Path) -> bool:
    """True if a move needs copy + delete instead of a rename (different drive / file system)."""
    if os.name == "nt":
        return os.path.splitdrive(str(src))[0].lower() != os.path.splitdrive(str(dst))[0].lower()
    # Linux/macOS have no drive letters: compare the file systems (dst may not exist yet)
    existing = dst
    while not existing.exists() and existing.parent != existing:
        existing = existing.parent
    try:
        return os.stat(src).st_dev != os.stat(existing).st_dev
    except OSError:
        return True  # unsure -> copy, which always works


def move_file(src: Path, dst: Path, progress: Callable[[int, int], None] | None = None,
              check: Callable[[], None] | None = None) -> None:
    _check_free(src, dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not crosses_drive(src, dst):
        os.rename(src, dst)
        return
    # Cross-drive: copy to .partial (Plex ignores it), verify, then swap in and delete source.
    # Cancelling mid-copy removes the .partial and leaves the source untouched.
    size = src.stat().st_size
    tmp = dst.with_name(dst.name + ".partial")
    done = 0
    try:
        with open(src, "rb") as fi, open(tmp, "wb") as fo:
            while chunk := fi.read(CHUNK):
                if check:
                    check()
                fo.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, size)
        shutil.copystat(src, tmp)
        if tmp.stat().st_size != size:
            raise IOError(tr("Größe stimmt nach dem Kopieren nicht: {name}", name=dst.name))
        os.replace(tmp, dst)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    os.remove(src)


class _Remap:
    """Keeps paths valid after folders were renamed earlier in the same run."""

    def __init__(self):
        self.pairs: list[tuple[Path, Path]] = []

    def add(self, old: Path, new: Path) -> None:
        self.pairs.append((old, new))

    def __call__(self, p: Path | None) -> Path | None:
        if p is None:
            return None
        for old, new in self.pairs:
            if p == old:
                return new
            if old in p.parents:
                return new / p.relative_to(old)
        return p


def _size(p: Path) -> int:
    try:
        return p.stat().st_size
    except OSError:
        return 0


def execute(items: list[PlanItem], rep: Reporter, library_roots: list[Path]) -> tuple[set[Path], bool]:
    """Run selected items. Returns (changed library paths, any folder renamed)."""
    todo = [it for it in items if it.selected and it.ops]
    fix = _Remap()
    touched: set[Path] = set()
    # Only cross-drive copies take time; same-drive renames are instant and not counted.
    all_total = sum(_size(o.src) for it in todo for o in it.ops
                    if o.kind == "move" and crosses_drive(o.src, o.dst))
    all_done = 0

    def fail(it: PlanItem, e: Exception) -> None:
        it.status, it.note = "error", str(e)
        rep.log(tr("FEHLER {name}: {error}", name=it.source.name, error=e))
        rep.item_state(it, "error")

    # 1) folder renames first, so file moves inside them can be remapped
    for it in todo:
        for op in (o for o in it.ops if o.kind == "rename_dir"):
            try:
                src, dst = fix(op.src), fix(op.dst)
                _check_free(src, dst)
                os.rename(src, dst)
                rep.journal.renamed(src, dst)
                fix.add(src, dst)
                touched.add(dst)
                rep.log(tr("Ordner: {old} → {new}", old=src.name, new=dst.name))
            except Exception as e:
                fail(it, e)

    # 2a) chains like E06->E07 while E05,5->E06: a file whose path is another move's target is
    #     parked under a temporary name first, so the order of the moves no longer matters.
    pending = [o for it in todo if it.status != "error" for o in it.ops if o.kind == "move"]
    targets = {str(fix(o.dst)).lower() for o in pending}
    parked: dict[int, tuple[Path, Path]] = {}  # id(op) -> (original src, temp)
    for o in pending:
        src = fix(o.src)
        if str(src).lower() in targets and str(src).lower() != str(fix(o.dst)).lower():
            tmp = src.with_name(src.name + ".shelfsort-tmp")
            os.rename(src, tmp)
            rep.journal.renamed(src, tmp)
            parked[id(o)] = (src, tmp)

    def source(o):
        return parked[id(o)][1] if id(o) in parked else fix(o.src)

    # 2) file moves
    cancelled = False
    for n, it in enumerate(todo, 1):
        if it.status == "error":
            continue
        if rep.cancel.is_set():
            cancelled = True
            break
        moves = [o for o in it.ops if o.kind == "move"]
        if not moves:
            continue
        rep.item_state(it, "running")
        base = all_done
        try:
            for i, op in enumerate(moves):
                src, dst = source(op), fix(op.dst)
                cross = crosses_drive(src, dst)
                size = _size(src)

                def progress(d, t, name=dst.name, cross=cross):
                    rep.transfer(TransferInfo(n, len(todo), name, d, t, base + (d if cross else 0), all_total))

                progress(0, size)
                # Only the main video may be cancelled mid-copy; subtitles follow it.
                move_file(src, dst, progress, rep.check if i == 0 else None)
                rep.journal.moved(src, dst, size)
                parked.pop(id(op), None)
                if cross:
                    base += size
                touched.add(dst.parent)
                rep.log(f"{src.name} → {dst}")
            all_done = base
            if not any(o.kind == "delete_dir" for o in it.ops):
                it.status, it.selected = "done", False
                rep.item_state(it, "done")
        except Cancelled:
            it.status, it.note = "cancelled", tr("Abgebrochen – Original unverändert")
            rep.item_state(it, "cancelled")
            cancelled = True
            break
        except Exception as e:
            all_done = base
            fail(it, e)

    # parked files whose move did not happen (error/cancel) get their old name back
    for orig, tmp in parked.values():
        try:
            if tmp.exists() and not orig.exists():
                os.rename(tmp, orig)
                rep.journal.renamed(tmp, orig)
            elif tmp.exists():
                rep.log(tr("ACHTUNG: {temp} konnte nicht zurückbenannt werden ({name} ist belegt)",
                           temp=tmp.name, name=orig.name))
        except OSError as e:
            rep.log(tr("ACHTUNG: {temp} konnte nicht zurückbenannt werden: {error}", temp=tmp, error=e))

    if cancelled:
        rep.log(tr("Abgebrochen – restliche Einträge wurden nicht angefasst."))

    # 3) deletions (empty library folders: network share has no recycle bin -> permanent)
    for it in ([] if cancelled else todo):
        if it.status == "error":
            continue
        dels = [o for o in it.ops if o.kind == "delete_dir"]
        if not dels:
            continue
        try:
            for op in dels:
                path = fix(op.src)
                if has_video(path):
                    raise RuntimeError(tr("Ordner enthält inzwischen ein Video – nicht gelöscht"))
                shutil.rmtree(path)
                rep.journal.deleted(path)
                rep.log(tr("Gelöscht: {path}", path=path))
            it.status, it.selected = "done", False
            rep.item_state(it, "done")
        except Exception as e:
            fail(it, e)

    # items that only had folder renames
    for it in todo:
        if it.status not in ("error", "cancelled", "done") and all(o.kind == "rename_dir" for o in it.ops):
            it.status, it.selected = "done", False
            rep.item_state(it, "done")

    # 4) import leftovers: release folders without videos go to the recycle bin
    cleanup = {it.cleanup for it in todo if it.cleanup}
    for d in sorted(cleanup):
        if any(i.cleanup == d and i.status != "done" for i in items):
            continue  # something from this release is still pending
        if d.exists() and not walk_videos(d, skip_extras=False):  # samples don't count
            try:
                send2trash(str(d))
                rep.journal.trashed(d)
                rep.log(tr("Aufgeräumt (Papierkorb): {name}", name=d.name))
            except Exception as e:
                rep.log(tr("Konnte {path} nicht aufräumen: {error}", path=d, error=e))

    lib_touched = {p for p in touched if any(r == p or r in p.parents for r in library_roots)}
    return lib_touched, bool(fix.pairs)
