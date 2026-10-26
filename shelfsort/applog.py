"""Log file next to the settings: everything from the log window plus error details."""
from __future__ import annotations

import logging
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
        log.critical("Unerwarteter Fehler", exc_info=(kind, value, tb))
        sys.__excepthook__(kind, value, tb)

    sys.excepthook = hook
    threading.excepthook = lambda a: hook(a.exc_type, a.exc_value, a.exc_traceback)
    from . import __version__
    log.info("ShelfSort %s gestartet (%s, Python %s)", __version__, sys.platform, sys.version.split()[0])
