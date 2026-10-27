from pathlib import Path

import pytest

from shelfsort.audit import AuditOptions, build_audit_plan
from shelfsort.executor import Reporter, execute
from shelfsort.importer import build_import_plan
from shelfsort.library import Library
from shelfsort.naming import episode_name, movie_folder, sanitize
from shelfsort.parse import current_episode_title, episode_numbers
from shelfsort.plan import Override


class FakeTMDB:
    movies = {
        911430: {"id": 911430, "title": "F1: Der Film", "original_title": "F1", "release_date": "2025-06-25"},
        555: {"id": 555, "title": "Pressure", "original_title": "Pressure", "release_date": "2026-03-01"},
        84: {"id": 84, "title": "American Sniper", "original_title": "American Sniper", "release_date": "2014-12-11"},
    }
    shows = {
        57243: {"id": 57243, "name": "Doctor Who", "original_name": "Doctor Who", "first_air_date": "2005-03-26"},
        52: {"id": 52, "name": "Die wilden Siebziger", "original_name": "That '70s Show", "first_air_date": "1998-08-23"},
    }
    titles = {(57243, 13, 1): "Kapitel Eins: Die Halloween-Apokalypse", (52, 5, 4): "Die Wechseljahre",
              (52, 5, 5): "Folge Fünf"}

    def search_movie(self, q, year=None):
        return [m for m in self.movies.values() if q.lower() in (m["title"] + m["original_title"]).lower()]

    def search_tv(self, q, year=None):
        return [s for s in self.shows.values() if q.lower() in (s["name"] + s["original_name"]).lower()]

    def movie(self, i):
        return self.movies.get(i)

    def tv(self, i):
        return self.shows.get(i)

    def episode_title(self, tv, s, e):
        return self.titles.get((tv, s, e))

    def episode(self, tv, s, e):
        t = self.titles.get((tv, s, e))
        return {"name": t, "season_number": s, "episode_number": e, "overview": ""} if t else None


def touch(p: Path, size: int = 10) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x" * size)
    return p


@pytest.fixture
def lib_dirs(tmp_path):
    movies, tv = tmp_path / "lib" / "movies", tmp_path / "lib" / "tvshows"
    movies.mkdir(parents=True)
    tv.mkdir(parents=True)
    return movies, tv


def test_naming():
    assert sanitize("F1: Der Film") == "F1 - Der Film"
    assert sanitize("Wer bist du?") == "Wer bist du"
    assert movie_folder("F1: Der Film", 2025, 911430) == "F1 - Der Film (2025) {tmdb-911430}"
    assert episode_name("Show", 1, [1, 2], "A & B") == "Show - S01E01-E02 - A & B"
    assert episode_numbers("Show.S01E01E02.German.mkv") == (1, [1, 2])
    assert episode_numbers("Die wilden Siebziger - S05E04 - Die Wechseljahre") == (5, [4])
    assert current_episode_title("Die wilden Siebziger - S05E04 - Die Wechseljahre") == "Die Wechseljahre"
    assert current_episode_title("Show.S01E02.German.1080p.WEB.x264-GRP") is None
    assert current_episode_title("EUReKA - S01E02 - S.A.R.A.H") == "S.A.R.A.H"
    assert current_episode_title("Show - S01E02.Die.Wechseljahre") == "Die Wechseljahre"
    assert episode_numbers("Doctor Who - S07E05,5 - Die Schneemänner") is None
    assert episode_numbers("Show.S07E05.5.mkv") is None
    assert episode_numbers("Show.S01E02.1080p.WEB.h264-GRP") == (1, [2])  # not "E02.1"
    assert episode_numbers("Show.S01E02.4K.HDR") == (1, [2])


def test_folder_title_year_keeps_numbers_in_titles():
    from shelfsort.audit import _guess_title_year
    assert _guess_title_year("10 Cloverfield Lane") == ("10 Cloverfield Lane", None)
    assert _guess_title_year("Blade Runner 2049") == ("Blade Runner 2049", None)
    assert _guess_title_year("2001 Odyssee im Weltraum (1968)") == ("2001 Odyssee im Weltraum", 1968)
    assert _guess_title_year("Some.Movie.2016.German.DL.1080p.BluRay.x264-GRP") == ("Some Movie", 2016)
    assert _guess_title_year(
        "Pressure.2026.German.5.1.MD.DL.2160p.DV.HDR.Bluray.x265-GRP - by uploader") == ("Pressure", 2026)


def test_import_movie_and_episode(tmp_path, lib_dirs):
    movies, tv = lib_dirs
    dl = tmp_path / "dl"
    rel = "Pressure.2026.German.DL.2160p.x265-GRP - by Someone/Pressure.2026.German.DL.2160p.x265-GRP"
    v = touch(dl / rel / "Pressure.2026.German.DL.2160p.x265-GRP.mkv")
    touch(dl / rel / "Pressure.2026.German.DL.2160p.x265-GRP.de.forced.srt")
    touch(dl / rel / "grp.nfo")
    touch(dl / rel / "Sample" / "pressure-sample.mkv")
    e = touch(dl / "Doctor.Who.2005.S13E01.German.DL.1080p.WEB.x264-GRP.mkv")
    (tv / "Doctor Who {tmdb-57243}" / "Staffel 13").mkdir(parents=True)

    lib = Library(movies, tv)
    items = {i.source: i for i in build_import_plan(dl, FakeTMDB(), lib, 0)}
    assert len(items) == 2

    m = items[v]
    assert m.status == "ok", m.note
    assert m.target == movies / "Pressure (2026) {tmdb-555}" / "Pressure (2026).mkv"
    ep = items[e]
    assert ep.target == tv / "Doctor Who {tmdb-57243}" / "Staffel 13" / \
        "Doctor Who - S13E01 - Kapitel Eins - Die Halloween-Apokalypse.mkv"

    changed, renamed = execute(list(items.values()), Reporter(), [movies, tv])
    assert all(i.status == "done" for i in items.values())
    assert (movies / "Pressure (2026) {tmdb-555}" / "Pressure (2026).de.forced.srt").exists()
    assert not v.exists() and not e.exists()
    assert not (dl / rel.split("/")[0]).exists()  # release folder went to the recycle bin
    assert movies / "Pressure (2026) {tmdb-555}" in changed and not renamed


def test_import_uses_plex_ordering_for_known_shows(tmp_path, lib_dirs):
    from shelfsort.plex_sync import PlexEpisode
    movies, tv = lib_dirs
    (tv / "Doctor Who {tmdb-57243}" / "Staffel 07").mkdir(parents=True)
    dl = tmp_path / "dl"
    six = touch(dl / "Doctor.Who.2005.S07E06.German.DL.1080p.WEB.x264-GRP.mkv")
    nine = touch(dl / "Doctor.Who.2005.S07E99.German.DL.1080p.WEB.x264-GRP.mkv")
    plex = [PlexEpisode(7, 6, "Die Schneemänner", summary="Weihnachten 1892", thumb="https://x/t/p/original/a.jpg")]
    asked = []

    def source(show_dir, tmdb_id=None, language=None):
        asked.append(show_dir)
        return plex

    items = {i.source: i for i in build_import_plan(dl, FakeTMDB(), Library(movies, tv), 0, plex_eps=source)}
    assert items[six].target.name == "Doctor Who - S07E06 - Die Schneemänner.mkv"  # not TMDB's numbering
    assert items[six].episode_info["overview"] == "Weihnachten 1892" and items[six].status == "ok"
    assert items[nine].status == "review" and "Plex-Reihenfolge unbekannt" in items[nine].note
    assert asked and asked[0] == tv / "Doctor Who {tmdb-57243}"


def test_obfuscated_scene_files_use_folder_title(tmp_path, lib_dirs):
    from shelfsort.parse import parse_release
    movies, tv = lib_dirs
    FakeTMDB.shows[82728] = {"id": 82728, "name": "Bluey", "original_name": "Bluey", "first_air_date": "2018-10-01"}
    dl = tmp_path / "dl"
    pack = dl / "Bluey.S03.GERMAN.DL.1080p.WEB.H264-ABC"
    e2 = touch(pack / "Bluey.S03E02.GERMAN.DL.1080P.WEB.H264-ABC" / "abc-bluey.s03e02.german.dl.1080p.web.h264.mkv")
    e3 = touch(pack / "Bluey.S03E03.GERMAN.DL.1080P.WEB.H264-ABC" / "abc-bluey.s03e03.german.dl.1080p.web.h264.mkv")
    assert parse_release(e2).titles()[:2] == ["abc-bluey", "bluey"]
    assert parse_release(Path("Spider-Man.2002.German.DL.1080p.mkv")).title == "Spider-Man"
    assert parse_release(Path("Ant-Man.and.the.Wasp.2018.German.DL.mkv")).title == "Ant-Man and the Wasp"

    items = {i.source: i for i in build_import_plan(dl, FakeTMDB(), Library(movies, tv), 0)}
    assert items[e2].match.tmdb_id == 82728 and items[e2].match.confident
    assert items[e3].target == tv / "Bluey {tmdb-82728}" / "Season 03" / "Bluey - S03E03.mkv"


def test_override_for_many_files_keeps_their_numbers(tmp_path, lib_dirs):
    movies, tv = lib_dirs
    dl = tmp_path / "dl"
    a = touch(dl / "xyz.S05E04.mkv")
    b = touch(dl / "xyz.S05E05.mkv")
    items = build_import_plan(dl, FakeTMDB(), Library(movies, tv), 0)
    assert all(i.status == "review" for i in items)  # unknown show
    new = [i.replan(Override("show", 52))[0] for i in items]  # as the GUI does for a multi-selection
    targets = {i.source: i.target.name for i in new}
    assert targets[a] == "Die wilden Siebziger - S05E04 - Die Wechseljahre.mkv"
    assert targets[b] == "Die wilden Siebziger - S05E05 - Folge Fünf.mkv"


def test_import_existing_title_without_id_needs_review(tmp_path, lib_dirs):
    movies, tv = lib_dirs
    (movies / "American Sniper").mkdir()
    touch(tmp_path / "dl" / "American.Sniper.2014.German.1080p.BluRay.x264.mkv")
    [it] = build_import_plan(tmp_path / "dl", FakeTMDB(), Library(movies, tv), 0)
    assert it.status == "review" and "Ähnlicher Ordner" in it.note and not it.selected


def test_import_override_episode_numbers(tmp_path, lib_dirs):
    movies, tv = lib_dirs
    v = touch(tmp_path / "dl" / "Die.wilden.Siebziger.Folge.mkv")
    [it] = build_import_plan(tmp_path / "dl", FakeTMDB(), Library(movies, tv), 0)
    [it2] = it.replan(Override("show", 52, season=5, episodes=[4]))
    assert it2.target == tv / "Die wilden Siebziger {tmdb-52}" / "Season 05" / \
        "Die wilden Siebziger - S05E04 - Die Wechseljahre.mkv"
    assert it2.selected


def test_audit(lib_dirs):
    movies, tv = lib_dirs
    ok_movie = touch(movies / "F1 - Der Film (2025) {tmdb-911430}" / "F1 - Der Film (2025).mkv")
    old = touch(movies / "American Sniper" / "american.sniper.2014.1080p.mkv")
    touch(movies / "Leer" / "poster.jpg")
    show = tv / "Die wilden Siebziger {tmdb-52}"
    good = touch(show / "Season 05" / "Die wilden Siebziger - S05E04 - Die Wechseljahre.mkv")
    wrong_season = touch(show / "Season 05" / "Die wilden Siebziger - S06E01 - Irgendwas.mkv")
    raw = touch(show / "Season 05" / "That.70s.Show.S05E05.German.DVDRip.x264.mkv")
    (show / "Season 07").mkdir()

    lib = Library(movies, tv)
    items = build_audit_plan(FakeTMDB(), lib, AuditOptions(episode_titles=False))
    by_src = {i.source: i for i in items}

    assert movies / "F1 - Der Film (2025) {tmdb-911430}" not in by_src
    assert good not in by_src
    sniper = by_src[movies / "American Sniper"]
    assert sniper.target == movies / "American Sniper (2014) {tmdb-84}" / "American Sniper (2014).mkv"
    assert by_src[movies / "Leer"].kind == "empty" and not by_src[movies / "Leer"].selected
    assert by_src[show / "Season 07"].kind == "empty"
    assert by_src[wrong_season].target == show / "Season 06" / "Die wilden Siebziger - S06E01 - Irgendwas.mkv"
    # release name without a title -> title comes from TMDB
    assert by_src[raw].target == show / "Season 05" / "Die wilden Siebziger - S05E05 - Folge Fünf.mkv"

    for i in items:
        i.selected = True
    execute(items, Reporter(), [movies, tv])
    assert (movies / "American Sniper (2014) {tmdb-84}" / "American Sniper (2014).mkv").exists()
    assert not (movies / "Leer").exists() and not (show / "Season 07").exists()
    assert (show / "Season 06" / "Die wilden Siebziger - S06E01 - Irgendwas.mkv").exists()
    assert ok_movie.exists() and not old.exists()


def test_audit_show_folder_rename_remaps_episodes(lib_dirs):
    movies, tv = lib_dirs
    show = tv / "Doctor Who (2005)"
    touch(show / "Season 13" / "Doctor.Who.S13E01.mkv")
    items = build_audit_plan(FakeTMDB(), Library(movies, tv), AuditOptions(episode_titles=True))
    for i in items:
        i.selected = True
    _, renamed = execute(items, Reporter(), [movies, tv])
    assert renamed
    assert (tv / "Doctor Who {tmdb-57243}" / "Season 13" /
            "Doctor Who - S13E01 - Kapitel Eins - Die Halloween-Apokalypse.mkv").exists()


def test_main_video_for_rows(tmp_path):
    from shelfsort.reveal import main_video
    movie = tmp_path / "A Movie (2020)"
    video = touch(movie / "a.mkv")
    touch(movie / "a.de.srt")
    touch(movie / "Sample" / "a-sample.mkv")
    assert main_video(video) == video                 # a file row
    assert main_video(movie) == video                 # a folder row (audit): the main video, not the sample
    assert main_video(movie / "a.de.srt") is None     # not a video
    assert main_video(tmp_path / "missing") is None
