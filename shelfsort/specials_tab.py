"""Tab 'Specials': find episode orderings that put a show's specials into the regular seasons."""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QHBoxLayout, QHeaderView, QLabel,
                               QPlainTextEdit, QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from .plex_sync import OrderingOption, SpecialsReport

COLS = ["", "Serie", "Aktuelle Reihenfolge", "Specials", "Neue Reihenfolge", "Im Ablauf", "Bleiben Special", "Fehlen"]
GOOD = QColor(46, 160, 67, 70)
WARN = QColor(210, 153, 34, 80)


class SpecialsTab(QWidget):
    scan_requested = Signal(bool)  # only shows with an improvement
    apply_requested = Signal(list)  # [(SpecialsReport, OrderingOption)]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.reports: list[SpecialsReport] = []

        intro = QLabel("Specials in Staffel 0 überspringt Plex bei „Weiter schauen“. Manche Episoden-Reihenfolgen "
                       "(z. B. TheTVDB DVD oder BBC iPlayer) sortieren sie in die normalen Staffeln ein. Hier siehst "
                       "du pro Serie, welche Reihenfolge wie viele Specials in den Ablauf bringt.")
        intro.setWordWrap(True)
        self.only_better = QCheckBox("Nur Serien, bei denen eine Reihenfolge hilft")
        self.only_better.setChecked(True)
        self.only_better.toggled.connect(lambda _: self._fill())
        self.scan_btn = QPushButton("Serien prüfen")
        self.scan_btn.clicked.connect(lambda: self.scan_requested.emit(True))
        top = QHBoxLayout()
        top.addWidget(self.only_better)
        top.addStretch()
        top.addWidget(self.scan_btn)

        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().hide()
        h = self.table.horizontalHeader()
        for c in range(len(COLS)):
            h.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.currentCellChanged.connect(lambda row, *_: self._details(row))

        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        split = QSplitter(Qt.Vertical)
        split.addWidget(self.table)
        split.addWidget(self.details)
        split.setSizes([420, 200])

        self.apply_btn = QPushButton("Reihenfolge in Plex umstellen")
        self.apply_btn.setMinimumWidth(220)
        self.apply_btn.clicked.connect(self._apply)
        hint = QLabel("Danach prüft das Tool die umgestellten Serien mit dem Plex-Abgleich und schlägt die "
                      "neuen Dateinummern vor.")
        hint.setStyleSheet("color: gray")
        bottom = QHBoxLayout()
        bottom.addWidget(hint, 1)
        bottom.addWidget(self.apply_btn)

        lay = QVBoxLayout(self)
        lay.addWidget(intro)
        lay.addLayout(top)
        lay.addWidget(split, 1)
        lay.addLayout(bottom)

    def set_busy(self, busy: bool) -> None:
        self.scan_btn.setEnabled(not busy)
        self.apply_btn.setEnabled(not busy)

    # --- table ---

    def set_reports(self, reports: list[SpecialsReport]) -> None:
        self.reports = reports
        self._fill()

    def _visible(self) -> list[SpecialsReport]:
        return [r for r in self.reports if r.best or not self.only_better.isChecked()]

    def _fill(self) -> None:
        rows = self._visible()
        self.table.setRowCount(len(rows))
        for r, rep in enumerate(rows):
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            check.setCheckState(Qt.Unchecked)
            check.setData(Qt.UserRole, rep)
            self.table.setItem(r, 0, check)
            self.table.setItem(r, 1, QTableWidgetItem(rep.show.title))
            current = rep.show.label(rep.show.ordering) + ("" if rep.show.own_ordering else " (Standard)")
            self.table.setItem(r, 2, QTableWidgetItem(current))
            self.table.setItem(r, 3, QTableWidgetItem(str(len(rep.specials))))
            combo = QComboBox()
            combo.addItem("– unverändert –", None)
            for opt in rep.options:
                combo.addItem(f"{opt.label}  ({len(opt.in_flow)} im Ablauf)", opt)
            best = rep.best
            if best:
                combo.setCurrentIndex(rep.options.index(best) + 1)
            combo.currentIndexChanged.connect(lambda _, row=r: self._update_row(row))
            self.table.setCellWidget(r, 4, combo)
            self._update_row(r)
        if rows:
            self.table.selectRow(0)
        self._details(0 if rows else -1)

    def _option(self, row: int) -> OrderingOption | None:
        combo = self.table.cellWidget(row, 4)
        return combo.currentData() if combo else None

    def _update_row(self, row: int) -> None:
        opt = self._option(row)
        vals = [len(opt.in_flow), len(opt.still_special), len(opt.missing)] if opt else ["", "", ""]
        for c, v in zip((5, 6, 7), vals):
            cell = QTableWidgetItem(str(v))
            cell.setTextAlignment(Qt.AlignCenter)
            if c == 5 and opt and opt.in_flow:
                cell.setBackground(QBrush(GOOD))
            if c == 7 and opt and opt.missing:
                cell.setBackground(QBrush(WARN))
            self.table.setItem(row, c, cell)
        check = self.table.item(row, 0)
        if check and opt is None:
            check.setCheckState(Qt.Unchecked)
        if row == self.table.currentRow():
            self._details(row)

    def _details(self, row: int) -> None:
        if row < 0 or row >= self.table.rowCount():
            self.details.setPlainText("")
            return
        rep: SpecialsReport = self.table.item(row, 0).data(Qt.UserRole)
        opt = self._option(row)
        lines = [f"{rep.show.title} – {len(rep.specials)} Specials mit „{rep.show.label(rep.show.ordering)}“:"]
        lines += [f"   {s}" for s in rep.specials]
        if opt:
            lines.append("")
            lines.append(f"Mit „{opt.label}“:")
            if opt.in_flow:
                lines.append(f"  Im Ablauf ({len(opt.in_flow)}):")
                lines += [f"     {s}" for s in opt.in_flow]
            if opt.still_special:
                lines.append(f"  Bleiben Special ({len(opt.still_special)}):")
                lines += [f"     {s}" for s in opt.still_special]
            if opt.missing:
                lines.append(f"  ACHTUNG – gibt es in dieser Reihenfolge nicht ({len(opt.missing)}). "
                             f"Hast du Dateien dafür, kann Plex sie danach nicht mehr zuordnen:")
                lines += [f"     {s}" for s in opt.missing]
        self.details.setPlainText("\n".join(lines))

    def _apply(self) -> None:
        chosen = []
        for r in range(self.table.rowCount()):
            check = self.table.item(r, 0)
            opt = self._option(r)
            if check and check.checkState() == Qt.Checked and opt:
                chosen.append((check.data(Qt.UserRole), opt))
        self.apply_requested.emit(chosen)
