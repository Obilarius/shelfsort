"""History of executed runs and undoing them.

Every run writes one JSON-lines file: a header, then one line per file system change, written
the moment it happened (so even a crash mid-run leaves an accurate record). Undo walks the lines
backwards and reverses what can be reversed safely; anything that changed since is skipped.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from .config import CONFIG_PATH
from .i18n import tr

HISTORY_DIR = CONFIG_PATH.parent / "history"
KEEP = 50  # older runs are deleted


class Journal:
    """Recorder the executor reports each change to. Without a directory it records nothing."""

    def __init__(self, directory: Path | None = None, title: str = ""):
        self.path: Path | None = None
        self.count = 0
        if directory is None:
            return
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = directory / f"run-{stamp}.jsonl"
        n = 1
        while path.exists():
            n += 1
            path = directory / f"run-{stamp}-{n}.jsonl"
        self.path = path
        self._write({"run": title, "started": time.time()})

    def _write(self, entry: dict) -> None:
        if self.path is None:
            return
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _record(self, op: str, **fields) -> None:
        self.count += 1
        self._write({"op": op, **{k: str(v) if isinstance(v, Path) else v for k, v in fields.items()}})

    def renamed(self, src: Path, dst: Path) -> None:
        """File or folder renamed / moved on the same drive."""
        self._record("rename", src=src, dst=dst)

    def moved(self, src: Path, dst: Path, size: int) -> None:
        """File moved; size identifies it again on undo."""
        self._record("move", src=src, dst=dst, size=size)

    def deleted(self, path: Path) -> None:
        self._record("delete_dir", path=path)

    def trashed(self, path: Path) -> None:
        self._record("trash", path=path)

    def close(self) -> None:
        """Drop the file if nothing happened, keep only the newest runs."""
        if self.path is None:
            return
        if not self.count:
            self.path.unlink(missing_ok=True)
        prune(self.path.parent)


@dataclass
class Run:
    path: Path
    title: str
    started: float
    entries: list[dict] = field(default_factory=list)
    undone: float | None = None

    @property
    def changes(self) -> list[dict]:
        return [e for e in self.entries if "op" in e]

    def when(self) -> str:
        return datetime.fromtimestamp(self.started).strftime("%Y-%m-%d %H:%M")


def load(path: Path) -> Run:
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            entries.append(json.loads(line))
        except ValueError:
            pass  # half-written last line after a crash
    head = entries[0] if entries and "run" in entries[0] else {}
    undone = next((e["undone"] for e in entries if "undone" in e), None)
    return Run(path, head.get("run", ""), head.get("started", path.stat().st_mtime), entries, undone)


def runs(directory: Path = HISTORY_DIR) -> list[Run]:
    """All recorded runs, newest first."""
    if not directory.exists():
        return []
    out = []
    for p in directory.glob("run-*.jsonl"):
        try:
            out.append(load(p))
        except OSError:
            pass
    return sorted(out, key=lambda r: r.started, reverse=True)


def prune(directory: Path, keep: int = KEEP) -> None:
    for old in sorted(directory.glob("run-*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[keep:]:
        old.unlink(missing_ok=True)


def describe(e: dict) -> str:
    """One line per change for the history dialog."""
    op = e.get("op")
    if op in ("rename", "move"):
        src, dst = Path(e["src"]), Path(e["dst"])
        if src.parent == dst.parent:
            return f"{src.name} → {dst.name}"
        return f"{src} → {dst}"
    if op == "delete_dir":
        return tr("Gelöscht: {path}", path=e["path"])
    if op == "trash":
        return tr("Papierkorb: {path}", path=e["path"])
    return str(e)


def _size(p: Path) -> int:
    try:
        return p.stat().st_size
    except OSError:
        return -1


def _remove_empty_parents(start: Path, roots: list[Path]) -> None:
    """Folders emptied by the undo go away, up to (never including) a library root.
    Outside the libraries (e.g. a download folder) nothing is removed."""
    d = start
    while any(r in d.parents for r in roots):
        try:
            if any(d.iterdir()):
                return
            d.rmdir()
        except OSError:
            return
        d = d.parent


def undo(run: Run, log: Callable[[str], None], library_roots: list[Path],
         move_file: Callable[[Path, Path], None]) -> tuple[set[Path], int, int]:
    """Reverse a run. Returns (changed folders for the Plex scan, undone, skipped)."""
    changed: set[Path] = set()
    left: set[Path] = set()  # folders that might be empty now
    ok = skipped = 0

    def skip(text: str) -> None:
        nonlocal skipped
        skipped += 1
        log(tr("Übersprungen: {reason}", reason=text))

    for e in reversed(run.changes):
        op = e["op"]
        try:
            if op in ("rename", "move"):
                src, dst = Path(e["src"]), Path(e["dst"])
                if not dst.exists():
                    skip(tr("{name} ist nicht mehr da", name=dst))
                    continue
                if src.exists():
                    skip(tr("{name} ist inzwischen belegt", name=src))
                    continue
                if op == "move" and _size(dst) != e.get("size"):
                    skip(tr("{name} wurde seitdem verändert", name=dst))
                    continue
                src.parent.mkdir(parents=True, exist_ok=True)
                if op == "rename":
                    os.rename(dst, src)
                else:
                    move_file(dst, src)
                changed.update((src.parent, dst.parent))
                left.add(dst.parent)
                ok += 1
                log(tr("Zurück: {new} → {old}", new=dst.name, old=src))
            elif op == "delete_dir":
                path = Path(e["path"])
                path.mkdir(parents=True, exist_ok=True)
                changed.add(path.parent)
                ok += 1
                log(tr("Ordner wieder angelegt: {path}", path=path))
            elif op == "trash":  # only a hint: the videos themselves are back already
                log(tr("{path} liegt im Papierkorb – bei Bedarf dort wiederherstellen", path=e["path"]))
        except Exception as ex:
            skip(f"{e.get('dst') or e.get('path')}: {ex}")

    for d in sorted(left, key=lambda p: len(p.parts), reverse=True):
        _remove_empty_parents(d, library_roots)

    run.undone = time.time()
    with open(run.path, "a", encoding="utf-8") as f:
        f.write(json.dumps({"undone": run.undone, "ok": ok, "skipped": skipped}) + "\n")

    def existing(p: Path) -> Path:  # removed folders: Plex scans their parent instead
        while not p.exists() and p.parent != p:
            p = p.parent
        return p

    lib = {existing(p) for p in changed if any(r == p or r in p.parents for r in library_roots)}
    return lib, ok, skipped
