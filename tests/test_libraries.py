import json
from pathlib import Path

from shelfsort import config as config_mod
from shelfsort.audit import AuditOptions, build_audit_plan
from shelfsort.config import Config, LibraryConfig
from shelfsort.importer import build_import_plan
from shelfsort.library import Library

from test_core import FakeTMDB, touch


def _lib(tmp_path):
    movies, disney = tmp_path / "movies", tmp_path / "disney"
    tv, kids = tmp_path / "tvshows", tmp_path / "kids"
    for d in (movies, disney, tv, kids):
        d.mkdir()
    (disney / "American Sniper (2014) {tmdb-84}").mkdir()  # pretend it lives in the second movie library
    (kids / "Die wilden Siebziger {tmdb-52}" / "Season 05").mkdir(parents=True)
    lib = Library(movies, tv, [movies, disney], [tv, kids],
                  {str(movies).lower(): "Filme", str(disney).lower(): "Disney",
                   str(tv).lower(): "Serien", str(kids).lower(): "Kinder"})
    return lib, movies, disney, tv, kids


def test_existing_items_stay_in_their_library_new_ones_go_to_default(tmp_path):
    lib, movies, disney, tv, kids = _lib(tmp_path)
    dl = tmp_path / "dl"
    sniper = touch(dl / "American.Sniper.2014.German.1080p.BluRay.x264.mkv")
    pressure = touch(dl / "Pressure.2026.German.DL.2160p.mkv")
    ep = touch(dl / "Die.wilden.Siebziger.S05E04.German.mkv")
    items = {i.source: i for i in build_import_plan(dl, FakeTMDB(), lib, 0)}

    assert items[sniper].target.parent == disney / "American Sniper (2014) {tmdb-84}"
    assert items[sniper].library == "Disney"
    assert items[pressure].target.parent.parent == movies and items[pressure].library == "Filme"
    assert items[ep].target.parent == kids / "Die wilden Siebziger {tmdb-52}" / "Season 05"


def test_retarget_moves_import_into_another_library(tmp_path):
    lib, movies, disney, tv, kids = _lib(tmp_path)
    dl = tmp_path / "dl"
    touch(dl / "Pressure.2026.German.DL.2160p.mkv")
    touch(dl / "Die.wilden.Siebziger.S05E04.German.mkv")
    items = build_import_plan(dl, FakeTMDB(), lib, 0)
    movie = next(i for i in items if i.kind == "movie")
    ep = next(i for i in items if i.kind == "episode")

    [moved] = movie.retarget(disney)
    assert moved.target == disney / "Pressure (2026) {tmdb-555}" / "Pressure (2026).mkv"
    assert moved.library == "Disney" and moved.status == "ok"

    # the show already lives in "Kinder": forcing "Serien" would split it -> flagged
    [split] = ep.retarget(tv)
    assert split.target.parent.parent == tv / "Die wilden Siebziger {tmdb-52}"
    assert split.status == "review" and "Kinder" in split.note


def test_audit_covers_all_libraries(tmp_path):
    lib, movies, disney, tv, kids = _lib(tmp_path)
    touch(disney / "American Sniper (2014) {tmdb-84}" / "sniper.mkv")
    touch(kids / "Die wilden Siebziger {tmdb-52}" / "Season 05" / "That.70s.Show.S05E04.German.mkv")
    lib.refresh()
    items = build_audit_plan(FakeTMDB(), lib, AuditOptions(empty=False))
    targets = {i.target.name for i in items if i.ops}
    assert "American Sniper (2014).mkv" in targets
    assert "Die wilden Siebziger - S05E04 - Die Wechseljahre.mkv" in targets


def test_old_config_is_migrated(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"tmdb_key": "k", "movies_root": r"X:\m", "tv_root": r"X:\t",
                                "tv_section": "2", "tv_server_root": "/data/tv"}), encoding="utf-8")
    monkeypatch.setattr(config_mod, "CONFIG_PATH", path)
    cfg = Config.load()
    assert [(l.kind, l.local_root, l.default) for l in cfg.libs] == [("movie", r"X:\m", True), ("show", r"X:\t", True)]
    assert cfg.default_lib("show").section_key == "2" and cfg.is_set_up
    cfg.set_libs(cfg.libs + [LibraryConfig("movie", "Disney", r"X:\d")])
    assert [l.title for l in cfg.libs_of("movie")] == ["Filme", "Disney"]
    assert cfg.default_lib("movie").title == "Filme"


class LangTMDB(FakeTMDB):
    """FakeTMDB that knows two languages: German titles, English = original titles."""

    def __init__(self, language="de-DE"):
        self.language = language

    def for_language(self, language):
        return self if language == self.language else LangTMDB(language)

    def movie(self, i):
        m = super().movie(i)
        if m and self.language.startswith("en"):
            m = {**m, "title": m["original_title"]}
        return m


def test_ov_library_gets_titles_in_its_own_language(tmp_path):
    movies, ov, tv = tmp_path / "movies", tmp_path / "ov", tmp_path / "tvshows"
    for d in (movies, ov, tv):
        d.mkdir()
    lib = Library(movies, tv, [movies, ov], [tv], {str(ov).lower(): "OV"},
                  {str(movies).lower(): "de-DE", str(ov).lower(): "en-US", str(tv).lower(): "de-DE"})
    touch(tmp_path / "dl" / "F1.2025.German.DL.1080p.WEB.mkv")
    [item] = build_import_plan(tmp_path / "dl", LangTMDB(), lib, 0)
    assert item.target.name == "F1 - Der Film (2025).mkv"  # default library: German
    [ov_item] = item.retarget(ov)
    assert ov_item.target == ov / "F1 (2025) {tmdb-911430}" / "F1 (2025).mkv"  # OV library: English
    assert ov_item.match.title == "F1"
