"""First-start setup: TMDB key, Plex sign-in, server, libraries and where their folders are locally."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QVBoxLayout, QWidget, QWizard, QWizardPage)

from . import plex_auth
from .config import Config
from .path_mapping import suggest, verify
from .plex import Plex
from .tmdb import TMDB

OK = "color: #2ea043"
BAD = "color: #da3633"
GRAY = "color: gray"


# --- background calls ---------------------------------------------------------------------

class _Relay(QObject):
    """Lives in the GUI thread; results emitted from a worker are delivered to the callbacks here."""
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, parent: QObject, ok: Callable, err: Callable | None):
        super().__init__(parent)
        self._ok, self._err = ok, err
        self.done.connect(self._on_done)
        self.failed.connect(self._on_failed)

    @Slot(object)
    def _on_done(self, result) -> None:
        self._ok(result)
        self.deleteLater()

    @Slot(str)
    def _on_failed(self, msg: str) -> None:
        if self._err:
            self._err(msg)
        self.deleteLater()


class _Job(QRunnable):
    def __init__(self, fn: Callable, relay: _Relay):
        super().__init__()
        self.fn, self.relay = fn, relay

    def run(self) -> None:
        try:
            self.relay.done.emit(self.fn())
        except Exception as e:
            self.relay.failed.emit(str(e))


def run_async(owner: QObject, fn: Callable, ok: Callable, err: Callable | None = None) -> None:
    QThreadPool.globalInstance().start(_Job(fn, _Relay(owner, ok, err)))


def _label(text: str = "", style: str = "") -> QLabel:
    lab = QLabel(text)
    lab.setWordWrap(True)
    lab.setTextFormat(Qt.RichText)
    lab.setOpenExternalLinks(True)
    if style:
        lab.setStyleSheet(style)
    return lab


# --- pages --------------------------------------------------------------------------------

PAGE_TMDB, PAGE_PLEX, PAGE_SERVER, PAGE_LIBS, PAGE_DONE = range(5)


class TmdbPage(QWizardPage):
    def __init__(self, cfg: Config):
        super().__init__()
        self.setTitle("TMDB-Zugang")
        self.setSubTitle("Titel, Jahre, Cover und Beschreibungen kommen von The Movie Database (TMDB).")
        self.key = QLineEdit(cfg.tmdb_key)
        self.key.setPlaceholderText("API-Key (v3) oder Lese-Token (v4)")
        self.key.setEchoMode(QLineEdit.PasswordEchoOnEdit)
        self.key.textChanged.connect(lambda _: (self.status.setText(""), self.completeChanged.emit()))
        self.status = _label()
        lay = QVBoxLayout(self)
        lay.addWidget(_label('Der Key ist kostenlos: Konto auf <a href="https://www.themoviedb.org/signup">'
                             'themoviedb.org</a> anlegen → Einstellungen → <a href="https://www.themoviedb.org/'
                             'settings/api">API</a> → Key beantragen (Typ „Developer“, private Nutzung).'))
        lay.addWidget(self.key)
        lay.addWidget(self.status)
        lay.addStretch()
        lay.addWidget(_label("This product uses TMDB and the TMDB APIs but is not endorsed, certified, or "
                             "otherwise approved by TMDB.", GRAY))

    def isComplete(self) -> bool:
        return bool(self.key.text().strip())

    def validatePage(self) -> bool:
        try:
            TMDB(self.key.text().strip()).search_movie("Matrix")
        except Exception as e:
            self.status.setText(f"Key funktioniert nicht: {e}")
            self.status.setStyleSheet(BAD)
            return False
        return True


class PlexLoginPage(QWizardPage):
    def __init__(self, cfg: Config):
        super().__init__()
        self.cfg = cfg
        self.setTitle("Bei Plex anmelden")
        self.setSubTitle("Für den Scan nach dem Verschieben, den Plex-Abgleich und den Specials-Check.")
        self.token = cfg.plex_token
        self.pin = None
        self.timer = QTimer(self)
        self.timer.setInterval(2000)
        self.timer.timeout.connect(self._poll)

        self.login = QPushButton("Bei Plex anmelden …")
        self.login.clicked.connect(self._start)
        self.status = _label()
        self.skip = QCheckBox("Ohne Plex weiter (nur Umbenennen und Verschieben)")
        self.skip.toggled.connect(lambda _: self.completeChanged.emit())
        lay = QVBoxLayout(self)
        lay.addWidget(_label("Die Anmeldung läuft auf plex.tv in deinem Browser – ShelfSort sieht dein Passwort "
                             "nicht, sondern bekommt nur einen Zugangsschlüssel für deinen Server."))
        lay.addWidget(self.login, 0, Qt.AlignLeft)
        lay.addWidget(self.status)
        lay.addStretch()
        lay.addWidget(self.skip)
        if self.token:
            self._signed_in("Bereits angemeldet. Zum Wechseln des Kontos erneut anmelden.")

    def _signed_in(self, text: str) -> None:
        self.status.setText(text)
        self.status.setStyleSheet(OK)
        self.login.setText("Erneut anmelden …")
        self.completeChanged.emit()
        token, cid = self.token, self.cfg.ensure_client_id()

        def named(name):
            if self.token == token:
                self.status.setText(f"{text} Konto: <b>{name}</b> – falls das nicht dein Server-Konto ist "
                                    f"(z. B. ein Plex-Home-Benutzer), im Browser abmelden und erneut anmelden.")

        run_async(self, lambda: plex_auth.account_name(cid, token), named)

    def _start(self) -> None:
        cid = self.cfg.ensure_client_id()
        self.login.setEnabled(False)
        self.status.setStyleSheet(GRAY)
        self.status.setText("Verbinde mit plex.tv …")

        def started(pin):
            self.pin = pin
            QDesktopServices.openUrl(QUrl(plex_auth.auth_url(cid, pin)))
            self.status.setText("Im Browser anmelden und ShelfSort erlauben – dieses Fenster wartet darauf …")
            self.timer.start()

        def failed(msg):
            self.login.setEnabled(True)
            self.status.setText(f"plex.tv nicht erreichbar: {msg}")
            self.status.setStyleSheet(BAD)

        run_async(self, lambda: plex_auth.start_pin(cid), started, failed)

    def _poll(self) -> None:
        if not self.pin:
            return
        cid, pin = self.cfg.client_id, self.pin

        def checked(token):
            if token and self.pin is pin:
                self.timer.stop()
                self.pin = None
                self.token = token
                self.login.setEnabled(True)
                self._signed_in("Angemeldet.")

        run_async(self, lambda: plex_auth.check_pin(cid, pin), checked)

    def isComplete(self) -> bool:
        return bool(self.token) or self.skip.isChecked()

    def nextId(self) -> int:
        return PAGE_LIBS if self.skip.isChecked() else PAGE_SERVER


class ServerPage(QWizardPage):
    def __init__(self, cfg: Config):
        super().__init__()
        self.cfg = cfg
        self.setTitle("Plex-Server")
        self.setSubTitle("Welcher Server enthält deine Bibliotheken?")
        self.servers: list[plex_auth.Server] = []
        self.url: str | None = None
        self.combo = QComboBox()
        self.combo.currentIndexChanged.connect(self._test)
        self.status = _label()

        # fallback: server address by hand (e.g. when plex.tv doesn't list the server)
        self.manual = QLineEdit(cfg.plex_url if cfg.plex_url and "localhost" not in cfg.plex_url else "")
        self.manual.setPlaceholderText("z. B. http://192.168.1.5:32400")
        self.manual_btn = QPushButton("Verbinden")
        self.manual_btn.clicked.connect(self._manual)
        manual_row = QHBoxLayout()
        manual_row.addWidget(self.manual, 1)
        manual_row.addWidget(self.manual_btn)

        lay = QVBoxLayout(self)
        lay.addWidget(self.combo)
        lay.addWidget(self.status)
        lay.addSpacing(18)
        lay.addWidget(_label("Server nicht in der Liste? Adresse von Hand eingeben:", GRAY))
        lay.addLayout(manual_row)
        lay.addStretch()

    def _fill(self, servers: list[plex_auth.Server]) -> None:
        self.servers = servers
        self.combo.blockSignals(True)
        self.combo.clear()
        for s in servers:
            self.combo.addItem(s.name + ("" if s.owned else "  (geteilt)"))
        idx = next((i for i, s in enumerate(servers) if s.name == self.cfg.plex_server_name), 0)
        self.combo.setCurrentIndex(idx)
        self.combo.blockSignals(False)
        self._test()

    def initializePage(self) -> None:
        token = self.wizard().page(PAGE_PLEX).token
        cid = self.cfg.ensure_client_id()
        self.combo.clear()
        self.servers = []
        self.url = None
        self.status.setStyleSheet(GRAY)
        self.status.setText("Suche Server …")

        def lookup():
            devices = plex_auth.resources(cid, token)
            return devices, plex_auth.servers(cid, token, devices), plex_auth.account_name(cid, token)

        def found(result):
            devices, servers, account = result
            if servers:
                self._fill(servers)
                return
            names = ", ".join(sorted({d.get("name", "?") for d in devices})) or "keine"
            self.status.setText(
                f"Im Konto <b>{account}</b> ist kein Plex Media Server zu sehen "
                f"({len(devices)} Geräte: {names}).<br>Ist das das Konto, dem der Server gehört? Sonst "
                f"zurück und mit dem richtigen Konto anmelden – oder unten die Adresse eingeben.")
            self.status.setStyleSheet(BAD)

        run_async(self, lookup, found,
                  lambda m: (self.status.setText(f"Fehler: {m}"), self.status.setStyleSheet(BAD)))

    def _manual(self) -> None:
        token = self.wizard().page(PAGE_PLEX).token
        url = self.manual.text().strip()
        if not url:
            return
        self.status.setStyleSheet(GRAY)
        self.status.setText(f"Verbinde mit {url} …")

        def connected(server):
            if server:
                self._fill([server])
            else:
                self.status.setText(f"{url} antwortet nicht oder lässt diesen Plex-Zugang nicht zu.")
                self.status.setStyleSheet(BAD)

        run_async(self, lambda: plex_auth.manual_server(url, token), connected)

    def server(self) -> plex_auth.Server | None:
        i = self.combo.currentIndex()
        return self.servers[i] if 0 <= i < len(self.servers) else None

    def _test(self, _=None) -> None:
        s = self.server()
        if not s:
            return
        self.url = None
        self.completeChanged.emit()
        self.status.setStyleSheet(GRAY)
        self.status.setText(f"Teste Verbindung zu {s.name} …")

        def tested(url):
            if self.server() is not s:
                return
            self.url = url
            if url:
                self.status.setText(f"Erreichbar über {url}")
                self.status.setStyleSheet(OK)
            else:
                self.status.setText("Server ist gerade nicht erreichbar.")
                self.status.setStyleSheet(BAD)
            self.completeChanged.emit()

        run_async(self, lambda: plex_auth.best_connection(s), tested)

    def isComplete(self) -> bool:
        return bool(self.url)


class _LibraryRow:
    """Plex library choice + local folder + check, for one kind (movies or shows)."""

    def __init__(self, page: "LibrariesPage", kind: str, label: str, local: str, section_key: str):
        self.page, self.kind = page, kind
        self.combo = QComboBox()
        self.combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.path = QLineEdit(local)
        self.path.setPlaceholderText("Ordner auf diesem Computer")
        self.browse = QPushButton("…")
        self.browse.setFixedWidth(32)
        self.browse.clicked.connect(self._browse)
        self.status = _label("", GRAY)
        self.label = QLabel(label)
        self.section_key = section_key
        self.sections: list[dict] = []
        self.samples: list[str] = []
        self.combo.currentIndexChanged.connect(self._section_changed)
        self.path.textChanged.connect(lambda _: self._verify())

    def add_to(self, grid: QGridLayout, row: int) -> None:
        grid.addWidget(self.label, row, 0)
        grid.addWidget(self.combo, row, 1)
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(self.path, 1)
        h.addWidget(self.browse)
        grid.addWidget(box, row, 2)
        grid.addWidget(self.status, row + 1, 1, 1, 2)

    def section(self) -> dict | None:
        i = self.combo.currentIndex()
        return self.sections[i] if 0 <= i < len(self.sections) else None

    def server_root(self) -> str:
        s = self.section()
        return s["locations"][0] if s and s["locations"] else ""

    def set_sections(self, sections: list[dict]) -> None:
        self.sections = [s for s in sections if s["type"] == self.kind]
        self.combo.blockSignals(True)
        self.combo.clear()
        for s in self.sections:
            self.combo.addItem(f"{s['title']}  ({', '.join(s['locations'])})")
        # saved choice, else the library whose folder name matches the current local folder
        local_name = Path(self.path.text().strip()).name.lower()
        idx = next((i for i, s in enumerate(self.sections) if s["key"] == self.section_key), None)
        if idx is None:
            idx = next((i for i, s in enumerate(self.sections)
                        if local_name and any(Plex._basename(l) == local_name for l in s["locations"])), 0)
        self.combo.setCurrentIndex(idx)
        self.combo.blockSignals(False)
        self.combo.setVisible(True)
        self._section_changed()

    def _section_changed(self, _=None) -> None:
        s, plex = self.section(), self.page.plex
        if not s or not plex:
            return
        self.samples = []
        self.status.setStyleSheet(GRAY)
        self.status.setText("Suche den Ordner auf diesem Computer …")
        root = self.server_root()
        current = self.path.text().strip()  # read here: widgets only in the GUI thread

        def work():
            samples = plex.sample_files(s)
            if current and samples and verify(Path(current), root, samples).ok:
                return samples, None  # the configured folder already fits
            return samples, suggest(root, samples)

        def done(result):
            if self.section() is not s:
                return
            self.samples, guess = result
            if guess:
                self.path.setText(str(guess.local_root))
            self._verify()

        run_async(self.page, work, done, lambda m: self.status.setText(f"Fehler: {m}"))

    def _browse(self) -> None:
        d = QFileDialog.getExistingDirectory(self.page, "Ordner wählen", self.path.text())
        if d:
            self.path.setText(d.replace("/", "\\"))

    def _verify(self) -> None:
        local = self.path.text().strip()
        if not local:
            self.status.setText("Ordner fehlt.")
            self.status.setStyleSheet(BAD)
        elif not Path(local).is_dir():
            self.status.setText("Ordner nicht gefunden.")
            self.status.setStyleSheet(BAD)
        elif self.samples:
            g = verify(Path(local), self.server_root(), self.samples)
            if g.ok:
                self.status.setText(f"✓ Passt: {g.hits} von {g.total} Beispieldateien aus Plex gefunden.")
                self.status.setStyleSheet(OK)
            else:
                self.status.setText(f"Nur {g.hits} von {g.total} Beispieldateien gefunden – ist das wirklich "
                                    f"der Ordner von „{self.server_root()}“?")
                self.status.setStyleSheet(BAD)
        else:
            self.status.setText("Ordner vorhanden.")
            self.status.setStyleSheet(GRAY)
        self.page.completeChanged.emit()


class LibrariesPage(QWizardPage):
    def __init__(self, cfg: Config):
        super().__init__()
        self.cfg = cfg
        self.plex: Plex | None = None
        self.setTitle("Bibliotheken")
        self.movies = _LibraryRow(self, "movie", "Filme", cfg.movies_root, cfg.movies_section)
        self.shows = _LibraryRow(self, "show", "Serien", cfg.tv_root, cfg.tv_section)
        self.info = _label()
        grid = QGridLayout()
        grid.setColumnStretch(2, 1)
        self.movies.add_to(grid, 0)
        self.shows.add_to(grid, 2)
        lay = QVBoxLayout(self)
        lay.addWidget(self.info)
        lay.addLayout(grid)
        lay.addStretch()

    def initializePage(self) -> None:
        wiz = self.wizard()
        server_page: ServerPage = wiz.page(PAGE_SERVER)
        login: PlexLoginPage = wiz.page(PAGE_PLEX)
        use_plex = not login.skip.isChecked() and server_page.url and server_page.server()
        for row in (self.movies, self.shows):
            row.combo.setVisible(bool(use_plex))
        if not use_plex:
            self.plex = None
            self.setSubTitle("Wo liegen deine Filme und Serien?")
            self.info.setText("")
            return
        self.setSubTitle("Welche Plex-Bibliothek ist welche – und wo liegt ihr Ordner auf diesem Computer?")
        self.info.setText("ShelfSort sucht den passenden Ordner selbst und prüft ihn an echten Dateien aus Plex. "
                          "Der Server kann einen anderen Pfad sehen (z. B. <i>/data/movies</i>) als dieser "
                          "Computer (z. B. <i>X:\\Medien\\movies</i>).")
        s = server_page.server()
        self.plex = Plex(server_page.url, s.access_token)
        plex = self.plex

        def loaded(sections):
            self.movies.set_sections(sections)
            self.shows.set_sections(sections)

        run_async(self, plex.sections, loaded, lambda m: self.info.setText(f"Fehler: {m}"))

    def isComplete(self) -> bool:
        return all(r.path.text().strip() and Path(r.path.text().strip()).is_dir() for r in (self.movies, self.shows))


class DonePage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Fertig")
        self.summary = _label()
        lay = QVBoxLayout(self)
        lay.addWidget(self.summary)
        lay.addStretch()

    def initializePage(self) -> None:
        wiz = self.wizard()
        libs: LibrariesPage = wiz.page(PAGE_LIBS)
        server: ServerPage = wiz.page(PAGE_SERVER)
        lines = [f"<b>Filme:</b> {libs.movies.path.text()}", f"<b>Serien:</b> {libs.shows.path.text()}"]
        if libs.plex and server.server():
            lines.insert(0, f"<b>Plex-Server:</b> {server.server().name} ({server.url})")
        lines.append("<br>Alles lässt sich später unter <i>Einstellungen</i> ändern oder mit dem Assistenten "
                     "neu einrichten.")
        self.summary.setText("<br>".join(lines))


class SetupWizard(QWizard):
    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("ShelfSort einrichten")
        self.setWizardStyle(QWizard.ModernStyle)
        self.resize(760, 520)
        self.setPage(PAGE_TMDB, TmdbPage(cfg))
        self.setPage(PAGE_PLEX, PlexLoginPage(cfg))
        self.setPage(PAGE_SERVER, ServerPage(cfg))
        self.setPage(PAGE_LIBS, LibrariesPage(cfg))
        self.setPage(PAGE_DONE, DonePage())
        self.setButtonText(QWizard.NextButton, "Weiter >")
        self.setButtonText(QWizard.BackButton, "< Zurück")
        self.setButtonText(QWizard.FinishButton, "Fertig")
        self.setButtonText(QWizard.CancelButton, "Abbrechen")

    def accept(self) -> None:
        c = self.cfg
        c.tmdb_key = self.page(PAGE_TMDB).key.text().strip()
        login: PlexLoginPage = self.page(PAGE_PLEX)
        libs: LibrariesPage = self.page(PAGE_LIBS)
        server: ServerPage = self.page(PAGE_SERVER)
        c.movies_root = libs.movies.path.text().strip()
        c.tv_root = libs.shows.path.text().strip()
        if libs.plex and not login.skip.isChecked():
            c.plex_token = server.server().access_token
            c.plex_url = server.url
            c.plex_server_name = server.server().name
            for row, prefix in ((libs.movies, "movies"), (libs.shows, "tv")):
                s = row.section()
                setattr(c, f"{prefix}_section", s["key"] if s else "")
                setattr(c, f"{prefix}_server_root", row.server_root())
        else:
            c.plex_token = c.plex_url = c.plex_server_name = ""
            c.movies_section = c.movies_server_root = c.tv_section = c.tv_server_root = ""
        c.save()
        super().accept()
