"""Naming schemes: Plex, Jellyfin, Kodi and custom; existing folders are recognised in every style."""
import pytest

from shelfsort import naming
from shelfsort.library import Library
from shelfsort.matcher import Match
from shelfsort.naming import (PRESETS, Scheme, episode_name, movie_folder, preset_of, season_folder, show_folder,
                              strip_ids, tmdb_id_of, valid_movie_dir, valid_show_dir)
from shelfsort.importer import _known_movie, _known_show


@pytest.fixture(autouse=True)
def plex_scheme_afterwards():
    yield
    naming.set_scheme(Scheme())


def test_presets_build_names():
    plex, jelly, kodi = PRESETS["plex"], PRESETS["jellyfin"], PRESETS["kodi"]
    assert movie_folder("Arrival", 2016, 329865, plex) == "Arrival (2016) {tmdb-329865}"
    assert movie_folder("Arrival", 2016, 329865, jelly) == "Arrival (2016) [tmdbid-329865]"
    assert movie_folder("Arrival", 2016, 329865, kodi) == "Arrival (2016)"
    assert show_folder("Severance", 95396, 2022, plex) == "Severance {tmdb-95396}"
    assert show_folder("Severance", 95396, 2022, jelly) == "Severance (2022) [tmdbid-95396]"
    assert show_folder("Severance", 95396, 2022, kodi) == "Severance (2022)"
    custom = Scheme(season="Staffel", episode_titles=False)
    assert season_folder(3, custom) == "Staffel 03"
    assert episode_name("Severance", 1, [2], "Half Loop", custom) == "Severance - S01E02"
    assert preset_of(custom) == "" and preset_of(Scheme(ids="jellyfin", show_year=True)) == "jellyfin"


def test_every_id_style_is_read():
    for name in ("Arrival (2016) {tmdb-329865}", "Arrival (2016) [tmdbid-329865]", "Arrival (2016) [tmdbid=329865]"):
        assert tmdb_id_of(name) == 329865
        assert strip_ids(name) == "Arrival (2016)"
    assert tmdb_id_of("Arrival (2016)") is None


def test_valid_folders_follow_the_scheme():
    plex, jelly, kodi = PRESETS["plex"], PRESETS["jellyfin"], PRESETS["kodi"]
    assert valid_movie_dir("Arrival (2016) {tmdb-329865}", plex)
    assert not valid_movie_dir("Arrival (2016) {tmdb-329865}", jelly)  # check library offers the switch
    assert valid_movie_dir("Arrival (2016) [tmdbid-329865]", jelly)
    assert valid_movie_dir("Arrival (2016)", kodi)
    assert not valid_movie_dir("Arrival (2016) {tmdb-329865}", kodi)  # ID gets removed
    assert not valid_movie_dir("Arrival", kodi)  # year missing
    # Plex without show year: a year that is there already is fine, no mass renaming
    assert valid_show_dir("Severance {tmdb-95396}", plex)
    assert valid_show_dir("Severance (2022) {tmdb-95396}", plex)
    assert not valid_show_dir("Severance [tmdbid-95396]", jelly)  # Jellyfin wants the year
    assert valid_show_dir("Severance (2022)", kodi)


def test_import_finds_folders_without_id(tmp_path):
    movies, shows = tmp_path / "movies", tmp_path / "tv"
    (movies / "Arrival (2016)").mkdir(parents=True)
    (shows / "Severance").mkdir(parents=True)
    (shows / "The Bear (2022)").mkdir()
    lib = Library(movies, shows)
    assert _known_movie(lib, Match("movie", 329865, "Arrival", 2016)) == movies / "Arrival (2016)"
    assert _known_movie(lib, Match("movie", 1, "Arrival", 1999)) is None  # other year, other movie
    assert _known_show(lib, Match("show", 95396, "Severance", 2022)) == shows / "Severance"
    assert _known_show(lib, Match("show", 136315, "The Bear", 2022)) == shows / "The Bear (2022)"


def test_global_scheme_is_used_by_default():
    naming.set_scheme(PRESETS["jellyfin"])
    assert movie_folder("Arrival", 2016, 329865) == "Arrival (2016) [tmdbid-329865]"
    assert season_folder(1) == "Season 01"


def test_nfo_written_and_undone(tmp_path):
    from shelfsort import history
    from shelfsort.executor import Reporter, execute
    from shelfsort.executor import move_file
    from shelfsort.plan import Op, PlanItem

    naming.set_scheme(PRESETS["kodi"])
    lib = tmp_path / "lib"
    src = tmp_path / "dl" / "arrival.mkv"
    src.parent.mkdir()
    src.write_bytes(b"x")
    folder = lib / "Arrival (2016)"
    it = PlanItem("movie", src, "a", target=folder / "Arrival (2016).mkv", selected=True,
                  ops=[Op("move", src, folder / "Arrival (2016).mkv")])
    it.add_nfo(folder / "Arrival (2016).nfo", "movie", 329865)
    it.add_nfo(folder / "Arrival (2016).nfo", "movie", 329865)  # only once
    assert [o.kind for o in it.ops] == ["move", "write"]

    journal = history.Journal(tmp_path / "hist", "t")
    lib.mkdir()
    execute([it], Reporter(journal=journal), [lib])
    journal.close()
    nfo = folder / "Arrival (2016).nfo"
    assert nfo.read_text(encoding="utf-8").strip() == "https://www.themoviedb.org/movie/329865"

    run = history.runs(tmp_path / "hist")[0]
    _, ok, skipped = history.undo(run, lambda s: None, [lib], move_file)
    assert (ok, skipped) == (2, 0) and src.exists() and not folder.exists()


def test_nfo_only_with_the_scheme_and_never_overwritten(tmp_path):
    from shelfsort.plan import PlanItem
    existing = tmp_path / "tvshow.nfo"
    existing.write_text("my own")
    it = PlanItem("show_dir", tmp_path, "s")
    it.add_nfo(tmp_path / "new.nfo", "show", 1)  # Plex scheme: no .nfo
    assert not it.ops
    naming.set_scheme(PRESETS["kodi"])
    it.add_nfo(existing, "show", 1)
    assert not it.ops
    it.add_nfo(tmp_path / "new.nfo", "show", 95396)
    assert it.ops[0].text.strip() == "https://www.themoviedb.org/tv/95396"
