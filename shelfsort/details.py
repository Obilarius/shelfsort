"""Side panel showing what a plan row was matched to: cover, metadata, episode still."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from .naming import episode_code
from .plan import PlanItem
from .posters import PosterLoader

POSTER = QSize(130, 195)
STILL = QSize(300, 169)
KIND = {"movie": "Film", "show": "Serie"}


def _date_de(d: str) -> str:
    return ".".join(reversed(d.split("-"))) if d else ""


class DetailsPanel(QScrollArea):
    rematch_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setMinimumWidth(360)
        self.posters = PosterLoader(self)
        self._current: PlanItem | None = None

        def label(selectable=True, wrap=True, style=""):
            lab = QLabel()
            lab.setWordWrap(wrap)
            if selectable:
                lab.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
            if style:
                lab.setStyleSheet(style)
            return lab

        self.kind = label(style="color: gray; text-transform: uppercase; letter-spacing: 1px")
        self.poster = QLabel()
        self.poster.setFixedSize(POSTER)
        self.poster.setAlignment(Qt.AlignCenter)
        self.poster.setStyleSheet("background: palette(base); border-radius: 6px; color: gray")
        self.title = label()
        f = QFont(self.title.font())
        f.setPointSizeF(f.pointSizeF() * 1.3)
        f.setBold(True)
        self.title.setFont(f)
        self.meta = label(style="color: gray")
        self.link = label()
        self.link.setOpenExternalLinks(True)
        self.overview = label()

        self.ep_header = label()
        f2 = QFont(self.ep_header.font())
        f2.setBold(True)
        self.ep_header.setFont(f2)
        self.still = QLabel()
        self.still.setFixedSize(STILL)
        self.still.setAlignment(Qt.AlignCenter)
        self.still.setStyleSheet("background: palette(base); border-radius: 6px; color: gray")
        self.ep_overview = label()

        self.source = label(style="color: gray")
        self.note = label()
        self.rematch = QPushButton("Anderen Treffer wählen…")
        self.rematch.clicked.connect(self.rematch_requested)
        self.empty = label(style="color: gray")

        head_text = QVBoxLayout()
        head_text.setContentsMargins(0, 0, 0, 0)
        for w in (self.kind, self.title, self.meta, self.link):
            head_text.addWidget(w)
        head_text.addStretch()
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.addWidget(self.poster, 0, Qt.AlignTop)
        head.addLayout(head_text, 1)

        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(12, 4, 12, 12)
        lay.addLayout(head)
        lay.addWidget(self.overview)
        lay.addSpacing(10)
        for w in (self.ep_header, self.still, self.ep_overview):
            lay.addWidget(w)
        lay.addSpacing(10)
        for w in (self.source, self.note, self.rematch, self.empty):
            lay.addWidget(w)
        lay.addStretch()
        self.setWidget(body)
        self.show_item(None)

    def show_multi(self, count: int) -> None:
        """Several rows selected: offer one match for all of them."""
        self._current = None
        for w in (self.kind, self.poster, self.title, self.meta, self.link, self.overview,
                  self.ep_header, self.still, self.ep_overview, self.source, self.note):
            w.setVisible(False)
        self.empty.setVisible(True)
        self.empty.setText(f"{count} Einträge ausgewählt.\nEin Treffer für alle – jede Datei behält ihre "
                           f"eigene Staffel- und Folgennummer.")
        self.rematch.setText(f"Treffer für {count} Einträge wählen…")
        self.rematch.setVisible(True)

    def show_item(self, it: PlanItem | None) -> None:
        self._current = it
        self.rematch.setText("Anderen Treffer wählen…")
        m = it.match if it else None
        info = it.episode_info if it else None

        for w in (self.kind, self.poster, self.title, self.meta, self.link, self.overview):
            w.setVisible(m is not None)
        for w in (self.ep_header, self.still, self.ep_overview):
            w.setVisible(info is not None)
        self.source.setVisible(it is not None)
        self.note.setVisible(bool(it and it.note))
        self.rematch.setVisible(bool(it and it.replan))
        self.empty.setVisible(it is None or m is None)

        if it is None:
            self.empty.setText("Zeile auswählen, um den Treffer zu sehen.")
            return
        self.source.setText(f"Datei: {it.source.name}")
        self.note.setText(it.note)
        if m is None:
            self.empty.setText("Kein TMDB-Treffer zugeordnet." if it.replan else
                               "Für diesen Eintrag gibt es keinen TMDB-Treffer (nur Umbenennung).")
            return

        self.kind.setText(KIND.get(m.kind, m.kind) + ("" if m.confident else "  ·  unsicher"))
        self.title.setText(m.label())
        meta = []
        if m.original_title and m.original_title != m.title:
            meta.append(f"Original: {m.original_title}")
        if m.date:
            meta.append(("Kinostart " if m.kind == "movie" else "Erstausstrahlung ") + _date_de(m.date))
        if m.vote_count:
            meta.append(f"★ {m.vote_average:.1f} ({m.vote_count} Bewertungen)")
        self.meta.setText("  ·  ".join(meta))
        self.link.setText(f'<a href="{m.url()}">Auf TMDB ansehen</a>  ·  tmdb-{m.tmdb_id}')
        self.overview.setText(m.overview or "Keine Beschreibung vorhanden.")
        self._image(self.poster, m.poster_path, "w342", POSTER, "kein Cover")

        if info is not None:
            p = it.parsed
            season = info.get("season_number", p.season if p else None)
            num = info.get("episode_number")
            code = episode_code(season, [num]) if season is not None and num is not None else ""
            date = _date_de(info.get("air_date") or "")
            src = "  ·  laut Plex" if info.get("source") == "Plex" else ""
            self.ep_header.setText(f"Folge {code} – {info.get('name') or '?'}" + (f"  ({date})" if date else "") + src)
            self.ep_overview.setText(info.get("overview") or "Keine Beschreibung vorhanden.")
            self._image(self.still, info.get("still_url") or info.get("still_path"), "w300", STILL, "kein Bild")

    def _image(self, target: QLabel, path: str | None, size: str, box: QSize, missing: str) -> None:
        target.clear()
        target.setText(missing if not path else "lädt …")
        it = self._current
        self.posters.load(path, size, lambda pix: self._current is it and
                          target.setPixmap(pix.scaled(box, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
