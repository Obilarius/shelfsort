"""Main window: Import tab and library audit tab."""
from __future__ import annotations

import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QLibraryInfo, QObject, Qt, QThread, QTimer, QTranslator, QUrl, Signal, Slot
from PySide6.QtGui import QAction, QBrush, QColor, QDesktopServices, QIcon
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QFileDialog, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QPlainTextEdit,
                               QProgressBar, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
                               QTabWidget, QVBoxLayout, QWidget)

from . import history
from .applog import log as file_log, setup as setup_log
from .audit import AuditOptions, build_audit_plan
from .config import KINDS, Config
from .details import DetailsPanel
from .dialogs import SettingsDialog, show_about
from .match_dialog import MatchDialog
from .executor import Blocked, Reporter, TransferInfo, execute, move_file
from .history_dialog import HistoryDialog
from . import i18n
from .i18n import N_, tr
from .importer import build_import_plan
from .library import Library
from .plan import Override, PlanItem, ScanCancelled
from .plex import Plex
from .plex_sync import PlexCatalog, PlexEpisodeSource, catalog_for, specials_overview
from .reveal import main_video, play as play_video, show_in_folder
from .specials_tab import SpecialsTab
from .tmdb import TMDB
from .transfer_panel import TransferPanel
from . import naming, update
from .setup_widgets import run_async
from .wizard import SetupWizard

STATUS = {
    "ok": (N_("Bereit"), QColor(46, 160, 67, 70)),
    "review": (N_("Prüfen"), QColor(210, 153, 34, 80)),
    "conflict": (N_("Konflikt"), QColor(218, 54, 51, 80)),
    "error": (N_("Fehler"), QColor(218, 54, 51, 110)),
    "done": (N_("Erledigt"), QColor(110, 118, 129, 60)),
    "running": (N_("Läuft"),QColor(56, 132, 255, 110)),
    "cancelled": (N_("Abgebrochen"), QColor(110, 118, 129, 60)),
}
KIND = {"movie": N_("Film"), "episode": N_("Folge"), "show_dir": N_("Serienordner"), "empty": N_("Leerer Ordner")}


# --- background work ----------------------------------------------------------------------

class Worker(QObject):
    progress = Signal(str, object, object)
    transfer = Signal(object)  # TransferInfo
    item_state = Signal(object, str)  # PlanItem, state
    log = Signal(str)
    finished = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, fn: Callable[["Worker"], object]):
        super().__init__()
        self.fn = fn
        self.cancel = threading.Event()

    def report(self, text: str, done, total) -> None:
        """Progress callback for scans; stops the scan here once the user clicked Cancel."""
        if self.cancel.is_set():
            raise ScanCancelled()
        self.progress.emit(text, done, total)

    @Slot()
    def run(self) -> None:
        try:
            self.finished.emit(self.fn(self))
        except ScanCancelled:
            self.cancelled.emit()
        except Exception:
            file_log.exception("Fehler im Hintergrund")
            self.failed.emit(traceback.format_exc(limit=3))


# --- table --------------------------------------------------------------------------------

class PlanTable(QTableWidget):
    COLS = ["", N_("Status"), N_("Typ"), N_("Aktuell"), N_("Neu"), N_("Hinweis")]

    def __init__(self, bases: Callable[[], list[Path]]):
        super().__init__(0, len(self.COLS))
        self.bases = bases
        self.items: list[PlanItem] = []
        self.setHorizontalHeaderLabels([tr(c) if c else c for c in self.COLS])
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
        target = tr("(löschen)") if it.kind == "empty" else self._rel(it.target)
        cells = [check, QTableWidgetItem(tr(text)), QTableWidgetItem(tr(KIND.get(it.kind, it.kind))),
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

    def selected_rows(self) -> list[int]:
        return sorted({i.row() for i in self.selectionModel().selectedRows()})

    def update_item(self, it: PlanItem, state: str) -> None:
        """Live status of one row while executing."""
        r = next((i for i, x in enumerate(self.items) if x is it), None)
        if r is None:
            return
        text, color = STATUS.get(state, (state, QColor(0, 0, 0, 0)))
        cell = self.item(r, 1)
        cell.setText(tr(text))
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
    def __init__(self, first_start_wizard: bool = True):
        super().__init__()
        self.cfg = Config.load()
        naming.set_scheme(naming.scheme_from_config(self.cfg))
        self.setWindowTitle("ShelfSort")
        self.resize(1400, 820)
        self.tmdb: TMDB | None = None
        self._thread: QThread | None = None
        self._worker: Worker | None = None
        self._last_cancelled = False  # the last task was stopped by the user (partial result)
        self.import_root: Path | None = None

        # the setup wizard opens on first start and from the settings ("Einrichtungsassistent starten")
        settings = QAction(tr("Einstellungen"), self)
        settings.triggered.connect(self.open_settings)
        self.menuBar().addAction(settings)
        hist = QAction(tr("Verlauf"), self)
        hist.triggered.connect(self.open_history)
        self.menuBar().addAction(hist)
        about = QAction(tr("Über"), self)
        about.triggered.connect(lambda: show_about(self))
        self.menuBar().addAction(about)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_import_tab(), tr("Import"))
        self.tabs.addTab(self._build_audit_tab(), tr("Bibliothek prüfen"))
        self.specials = SpecialsTab()
        self.specials.scan_requested.connect(lambda _: self.scan_specials())
        self.specials.apply_requested.connect(self.apply_specials)
        self.tabs.addTab(self.specials, tr("Specials"))

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
        self.scan_cancel = QPushButton(tr("Abbrechen"))
        self.scan_cancel.clicked.connect(self._cancel_scan)
        self.scan_cancel.hide()
        self.statusBar().addPermanentWidget(self.scan_cancel)
        self.update_label = QLabel()
        self.update_label.setTextFormat(Qt.RichText)
        self.update_label.linkActivated.connect(self._update_link)
        self.update_label.hide()
        self.statusBar().addPermanentWidget(self.update_label)
        self.setAcceptDrops(True)

        if first_start_wizard and not self.cfg.is_set_up:
            QTimer.singleShot(0, self.open_wizard)  # first start
        QTimer.singleShot(3000, self.check_for_update)

    # --- tabs ---

    def _bases(self) -> list[Path]:
        # show paths relative to the folder above the libraries ("movies\\…", "Disney\\…")
        bases = list(dict.fromkeys(lib.path.parent for lib in self.cfg.libs))
        if self.import_root:
            bases.insert(0, self.import_root)
        return bases

    def _build_import_tab(self) -> QWidget:
        self.folder = QLineEdit(self.cfg.last_import_dir)
        self.folder.setPlaceholderText(tr(r"z. B. H:\Downloads – oder Ordner ins Fenster ziehen"))
        browse = QPushButton(tr("Ordner wählen…"))
        browse.clicked.connect(self._browse)
        self.scan_btn = QPushButton(tr("Scannen"))
        self.scan_btn.clicked.connect(self.scan_import)
        top = QHBoxLayout()
        top.addWidget(self.folder, 1)
        top.addWidget(browse)
        top.addWidget(self.scan_btn)

        self.import_table = PlanTable(self._bases)
        self.import_table.cellDoubleClicked.connect(lambda r, _: self._rematch(self.import_table, r, True))
        self.import_run = QPushButton(tr("Übertragen"))
        self.import_run.clicked.connect(lambda: self.run_plan(self.import_table))

        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addLayout(top)
        lay.addWidget(self._with_details(self.import_table, True), 1)
        lay.addLayout(self._action_row(self.import_table, self.import_run))
        return w

    def _fill_library_checks(self) -> None:
        """One checkbox per managed library (rebuilt after the setup wizard)."""
        while self.lib_checks_box.count():
            w = self.lib_checks_box.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.lib_checks: list[tuple[QCheckBox, object]] = []
        label = QLabel(tr("Bibliotheken:"))
        label.setStyleSheet("color: gray")
        self.lib_checks_box.addWidget(label)
        for lib in self.cfg.libs:
            name = tr(lib.title) if lib.title == KINDS[lib.kind] else f"{lib.title} ({tr(KINDS[lib.kind])})"
            cb = QCheckBox(name)
            cb.setToolTip(str(lib.path))
            cb.setChecked(True)
            cb.toggled.connect(lambda _: self._update_audit_options())
            self.lib_checks_box.addWidget(cb)
            self.lib_checks.append((cb, lib))
        self.lib_checks_box.addStretch()
        self._update_audit_options()

    def _checked_libs(self) -> list:
        return [lib for cb, lib in self.lib_checks if cb.isChecked()]

    def _update_audit_options(self) -> None:
        # the Plex sync is about episodes - only useful with a TV library selected
        has_shows = any(lib.kind == "show" for lib in self._checked_libs())
        self.opt_plex.setEnabled(has_shows)
        self.opt_titles.setEnabled(has_shows)
        self.audit_btn.setEnabled(bool(self._checked_libs()) and self._thread is None)

    def _build_audit_tab(self) -> QWidget:
        self.lib_checks_box = QHBoxLayout()
        self.lib_checks: list = []
        self.opt_empty = QCheckBox(tr("Leere Ordner"))
        self.opt_plex = QCheckBox(tr("Plex-Abgleich (Folgennummern)"))
        self.opt_plex.setToolTip(tr("Vergleicht jede Folge mit der Reihenfolge, die in Plex für die Serie eingestellt ist\n"
                                    "(z. B. TheTVDB BBC iPlayer), und schlägt korrigierte Nummern vor. Braucht den Plex-Token."))
        self.opt_titles = QCheckBox(tr("Episodentitel übernehmen"))
        self.opt_titles.setToolTip(tr("Aus: nur Struktur prüfen (Ordner, SxxEyy, Staffelordner), vorhandene Titel bleiben.\n"
                                      "An: Titel jeder Folge mit TMDB abgleichen (langsamer, viele Änderungen)."))
        self.opt_empty.setChecked(True)
        self.audit_btn = QPushButton(tr("Bibliothek prüfen"))
        self.audit_btn.clicked.connect(self.scan_audit)
        options = QHBoxLayout()
        options_label = QLabel(tr("Prüfen:"))
        options_label.setStyleSheet("color: gray")
        options.addWidget(options_label)
        for cb in (self.opt_empty, self.opt_plex, self.opt_titles):
            options.addWidget(cb)
        options.addStretch()
        options.addWidget(self.audit_btn)
        top = QVBoxLayout()
        top.addLayout(self.lib_checks_box)
        top.addLayout(options)
        self._fill_library_checks()

        self.audit_table = PlanTable(self._bases)
        self.audit_table.cellDoubleClicked.connect(lambda r, _: self._rematch(self.audit_table, r, False))
        self.audit_run = QPushButton(tr("Ausgewählte ausführen"))
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
        def selection_changed():
            rows = table.selected_rows()
            if len(rows) > 1:
                details.show_multi(len(rows))
            else:
                row = table.currentRow()
                details.show_item(table.items[row] if 0 <= row < len(table.items) else None)

        table.itemSelectionChanged.connect(selection_changed)
        details.rematch_requested.connect(lambda: self._rematch(table, table.currentRow(), import_mode))
        details.show_requested.connect(lambda: self._show_file(table, table.currentRow()))
        details.play_requested.connect(lambda: self._play_file(table, table.currentRow()))

        # right-click: same action, works with a multi-row selection
        table.setContextMenuPolicy(Qt.CustomContextMenu)

        def context_menu(pos):
            row = table.rowAt(pos.y())
            if row < 0:
                return
            rows = table.selected_rows() if row in table.selected_rows() else [row]
            n = len(rows)
            menu = QMenu(table)
            act = menu.addAction(tr("Treffer für {n} Einträge wählen…", n=n) if n > 1 else tr("Anderen Treffer wählen…"))
            targets = {}
            if import_mode:
                # move the selection into another library of the same kind (movies/shows)
                items = [table.items[r] for r in rows if table.items[r].retarget]
                kinds = {"movie" if it.kind == "movie" else "show" for it in items}
                if len(kinds) == 1 and len(libs := self.cfg.libs_of(kinds.pop())) > 1:
                    sub = menu.addMenu(tr("Ziel-Bibliothek"))
                    for lib in libs:
                        a = sub.addAction(lib.title + ("  " + tr("(Standard)") if lib.default else ""))
                        a.setCheckable(True)
                        a.setChecked(all(it.library == lib.title for it in items))
                        targets[a] = lib
            # look at the file itself (e.g. "2 videos in the folder" or unsure which movie it is)
            menu.addSeparator()
            show = menu.addAction(tr("Im Ordner zeigen"))
            play = menu.addAction(tr("Video abspielen"))
            play.setEnabled(main_video(table.items[row].source) is not None)
            chosen = menu.exec(table.viewport().mapToGlobal(pos))
            if chosen == act:
                self._rematch(table, row, import_mode)
            elif chosen in targets:
                self._retarget(table, rows, targets[chosen])
            elif chosen == show:
                self._show_file(table, row)
            elif chosen == play:
                self._play_file(table, row)

        table.customContextMenuRequested.connect(context_menu)
        split = QSplitter(Qt.Horizontal)
        split.addWidget(table)
        split.addWidget(details)
        split.setStretchFactor(0, 1)
        split.setSizes([1000, 420])
        return split

    def _action_row(self, table: PlanTable, run: QPushButton) -> QHBoxLayout:
        all_btn = QPushButton(tr("Alle auswählen"))
        all_btn.clicked.connect(lambda: table.set_all(True))
        none_btn = QPushButton(tr("Keine"))
        none_btn.clicked.connect(lambda: table.set_all(False))
        hint = QLabel(tr("Doppelklick oder Rechtsklick: Treffer manuell wählen – mit Shift/Strg auch für mehrere Zeilen. "
                         "Gelb = bitte prüfen, nicht vorausgewählt."))
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
        file_log.info(text)

    def _services(self) -> tuple[TMDB, Library]:
        lib = Library.from_config(self.cfg)
        self.tmdb = TMDB(self.cfg.tmdb_key, self.cfg.language)
        return self.tmdb, lib

    def _busy(self, on: bool, statusbar: bool = True, cancellable: bool = False) -> None:
        for b in (self.scan_btn, self.import_run, self.audit_btn, self.audit_run):
            b.setEnabled(not on)
        self.specials.set_busy(on)
        self.progress.setVisible(on and statusbar)
        self.scan_cancel.setVisible(on and cancellable)
        self.scan_cancel.setEnabled(True)
        if on:
            self.progress.setRange(0, 0)

    def run_task(self, fn: Callable[[Worker], object], done: Callable[[object], None],
                 statusbar: bool = True, cancellable: bool = False) -> None:
        """cancellable: a scan that stops at its next progress report (fn must use w.report)."""
        if self._thread is not None:
            return
        self._busy(True, statusbar, cancellable)
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
        worker.cancelled.connect(self._task_cancelled)
        self._done = done
        self._thread, self._worker = thread, worker
        thread.start()

    def _finish_task(self) -> None:
        self._last_cancelled = self._worker.cancel.is_set()
        self._thread.quit()
        self._thread.wait()
        self._thread = self._worker = None
        self._busy(False)
        self.status_label.setText("")

    @Slot(object)
    def _task_ok(self, result) -> None:
        self._finish_task()
        self._done(result)

    @Slot()
    def _task_cancelled(self) -> None:
        self._finish_task()
        self.log(tr("Abgebrochen."))

    def _cancel_scan(self) -> None:
        if self._worker is not None:
            self._worker.cancel.set()
            self.scan_cancel.setEnabled(False)
            self.status_label.setText(tr("Wird abgebrochen …"))

    @Slot(str)
    def _task_failed(self, msg: str) -> None:
        self._finish_task()
        self.log(msg)
        QMessageBox.critical(self, tr("Fehler"), msg.strip().splitlines()[-1])

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
        self.setWindowTitle(tr("{percent} % – ShelfSort", percent=self.panel.percent()))

    @Slot(object, str)
    def _on_item_state(self, it: PlanItem, state: str) -> None:
        if self._run_table:
            self._run_table.update_item(it, state)
        if state != "running":
            self.panel.item_finished(state)

    def _cancel_run(self) -> None:
        self._cancel.set()
        self.log(tr("Abbruch angefordert – laufende Datei wird verworfen …"))

    # --- actions ---

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.cfg, self)
        saved = dialog.exec()
        if dialog.start_wizard:
            self.open_wizard()
        elif saved and dialog.language_changed:
            self._switch_language(self.cfg.app_language).log(tr("Einstellungen gespeichert."))
        elif saved:
            self._fill_library_checks()
            self.log(tr("Einstellungen gespeichert."))

    def open_wizard(self, start_meta: str | None = None) -> None:
        wizard = SetupWizard(self.cfg, self, start_meta)
        result = wizard.exec()
        if result == SetupWizard.LANGUAGE_CHANGED:
            # app language changed on page 1: switch now and reopen the wizard in the new language
            lang, meta = wizard.language_switch
            self.cfg.app_language = lang
            self.cfg.save()
            new = self._switch_language(lang)
            QTimer.singleShot(0, lambda: new.open_wizard(meta))
            return
        if not result:
            return
        self._fill_library_checks()
        self.log(tr("Einrichtung gespeichert."))

    def _switch_language(self, lang: str) -> "MainWindow":
        """Rebuild the main window in another UI language (no restart needed)."""
        apply_language(lang)
        new = MainWindow(first_start_wizard=False)
        new.setGeometry(self.geometry())
        new.show()
        QApplication.instance().main_window = new
        self.close()
        self.deleteLater()
        return new

    def _browse(self) -> None:
        d = QFileDialog.getExistingDirectory(self, tr("Download-Ordner wählen"), self.folder.text())
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
            QMessageBox.warning(self, tr("Import"), tr("Ordner nicht gefunden:\n{path}", path=root))
            return
        self.cfg.last_import_dir = str(root)
        self.cfg.save()
        self.import_root = root
        try:
            tmdb, lib = self._services()
        except Exception as e:
            QMessageBox.warning(self, tr("Import"), str(e))
            return
        self.log(tr("Scanne {path} …", path=root))
        min_bytes = self.cfg.min_video_mb * 1024 * 1024
        # episode titles of shows Plex already has follow the show's ordering in Plex
        plex_eps = PlexEpisodeSource(catalog_for(self.cfg)) if self.cfg.plex_token else None

        def done(items):
            if plex_eps and plex_eps.error:
                self.log(tr("Plex nicht erreichbar, Folgentitel kommen von TMDB: {error}", error=plex_eps.error))
            self._show(self.import_table, items)

        self.run_task(lambda w: build_import_plan(root, tmdb, lib, min_bytes, w.report, plex_eps), done, cancellable=True)

    def _catalog(self) -> PlexCatalog | None:
        if not self.cfg.plex_token:
            QMessageBox.warning(self, "Plex", tr("Kein Plex-Token in den Einstellungen."))
            return None
        return catalog_for(self.cfg)

    def scan_specials(self) -> None:
        catalog = self._catalog()
        if not catalog:
            return
        self.log(tr("Prüfe Specials und Episoden-Reihenfolgen …"))

        def done(result):
            reports, errors = result
            for e in errors:
                self.log(tr("Specials-Check: {error}", error=e))
            better = sum(1 for r in reports if r.best)
            self.log(tr("{n} Serien mit Specials, bei {better} bringt eine andere Reihenfolge Specials in den Ablauf.",
                        n=len(reports), better=better))
            self.specials.set_reports(reports)

        self.run_task(lambda w: specials_overview(catalog, w.report), done, cancellable=True)

    def apply_specials(self, chosen: list) -> None:
        if not chosen:
            QMessageBox.information(self, tr("Specials"), tr("Keine Serie angehakt."))
            return
        lines, warn = [], False
        for rep, opt in chosen:
            line = tr("• {show}: {old} → {new} ({n} Specials in den Ablauf)", show=rep.show.title,
                      old=rep.show.label(rep.show.ordering), new=opt.label, n=len(opt.in_flow))
            if opt.missing:
                warn = True
                line += "\n    " + tr("ACHTUNG: {n} Specials gibt es in dieser Reihenfolge nicht", n=len(opt.missing))
            lines.append(line)
        text = tr("Die Episoden-Reihenfolge wird in Plex umgestellt und die Metadaten der Serie neu geladen:\n\n"
                  "{lines}\n\nDanach schlägt der Plex-Abgleich die neuen Dateinummern vor "
                  "(nichts wird automatisch umbenannt). Zurückstellen geht jederzeit in Plex oder hier.\n\nFortfahren?",
                  lines="\n".join(lines))
        box = QMessageBox(QMessageBox.Warning if warn else QMessageBox.Question, tr("Reihenfolge umstellen"), text,
                          QMessageBox.Yes | QMessageBox.No, self)
        if box.exec() != QMessageBox.Yes:
            return
        catalog = self._catalog()
        if not catalog:
            return
        try:
            tmdb, lib = self._services()
        except Exception as e:
            QMessageBox.warning(self, tr("Specials"), str(e))
            return
        cfg = self.cfg

        def work(w: Worker):
            for rep, opt in chosen:
                catalog.set_ordering(rep.show, opt.value)
                w.log.emit(f"Plex: {rep.show.title} → {opt.label}")
            fresh = catalog_for(cfg)
            return build_audit_plan(tmdb, lib, AuditOptions(movies=False, empty=False, plex_sync=True),
                                    w.progress.emit, fresh, only_shows={rep.show.local_dir for rep, _ in chosen})

        def done(items):
            self.tabs.setCurrentIndex(1)
            self._show(self.audit_table, items)
            self.log(tr("Neue Dateinummern stehen unter „Bibliothek prüfen“ – bitte prüfen und ausführen."))
            self.scan_specials()

        self.run_task(work, done)

    def scan_audit(self) -> None:
        try:
            tmdb, lib = self._services()
        except Exception as e:
            QMessageBox.warning(self, tr("Bibliothek"), str(e))
            return
        libs = self._checked_libs()
        if not libs:
            QMessageBox.information(self, tr("Bibliothek prüfen"), tr("Keine Bibliothek angehakt."))
            return
        has_shows = any(l.kind == "show" for l in libs)
        opts = AuditOptions(movies=any(l.kind == "movie" for l in libs), shows=has_shows,
                            empty=self.opt_empty.isChecked(), episode_titles=has_shows and self.opt_titles.isChecked(),
                            plex_sync=has_shows and self.opt_plex.isChecked(), libraries={l.path for l in libs})
        catalog = None
        if opts.plex_sync and opts.shows:
            if not self.cfg.plex_token:
                QMessageBox.warning(self, tr("Plex-Abgleich"), tr("Kein Plex-Token in den Einstellungen."))
                return
            catalog = catalog_for(self.cfg)
        self.log(tr("Prüfe Bibliothek …"))
        self.run_task(lambda w: build_audit_plan(tmdb, lib, opts, w.report, catalog),
                      lambda items: self._show(self.audit_table, items), cancellable=True)

    def _show(self, table: PlanTable, items: list[PlanItem]) -> None:
        table.set_items(items)
        if items:
            table.selectRow(0)
        table.details.show_item(items[0] if items else None)
        counts: dict[str, int] = {}
        for it in items:
            counts[it.status] = counts.get(it.status, 0) + 1
        summary = ", ".join(f"{n}× {tr(STATUS.get(s, (s,))[0])}" for s, n in counts.items()) or tr("nichts zu tun")
        self.log(tr("{n} Einträge: {summary}", n=len(items), summary=summary))
        if self._last_cancelled:
            self.log(tr("Abgebrochen – die Liste zeigt nur, was bis dahin geprüft wurde."))

    def _show_file(self, table: PlanTable, row: int) -> None:
        if 0 <= row < len(table.items):
            show_in_folder(table.items[row].source)

    def _play_file(self, table: PlanTable, row: int) -> None:
        if 0 <= row < len(table.items) and not play_video(table.items[row].source):
            QMessageBox.information(self, tr("Video abspielen"), tr("Hier gibt es kein Video zum Abspielen."))

    def _retarget(self, table: PlanTable, rows: list[int], lib) -> None:
        """Import the selected rows into another library."""
        items = [table.items[r] for r in rows if table.items[r].retarget]
        first_group, errors = items[0].group if items else None, []
        for it in items:
            try:
                table.replace_group(it.group, it.retarget(lib.path))
            except Exception as e:
                errors.append(f"{it.source.name}: {e}")
        if errors:
            QMessageBox.warning(self, tr("Ziel-Bibliothek"), "\n".join(errors[:10]))
        new_row = next((i for i, x in enumerate(table.items) if x.group == first_group), 0)
        table.selectRow(min(new_row, table.rowCount() - 1))
        self.log(tr("{n} Einträge → Bibliothek „{library}“", n=len(items), library=lib.title))

    def _rematch(self, table: PlanTable, row: int, import_mode: bool) -> None:
        """Pick a TMDB match by hand - for the row, or for all selected rows at once."""
        if row < 0 or row >= len(table.items) or not self.tmdb or self._thread:
            return
        rows = table.selected_rows()
        if row not in rows:
            rows = [row]
        targets = [table.items[r] for r in rows if table.items[r].replan]
        if not targets:
            return
        it = table.items[row] if table.items[row].replan else targets[0]
        multi = len(targets) > 1
        p = it.parsed
        query = it.match.title if it.match else (p.title if p else it.source.name)
        year = it.match.year if it.match else (p.year if p else None)
        context = table._rel(it.source)
        if multi:
            context = tr("{n} Einträge (u. a. {name}) – jede Datei behält ihre Staffel/Folge", n=len(targets), name=it.source.name)
        dlg = MatchDialog(self.tmdb, it.dialog_kind, query, year,
                          season=p.season if p else None, episodes=p.episodes if p else None,
                          episode_fields=import_mode and not multi, kind_fixed=not import_mode,
                          context=context, parent=self)
        if not dlg.exec() or not dlg.result_override:
            return
        ov = dlg.result_override
        if multi:  # same show/movie for all, but every file keeps its own numbers
            ov = Override(ov.kind, ov.tmdb_id)
        first_group, done, errors = it.group, set(), []
        for t in targets:
            if t.group in done:
                continue
            done.add(t.group)
            try:
                table.replace_group(t.group, t.replan(ov))
            except Exception as e:
                errors.append(f"{t.source.name}: {e}")
        if errors:
            QMessageBox.warning(self, "TMDB", "\n".join(errors[:10]))
        new_row = next((i for i, x in enumerate(table.items) if x.group == first_group), 0)
        table.selectRow(min(new_row, table.rowCount() - 1))
        table.details.show_item(table.items[table.currentRow()] if table.currentRow() >= 0 else None)
        if multi:
            self.log(tr("Treffer für {n} Einträge gesetzt.", n=len(done)))

    def run_plan(self, table: PlanTable) -> None:
        table.sync()
        todo = [it for it in table.items if it.selected and it.ops]
        if not todo:
            QMessageBox.information(self, tr("Ausführen"), tr("Nichts ausgewählt."))
            return
        deletions = [it for it in todo if it.kind == "empty"]
        moves = len(todo) - len(deletions)
        text = tr("{n} Einträge umbenennen/verschieben.", n=moves)
        if deletions:
            text += ("\n\n" + tr("{n} Ordner werden ENDGÜLTIG gelöscht (Netzlaufwerk, kein Papierkorb):",
                                  n=len(deletions)) + "\n" +
                     "\n".join(f"  • {it.source.name}" for it in deletions[:15]) +
                     ("\n  …" if len(deletions) > 15 else ""))
        icon = QMessageBox.Warning if deletions else QMessageBox.Question
        box = QMessageBox(icon, tr("Ausführen"), text + "\n\n" + tr("Fortfahren?"), QMessageBox.Yes | QMessageBox.No, self)
        if box.exec() != QMessageBox.Yes:
            return

        cfg = self.cfg
        if table is self.import_table and self.import_root:
            title = tr("Import: {folder}", folder=self.import_root.name)
        else:
            title = tr("Bibliothek prüfen")
        cancel = self._cancel = threading.Event()
        self._run_table = table
        self.panel.start(len(todo))

        def work(w: Worker):
            journal = history.Journal(history.HISTORY_DIR, title)
            rep = Reporter(w.log.emit, w.transfer.emit, w.item_state.emit, cancel, journal)
            try:
                changed, renamed = execute(table.items, rep, cfg.roots)
            except Blocked as e:
                return str(e)
            finally:
                journal.close()
            self._plex_refresh(w, changed, renamed)

        def done(blocked):
            if blocked:  # nothing was touched
                self._run_table = None
                self.panel.finish(True)
                self.log(blocked)
                QMessageBox.warning(self, tr("Ausführen"), tr("Nichts wurde verändert:") + "\n\n" + blocked)
                return
            self._run_table = None
            table.set_items(table.items)
            self.setWindowTitle("ShelfSort")
            self.log(self.panel.finish(cancel.is_set()))
            QApplication.alert(self)  # flash the taskbar button if the window is in the background

        self.run_task(work, done, statusbar=False)

    def _plex_refresh(self, w: Worker, changed: set[Path], full: bool) -> None:
        """Runs in the worker thread after files changed."""
        cfg = self.cfg
        if changed and cfg.plex_token:
            try:
                for msg in Plex(cfg.plex_url, cfg.plex_token).refresh(changed, cfg.library_maps(), full=full):
                    w.log.emit(msg)
            except Exception as e:
                w.log.emit(tr("Plex-Scan fehlgeschlagen: {error}", error=e))
        elif changed:
            w.log.emit(tr("Kein Plex-Token – Bibliothek bitte manuell scannen."))

    # --- update hint ---

    def check_for_update(self) -> None:
        """Once a day in the background; quiet when offline or nothing is new."""
        if not update.due(self.cfg):
            return

        def ok(release: update.Release) -> None:
            self.cfg.last_update_check = time.time()
            self.cfg.save()
            if update.newer(release, self.cfg):
                self._release = release
                self.update_label.setText(tr('Neue Version {version} verfügbar – <a href="open">Herunterladen</a>'
                                             ' · <a href="skip">Überspringen</a>', version=release.version))
                self.update_label.show()
                file_log.info("Neue Version verfügbar: %s", release.version)

        run_async(self, update.latest, ok, lambda e: file_log.info("Update-Prüfung fehlgeschlagen: %s", e))

    def _update_link(self, link: str) -> None:
        if link == "open":
            QDesktopServices.openUrl(QUrl(self._release.url))
        else:
            self.cfg.skipped_version = self._release.version
            self.cfg.save()
        self.update_label.hide()

    # --- history ---

    def open_history(self) -> None:
        dlg = HistoryDialog(self, busy=self._thread is not None)
        dlg.undo_requested.connect(self.undo_run)
        dlg.exec()

    def undo_run(self, run: history.Run) -> None:
        roots = self.cfg.roots
        self.log(tr("Rückgängig: Lauf vom {when} ({title})", when=run.when(), title=run.title))

        def work(w: Worker):
            changed, ok, skipped = history.undo(run, w.log.emit, roots, move_file)
            renamed_dirs = any(e["op"] == "rename" and Path(e["src"]).is_dir() for e in run.changes)
            self._plex_refresh(w, changed, renamed_dirs)
            return ok, skipped

        def done(result):
            ok, skipped = result
            text = tr("{ok} Änderungen rückgängig gemacht, {skipped} übersprungen.", ok=ok, skipped=skipped)
            self.log(text)
            for table in (self.import_table, self.audit_table):
                if table.items:
                    text += "\n\n" + tr("Die Listen sind jetzt veraltet – bitte neu scannen bzw. prüfen.")
                    break
            (QMessageBox.warning if skipped else QMessageBox.information)(self, tr("Rückgängig machen"), text)

        self.run_task(work, done)


def main() -> None:
    if sys.platform == "win32":
        # own taskbar identity, so Windows shows ShelfSort's icon instead of Python's
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ShelfSort.App")
    setup_log()
    app = QApplication(sys.argv)
    app.setApplicationName("ShelfSort")
    app.setWindowIcon(QIcon(str(Path(__file__).parent / "assets" / "icon.png")))
    cfg = Config.load()
    apply_language(cfg.app_language or i18n.system_language())
    app.main_window = MainWindow()  # kept on the app so a language switch can replace it
    app.main_window.show()
    sys.exit(app.exec())


_qt_translator: QTranslator | None = None


def apply_language(lang: str) -> str:
    """UI language for ShelfSort's texts and Qt's own (Yes/No buttons, file dialogs)."""
    global _qt_translator
    lang = i18n.set_language(lang)
    app = QApplication.instance()
    if _qt_translator:
        app.removeTranslator(_qt_translator)
        _qt_translator = None
    if lang != "en":  # Qt's built-in texts are English
        tr_ = QTranslator(app)
        if tr_.load(f"qtbase_{lang}", QLibraryInfo.path(QLibraryInfo.TranslationsPath)):
            app.installTranslator(tr_)
            _qt_translator = tr_
    return lang
