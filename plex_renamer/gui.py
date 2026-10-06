"""Main window: Import tab and library audit tab."""
from __future__ import annotations

import sys
import threading
import traceback
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QAction, QBrush, QColor
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QFileDialog, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit,
                               QProgressBar, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
                               QTabWidget, QVBoxLayout, QWidget)

from .audit import AuditOptions, build_audit_plan
from .config import Config
from .details import DetailsPanel
from .dialogs import SettingsDialog
from .match_dialog import MatchDialog
from .executor import Reporter, TransferInfo, execute
from .importer import build_import_plan
from .library import Library
from .plan import PlanItem
from .plex import Plex
from .plex_sync import PlexCatalog, PlexEpisodeSource, specials_overview
from .specials_tab import SpecialsTab
from .tmdb import TMDB
from .transfer_panel import TransferPanel

STATUS = {
    "ok": ("Bereit", QColor(46, 160, 67, 70)),
    "review": ("Prüfen", QColor(210, 153, 34, 80)),
    "conflict": ("Konflikt", QColor(218, 54, 51, 80)),
    "error": ("Fehler", QColor(218, 54, 51, 110)),
    "done": ("Erledigt", QColor(110, 118, 129, 60)),
    "running": ("Läuft",QColor(56, 132, 255, 110)),
    "cancelled": ("Abgebrochen", QColor(110, 118, 129, 60)),
}
KIND = {"movie": "Film", "episode": "Folge", "show_dir": "Serienordner", "empty": "Leerer Ordner"}


# --- background work ----------------------------------------------------------------------

class Worker(QObject):
    progress = Signal(str, object, object)
    transfer = Signal(object)  # TransferInfo
    item_state = Signal(object, str)  # PlanItem, state
    log = Signal(str)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: Callable[["Worker"], object]):
        super().__init__()
        self.fn = fn

    @Slot()
    def run(self) -> None:
        try:
            self.finished.emit(self.fn(self))
        except Exception:
            self.failed.emit(traceback.format_exc(limit=3))


# --- table --------------------------------------------------------------------------------

class PlanTable(QTableWidget):
    COLS = ["", "Status", "Typ", "Aktuell", "Neu", "Hinweis"]

    def __init__(self, bases: Callable[[], list[Path]]):
        super().__init__(0, len(self.COLS))
        self.bases = bases
        self.items: list[PlanItem] = []
        self.setHorizontalHeaderLabels(self.COLS)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setWordWrap(False)
        self.verticalHeader().hide()
        self.setSortingEnabled(False)
        h = self.horizontalHeader()
        for c in (0, 1, 2):
            h.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.Interactive)
        h.setSectionResizeMode(4, QHeaderView.Interactive)
        h.setStretchLastSection(True)
        self.setColumnWidth(3, 420)
        self.setColumnWidth(4, 520)

    def _rel(self, p: Path | None) -> str:
        if p is None:
            return ""
        for b in self.bases():
            try:
                return str(p.relative_to(b))
            except ValueError:
                pass
        return str(p)

    def set_items(self, items: list[PlanItem]) -> None:
        self.items = items
        self.setRowCount(len(items))
        for r, it in enumerate(items):
            self._fill(r, it)

    def _fill(self, r: int, it: PlanItem) -> None:
        check = QTableWidgetItem()
        if it.ops and it.status != "done":
            check.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            check.setCheckState(Qt.Checked if it.selected else Qt.Unchecked)
        else:
            check.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        text, color = STATUS.get(it.status, (it.status, QColor(0, 0, 0, 0)))
        target = "(löschen)" if it.kind == "empty" else self._rel(it.target)
        cells = [check, QTableWidgetItem(text), QTableWidgetItem(KIND.get(it.kind, it.kind)),
                 QTableWidgetItem(self._rel(it.source)), QTableWidgetItem(target), QTableWidgetItem(it.note)]
        for c, cell in enumerate(cells):
            if c:
                cell.setToolTip(cell.text())
            if c == 1:
                cell.setBackground(QBrush(color))
            self.setItem(r, c, cell)

    def sync(self) -> None:
        for r, it in enumerate(self.items):
            cell = self.item(r, 0)
            if cell and cell.flags() & Qt.ItemIsUserCheckable:
                it.selected = cell.checkState() == Qt.Checked

    def set_all(self, on: bool) -> None:
        for r, it in enumerate(self.items):
            cell = self.item(r, 0)
            if cell and cell.flags() & Qt.ItemIsUserCheckable:
                # never auto-select deletions or conflicts
                allowed = it.kind != "empty" and it.status not in ("conflict", "error")
                cell.setCheckState(Qt.Checked if on and allowed else Qt.Unchecked)

    def update_item(self, it: PlanItem, state: str) -> None:
        """Live status of one row while executing."""
        r = next((i for i, x in enumerate(self.items) if x is it), None)
        if r is None:
            return
        text, color = STATUS.get(state, (state, QColor(0, 0, 0, 0)))
        cell = self.item(r, 1)
        cell.setText(text)
        cell.setBackground(QBrush(color))
        if state == "running":
            self.scrollToItem(cell, QAbstractItemView.PositionAtCenter)
        else:
            self.item(r, 5).setText(it.note)
            check = self.item(r, 0)
            if state == "done" and check.flags() & Qt.ItemIsUserCheckable:
                check.setData(Qt.CheckStateRole, None)
                check.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)

    def replace_group(self, group: str, new: list[PlanItem]) -> None:
        self.sync()
        idx = next((i for i, it in enumerate(self.items) if it.group == group), len(self.items))
        rest = [it for it in self.items if it.group != group]
        self.set_items(rest[:idx] + new + rest[idx:])


# --- main window --------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = Config.load()
        self.setWindowTitle("Plex Renamer")
        self.resize(1400, 820)
        self.tmdb: TMDB | None = None
        self._thread: QThread | None = None
        self._worker: Worker | None = None
        self.import_root: Path | None = None

        settings = QAction("Einstellungen", self)
        settings.triggered.connect(self.open_settings)
        self.menuBar().addAction(settings)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_import_tab(), "Import")
        self.tabs.addTab(self._build_audit_tab(), "Bibliothek prüfen")
        self.specials = SpecialsTab()
        self.specials.scan_requested.connect(lambda _: self.scan_specials())
        self.specials.apply_requested.connect(self.apply_specials)
        self.tabs.addTab(self.specials, "Specials")

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(5000)
        self.panel = TransferPanel()
        self.panel.cancel_requested.connect(self._cancel_run)
        self._cancel = threading.Event()
        self._run_table: PlanTable | None = None

        top = QWidget()
        top_lay = QVBoxLayout(top)
        top_lay.setContentsMargins(0, 0, 0, 0)
        top_lay.addWidget(self.panel)
        top_lay.addWidget(self.tabs, 1)
        split = QSplitter(Qt.Vertical)
        split.addWidget(top)
        split.addWidget(self.log_view)
        split.setSizes([620, 160])
        self.setCentralWidget(split)

        self.progress = QProgressBar()
        self.progress.setMaximumWidth(360)
        self.progress.hide()
        self.status_label = QLabel()
        self.statusBar().addWidget(self.status_label, 1)
        self.statusBar().addPermanentWidget(self.progress)
        self.setAcceptDrops(True)

        if not self.cfg.tmdb_key:
            QTimer.singleShot(0, self.open_settings)

    # --- tabs ---

    def _bases(self) -> list[Path]:
        bases = [Path(self.cfg.movies_root).parent]
        if self.import_root:
            bases.insert(0, self.import_root)
        return bases

    def _build_import_tab(self) -> QWidget:
        self.folder = QLineEdit(self.cfg.last_import_dir)
        self.folder.setPlaceholderText(r"z. B. H:\Downloads – oder Ordner ins Fenster ziehen")
        browse = QPushButton("Ordner wählen…")
        browse.clicked.connect(self._browse)
        self.scan_btn = QPushButton("Scannen")
        self.scan_btn.clicked.connect(self.scan_import)
        top = QHBoxLayout()
        top.addWidget(self.folder, 1)
        top.addWidget(browse)
        top.addWidget(self.scan_btn)

        self.import_table = PlanTable(self._bases)
        self.import_table.cellDoubleClicked.connect(lambda r, _: self._rematch(self.import_table, r, True))
        self.import_run = QPushButton("Übertragen")
        self.import_run.clicked.connect(lambda: self.run_plan(self.import_table))

        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addLayout(top)
        lay.addWidget(self._with_details(self.import_table, True), 1)
        lay.addLayout(self._action_row(self.import_table, self.import_run))
        return w

    def _build_audit_tab(self) -> QWidget:
        self.opt_movies = QCheckBox("Filme")
        self.opt_shows = QCheckBox("Serien")
        self.opt_empty = QCheckBox("Leere Ordner")
        self.opt_plex = QCheckBox("Plex-Abgleich (Folgennummern)")
        self.opt_plex.setToolTip("Vergleicht jede Folge mit der Reihenfolge, die in Plex für die Serie eingestellt ist\n"
                                 "(z. B. TheTVDB BBC iPlayer), und schlägt korrigierte Nummern vor. Braucht den Plex-Token.")
        self.opt_titles = QCheckBox("Episodentitel übernehmen")
        self.opt_titles.setToolTip("Aus: nur Struktur prüfen (Ordner, SxxEyy, Staffelordner), vorhandene Titel bleiben.\n"
                                   "An: Titel jeder Folge mit TMDB abgleichen (langsamer, viele Änderungen).")
        for cb in (self.opt_movies, self.opt_shows, self.opt_empty):
            cb.setChecked(True)
        self.audit_btn = QPushButton("Bibliothek prüfen")
        self.audit_btn.clicked.connect(self.scan_audit)
        top = QHBoxLayout()
        for cb in (self.opt_movies, self.opt_shows, self.opt_empty, self.opt_plex, self.opt_titles):
            top.addWidget(cb)
        top.addStretch()
        top.addWidget(self.audit_btn)

        self.audit_table = PlanTable(self._bases)
        self.audit_table.cellDoubleClicked.connect(lambda r, _: self._rematch(self.audit_table, r, False))
        self.audit_run = QPushButton("Ausgewählte ausführen")
        self.audit_run.clicked.connect(lambda: self.run_plan(self.audit_table))

        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addLayout(top)
        lay.addWidget(self._with_details(self.audit_table, False), 1)
        lay.addLayout(self._action_row(self.audit_table, self.audit_run))
        return w

    def _with_details(self, table: PlanTable, import_mode: bool) -> QSplitter:
        """Table on the left, details of the selected row (cover, metadata) on the right."""
        details = DetailsPanel()
        table.details = details
        table.currentCellChanged.connect(
            lambda row, *_: details.show_item(table.items[row] if 0 <= row < len(table.items) else None))
        details.rematch_requested.connect(lambda: self._rematch(table, table.currentRow(), import_mode))
        split = QSplitter(Qt.Horizontal)
        split.addWidget(table)
        split.addWidget(details)
        split.setStretchFactor(0, 1)
        split.setSizes([1000, 420])
        return split

    def _action_row(self, table: PlanTable, run: QPushButton) -> QHBoxLayout:
        all_btn = QPushButton("Alle auswählen")
        all_btn.clicked.connect(lambda: table.set_all(True))
        none_btn = QPushButton("Keine")
        none_btn.clicked.connect(lambda: table.set_all(False))
        hint = QLabel("Doppelklick auf eine Zeile: Treffer manuell wählen. Gelb = bitte prüfen, nicht vorausgewählt.")
        hint.setStyleSheet("color: gray")
        row = QHBoxLayout()
        row.addWidget(all_btn)
        row.addWidget(none_btn)
        row.addWidget(hint, 1)
        run.setMinimumWidth(180)
        row.addWidget(run)
        return row

    # --- helpers ---

    @Slot(str)
    def log(self, text: str) -> None:
        self.log_view.appendPlainText(text)

    def _services(self) -> tuple[TMDB, Library]:
        self.tmdb = TMDB(self.cfg.tmdb_key, self.cfg.language)
        return self.tmdb, Library(Path(self.cfg.movies_root), Path(self.cfg.tv_root))

    def _busy(self, on: bool, statusbar: bool = True) -> None:
        for b in (self.scan_btn, self.import_run, self.audit_btn, self.audit_run):
            b.setEnabled(not on)
        self.specials.set_busy(on)
        self.progress.setVisible(on and statusbar)
        if on:
            self.progress.setRange(0, 0)

    def run_task(self, fn: Callable[[Worker], object], done: Callable[[object], None],
                 statusbar: bool = True) -> None:
        if self._thread is not None:
            return
        self._busy(True, statusbar)
        thread, worker = QThread(self), Worker(fn)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        # bound methods of this (main-thread) QObject -> queued into the GUI thread
        worker.progress.connect(self._on_progress)
        worker.transfer.connect(self._on_transfer)
        worker.item_state.connect(self._on_item_state)
        worker.log.connect(self.log)
        worker.finished.connect(self._task_ok)
        worker.failed.connect(self._task_failed)
        self._done = done
        self._thread, self._worker = thread, worker
        thread.start()

    def _finish_task(self) -> None:
        self._thread.quit()
        self._thread.wait()
        self._thread = self._worker = None
        self._busy(False)
        self.status_label.setText("")

    @Slot(object)
    def _task_ok(self, result) -> None:
        self._finish_task()
        self._done(result)

    @Slot(str)
    def _task_failed(self, msg: str) -> None:
        self._finish_task()
        self.log(msg)
        QMessageBox.critical(self, "Fehler", msg.strip().splitlines()[-1])

    @Slot(str, object, object)
    def _on_progress(self, text: str, done: int, total: int) -> None:
        self.status_label.setText(text)
        if total > 0:
            # scale bytes to permille so huge files fit into int range
            self.progress.setRange(0, 1000)
            self.progress.setValue(int(done * 1000 / total))

    @Slot(object)
    def _on_transfer(self, info: TransferInfo) -> None:
        self.panel.update_transfer(info)
        self.setWindowTitle(f"{self.panel.percent()} % – Plex Renamer")

    @Slot(object, str)
    def _on_item_state(self, it: PlanItem, state: str) -> None:
        if self._run_table:
            self._run_table.update_item(it, state)
        if state != "running":
            self.panel.item_finished(state)

    def _cancel_run(self) -> None:
        self._cancel.set()
        self.log("Abbruch angefordert – laufende Datei wird verworfen …")

    # --- actions ---

    def open_settings(self) -> None:
        SettingsDialog(self.cfg, self).exec()

    def _browse(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Download-Ordner wählen", self.folder.text())
        if d:
            self.folder.setText(d.replace("/", "\\"))
            self.scan_import()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [Path(u.toLocalFile()) for u in e.mimeData().urls()]
        d = next((p if p.is_dir() else p.parent for p in paths), None)
        if d:
            self.tabs.setCurrentIndex(0)
            self.folder.setText(str(d))
            self.scan_import()

    def scan_import(self) -> None:
        root = Path(self.folder.text().strip().strip('"'))
        if not root.is_dir():
            QMessageBox.warning(self, "Import", f"Ordner nicht gefunden:\n{root}")
            return
        self.cfg.last_import_dir = str(root)
        self.cfg.save()
        self.import_root = root
        try:
            tmdb, lib = self._services()
        except Exception as e:
            QMessageBox.warning(self, "Import", str(e))
            return
        self.log(f"Scanne {root} …")
        min_bytes = self.cfg.min_video_mb * 1024 * 1024
        # episode titles of shows Plex already has follow the show's ordering in Plex
        plex_eps = (PlexEpisodeSource(PlexCatalog(Plex(self.cfg.plex_url, self.cfg.plex_token), self.cfg.language),
                                      lib.tv_root) if self.cfg.plex_token else None)

        def done(items):
            if plex_eps and plex_eps.error:
                self.log(f"Plex nicht erreichbar, Folgentitel kommen von TMDB: {plex_eps.error}")
            self._show(self.import_table, items)

        self.run_task(lambda w: build_import_plan(root, tmdb, lib, min_bytes, w.progress.emit, plex_eps), done)

    def _catalog(self) -> PlexCatalog | None:
        if not self.cfg.plex_token:
            QMessageBox.warning(self, "Plex", "Kein Plex-Token in den Einstellungen.")
            return None
        return PlexCatalog(Plex(self.cfg.plex_url, self.cfg.plex_token), self.cfg.language)

    def scan_specials(self) -> None:
        catalog = self._catalog()
        if not catalog:
            return
        tv_root = Path(self.cfg.tv_root)
        self.log("Prüfe Specials und Episoden-Reihenfolgen …")

        def done(result):
            reports, errors = result
            for e in errors:
                self.log(f"Specials-Check: {e}")
            better = sum(1 for r in reports if r.best)
            self.log(f"{len(reports)} Serien mit Specials, bei {better} bringt eine andere Reihenfolge Specials in den Ablauf.")
            self.specials.set_reports(reports)

        self.run_task(lambda w: specials_overview(catalog, tv_root, w.progress.emit), done)

    def apply_specials(self, chosen: list) -> None:
        if not chosen:
            QMessageBox.information(self, "Specials", "Keine Serie angehakt.")
            return
        lines, warn = [], False
        for rep, opt in chosen:
            line = f"• {rep.show.title}: {rep.show.label(rep.show.ordering)} → {opt.label} ({len(opt.in_flow)} Specials in den Ablauf)"
            if opt.missing:
                warn = True
                line += f"\n    ACHTUNG: {len(opt.missing)} Specials gibt es in dieser Reihenfolge nicht"
            lines.append(line)
        text = ("Die Episoden-Reihenfolge wird in Plex umgestellt und die Metadaten der Serie neu geladen:\n\n"
                + "\n".join(lines) + "\n\nDanach schlägt der Plex-Abgleich die neuen Dateinummern vor "
                "(nichts wird automatisch umbenannt). Zurückstellen geht jederzeit in Plex oder hier.\n\nFortfahren?")
        box = QMessageBox(QMessageBox.Warning if warn else QMessageBox.Question, "Reihenfolge umstellen", text,
                          QMessageBox.Yes | QMessageBox.No, self)
        if box.exec() != QMessageBox.Yes:
            return
        catalog = self._catalog()
        if not catalog:
            return
        try:
            tmdb, lib = self._services()
        except Exception as e:
            QMessageBox.warning(self, "Specials", str(e))
            return
        cfg = self.cfg

        def work(w: Worker):
            for rep, opt in chosen:
                catalog.set_ordering(rep.show, opt.value)
                w.log.emit(f"Plex: {rep.show.title} → {opt.label}")
            fresh = PlexCatalog(Plex(cfg.plex_url, cfg.plex_token), cfg.language)
            return build_audit_plan(tmdb, lib, AuditOptions(movies=False, empty=False, plex_sync=True),
                                    w.progress.emit, fresh, only_shows={rep.show.local_dir for rep, _ in chosen})

        def done(items):
            self.tabs.setCurrentIndex(1)
            self._show(self.audit_table, items)
            self.log("Neue Dateinummern stehen unter „Bibliothek prüfen“ – bitte prüfen und ausführen.")
            self.scan_specials()

        self.run_task(work, done)

    def scan_audit(self) -> None:
        try:
            tmdb, lib = self._services()
        except Exception as e:
            QMessageBox.warning(self, "Bibliothek", str(e))
            return
        opts = AuditOptions(self.opt_movies.isChecked(), self.opt_shows.isChecked(),
                            self.opt_empty.isChecked(), self.opt_titles.isChecked(), self.opt_plex.isChecked())
        catalog = None
        if opts.plex_sync and opts.shows:
            if not self.cfg.plex_token:
                QMessageBox.warning(self, "Plex-Abgleich", "Kein Plex-Token in den Einstellungen.")
                return
            catalog = PlexCatalog(Plex(self.cfg.plex_url, self.cfg.plex_token), self.cfg.language)
        self.log("Prüfe Bibliothek …")
        self.run_task(lambda w: build_audit_plan(tmdb, lib, opts, w.progress.emit, catalog),
                      lambda items: self._show(self.audit_table, items))

    def _show(self, table: PlanTable, items: list[PlanItem]) -> None:
        table.set_items(items)
        if items:
            table.selectRow(0)
        table.details.show_item(items[0] if items else None)
        counts: dict[str, int] = {}
        for it in items:
            counts[it.status] = counts.get(it.status, 0) + 1
        summary = ", ".join(f"{n}× {STATUS.get(s, (s,))[0]}" for s, n in counts.items()) or "nichts zu tun"
        self.log(f"{len(items)} Einträge: {summary}")

    def _rematch(self, table: PlanTable, row: int, import_mode: bool) -> None:
        it = table.items[row]
        if not it.replan or not self.tmdb or self._thread:
            return
        p = it.parsed
        query = it.match.title if it.match else (p.title if p else it.source.name)
        year = it.match.year if it.match else (p.year if p else None)
        dlg = MatchDialog(self.tmdb, it.dialog_kind, query, year,
                          season=p.season if p else None, episodes=p.episodes if p else None,
                          episode_fields=import_mode, kind_fixed=not import_mode,
                          context=table._rel(it.source), parent=self)
        if not dlg.exec() or not dlg.result_override:
            return
        try:
            new = it.replan(dlg.result_override)
        except Exception as e:
            QMessageBox.warning(self, "TMDB", str(e))
            return
        table.replace_group(it.group, new)
        table.selectRow(min(row, table.rowCount() - 1))
        table.details.show_item(table.items[table.currentRow()] if table.currentRow() >= 0 else None)

    def run_plan(self, table: PlanTable) -> None:
        table.sync()
        todo = [it for it in table.items if it.selected and it.ops]
        if not todo:
            QMessageBox.information(self, "Ausführen", "Nichts ausgewählt.")
            return
        deletions = [it for it in todo if it.kind == "empty"]
        moves = len(todo) - len(deletions)
        text = f"{moves} Einträge umbenennen/verschieben."
        if deletions:
            text += (f"\n\n{len(deletions)} Ordner werden ENDGÜLTIG gelöscht "
                     f"(Netzlaufwerk, kein Papierkorb):\n" +
                     "\n".join(f"  • {it.source.name}" for it in deletions[:15]) +
                     ("\n  …" if len(deletions) > 15 else ""))
        icon = QMessageBox.Warning if deletions else QMessageBox.Question
        box = QMessageBox(icon, "Ausführen", text + "\n\nFortfahren?", QMessageBox.Yes | QMessageBox.No, self)
        if box.exec() != QMessageBox.Yes:
            return

        cfg = self.cfg
        cancel = self._cancel = threading.Event()
        self._run_table = table
        self.panel.start(len(todo))

        def work(w: Worker):
            rep = Reporter(w.log.emit, w.transfer.emit, w.item_state.emit, cancel)
            changed, renamed = execute(table.items, rep, cfg.roots)
            if changed and cfg.plex_token:
                try:
                    for msg in Plex(cfg.plex_url, cfg.plex_token).refresh(changed, cfg.roots, full=renamed):
                        w.log.emit(msg)
                except Exception as e:
                    w.log.emit(f"Plex-Scan fehlgeschlagen: {e}")
            elif changed:
                w.log.emit("Kein Plex-Token – Bibliothek bitte manuell scannen.")

        def done(_):
            self._run_table = None
            table.set_items(table.items)
            self.setWindowTitle("Plex Renamer")
            self.log(self.panel.finish(cancel.is_set()))
            QApplication.alert(self)  # flash the taskbar button if the window is in the background

        self.run_task(work, done, statusbar=False)


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Plex Renamer")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
