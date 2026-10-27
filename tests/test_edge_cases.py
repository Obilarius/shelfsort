"""What happens when the disk is full, a share disappears or a file is locked."""
import os
import shutil
from collections import namedtuple
from pathlib import Path

import pytest

from shelfsort import executor, plan
from shelfsort.executor import Blocked, Reporter, execute
from shelfsort.plan import Op, PlanItem, finalize

Usage = namedtuple("Usage", "total used free")


def _setup(tmp_path, n=2, size=5000):
    src, lib = tmp_path / "dl", tmp_path / "lib"
    src.mkdir()
    lib.mkdir()
    items = []
    for i in range(n):
        f = src / f"m{i}.mkv"
        f.write_bytes(b"x" * size)
        items.append(PlanItem("movie", f, f.name, target=lib / f"M{i}.mkv", selected=True,
                              ops=[Op("move", f, lib / f"M{i}.mkv")]))
    return src, lib, items


def test_not_enough_space_touches_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(executor, "crosses_drive", lambda a, b: True)
    monkeypatch.setattr(shutil, "disk_usage", lambda p: Usage(10 ** 12, 0, 1000))
    src, lib, items = _setup(tmp_path)
    with pytest.raises(Blocked, match="Platz"):
        execute(items, Reporter(), [lib])
    assert len(list(src.iterdir())) == 2 and not list(lib.iterdir())


def test_no_write_permission_touches_nothing(tmp_path, monkeypatch):
    src, lib, items = _setup(tmp_path)
    monkeypatch.setattr(executor, "_writable", lambda folder: folder != lib)
    with pytest.raises(Blocked, match="Schreibrechte"):
        execute(items, Reporter(), [lib])
    assert len(list(src.iterdir())) == 2


def test_share_gone_stops_the_run(tmp_path, monkeypatch):
    src, lib, items = _setup(tmp_path, n=3)
    real_move = executor.move_file

    def move(s, d, *a):
        if s.name == "m1.mkv":  # the share drops out during the second file
            shutil.rmtree(lib)
            raise OSError("Der Netzwerkpfad wurde nicht gefunden")
        real_move(s, d, *a)

    monkeypatch.setattr(executor, "move_file", move)
    logs = []
    execute(items, Reporter(log=logs.append), [lib])
    assert [it.status for it in items] == ["done", "error", "ok"]  # third one not even tried
    assert (src / "m1.mkv").exists() and (src / "m2.mkv").exists()
    assert any("nicht mehr erreichbar" in s for s in logs)


def test_partial_is_removed_when_copy_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(executor, "crosses_drive", lambda a, b: True)
    monkeypatch.setattr(executor, "CHUNK", 1000)
    src, lib, items = _setup(tmp_path, n=1)
    calls = 0

    def progress(done, total):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise OSError("Netzwerkfehler")

    with pytest.raises(OSError):
        executor.move_file(items[0].source, items[0].target, progress)
    assert items[0].source.exists() and not list(lib.iterdir())


def test_locked_original_keeps_the_copy(tmp_path, monkeypatch):
    monkeypatch.setattr(executor, "crosses_drive", lambda a, b: True)
    src, lib, items = _setup(tmp_path, n=1)
    real_remove = os.remove

    def remove(p):
        if Path(p).parent == src:
            raise PermissionError("Datei wird verwendet")
        real_remove(p)

    monkeypatch.setattr(os, "remove", remove)
    logs = []
    execute(items, Reporter(log=logs.append), [lib])
    assert items[0].status == "done" and "Original" in items[0].note
    assert (lib / "M0.mkv").read_bytes() == (src / "m0.mkv").read_bytes()
    assert any("von Hand" in s for s in logs)


def test_too_long_paths_are_flagged(monkeypatch):
    monkeypatch.setattr(plan, "long_paths_enabled", lambda: False)
    deep = Path("X:/") / ("a" * 120) / ("b" * 120) / "Film (2020).mkv"
    short = Path("X:/Film (2020)/Film (2020).mkv")
    items = finalize([PlanItem("movie", Path("a.mkv"), "a", target=deep, ops=[Op("move", Path("a.mkv"), deep)]),
                      PlanItem("movie", Path("b.mkv"), "b", target=short, ops=[Op("move", Path("b.mkv"), short)])])
    assert items[0].status == "conflict" and "zu lang" in items[0].note and not items[0].selected
    assert items[1].status == "ok" and items[1].selected
