from pathlib import Path

from shelfsort.audit import AuditOptions, audit_show_dir
from shelfsort.executor import Reporter, execute
from shelfsort.library import Library
from shelfsort.plan import finalize
from shelfsort.plex_sync import PlexEpisode, find_by_title, similar

# Doctor Who, TheTVDB "BBC iPlayer" order (as Plex's metadata provider returns it, German titles)
EPS = [
    PlexEpisode(6, 13, "Hochzeits-Song"),
    PlexEpisode(6, 14, "Sternenhimmel"),
    PlexEpisode(7, 5, "Die Macht des Wortes"),
    PlexEpisode(7, 6, "Weihnachtsspecial 2012 - Die Schneemänner"),
    PlexEpisode(7, 7, "Die Glocken von Saint John"),
    PlexEpisode(7, 8, "Die Ringe von Akathen"),
    PlexEpisode(7, 9, "Kalter Krieg"),
    PlexEpisode(7, 15, "The Night of the Doctor"),
    PlexEpisode(7, 16, "Der Tag des Doktors"),
]


def touch(p: Path) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(p.name.encode())
    return p


def test_similar():
    assert similar("Die Schneemänner (Christmas Special)", "Weihnachtsspecial 2012 - Die Schneemänner") >= 0.9
    assert similar("Die Ringe von Akhaten", "Die Ringe von Akathen") >= 0.85
    assert similar("Das Herz der TARDIS", "Das Herz der Tardis") == 1.0
    assert similar("Kalter Krieg", "Geisterjagd") < 0.5
    hit, _ = find_by_title(EPS, "Der Tag des Doktors (50th Anniversary Special)")
    assert (hit.season, hit.episode) == (7, 16)


def test_doctor_who_renumbering(tmp_path):
    tv = tmp_path / "tvshows"
    (tmp_path / "movies").mkdir()
    show = tv / "Doctor Who {tmdb-57243}"
    s7 = show / "Staffel 07"
    files = {
        "ok": touch(s7 / "Doctor Who - S07E05 - Die Macht des Wortes.mkv"),
        "snow": touch(s7 / "Doctor Who - S07E05,5 - Die Schneemänner (Christmas Special).mkv"),
        "bells": touch(s7 / "Doctor Who - S07E06 - Die Glocken von Saint John.mkv"),
        "rings": touch(s7 / "Doctor Who - S07E07 - Die Ringe von Akhaten.mkv"),
        "cold": touch(s7 / "Doctor Who - S07E08 - Kalter Krieg.mkv"),
        "stars": touch(s7 / "Doctor Who - S07E00 - Sternenhimmel (Christmas Special).mkv"),
        "day": touch(s7 / "Doctor Who - S07E14 - Der Tag des Doktors (50th Anniversary Special).mkv"),
        "unknown": touch(s7 / "Doctor Who - S07E13 - Irgendwas anderes.mkv"),
    }
    touch(show / "Staffel 06" / "Doctor Who - S06E13 - Hochzeits-Song.mkv")
    lib = Library(tmp_path / "movies", tv)

    items = finalize(audit_show_dir(show, None, lib, AuditOptions(empty=False, plex_sync=True), plex_eps=EPS))
    by = {i.source: i for i in items}

    assert files["ok"] not in by
    assert by[files["snow"]].target.name == "Doctor Who - S07E06 - Die Schneemänner (Christmas Special).mkv"
    assert by[files["bells"]].target.name == "Doctor Who - S07E07 - Die Glocken von Saint John.mkv"
    assert by[files["rings"]].target.name == "Doctor Who - S07E08 - Die Ringe von Akhaten.mkv"
    assert by[files["cold"]].target.name == "Doctor Who - S07E09 - Kalter Krieg.mkv"
    assert by[files["stars"]].target == show / "Staffel 06" / "Doctor Who - S06E14 - Sternenhimmel (Christmas Special).mkv"
    assert by[files["day"]].target.name == "Doctor Who - S07E16 - Der Tag des Doktors (50th Anniversary Special).mkv"
    assert files["unknown"] not in by  # title matches nothing -> probably just translated differently, left alone
    assert all(by[files[k]].selected for k in ("snow", "bells", "rings", "cold", "stars", "day"))

    execute(items, Reporter(), [tv])
    names = sorted(p.name for p in s7.iterdir())
    assert "Doctor Who - S07E06 - Die Schneemänner (Christmas Special).mkv" in names
    assert "Doctor Who - S07E09 - Kalter Krieg.mkv" in names
    assert not any("shelfsort-tmp" in n for n in names)
    # contents moved with their names (no swaps mixed up)
    assert (s7 / "Doctor Who - S07E07 - Die Glocken von Saint John.mkv").read_bytes() == \
        b"Doctor Who - S07E06 - Die Glocken von Saint John.mkv"
    assert (show / "Staffel 06" / "Doctor Who - S06E14 - Sternenhimmel (Christmas Special).mkv").exists()


def test_two_parters_use_season_offset_and_english_titles(tmp_path):
    # Season 9 in iPlayer order: a prologue is E01, so every file is off by one, and Plex names
    # parts 1 and 2 of the Zygon story identically.
    eps = [PlexEpisode(9, 1, "Season 9 Prologue"),
           PlexEpisode(9, 2, "Der Zauberlehrling (1)"), PlexEpisode(9, 3, "Hexenkunst (2)"),
           PlexEpisode(9, 8, "Die Invasion der Zygonen (1)"), PlexEpisode(9, 9, "Die Invasion der Zygonen (2)"),
           PlexEpisode(9, 10, "Morpheus Arme"),
           PlexEpisode(13, 10, "Das Monster von den Sternen", ["The Star Beast"])]
    tv = tmp_path / "tvshows"
    (tmp_path / "movies").mkdir()
    show = tv / "Doctor Who {tmdb-57243}"
    s9 = show / "Staffel 09"
    for name in ("S09E01 - Der Zauberlehrling", "S09E02 - Hexenkunst", "S09E07 - Die Invasion der Zygonen",
                 "S09E08 - Die Inversion der Zygonen", "S09E09 - Morpheus Arme"):
        touch(s9 / f"Doctor Who - {name}.mkv")
    star = touch(show / "Staffel 13" / "Doctor Who - S13E10 - The Star Beast.mkv")
    items = finalize(audit_show_dir(show, None, Library(tmp_path / "movies", tv),
                                    AuditOptions(empty=False, plex_sync=True), plex_eps=eps))
    moves = {i.source.name: i.target.name for i in items if i.ops}
    assert moves["Doctor Who - S09E07 - Die Invasion der Zygonen.mkv"] == \
        "Doctor Who - S09E08 - Die Invasion der Zygonen.mkv"
    assert moves["Doctor Who - S09E08 - Die Inversion der Zygonen.mkv"] == \
        "Doctor Who - S09E09 - Die Inversion der Zygonen.mkv"
    assert moves["Doctor Who - S09E09 - Morpheus Arme.mkv"] == "Doctor Who - S09E10 - Morpheus Arme.mkv"
    assert all(i.status == "ok" for i in items if i.ops)
    assert star not in {i.source for i in items}  # English title matches -> nothing to do


def test_no_false_moves(tmp_path):
    eps = [PlexEpisode(1, 3, "Monster"), PlexEpisode(7, 22, "Ich war einmal"), PlexEpisode(2, 1, "Die Kreuzfahrt"),
           PlexEpisode(1, 1, "Der Endzeit-Heiratsantrag"), PlexEpisode(1, 2, "Lebendig in Tucson")]
    tv = tmp_path / "tvshows"
    (tmp_path / "movies").mkdir()
    show = tv / "Show {tmdb-1}"
    touch(show / "Season 07" / "Show - S07E22 - Götter und Monster.mkv")  # "Monster" is S01E03 - must not move
    placeholder = touch(show / "Season 02" / "Show - S02E01 - Episode 1.mkv")
    touch(show / "Season 01" / "Show - S01E01-E02 - Lebendig in Tucson & Der Endzeit-Heiratsantrag.mkv")
    items = finalize(audit_show_dir(show, None, Library(tmp_path / "movies", tv),
                                    AuditOptions(empty=False, plex_sync=True), plex_eps=eps))
    moves = {i.source.name: i.target.name for i in items if i.ops}
    assert "Show - S07E22 - Götter und Monster.mkv" not in moves
    assert "Show - S01E01-E02 - Lebendig in Tucson & Der Endzeit-Heiratsantrag.mkv" not in moves
    # placeholder title is replaced by the Plex title, number unchanged
    assert moves[placeholder.name] == "Show - S02E01 - Die Kreuzfahrt.mkv"


def test_episode_source_finds_new_shows_by_tmdb_id(tmp_path):
    from shelfsort.plex_sync import PlexEpisodeSource, PlexShow

    class FakeCatalog:
        def __init__(self):
            self.lists = []

        def shows(self, progress=None):
            return {}  # show not in the library yet

        def library_ordering(self, lib=None):
            return "tvdbAiring"

        def match_show(self, tmdb_id):
            return "plex://show/abc" if tmdb_id == 82728 else None

        def load_episodes(self, show: PlexShow, language=None):
            self.lists.append((show.guid, show.ordering))
            return [PlexEpisode(3, 49, "Das Schild"), PlexEpisode(3, 50, "Überraschung")]

    cat = FakeCatalog()
    src = PlexEpisodeSource(cat)
    eps = src(tmp_path / "Bluey {tmdb-82728}", 82728)
    assert [e.title for e in eps] == ["Das Schild", "Überraschung"]
    assert cat.lists == [("plex://show/abc", "tvdbAiring")]  # library default ordering
    assert src(tmp_path / "Unbekannt", 1) is None


def test_target_blocked_by_staying_file(tmp_path):
    tv = tmp_path / "tvshows"
    (tmp_path / "movies").mkdir()
    show = tv / "Doctor Who {tmdb-57243}"
    s7 = show / "Staffel 07"
    touch(s7 / "Doctor Who - S07E06 - Die Glocken von Saint John.mkv")
    blocker = touch(s7 / "Doctor Who - S07E07 - Ganz was anderes.mkv")  # unknown title, stays put
    items = finalize(audit_show_dir(show, None, Library(tmp_path / "movies", tv),
                                    AuditOptions(empty=False, plex_sync=True), plex_eps=EPS))
    bells = next(i for i in items if "Glocken" in i.source.name)
    assert bells.status == "conflict" and blocker.name in bells.note and not bells.selected
