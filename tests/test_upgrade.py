"""A better copy of a movie that is already in the library replaces the old file."""
from pathlib import Path

from shelfsort import executor, history
from shelfsort.executor import Reporter, execute, move_file
from shelfsort.importer import build_import_plan
from shelfsort.library import Library
from shelfsort.quality import compare, quality_of
from test_core import FakeTMDB, touch


def q(name, tmp_path, size=10):
    return quality_of(touch(tmp_path / name, size))


def test_quality_order(tmp_path):
    uhd = q("A.2016.2160p.UHD.BluRay.x265-G.mkv", tmp_path)
    remux = q("A.2016.1080p.BluRay.REMUX.AVC-G.mkv", tmp_path)
    bluray = q("A.2016.1080p.BluRay.x264-G.mkv", tmp_path)
    web = q("A.2016.1080p.WEB-DL.H264-G.mkv", tmp_path)
    webrip = q("A.2016.1080p.WEBRip.x264-G.mkv", tmp_path)
    sd = q("A.2016.DVDRip.XviD-G.avi", tmp_path)
    plain = q("Arrival (2016).mkv", tmp_path)  # already renamed: nothing to read
    assert compare(uhd, bluray)[0] == 1
    assert compare(remux, bluray)[0] == 1
    assert compare(bluray, web)[0] == 1
    assert compare(web, webrip)[0] == 1
    assert compare(sd, web)[0] == -1
    assert compare(bluray, plain)[0] is None and "unbekannt" in compare(bluray, plain)[1]


def _import(tmp_path, existing_name, new_name):
    movies, tv = tmp_path / "movies", tmp_path / "tv"
    tv.mkdir(parents=True)
    folder = movies / "American Sniper (2014) {tmdb-84}"
    old = touch(folder / existing_name, 5)
    touch(folder / (Path(existing_name).stem + ".de.srt"), 1)
    new = touch(tmp_path / "dl" / new_name, 9)
    touch(tmp_path / "dl" / (Path(new_name).stem + ".de.srt"), 2)
    [item] = build_import_plan(tmp_path / "dl", FakeTMDB(), Library(movies, tv), 0)
    return item, old, new, folder, movies


def test_better_copy_is_offered_and_replaces(tmp_path):
    item, old, new, folder, movies = _import(tmp_path, "American.Sniper.2014.720p.HDTV.x264-G.mkv",
                                            "American.Sniper.2014.1080p.BluRay.x264-G.mkv")
    assert item.status == "review" and not item.selected and "Bessere Qualität" in item.note
    assert item.ops[0].replaces == old
    item.selected = True
    journal = history.Journal(tmp_path / "hist", "t")
    execute([item], Reporter(journal=journal), [movies])
    journal.close()
    assert item.status == "done"
    assert not old.exists() and not new.exists()
    assert (folder / "American Sniper (2014).mkv").stat().st_size == 9
    assert (folder / "American Sniper (2014).de.srt").stat().st_size == 2
    # undo brings the new file back, says that the old one is gone
    logs = []
    history.undo(history.runs(tmp_path / "hist")[0], logs.append, [movies], move_file)
    assert new.exists() and any("nicht wiederherstellen" in s for s in logs)


def test_worse_copy_is_a_conflict(tmp_path):
    item, *_ = _import(tmp_path, "American.Sniper.2014.2160p.UHD.BluRay.x265-G.mkv",
                       "American.Sniper.2014.720p.HDTV.x264-G.mkv")
    assert item.status == "conflict" and "besser" in item.note


def test_replace_across_drives_keeps_old_until_copy_is_done(tmp_path, monkeypatch):
    monkeypatch.setattr(executor, "crosses_drive", lambda a, b: True)
    old = touch(tmp_path / "lib" / "A (2016).mkv", 5)
    new = touch(tmp_path / "dl" / "a.mkv", 9)

    def fail(done, total):
        raise OSError("network gone")

    try:
        move_file(new, old, fail, overwrite=True)
    except OSError:
        pass
    assert old.stat().st_size == 5 and new.exists()  # nothing lost
    move_file(new, old, overwrite=True)
    assert old.stat().st_size == 9 and not new.exists()
