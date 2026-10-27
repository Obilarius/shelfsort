"""Is there a newer release on GitHub? One small request at most once a day, nothing is downloaded."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass

import requests

from . import __version__

REPO = "Obilarius/shelfsort"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES = f"https://github.com/{REPO}/releases/latest"
INTERVAL = 24 * 3600


@dataclass
class Release:
    version: str  # "0.2.0"
    url: str  # release page


def parse(version: str) -> tuple[int, ...]:
    """'v0.10.1' -> (0, 10, 1); pre-releases like '0.2.0-beta' count as their base version."""
    return tuple(int(x) for x in re.findall(r"\d+", version.split("-")[0]))


def latest(session: requests.Session | None = None) -> Release:
    r = (session or requests).get(API, timeout=10, headers={"Accept": "application/vnd.github+json",
                                                            "User-Agent": f"ShelfSort/{__version__}"})
    r.raise_for_status()
    data = r.json()
    return Release(data["tag_name"].lstrip("v"), data.get("html_url") or RELEASES)


def due(cfg, now: float | None = None) -> bool:
    return cfg.check_updates and (now or time.time()) - cfg.last_update_check >= INTERVAL


def newer(release: Release, cfg, current: str = __version__) -> bool:
    """Newer than this version and not skipped by the user."""
    return parse(release.version) > parse(current) and release.version != cfg.skipped_version
