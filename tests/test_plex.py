from pathlib import Path

from plex_renamer.plex import Plex


def test_refresh_maps_local_folder_to_server_path(monkeypatch):
    calls = []

    def fake_get(self, endpoint, **params):
        calls.append((endpoint, params))
        if endpoint == "/library/sections":
            return {"MediaContainer": {"Directory": [
                {"key": "1", "title": "Filme", "type": "movie", "Location": [{"path": "/data/plex_media/movies"}]},
                {"key": "2", "title": "Serien", "type": "show", "Location": [{"path": "/data/plex_media/tvshows"}]},
            ]}}
        return {}

    monkeypatch.setattr(Plex, "_get", fake_get)
    movies, tv = Path(r"X:\plex_media\movies"), Path(r"X:\plex_media\tvshows")
    msgs = Plex("http://nexus:32400", "t").refresh({movies / "Pressure (2026) {tmdb-1318413}"}, [movies, tv])

    assert ("/library/sections/1/refresh", {"path": "/data/plex_media/movies/Pressure (2026) {tmdb-1318413}"}) in calls
    assert len(msgs) == 1
