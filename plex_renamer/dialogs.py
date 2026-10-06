"""Settings dialog."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox, QVBoxLayout,
                               QWidget)

from .config import Config
from .plex import Plex
from .tmdb import TMDB


def _path_row(edit: QLineEdit, parent: QWidget) -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    btn = QPushButton("…")
    btn.setFixedWidth(32)
    btn.clicked.connect(lambda: (d := QFileDialog.getExistingDirectory(parent, "Ordner wählen", edit.text()))
                        and edit.setText(d.replace("/", "\\")))
    lay.addWidget(edit)
    lay.addWidget(btn)
    return w


class SettingsDialog(QDialog):
    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Einstellungen")
        self.setMinimumWidth(560)
        self.cfg = cfg
        self.tmdb_key = QLineEdit(cfg.tmdb_key)
        self.tmdb_key.setEchoMode(QLineEdit.PasswordEchoOnEdit)
        self.language = QLineEdit(cfg.language)
        self.plex_url = QLineEdit(cfg.plex_url)
        self.plex_token = QLineEdit(cfg.plex_token)
        self.plex_token.setEchoMode(QLineEdit.PasswordEchoOnEdit)
        self.movies_root = QLineEdit(cfg.movies_root)
        self.tv_root = QLineEdit(cfg.tv_root)
        self.min_mb = QSpinBox()
        self.min_mb.setRange(0, 10000)
        self.min_mb.setSuffix(" MB")
        self.min_mb.setValue(cfg.min_video_mb)

        form = QFormLayout()
        form.addRow("TMDB API-Key / Token", self.tmdb_key)
        form.addRow("Sprache", self.language)
        form.addRow("Plex-URL", self.plex_url)
        form.addRow("Plex-Token", self.plex_token)
        form.addRow("Filme-Ordner", _path_row(self.movies_root, self))
        form.addRow("Serien-Ordner", _path_row(self.tv_root, self))
        form.addRow("Videos ignorieren unter", self.min_mb)
        hint = QLabel('TMDB-Key: themoviedb.org → Einstellungen → API. '
                      'Plex-Token: in Plex Web bei einem Film „Medien-Info“ → „XML anzeigen“, '
                      'Wert von <code>X-Plex-Token</code> in der URL.')
        hint.setWordWrap(True)
        hint.setTextFormat(Qt.RichText)

        test = QPushButton("Verbindung testen")
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
            r = TMDB(self.tmdb_key.text().strip(), self.language.text().strip()).search_movie("Matrix")
            lines.append(f"TMDB: OK ({len(r)} Treffer für „Matrix“)")
        except Exception as e:
            lines.append(f"TMDB: {e}")
        if self.plex_token.text().strip():
            try:
                secs = Plex(self.plex_url.text().strip(), self.plex_token.text().strip()).sections()
                lines.append("Plex: OK – " + ", ".join(f"{s['title']} ({'; '.join(s['locations'])})" for s in secs))
            except Exception as e:
                lines.append(f"Plex: {e}")
        else:
            lines.append("Plex: kein Token – Scan nach dem Übertragen wird übersprungen")
        QMessageBox.information(self, "Verbindungstest", "\n\n".join(lines))

    def _save(self) -> None:
        c = self.cfg
        c.tmdb_key = self.tmdb_key.text().strip()
        c.language = self.language.text().strip() or "de-DE"
        c.plex_url = self.plex_url.text().strip()
        c.plex_token = self.plex_token.text().strip()
        c.movies_root = self.movies_root.text().strip()
        c.tv_root = self.tv_root.text().strip()
        c.min_video_mb = self.min_mb.value()
        c.save()
        self.accept()
