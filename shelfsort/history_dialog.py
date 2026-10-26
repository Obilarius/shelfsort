"""History of runs: what changed, undo a run, open the log file."""
from __future__ import annotations

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QMessageBox, QPlainTextEdit, QPushButton, QSplitter, QVBoxLayout)

from . import history
from .applog import LOG_FILE
from .i18n import tr


def open_log_file(parent=None) -> None:
    if not LOG_FILE.exists():
        QMessageBox.information(parent, tr("Log-Datei"), tr("Es gibt noch keine Log-Datei."))
        return
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(LOG_FILE)))


class HistoryDialog(QDialog):
    undo_requested = Signal(object)  # history.Run

    def __init__(self, parent=None, busy: bool = False):
        super().__init__(parent)
        self.setWindowTitle(tr("Verlauf"))
        self.resize(1000, 560)
        self.busy = busy
        self.runs = history.runs()

        self.list = QListWidget()
        for run in self.runs:
            n = len(run.changes)
            text = f"{run.when()}  ·  {run.title or '?'}  ·  " + tr("{n} Änderungen", n=n)
            if run.undone:
                text += "  ·  " + tr("rückgängig gemacht")
            item = QListWidgetItem(text)
            if run.undone:
                item.setForeground(QColor(128, 128, 128))
            self.list.addItem(item)
        self.list.currentRowChanged.connect(self._show)

        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setLineWrapMode(QPlainTextEdit.NoWrap)

        split = QSplitter(Qt.Vertical)
        split.addWidget(self.list)
        split.addWidget(self.details)
        split.setSizes([200, 360])

        hint = QLabel(tr("Rückgängig machen bringt Dateien und Ordner zurück an ihren alten Platz. "
                         "Was sich seitdem verändert hat, wird übersprungen, nicht überschrieben. "
                         "Gelöschte leere Ordner werden neu angelegt (ohne ihren alten Inhalt), "
                         "Release-Ordner im Papierkorb müssen dort wiederhergestellt werden."))
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray")

        self.undo_btn = QPushButton(tr("Rückgängig machen"))
        self.undo_btn.clicked.connect(self._undo)
        log_btn = QPushButton(tr("Log-Datei öffnen"))
        log_btn.clicked.connect(lambda: open_log_file(self))
        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.rejected.connect(self.reject)
        buttons = QHBoxLayout()
        buttons.addWidget(self.undo_btn)
        buttons.addWidget(log_btn)
        buttons.addStretch()
        buttons.addWidget(close)

        lay = QVBoxLayout(self)
        if not self.runs:
            lay.addWidget(QLabel(tr("Noch keine Läufe aufgezeichnet.")))
        lay.addWidget(split, 1)
        lay.addWidget(hint)
        lay.addLayout(buttons)

        if self.runs:
            self.list.setCurrentRow(0)
        else:
            self._show(-1)

    def _current(self) -> history.Run | None:
        r = self.list.currentRow()
        return self.runs[r] if 0 <= r < len(self.runs) else None

    def _show(self, row: int) -> None:
        run = self._current()
        self.undo_btn.setEnabled(bool(run and run.changes and not run.undone and not self.busy))
        if run is None:
            self.details.setPlainText("")
            return
        self.details.setPlainText("\n".join(history.describe(e) for e in run.changes))

    def _undo(self) -> None:
        run = self._current()
        if run is None:
            return
        newer = [r for r in self.runs[:self.runs.index(run)] if not r.undone and r.changes]
        text = tr("Lauf vom {when} rückgängig machen ({n} Änderungen)?", when=run.when(), n=len(run.changes))
        if newer:
            text += "\n\n" + tr("Danach gab es noch {n} weitere Läufe. Dateien, die sie verändert haben, "
                                "werden übersprungen.", n=len(newer))
        if QMessageBox.question(self, tr("Rückgängig machen"), text) != QMessageBox.Yes:
            return
        self.undo_requested.emit(run)
        self.accept()
