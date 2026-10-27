"""Manual TMDB search with posters and overview."""
from __future__ import annotations

from PySide6.QtCore import QLocale, QSize, Qt
from PySide6.QtGui import QColor, QFont, QIntValidator, QPixmap
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMessageBox, QPushButton, QScrollArea, QSpinBox,
                               QSplitter, QVBoxLayout, QWidget)

from . import i18n
from .details import _date_de
from .i18n import tr
from .matcher import norm, year_of
from .plan import Override
from .posters import PosterLoader
from .setup_widgets import fit_to_screen
from .tmdb import TMDB

THUMB = QSize(46, 69)
POSTER = QSize(220, 330)


class MatchDialog(QDialog):
    """Search TMDB by hand and pick the right movie/show (plus season/episode for imports)."""

    def __init__(self, tmdb: TMDB, kind: str, query: str, year: int | None,
                 season: int | None = None, episodes: list[int] | None = None,
                 episode_fields: bool = False, kind_fixed: bool = False, context: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("TMDB-Treffer wählen"))
        fit_to_screen(self, 1000, 640)
        self.tmdb = tmdb
        self.result_override: Override | None = None
        self.posters = PosterLoader(self)
        self._generation = 0  # ignores posters arriving for an outdated result list
        self._results: list[dict] = []

        ctx = QLabel(tr("Aktuell: <b>{context}</b>", context=context) if context else "")
        ctx.setTextFormat(Qt.RichText)
        ctx.setTextInteractionFlags(Qt.TextSelectableByMouse)
        ctx.setVisible(bool(context))

        self.kind = QComboBox()
        self.kind.addItem(tr("Film"), "movie")
        self.kind.addItem(tr("Serie"), "show")
        self.kind.setCurrentIndex(0 if kind == "movie" else 1)
        self.kind.setEnabled(not kind_fixed)
        self.query = QLineEdit(query)
        self.query.setClearButtonEnabled(True)
        self.year = QLineEdit(str(year) if year else "")
        self.year.setPlaceholderText(tr("alle Jahre"))
        self.year.setValidator(QIntValidator(1870, 2100, self))
        self.year.setClearButtonEnabled(True)
        self.year.setFixedWidth(110)
        search = QPushButton(tr("Suchen"))
        search.setDefault(True)
        search.clicked.connect(self._search)
        self.query.returnPressed.connect(self._search)
        self.year.returnPressed.connect(self._search)

        top = QHBoxLayout()
        top.addWidget(self.kind)
        top.addWidget(self.query, 1)
        top.addWidget(QLabel(tr("Jahr")))
        top.addWidget(self.year)
        top.addWidget(search)

        self.info = QLabel()
        self.info.setStyleSheet("color: gray")

        self._placeholder = QPixmap(THUMB)
        self._placeholder.fill(QColor(128, 128, 128, 40))
        self.results = QListWidget()
        self.results.setIconSize(THUMB)
        self.results.setSpacing(2)
        self.results.currentRowChanged.connect(self._show_details)
        self.results.itemDoubleClicked.connect(lambda _: self._accept())

        split = QSplitter(Qt.Horizontal)
        split.addWidget(self.results)
        split.addWidget(self._build_details())
        split.setSizes([430, 570])

        self.ep_row = QWidget()
        ep = QHBoxLayout(self.ep_row)
        ep.setContentsMargins(0, 0, 0, 0)
        self.season = QSpinBox()
        self.season.setRange(0, 999)
        self.season.setValue(season if season is not None else 1)
        self.ep_from = QSpinBox()
        self.ep_from.setRange(0, 9999)
        self.ep_from.setValue((episodes or [1])[0])
        self.ep_to = QSpinBox()
        self.ep_to.setRange(0, 9999)
        self.ep_to.setValue((episodes or [1])[-1])
        for label, w in ((tr("Staffel"), self.season), (tr("Folge"), self.ep_from), (tr("bis"), self.ep_to)):
            ep.addWidget(QLabel(label))
            ep.addWidget(w)
        ep.addStretch()
        self.episode_fields = episode_fields
        self.kind.currentIndexChanged.connect(self._toggle_ep)
        self._toggle_ep()

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(tr("Übernehmen"))
        buttons.button(QDialogButtonBox.Cancel).setText(tr("Abbrechen"))
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addWidget(ctx)
        lay.addLayout(top)
        lay.addWidget(self.info)
        lay.addWidget(split, 1)
        lay.addWidget(self.ep_row)
        lay.addWidget(buttons)
        if query:
            self._search()

    def _build_details(self) -> QWidget:
        self.poster = QLabel()
        self.poster.setFixedSize(POSTER)
        self.poster.setAlignment(Qt.AlignCenter)
        self.poster.setStyleSheet("background: palette(base); border-radius: 6px; color: gray")
        self.d_title = QLabel()
        f = QFont(self.d_title.font())
        f.setPointSizeF(f.pointSizeF() * 1.35)
        f.setBold(True)
        self.d_title.setFont(f)
        self.d_title.setWordWrap(True)
        self.d_meta = QLabel()
        self.d_meta.setStyleSheet("color: gray")
        self.d_meta.setWordWrap(True)
        self.d_overview = QLabel()
        self.d_overview.setWordWrap(True)
        self.d_overview.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.d_overview.setTextInteractionFlags(Qt.TextSelectableByMouse)

        text = QWidget()
        tl = QVBoxLayout(text)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.addWidget(self.d_title)
        tl.addWidget(self.d_meta)
        tl.addSpacing(6)
        tl.addWidget(self.d_overview, 1)
        scroll = QScrollArea()
        scroll.setWidget(text)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        w = QWidget()
        row = QHBoxLayout(w)
        row.setContentsMargins(8, 0, 0, 0)
        row.addWidget(self.poster, 0, Qt.AlignTop)
        row.addWidget(scroll, 1)
        return w

    # --- posters ---

    def _load(self, path: str | None, size: str, done) -> None:
        gen = self._generation
        self.posters.load(path, size, lambda pix: gen == self._generation and done(pix))

    # --- search ---

    def _toggle_ep(self) -> None:
        self.ep_row.setVisible(self.episode_fields and self.kind.currentData() == "show")

    def _year(self) -> int | None:
        t = self.year.text().strip()
        return int(t) if t.isdigit() else None

    def _search(self) -> None:
        q = self.query.text().strip()
        if not q:
            return
        year = self._year()
        movie = self.kind.currentData() == "movie"
        search = self.tmdb.search_movie if movie else self.tmdb.search_tv
        try:
            res = search(q, year)
            info = (tr("{count} Treffer für {year}", count=len(res), year=year) if year else
                    tr("{count} Treffer", count=len(res)))
            if not res and year:
                res = search(q)
                info = tr("Keine Treffer für {year} – zeige alle Jahre ({count} Treffer)", year=year, count=len(res))
        except Exception as e:
            QMessageBox.warning(self, "TMDB", str(e))
            return
        self.info.setText(info)
        self._generation += 1
        # exact title first, then well-known before obscure (TMDB's own order often isn't)
        q = norm(q)
        keys = ("title", "original_title") if movie else ("name", "original_name")
        res = sorted(res[:20], key=lambda r: (q not in {norm(r.get(k) or "") for k in keys},
                                              -(r.get("vote_count") or 0)))
        self._results = res
        self.results.clear()
        for r in self._results:
            title = (r.get("title") if movie else r.get("name")) or ""
            orig = (r.get("original_title") if movie else r.get("original_name")) or ""
            y = year_of(r.get("release_date") if movie else r.get("first_air_date"))
            line2 = []
            if orig and orig != title:
                line2.append(orig)
            if r.get("vote_count"):
                line2.append(f"★ {r.get('vote_average', 0):.1f} ({QLocale(i18n.language()).toString(r['vote_count'])})")
            item = QListWidgetItem(f"{title} ({y or '?'})" + ("\n" + "  ·  ".join(line2) if line2 else ""))
            item.setSizeHint(QSize(0, THUMB.height() + 8))
            item.setIcon(self._placeholder)  # keeps text aligned for results without a cover
            item.setData(Qt.UserRole, r["id"])
            self.results.addItem(item)
            self._load(r.get("poster_path"), "w92",
                       lambda pix, item=item: item.setIcon(pix.scaled(THUMB, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
        if self.results.count():
            self.results.setCurrentRow(0)
        else:
            self._show_details(-1)

    def _show_details(self, row: int) -> None:
        if row < 0 or row >= len(self._results):
            self.poster.clear()
            self.poster.setText("")
            self.d_title.setText("")
            self.d_meta.setText("")
            self.d_overview.setText("")
            return
        r = self._results[row]
        movie = self.kind.currentData() == "movie"
        title = (r.get("title") if movie else r.get("name")) or ""
        orig = (r.get("original_title") if movie else r.get("original_name")) or ""
        date = (r.get("release_date") if movie else r.get("first_air_date")) or ""
        self.d_title.setText(f"{title} ({date[:4] or '?'})")
        meta = []
        if orig and orig != title:
            meta.append(tr("Original: {title}", title=orig))
        if date:
            shown = _date_de(date)
            meta.append(tr("Kinostart {date}", date=shown) if movie else tr("Erstausstrahlung {date}", date=shown))
        if r.get("vote_count"):
            meta.append(tr("★ {rating} von {count} Bewertungen", rating=f"{r.get('vote_average', 0):.1f}",
                           count=QLocale(i18n.language()).toString(r["vote_count"])))
        meta.append(f"tmdb-{r['id']}")
        self.d_meta.setText("  ·  ".join(meta))
        self.d_overview.setText(r.get("overview") or tr("Keine Beschreibung vorhanden."))
        self.poster.clear()
        self.poster.setText(tr("kein Cover") if not r.get("poster_path") else tr("lädt …"))
        rid = r["id"]
        self._load(r.get("poster_path"), "w342",
                   lambda pix: self._results and self.results.currentRow() >= 0
                   and self._results[self.results.currentRow()]["id"] == rid
                   and self.poster.setPixmap(pix.scaled(POSTER, Qt.KeepAspectRatio, Qt.SmoothTransformation)))

    def _accept(self) -> None:
        item = self.results.currentItem()
        if not item:
            QMessageBox.information(self, "TMDB", tr("Bitte einen Treffer auswählen."))
            return
        kind = self.kind.currentData()
        ov = Override(kind, int(item.data(Qt.UserRole)))
        if kind == "show" and self.episode_fields:
            first, last = self.ep_from.value(), max(self.ep_from.value(), self.ep_to.value())
            ov.season = self.season.value()
            ov.episodes = [first] if first == last else [first, last]
        self.result_override = ov
        self.accept()
