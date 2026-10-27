"""Loading TMDB images asynchronously (Qt network, no extra threads) with a session-wide cache."""
from __future__ import annotations

import logging
from typing import Callable

from PySide6.QtCore import QObject, QUrl
from PySide6.QtGui import QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

IMG = "https://image.tmdb.org/t/p/{size}{path}"
_cache: dict[str, QPixmap] = {}


class PosterLoader(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.nam = QNetworkAccessManager(self)

    def load(self, path: str | None, size: str, done: Callable[[QPixmap], None]) -> None:
        """Calls done(pixmap) once loaded; immediately if cached. Nothing happens for missing images."""
        if not path:
            return
        if path.startswith("http"):
            # full URL (from Plex); TMDB originals are huge, ask for the needed size instead
            url = path.replace("/t/p/original/", f"/t/p/{size}/")
        else:
            url = IMG.format(size=size, path=path)
        if url in _cache:
            done(_cache[url])
            return
        reply = self.nam.get(QNetworkRequest(QUrl(url)))

        def finished():
            reply.deleteLater()
            if reply.error() != QNetworkReply.NoError:
                logging.getLogger("shelfsort").warning("Image %s not loaded: %s", url, reply.errorString())
                return
            pix = QPixmap()
            if pix.loadFromData(reply.readAll()):
                _cache[url] = pix
                done(pix)

        reply.finished.connect(finished)
