from shelfsort import update
from shelfsort.config import Config


class FakeSession:
    def __init__(self, data):
        self.data = data
        self.urls = []

    def get(self, url, **kw):
        self.urls.append(url)
        data = self.data

        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return data
        return R()


def test_version_order():
    assert update.parse("v0.10.1") == (0, 10, 1)
    assert update.parse("0.2.0-beta") == (0, 2, 0)
    assert update.parse("0.10.0") > update.parse("0.9.9")


def test_latest_and_newer():
    s = FakeSession({"tag_name": "v0.2.0", "html_url": "https://github.com/x/y/releases/tag/v0.2.0"})
    rel = update.latest(s)
    assert s.urls == [update.API]
    assert rel.version == "0.2.0" and rel.url.endswith("v0.2.0")
    cfg = Config()
    assert update.newer(rel, cfg, current="0.1.0")
    assert not update.newer(rel, cfg, current="0.2.0")
    assert not update.newer(rel, cfg, current="0.10.0")
    cfg.skipped_version = "0.2.0"
    assert not update.newer(rel, cfg, current="0.1.0")


def test_due_once_a_day():
    cfg = Config()
    assert update.due(cfg, now=1_000_000)
    cfg.last_update_check = 1_000_000
    assert not update.due(cfg, now=1_000_000 + 3600)
    assert update.due(cfg, now=1_000_000 + update.INTERVAL)
    cfg.check_updates = False
    assert not update.due(cfg, now=9_999_999)
