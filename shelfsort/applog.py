"""Log file next to the settings: everything from the log window plus error details."""
from __future__ import annotations

import logging
import platform
import sys
import threading
from logging.handlers import RotatingFileHandler

from .config import CONFIG_PATH

LOG_DIR = CONFIG_PATH.parent / "logs"
LOG_FILE = LOG_DIR / "shelfsort.log"

log = logging.getLogger("shelfsort")


def setup() -> None:
    """File logging with rotation (1 MB, 3 old files) and uncaught exceptions in the log."""
    if log.handlers:
        return
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(LOG_FILE, maxBytes=1024 * 1024, backupCount=3, encoding="utf-8")
    except OSError:
        return  # no log file is no reason not to start
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    log.propagate = False

    def hook(kind, value, tb):
        log.critical("Unexpected error", exc_info=(kind, value, tb))
        sys.__excepthook__(kind, value, tb)

    sys.excepthook = hook
    threading.excepthook = lambda a: hook(a.exc_type, a.exc_value, a.exc_traceback)
    from . import __version__
    log.info("ShelfSort %s started (%s, Python %s)", __version__, platform.platform(), sys.version.split()[0])


def environment(cfg) -> None:
    """Setup in the log, for bug reports. Never the TMDB key or the Plex token, only whether they are set."""
    from PySide6 import __version__ as pyside
    from PySide6.QtCore import qVersion

    from . import i18n, naming
    log.info("Qt %s / PySide6 %s, UI language %s, title language %s", qVersion(), pyside, i18n.language(), cfg.language)
    log.info("Naming: %s (%s)", naming.preset_of(naming.scheme) or "custom", naming.scheme)
    log.info("TMDB key %s, Plex %s%s", "set" if cfg.tmdb_key else "MISSING",
             f"signed in, server {cfg.plex_server_name or cfg.plex_url}" if cfg.plex_token else "not signed in",
             "" if cfg.check_updates else ", update check off")
    for lib in cfg.libs:
        log.info("Library %s (%s): %s, language %s%s%s", lib.title, lib.kind, lib.local_root, lib.language or "default",
                 ", Plex section " + lib.section_key if lib.section_key else ", no Plex section",
                 ", default" if lib.default else "")


def plan(title: str, items, seconds: float) -> None:
    """Every row of a scan result: status, kind, source -> target, note."""
    counts: dict[str, int] = {}
    for it in items:
        counts[it.status] = counts.get(it.status, 0) + 1
    log.info("%s finished in %.1f s: %d items %s", title, seconds, len(items), counts)
    for it in items:
        log.info("  %-8s %-8s %s -> %s%s%s", it.status, it.kind, it.source, it.target or "-",
                 " | " + it.note if it.note else "", " [selected]" if it.selected else "")
