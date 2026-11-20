"""Files numbered by another ordering than the one Plex uses (Bluey season 3 from Disney+)."""
from pathlib import Path

from test_core import FakeTMDB, touch

from shelfsort.audit import AuditOptions, audit_show_dir
from shelfsort.executor import Reporter, execute
from shelfsort.importer import build_import_plan
from shelfsort.library import Library
from shelfsort.plan import Override, finalize
from shelfsort.plex_sync import PlexEpisode, ordering_fit

# Bluey season 3: TheTVDB aired order (what Plex uses) - Disney+ starts with "Eigenes Zimmer" and has
# "Perfekt" as episode 14. "Das Päckchen-Spiel" is the one episode a minute longer.
AIRED = ["Perfekt", "Eigenes Zimmer", "Der Hindernisparcours", "Versprechen", "Omelette", "Neugeboren",
         "Das doppelte Kind", "Gemeinhorn", "Curry-Mission", "Zauberei", "Schach", "Schafshund", "Hausarbeit",
         "Das Päckchen-Spiel"]
DISNEY = AIRED[1:] + AIRED[:1]
ENGLISH = {"Neugeboren": "Born Yesterday"}


def eps(titles: list[str]) -> list[PlexEpisode]:
    return [PlexEpisode(3, n, t, alt_titles=[ENGLISH[t]] if t in ENGLISH else [], guid=f"plex://episode/{t}",
                        duration=480 if t == "Das Päckchen-Spiel" else 420)
            for n, t in enumerate(titles, 1)]


def lengths(titles: list[str]) -> dict[tuple[int, int], int]:
    """What the server measures for files holding these episodes (a little longer than the metadata says)."""
    return {(3, n): (502 if t == "Das Päckchen-Spiel" else 439) for n, t in enumerate(titles, 1)}


def test_lengths_point_to_the_ordering_the_files_follow():
    others = {"tvdbDisney": eps(DISNEY), "tmdbAiring": eps(AIRED)}
    assert ordering_fit(lengths(DISNEY), eps(AIRED), others) == {3: ["tvdbDisney"]}
    assert ordering_fit(lengths(AIRED), eps(AIRED), others) == {}  # files fit Plex's ordering
    flat = {k: 439 for k in lengths(DISNEY)}  # all the same length: nothing to tell
    assert ordering_fit(flat, eps(AIRED), others) == {}


def bluey(tmp_path) -> tuple[Path, Path, Library, dict[str, Path]]:
    tv = tmp_path / "tvshows"
    (tmp_path / "movies").mkdir()
    show = tv / "Bluey {tmdb-82728}"
    # imported by number from a Disney+ release: the name says "Omelette", the file is "Neugeboren"
    files = {DISNEY[n - 1]: touch(show / "Season 03" / f"Bluey - S03E{n:02d} - {AIRED[n - 1]}.mkv")
             for n in range(1, 15)}
    for content, f in files.items():
        f.write_text(content, encoding="utf-8")
    return tv, show, Library(tmp_path / "movies", tv), files


def test_library_check_renumbers_a_season_by_length(tmp_path):
    tv, show, lib, files = bluey(tmp_path)
    hints = {3: [("tvdbDisney", "TheTVDB (Disney+)", eps(DISNEY))]}
    items = finalize(audit_show_dir(show, None, lib, AuditOptions(empty=False, plex_sync=True),
                                    plex_eps=eps(AIRED), hints=hints))
    hint = next(i for i in items if i.kind == "season")
    assert hint.status == "review" and "Disney+" in hint.note and not hint.ops
    by = {i.source: i for i in items if i.kind == "episode"}
    assert by[files["Neugeboren"]].target.name == "Bluey - S03E06 - Neugeboren.mkv"
    assert by[files["Perfekt"]].target.name == "Bluey - S03E01 - Perfekt.mkv"
    assert all(i.status == "review" and not i.selected for i in by.values())  # nothing runs unseen
    assert len(by) == 14

    for i in by.values():
        i.selected = True
    execute(items, Reporter(), [tv])
    for n, title in enumerate(AIRED, 1):
        f = show / "Season 03" / f"Bluey - S03E{n:02d} - {title}.mkv"
        assert f.read_text(encoding="utf-8") == title  # every file now carries the name of what it holds


def test_tied_orderings_wait_for_a_choice(tmp_path):
    tv, show, lib, files = bluey(tmp_path)
    dvd_eps = eps(DISNEY)  # made up: same lengths as Disney+, but another episode 1
    dvd_eps[0] = PlexEpisode(3, 1, "Versprechen", guid="plex://episode/Versprechen", duration=420)
    hints = {3: [("tvdbDisney", "TheTVDB (Disney+)", eps(DISNEY)), ("tvdbDvd", "TheTVDB (DVD)", dvd_eps)]}
    items = finalize(audit_show_dir(show, None, lib, AuditOptions(empty=False, plex_sync=True),
                                    plex_eps=eps(AIRED), hints=hints))
    hint = next(i for i in items if i.kind == "season")
    assert hint.dialog_kind == "ordering" and [l for _, l in hint.choices] == ["TheTVDB (Disney+)", "TheTVDB (DVD)"]
    assert not [i for i in items if i.kind == "episode"]  # no guessing between them

    items = hint.replan(Override("ordering", 0, ordering="tvdbDisney"))
    by = {i.source: i for i in items if i.kind == "episode"}
    assert by[files["Neugeboren"]].target.name == "Bluey - S03E06 - Neugeboren.mkv"
    assert next(i for i in items if i.kind == "season").choices  # can still be changed


class Source:
    """Plex episode source as the import sees it: Plex's list plus the other orderings."""

    def __call__(self, show_dir, tmdb_id=None, language=None):
        return eps(AIRED)

    def orderings(self, show_dir, tmdb_id=None, language=None):
        return [("tvdbDisney", "TheTVDB (Disney+)", eps(DISNEY))]


def test_import_translates_streaming_numbers_and_flags_doubtful_ones(tmp_path):
    FakeTMDB.shows[82728] = {"id": 82728, "name": "Bluey", "original_name": "Bluey", "first_air_date": "2018-10-01"}
    tv, movies = tmp_path / "tv", tmp_path / "movies"
    (tv / "Bluey {tmdb-82728}" / "Season 03").mkdir(parents=True)
    movies.mkdir()
    dl = tmp_path / "dl"
    disney = touch(dl / "Bluey.S03E06.German.DL.1080p.DSNP.WEB.h264-GRP.mkv")
    titled = touch(dl / "Bluey.S03E09.Born.Yesterday.1080p.WEB-DL.mkv")
    plain = touch(dl / "Bluey.S03E08.German.DL.1080p.WEB.h264-GRP.mkv")
    items = {i.source: i for i in build_import_plan(dl, FakeTMDB(), Library(movies, tv), 0, plex_eps=Source())}

    assert items[disney].target.name == "Bluey - S03E07 - Das doppelte Kind.mkv"
    assert items[disney].status == "review" and "Disney+" in items[disney].note
    assert items[titled].target.name == "Bluey - S03E06 - Neugeboren.mkv"  # the title decides
    assert items[plain].target.name == "Bluey - S03E08 - Gemeinhorn.mkv"  # kept, but asked
    assert items[plain].status == "review" and "„Curry-Mission“" in items[plain].note
