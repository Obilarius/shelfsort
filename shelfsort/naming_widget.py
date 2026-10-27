"""Settings tab for the naming scheme: presets for Plex, Jellyfin and Kodi, or each part by hand."""
from __future__ import annotations

from html import escape

from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QLabel, QVBoxLayout, QWidget

from . import naming
from .i18n import N_, tr
from .naming import Scheme
from .setup_widgets import GRAY, label

PRESET_LABELS = [("plex", "Plex"), ("jellyfin", "Jellyfin"), ("kodi", "Kodi"), ("", N_("Eigenes"))]
ID_LABELS = [("plex", N_("{tmdb-…}  (Plex)")), ("jellyfin", N_("[tmdbid-…]  (Jellyfin)")),
             ("none", N_("keine ID  (Kodi)"))]


class NamingWidget(QWidget):
    def __init__(self, current: Scheme, parent=None):
        super().__init__(parent)
        self.preset = QComboBox()
        for key, text in PRESET_LABELS:
            self.preset.addItem(tr(text) if key == "" else text, key)
        self.ids = QComboBox()
        for key, text in ID_LABELS:
            self.ids.addItem(tr(text), key)
        self.show_year = QCheckBox(tr("Jahr im Serienordner"))
        self.season = QComboBox()
        for word in naming.SEASON_WORDS:
            self.season.addItem(f"{word} 01", word)
        self.titles = QCheckBox(tr("Folgentitel im Dateinamen"))
        self.nfo = QCheckBox(tr("TMDB-Link als .nfo-Datei (für Kodi)"))

        form = QFormLayout()
        form.addRow(tr("Vorlage"), self.preset)
        form.addRow(tr("ID im Ordnernamen"), self.ids)
        form.addRow("", self.show_year)
        form.addRow(tr("Staffelordner"), self.season)
        form.addRow("", self.titles)
        form.addRow("", self.nfo)

        self.example = QLabel()
        self.example.setStyleSheet("font-family: Consolas, monospace; padding: 8px; background: palette(base);")
        self.example.setWordWrap(True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(form)
        lay.addWidget(QLabel(tr("So sehen neue Namen aus:")))
        lay.addWidget(self.example)
        lay.addWidget(label(tr("Vorhandene Ordner werden in jedem Format erkannt – auch ohne ID. Nach einem Wechsel "
                               "schlägt <i>Bibliothek prüfen</i> vor, die vorhandenen Ordner umzubenennen; "
                               "es passiert nichts ungefragt."), GRAY))

        self._set(current)
        self.preset.currentIndexChanged.connect(self._preset_chosen)
        for w in (self.ids, self.season):
            w.currentIndexChanged.connect(self._changed)
        for w in (self.show_year, self.titles, self.nfo):
            w.toggled.connect(self._changed)

    def scheme(self) -> Scheme:
        return Scheme(ids=self.ids.currentData(), show_year=self.show_year.isChecked(),
                      season=self.season.currentData(), episode_titles=self.titles.isChecked(),
                      nfo=self.nfo.isChecked())

    def _set(self, s: Scheme) -> None:
        for w in (self.ids, self.season, self.show_year, self.titles, self.nfo, self.preset):
            w.blockSignals(True)
        self.ids.setCurrentIndex(self.ids.findData(s.ids))
        self.season.setCurrentIndex(self.season.findData(s.season))
        self.show_year.setChecked(s.show_year)
        self.titles.setChecked(s.episode_titles)
        self.nfo.setChecked(s.nfo)
        self.preset.setCurrentIndex(self.preset.findData(naming.preset_of(s)))
        for w in (self.ids, self.season, self.show_year, self.titles, self.nfo, self.preset):
            w.blockSignals(False)
        self._show_example()

    def _preset_chosen(self) -> None:
        key = self.preset.currentData()
        if key:
            self._set(naming.PRESETS[key])

    def _changed(self) -> None:
        self._set(self.scheme())  # the preset follows: a hand-made combination shows "Custom"

    def _show_example(self) -> None:
        self.example.setText("<br>".join(escape(p) for p in naming.example(self.scheme())))
