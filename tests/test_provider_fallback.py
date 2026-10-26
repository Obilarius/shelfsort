from pathlib import Path

from shelfsort.audit import AuditOptions, build_audit_plan
from shelfsort.library import Library
from shelfsort.plex_sync import PlexShow, ProviderError


def touch(p: Path) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x")
    return p


class DownCatalog:
    """Local Plex server answers, Plex's metadata service does not."""

    def __init__(self, tv: Path):
        self.tv = tv

    def shows(self, progress=None):
        return {str(d).lower(): PlexShow(d.name, "1", "plex://show/x", "tvdbAiring", d) for d in self.tv.iterdir()}

    def load_episodes(self, show):
        raise ProviderError("Plex-Metadatendienst nicht erreichbar oder verändert (503)")


def test_audit_continues_without_plex_when_provider_is_down(tmp_path):
    movies, tv = tmp_path / "movies", tmp_path / "tvshows"
    movies.mkdir()
    for show in ("A {tmdb-1}", "B {tmdb-2}"):
        touch(tv / show / "Season 01" / f"{show.split()[0]}.S01E01.German.1080p.WEB.x264-GRP.mkv")
    class NoTitles:
        def episode_title(self, *a):
            return None

    items = build_audit_plan(NoTitles(), Library(movies, tv), AuditOptions(movies=False, empty=False, plex_sync=True),
                             catalog=DownCatalog(tv))
    errors = [i for i in items if i.status == "error"]
    assert len(errors) == 1 and "Plex-Abgleich übersprungen" in errors[0].note  # one message, not one per show
    # the structural check still ran for both shows
    renames = sorted(i.target.name for i in items if i.ops)
    assert renames == ["A - S01E01.mkv", "B - S01E01.mkv"]
