import shutil
from pathlib import Path

from shelfsort import executor, history
from shelfsort.executor import Reporter, execute, move_file
from shelfsort.plan import Op, PlanItem


def _run(items, tmp_path, lib):
    journal = history.Journal(tmp_path / "history", "Test")
    execute(items, Reporter(journal=journal), [lib])
    journal.close()
    return history.runs(tmp_path / "history")[0]


def _undo(run, lib):
    logs = []
    changed, ok, skipped = history.undo(run, logs.append, [lib], move_file)
    return changed, ok, skipped, logs


def test_undo_import(tmp_path, monkeypatch):
    monkeypatch.setattr(executor, "send2trash", lambda p: shutil.rmtree(p))  # no real recycle bin in tests
    monkeypatch.setattr(executor, "crosses_drive", lambda a, b: True)  # copy path like a network share
    rel, lib = tmp_path / "dl" / "Movie.2020.1080p", tmp_path / "lib"
    rel.mkdir(parents=True)
    lib.mkdir()
    (rel / "movie.mkv").write_bytes(b"x" * 3000)
    (rel / "movie.de.srt").write_text("sub")
    dst = lib / "Movie (2020) {tmdb-1}"
    it = PlanItem("movie", rel / "movie.mkv", "Movie", target=dst / "Movie (2020).mkv", selected=True, cleanup=rel,
                  ops=[Op("move", rel / "movie.mkv", dst / "Movie (2020).mkv"),
                       Op("move", rel / "movie.de.srt", dst / "Movie (2020).de.srt")])
    run = _run([it], tmp_path, lib)
    assert not rel.exists() and (dst / "Movie (2020).mkv").exists()
    assert [e["op"] for e in run.changes] == ["move", "move", "trash"]

    changed, ok, skipped, logs = _undo(run, lib)
    assert (rel / "movie.mkv").read_bytes() == b"x" * 3000 and (rel / "movie.de.srt").exists()
    assert not dst.exists() and lib.exists()  # emptied movie folder gone, library root stays
    assert (ok, skipped) == (2, 0) and any("Papierkorb" in s for s in logs)
    assert changed == {lib}
    assert history.runs(tmp_path / "history")[0].undone


def test_undo_chain_and_folder_rename(tmp_path):
    lib = tmp_path / "lib"
    old, new = lib / "Show", lib / "Show {tmdb-5}"
    season = old / "Season 01"
    season.mkdir(parents=True)
    for n in (1, 2):
        (season / f"E0{n}.mkv").write_text(f"episode {n}")
    (lib / "Empty").mkdir()
    (lib / "Empty" / "poster.jpg").write_text("p")
    # rename the show folder, shift E01->E02 and E02->E03 (needs parking), delete an empty folder
    items = [
        PlanItem("show_dir", old, "", target=new, selected=True, ops=[Op("rename_dir", old, new)]),
        PlanItem("episode", season / "E01.mkv", "", selected=True,
                 ops=[Op("move", season / "E01.mkv", season / "E02.mkv")]),
        PlanItem("episode", season / "E02.mkv", "", selected=True,
                 ops=[Op("move", season / "E02.mkv", season / "E03.mkv")]),
        PlanItem("empty", lib / "Empty", "", selected=True, ops=[Op("delete_dir", lib / "Empty")]),
    ]
    run = _run(items, tmp_path, lib)
    s_new = new / "Season 01"
    assert (s_new / "E02.mkv").read_text() == "episode 1" and (s_new / "E03.mkv").read_text() == "episode 2"
    assert not (lib / "Empty").exists()

    _, ok, skipped, _ = _undo(run, lib)
    assert skipped == 0
    assert (season / "E01.mkv").read_text() == "episode 1" and (season / "E02.mkv").read_text() == "episode 2"
    assert not new.exists() and (lib / "Empty").is_dir()


def test_undo_skips_changed_files(tmp_path):
    lib = tmp_path / "lib"
    lib.mkdir()
    a, b = lib / "a.mkv", lib / "b.mkv"
    c, d = lib / "c.mkv", lib / "d.mkv"
    a.write_text("a")
    c.write_text("c")
    run = _run([PlanItem("movie", a, "", selected=True, ops=[Op("move", a, b)]),
                PlanItem("movie", c, "", selected=True, ops=[Op("move", c, d)])], tmp_path, lib)
    b.write_text("changed afterwards")  # different size
    c.write_text("new file in the old place")
    _, ok, skipped, logs = _undo(run, lib)
    assert (ok, skipped) == (0, 2)
    assert b.read_text() == "changed afterwards" and d.read_text() == "c"  # nothing overwritten


def test_empty_runs_are_not_kept(tmp_path):
    for _ in range(3):
        history.Journal(tmp_path, "nothing").close()
    assert history.runs(tmp_path) == []
    for _ in range(4):
        j = history.Journal(tmp_path, "x")
        j.renamed(tmp_path / "a", tmp_path / "b")
        j.close()
    history.prune(tmp_path, keep=2)
    assert len(history.runs(tmp_path)) == 2
