"""Cancel during a scan: what was found so far stays, the rest is not fetched."""
import time

import pytest

from shelfsort import audit, importer
from shelfsort.audit import AuditOptions, build_audit_plan
from shelfsort.importer import build_import_plan
from shelfsort.library import Library
from shelfsort.plan import PlanItem, ScanCancelled
from shelfsort.plex import LibraryMap
from shelfsort.plex_sync import PlexCatalog


def _stop_after(n):
    def progress(text, i, total):
        if i >= n:
            raise ScanCancelled()
    return progress


def test_import_keeps_what_was_recognised(tmp_path, monkeypatch):
    for i in range(5):
        (tmp_path / f"Film.{i}.2020.mkv").write_bytes(b"x")
    monkeypatch.setattr(importer, "plan_import",
                        lambda v, *a, **k: PlanItem("movie", v, v.name, target=v, status="review"))
    items = build_import_plan(tmp_path, None, None, 0, _stop_after(2))
    assert len(items) == 2


def test_library_check_keeps_checked_folders(tmp_path, monkeypatch):
    movies, shows = tmp_path / "movies", tmp_path / "tv"
    for i in range(4):
        (movies / f"Film {i}").mkdir(parents=True)
    shows.mkdir()
    monkeypatch.setattr(audit, "audit_movie_dir",
                        lambda d, *a, **k: [PlanItem("movie", d, d.name, status="review")])
    lib = Library(movies, shows, [movies], [shows], {}, {})
    items = build_audit_plan(None, lib, AuditOptions(shows=False), _stop_after(3))
    assert len(items) == 3


def test_plex_show_list_stops_fetching(tmp_path):
    calls = []

    class FakePlex:
        token = "t"

        def _get(self, endpoint, **params):
            if endpoint.endswith("/all"):
                return {"MediaContainer": {"Metadata": [
                    {"ratingKey": str(i), "title": f"Show {i}", "guid": f"plex://show/{i}"} for i in range(200)]}}
            calls.append(endpoint)
            time.sleep(0.01)
            return {"MediaContainer": {"Metadata": [{"Location": []}]}}

    catalog = PlexCatalog(FakePlex(), "de-DE", [LibraryMap(tmp_path, "2", "/data/tv")])
    catalog._section = lambda lib: {"key": "2"}
    catalog.library_ordering = lambda lib: "aired"
    with pytest.raises(ScanCancelled):
        catalog.shows(_stop_after(3))
    time.sleep(0.2)  # threads that were already running may finish
    assert len(calls) < 50  # not all 200 shows were fetched before stopping
