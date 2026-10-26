from pathlib import Path

from shelfsort.path_mapping import relative, suggest, verify
from shelfsort.plex import LibraryMap, Plex

SECTIONS = {"MediaContainer": {"Directory": [
    {"key": "1", "title": "Filme", "type": "movie", "Location": [{"path": "/data/movies"}]},
    {"key": "2", "title": "Serien", "type": "show", "Location": [{"path": "/data/tvshows"}]},
]}}


def _fake(calls):
    def fake_get(self, endpoint, **params):
        calls.append((endpoint, params))
        return SECTIONS if endpoint == "/library/sections" else {}
    return fake_get


def test_refresh_with_configured_mapping(monkeypatch):
    calls = []
    monkeypatch.setattr(Plex, "_get", _fake(calls))
    movies = Path(r"X:\plex_media\movies")
    msgs = Plex("http://nexus:32400", "t").refresh({movies / "A Movie (2026) {tmdb-1}"},
                                                   [LibraryMap(movies, "1", "/data/movies")])
    assert ("/library/sections/1/refresh", {"path": "/data/movies/A Movie (2026) {tmdb-1}"}) in calls
    assert len(msgs) == 1


def test_refresh_falls_back_to_folder_name(monkeypatch):
    calls = []
    monkeypatch.setattr(Plex, "_get", _fake(calls))
    tv = Path(r"X:\media\tvshows")
    Plex("http://nexus:32400", "t").refresh({tv / "Show {tmdb-2}" / "Season 01"}, [LibraryMap(tv)])
    assert ("/library/sections/2/refresh", {"path": "/data/tvshows/Show {tmdb-2}"}) in calls


def test_path_mapping(tmp_path):
    local = tmp_path / "plex_media" / "movies"
    (local / "A (2020)").mkdir(parents=True)
    (local / "A (2020)" / "A (2020).mkv").write_bytes(b"x")
    samples = ["/data/movies/A (2020)/A (2020).mkv"]
    assert relative(samples[0], "/data/movies") == ["A (2020)", "A (2020).mkv"]
    assert relative("/other/x.mkv", "/data/movies") is None
    assert verify(local, "/data/movies", samples).ok
    assert not verify(tmp_path, "/data/movies", samples).ok
    # Windows server paths work the same way
    assert verify(local, r"D:\Media\movies", [r"D:\Media\movies\A (2020)\A (2020).mkv"]).ok
    assert suggest("/nonexistent/xyz-nowhere", samples) is None
