"""Settings and about dialogs."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox, QVBoxLayout,
                               QWidget)

from .config import KINDS, METADATA_LANGUAGES, Config, language_name
from .i18n import N_, tr
from .plex import Plex
from .tmdb import TMDB


def _path_row(edit: QLineEdit, parent: QWidget) -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    btn = QPushButton("…")
    btn.setFixedWidth(32)
    btn.clicked.connect(lambda: (d := QFileDialog.getExistingDirectory(parent, tr("Ordner wählen"), edit.text()))
                        and edit.setText(d.replace("/", "\\")))
    lay.addWidget(edit)
    lay.addWidget(btn)
    return w


class SettingsDialog(QDialog):
    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Einstellungen"))
        self.setMinimumWidth(560)
        self.cfg = cfg
        self.tmdb_key = QLineEdit(cfg.tmdb_key)
        self.tmdb_key.setEchoMode(QLineEdit.PasswordEchoOnEdit)
        self.language = QComboBox()
        for code, name in METADATA_LANGUAGES:
            self.language.addItem(f"{tr(name)}  ({code})", code)
        if self.language.findData(cfg.language) < 0:
            self.language.addItem(cfg.language, cfg.language)
        self.language.setCurrentIndex(self.language.findData(cfg.language))
        self.plex_url = QLineEdit(cfg.plex_url)
        self.plex_token = QLineEdit(cfg.plex_token)
        self.plex_token.setEchoMode(QLineEdit.PasswordEchoOnEdit)
        self.min_mb = QSpinBox()
        self.min_mb.setRange(0, 10000)
        self.min_mb.setSuffix(" MB")
        self.min_mb.setValue(cfg.min_video_mb)

        form = QFormLayout()
        form.addRow(tr("TMDB API-Key / Token"), self.tmdb_key)
        form.addRow(tr("Standard-Sprache der Titel"), self.language)
        form.addRow(tr("Plex-URL"), self.plex_url)
        form.addRow(tr("Plex-Token"), self.plex_token)
        libs = "<br>".join(
            (tr("<b>{title}</b> ({kind}, Standard, Titel: {language}): {folder}", title=lib.title,
                kind=tr(KINDS[lib.kind]), language=language_name(lib.language or cfg.language),
                folder=lib.local_root) if lib.default
             else tr("<b>{title}</b> ({kind}, Titel: {language}): {folder}", title=lib.title,
                     kind=tr(KINDS[lib.kind]), language=language_name(lib.language or cfg.language),
                     folder=lib.local_root))
            for lib in cfg.libs) or tr("keine")
        libs_label = QLabel(libs + "<br>" + tr("<i>Ändern über „Einrichten“ im Menü.</i>"))
        libs_label.setTextFormat(Qt.RichText)
        libs_label.setWordWrap(True)
        form.addRow(tr("Bibliotheken"), libs_label)
        form.addRow(tr("Videos ignorieren unter"), self.min_mb)
        hint = QLabel(tr("TMDB-Key: themoviedb.org → Einstellungen → API. Plex-Anmeldung, Server und "
                         "Bibliotheken richtet „Einrichten“ im Menü ein; URL und Token hier nur bei Bedarf von Hand."))
        hint.setWordWrap(True)
        hint.setTextFormat(Qt.RichText)

        test = QPushButton(tr("Verbindung testen"))
        test.clicked.connect(self._test)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        bottom = QHBoxLayout()
        bottom.addWidget(test)
        bottom.addStretch()
        bottom.addWidget(buttons)

        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(hint)
        lay.addLayout(bottom)

    def _test(self) -> None:
        lines = []
        try:
            r = TMDB(self.tmdb_key.text().strip(), self.language.currentData()).search_movie("Matrix")
            lines.append(tr("TMDB: OK ({n} Treffer für „Matrix“)", n=len(r)))
        except Exception as e:
            lines.append(f"TMDB: {e}")
        if self.plex_token.text().strip():
            try:
                secs = Plex(self.plex_url.text().strip(), self.plex_token.text().strip()).sections()
                lines.append("Plex: OK – " + ", ".join(f"{s['title']} ({'; '.join(s['locations'])})" for s in secs))
            except Exception as e:
                lines.append(f"Plex: {e}")
        else:
            lines.append(tr("Plex: kein Token – Scan nach dem Übertragen wird übersprungen"))
        QMessageBox.information(self, tr("Verbindungstest"), "\n\n".join(lines))

    def _save(self) -> None:
        c = self.cfg
        c.tmdb_key = self.tmdb_key.text().strip()
        c.language = self.language.currentData() or "de-DE"
        c.plex_url = self.plex_url.text().strip()
        c.plex_token = self.plex_token.text().strip()
        c.min_video_mb = self.min_mb.value()
        c.save()
        self.accept()


ASSETS = Path(__file__).parent / "assets"

ABOUT_HTML = N_("""
<h2>ShelfSort {version}</h2>
<p>Benennt Filme und Serien so, wie Plex sie erwartet, verschiebt sie in die Bibliothek und
prüft Folgennummern gegen die in Plex eingestellte Reihenfolge.</p>
<p>Freie Software unter der MIT-Lizenz. Verwendete Bibliotheken und ihre Lizenzen:
siehe <i>THIRD_PARTY_LICENSES.md</i>.</p>
<hr>
<p><a href="https://www.themoviedb.org"><img src="{tmdb_logo}" width="110"></a><br>
This product uses TMDB and the TMDB APIs but is not endorsed, certified, or otherwise approved by TMDB.</p>
<p><b>Plex</b> – ShelfSort ist kein Produkt von Plex, Inc. und wird von Plex weder unterstützt noch
gesponsert. „Plex“ ist eine Marke von Plex, Inc.</p>
""")


def show_about(parent=None) -> None:
    from . import __version__
    box = QMessageBox(parent)
    box.setWindowTitle(tr("Über ShelfSort"))
    box.setTextFormat(Qt.RichText)
    box.setTextInteractionFlags(Qt.TextBrowserInteraction)
    # TMDB requires its logo next to the notice (smaller than our own branding)
    logo = QUrl.fromLocalFile(str(ASSETS / "tmdb.svg")).toString()
    box.setText(tr(ABOUT_HTML, version=__version__, tmdb_logo=logo))
    box.exec()
