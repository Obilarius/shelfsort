"""Movie editions (Director's Cut, 3D, …), extras and multi-part movies."""
from pathlib import Path

import pytest

from shelfsort import naming
from shelfsort.audit import AuditOptions, audit_movie_dir
from shelfsort.importer import build_import_plan
from shelfsort.library import Library
from shelfsort.naming import PRESETS, Scheme, movie_file
from shelfsort.parse import parse_release, walk_videos
from test_core import FakeTMDB, touch


@pytest.fixture(autouse=True)
def plex_scheme_afterwards():
    yield
    naming.set_scheme(Scheme())


@pytest.mark.parametrize("name, kind, edition", [
    ("Aliens.1986.Directors.Cut.1080p.BluRay.x264-GRP.mkv", "movie", "Director's Cut"),
    ("Avatar.2009.EXTENDED.1080p.BluRay.x264-GRP.mkv", "movie", "Extended"),
    ("Avatar.2009.3D.HSBS.1080p.BluRay.x264-GRP.mkv", "movie", "3D"),
    ("Avatar.2009.Extended.3D.HOU.1080p.mkv", "movie", "Extended 3D"),
    # used to be read as an episode because of "The Final Cut"
    ("Blade.Runner.1982.The.Final.Cut.1080p.BluRay.x264-GRP.mkv", "movie", "Final Cut"),
    ("Arrival.2016.LIMITED.1080p.mkv", "movie", None),  # a release tag, not an edition
    ("Show.S01E02.Extended.1080p.mkv", "episode", None),
])
def test_editions_are_recognised(name, kind, edition):
    p = parse_release(Path(name))
    assert (p.kind, p.edition) == (kind, edition)


def test_edition_names_per_scheme():
    assert movie_file("Aliens (1986)", "Director's Cut", s=PRESETS["plex"]) == "Aliens (1986) {edition-Director's Cut}"
    assert movie_file("Aliens (1986)", "Director's Cut", s=PRESETS["jellyfin"]) == "Aliens (1986) - Director's Cut"
    assert movie_file("Kill Bill (2003)", None, 2) == "Kill Bill (2003) - pt2"


def test_extras_are_not_main_videos(tmp_path):
    d = tmp_path / "Arrival (2016)"
    for rel in ["Arrival (2016).mkv", "Arrival (2016)-trailer.mkv", "Bonus/Making of.mkv", "Featurettes/x.mkv"]:
        touch(d / rel)
    assert walk_videos(d) == [d / "Arrival (2016).mkv"]
    assert len(walk_videos(d, skip_extras=False)) == 4


def _audit(d, lib_root):
    lib = Library(lib_root, lib_root)
    return audit_movie_dir(d, FakeTMDB(), lib, AuditOptions())


def test_library_check_keeps_editions_side_by_side(tmp_path):
    d = tmp_path / "Aliens (1986) {tmdb-679}"
    touch(d / "Aliens (1986).mkv")
    touch(d / "Aliens.1986.Directors.Cut.1080p.BluRay.x264-GRP.mkv")
    touch(d / "Aliens (1986) - Special Edition.mkv")  # Jellyfin style -> Plex tag
    [item] = _audit(d, tmp_path)
    assert item.status == "ok"
    targets = sorted(op.dst.name for op in item.ops)
    assert targets == ["Aliens (1986) {edition-Director's Cut}.mkv", "Aliens (1986) {edition-Special Edition}.mkv"]


def test_two_plain_files_still_need_a_look(tmp_path):
    d = tmp_path / "Aliens (1986) {tmdb-679}"
    touch(d / "Aliens (1986).mkv")
    touch(d / "aliens.1986.1080p.mkv")
    [item] = _audit(d, tmp_path)
    assert item.status == "review" and "Videodateien" in item.note


def test_multi_part_movie(tmp_path):
    d = tmp_path / "Kill Bill (2003) {tmdb-24}"
    touch(d / "Kill.Bill.2003.CD1.DVDRip.XviD-GRP.avi")
    touch(d / "Kill.Bill.2003.CD2.DVDRip.XviD-GRP.avi")
    [item] = _audit(d, tmp_path)
    assert item.status == "ok"
    assert sorted(op.dst.name for op in item.ops) == ["Kill Bill (2003) - pt1.avi", "Kill Bill (2003) - pt2.avi"]


def test_import_adds_an_edition_next_to_the_existing_movie(tmp_path):
    movies, tv = tmp_path / "movies", tmp_path / "tv"
    tv.mkdir(parents=True)
    touch(movies / "American Sniper (2014) {tmdb-84}" / "American Sniper (2014).mkv")
    dl = tmp_path / "dl"
    touch(dl / "American.Sniper.2014.Extended.1080p.BluRay.x264-GRP.mkv")
    touch(dl / "American.Sniper.2014.1080p.WEB.x264-GRP.mkv")
    items = build_import_plan(dl, FakeTMDB(), Library(movies, tv), 0)
    by_name = {it.source.name: it for it in items}
    ext = by_name["American.Sniper.2014.Extended.1080p.BluRay.x264-GRP.mkv"]
    assert ext.target.name == "American Sniper (2014) {edition-Extended}.mkv"
    assert ext.status == "ok" and "Fassung: Extended" in ext.note
    plain = by_name["American.Sniper.2014.1080p.WEB.x264-GRP.mkv"]
    # the same edition again: offered as a replacement, never preselected
    assert plain.status == "review" and not plain.selected and plain.ops[0].replaces is not None
