"""First-start setup: TMDB key, Plex sign-in, server, libraries and where their folders are locally."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import QLocale, QObject, QRunnable, Qt, QThreadPool, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QFileDialog, QFormLayout, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton, QRadioButton, QVBoxLayout, QWidget,
                               QWizard, QWizardPage)

from . import plex_auth
from .config import KINDS, METADATA_LANGUAGES, Config, LibraryConfig, language_name
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

PAGE_WELCOME, PAGE_TMDB, PAGE_PLEX, PAGE_SERVER, PAGE_LIBS, PAGE_DONE = range(6)

APP_LANGUAGES = [("de", "Deutsch", True), ("en", "English – folgt", False)]


def _same_language(a: str, b: str) -> bool:
    return (a or "").split("-")[0].lower() == (b or "").split("-")[0].lower()


class WelcomePage(QWizardPage):
    def __init__(self, cfg: Config):
        super().__init__()
        self.setTitle("Willkommen bei ShelfSort")
        self.setSubTitle("Ein paar Schritte, dann kann es losgehen.")
        system = QLocale.system().name().replace("_", "-")  # e.g. "de-DE"

        self.app = QComboBox()
        for code, name, available in APP_LANGUAGES:
            self.app.addItem(name, code)
            if not available:
                self.app.model().item(self.app.count() - 1).setEnabled(False)
        self.app.setCurrentIndex(max(0, self.app.findData(cfg.app_language or "de")))

        self.meta = QComboBox()
        for code, name in METADATA_LANGUAGES:
            self.meta.addItem(f"{name}  ({code})", code)
        current = cfg.language if cfg.is_set_up else system
        self.set_metadata_language(current)

        form = QFormLayout()
        form.addRow("Sprache der App", self.app)
        form.addRow("Sprache der Titel", self.meta)  # default; each library can override it
        lay = QVBoxLayout(self)
        lay.addWidget(_label("ShelfSort benennt Filme und Serien so, wie Plex sie erwartet, verschiebt sie in deine "
                             "Bibliothek und hält Folgennummern passend zur Reihenfolge in Plex."))
        lay.addSpacing(8)
        lay.addLayout(form)
        lay.addWidget(_label("Die <b>Sprache der Titel</b> bestimmt Film-, Serien- und Folgentitel in den "
                             "Dateinamen. Bibliotheken aus Plex bekommen automatisch ihre Plex-Sprache, und jede "
                             "Bibliothek lässt sich einzeln umstellen (z. B. Englisch für eine OV-Bibliothek). "
                             "Diese Einstellung gilt für alles andere.", GRAY))
        lay.addStretch()

    def set_metadata_language(self, code: str) -> None:
        idx = self.meta.findData(code)
        if idx < 0:
            idx = next((i for i in range(self.meta.count()) if _same_language(self.meta.itemData(i), code)), -1)
        if idx < 0:
            self.meta.addItem(code, code)
            idx = self.meta.count() - 1
        self.meta.setCurrentIndex(idx)

    @property
    def metadata_language(self) -> str:
        return self.meta.currentData()


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
    """One library: managed yes/no, local folder (found automatically), default for its kind."""

    def __init__(self, page: "LibrariesPage", kind: str, title: str, section: dict | None,
                 local: str, managed: bool, default: bool, language: str, count: int | None = None):
        self.page, self.kind, self.title, self.section = page, kind, title, section
        self.count = count or 0
        self.samples: list[str] = []
        self.searched = False
        self.check = QCheckBox(f"{title}" + (f"  ({', '.join(section['locations'])})" if section else ""))
        self.check.setChecked(managed)
        self.check.setEnabled(section is not None)  # without Plex both rows are required
        self.check.toggled.connect(self._toggled)
        unit = "Filme" if kind == "movie" else "Serien"
        self.kind_label = QLabel(f"{count} {unit}" if count is not None else KINDS[kind])
        self.kind_label.setStyleSheet(GRAY)
        # title language of this library (an OV library may want English titles)
        self.lang = QComboBox()
        for code, name in METADATA_LANGUAGES:
            self.lang.addItem(name, code)
        if self.lang.findData(language) < 0:
            self.lang.addItem(language, language)
        self.lang.setCurrentIndex(self.lang.findData(language))
        self.lang.setToolTip("Sprache der Titel für diese Bibliothek")
        self.lang.currentIndexChanged.connect(lambda _: self._verify())
        self.default = QRadioButton("Standard")
        self.default.setToolTip(f"Neue {KINDS[kind]} werden hierhin importiert.")
        self.default.setChecked(default)
        self.path = QLineEdit(local)
        self.path.setPlaceholderText("Ordner auf diesem Computer")
        self.browse = QPushButton("…")
        self.browse.setFixedWidth(32)
        self.browse.clicked.connect(self._browse)
        self.status = _label("", GRAY)
        self.path.textChanged.connect(lambda _: self._verify())
        page.groups[kind].addButton(self.default)

    def add_to(self, grid: QGridLayout, row: int) -> None:
        grid.addWidget(self.check, row, 0)
        grid.addWidget(self.kind_label, row, 1)
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(self.path, 1)
        h.addWidget(self.browse)
        grid.addWidget(box, row, 2)
        grid.addWidget(self.lang, row, 3)
        grid.addWidget(self.default, row, 4)
        grid.addWidget(self.status, row + 1, 0, 1, 5)
        self._toggled(self.check.isChecked())

    @property
    def plex_language(self) -> str:
        lang = (self.section or {}).get("language", "")
        return "" if lang in ("", "xn") else lang

    @property
    def managed(self) -> bool:
        return self.check.isChecked()

    def server_root(self) -> str:
        return self.section["locations"][0] if self.section and self.section["locations"] else ""

    def _toggled(self, on: bool) -> None:
        for w in (self.path, self.browse, self.default, self.lang):
            w.setEnabled(on)
        if not on:
            self.status.setText("")
            if self.default.isChecked():
                self.page.pick_default(self.kind)
        elif not self.searched:
            self.search()
        else:
            self._verify()
        self.page.completeChanged.emit()

    def search(self) -> None:
        """Fetch sample files from Plex and find the folder on this computer (in the background)."""
        plex = self.page.plex
        self.searched = True
        if not self.section or not plex:
            self._verify()
            return
        s, root = self.section, self.server_root()
        current = self.path.text().strip()  # read here: widgets only in the GUI thread
        self.status.setStyleSheet(GRAY)
        self.status.setText("Suche den Ordner auf diesem Computer …")

        def work():
            samples = plex.sample_files(s)
            if current and samples and verify(Path(current), root, samples).ok:
                return samples, None  # the configured folder already fits
            return samples, suggest(root, samples)

        def done(result):
            self.samples, guess = result
            if guess:
                self.path.setText(str(guess.local_root))
            self._verify()

        run_async(self.page, work, done, lambda m: self.status.setText(f"Fehler: {m}"))

    def _browse(self) -> None:
        d = QFileDialog.getExistingDirectory(self.page, "Ordner wählen", self.path.text())
        if d:
            self.path.setText(d.replace("/", "\\"))

    def valid(self) -> bool:
        p = self.path.text().strip()
        return bool(p) and Path(p).is_dir()

    def _verify(self) -> None:
        if not self.managed:
            return
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

    def to_config(self) -> LibraryConfig:
        return LibraryConfig(self.kind, self.title, self.path.text().strip(),
                             self.section["key"] if self.section else "", self.server_root(),
                             self.default.isChecked(), self.lang.currentData())


class LibrariesPage(QWizardPage):
    def __init__(self, cfg: Config):
        super().__init__()
        self.cfg = cfg
        self.plex: Plex | None = None
        self.rows: list[_LibraryRow] = []
        self.groups = {"movie": QButtonGroup(self), "show": QButtonGroup(self)}
        self.setTitle("Bibliotheken")
        self.info = _label()
        self.grid = QGridLayout()
        self.grid.setColumnStretch(2, 1)
        lay = QVBoxLayout(self)
        lay.addWidget(self.info)
        lay.addLayout(self.grid)
        lay.addStretch()

    def _clear(self) -> None:
        for row in self.rows:
            for w in (row.check, row.kind_label, row.path.parentWidget(), row.lang, row.default, row.status):
                w.setParent(None)
            self.groups[row.kind].removeButton(row.default)
        self.rows = []

    def _add(self, row: _LibraryRow) -> None:
        row.add_to(self.grid, len(self.rows) * 2)
        self.rows.append(row)

    def pick_default(self, kind: str) -> None:
        """Keep exactly one default per kind among the managed libraries."""
        rows = [r for r in self.rows if r.kind == kind and r.managed]
        if rows and not any(r.default.isChecked() for r in rows):
            # the biggest library is usually the main one ("Filme" rather than "Disney")
            max(rows, key=lambda r: r.count).default.setChecked(True)

    def initializePage(self) -> None:
        wiz = self.wizard()
        server_page: ServerPage = wiz.page(PAGE_SERVER)
        login: PlexLoginPage = wiz.page(PAGE_PLEX)
        self._clear()
        default_lang = wiz.page(PAGE_WELCOME).metadata_language
        use_plex = not login.skip.isChecked() and server_page.url and server_page.server()
        if not use_plex:
            self.plex = None
            self.setSubTitle("Wo liegen deine Filme und Serien?")
            self.info.setText("")
            for kind in ("movie", "show"):
                lib = self.cfg.default_lib(kind)
                self._add(_LibraryRow(self, kind, KINDS[kind], None, lib.local_root if lib else "", True, True,
                                      (lib.language if lib and lib.language else default_lang)))
            return
        self.setSubTitle("Welche Plex-Bibliotheken soll ShelfSort verwalten – und wo liegen ihre Ordner?")
        self.info.setText("ShelfSort sucht die Ordner selbst und prüft sie an echten Dateien aus Plex (der Server "
                          "kann einen anderen Pfad sehen, z. B. <i>/data/movies</i>, als dieser Computer, z. B. "
                          "<i>X:\\Medien\\movies</i>). Pro Typ ist eine Bibliothek <b>Standard</b> für neue Importe; "
                          "neue Folgen vorhandener Serien landen immer bei ihrer Serie.")
        s = server_page.server()
        self.plex = Plex(server_page.url, s.access_token)
        known = {lib.section_key: lib for lib in self.cfg.libs if lib.section_key}
        by_folder = {Path(lib.local_root).name.lower(): lib for lib in self.cfg.libs}

        plex = self.plex

        def load():
            sections = [s for s in plex.sections() if s["type"] in KINDS]
            return [(s, plex.section_size(s)) for s in sections]

        def loaded(result):
            for sec, count in result:
                kind = "movie" if sec["type"] == "movie" else "show"
                old = known.get(sec["key"]) or next(
                    (by_folder[Plex._basename(l)] for l in sec["locations"] if Plex._basename(l) in by_folder), None)
                personal = sec.get("agent", "").endswith(".none")  # e.g. "Andere Videos"
                managed = old is not None if self.cfg.libs else not personal
                plex_lang = sec.get("language", "")
                # saved choice, else the language the library uses in Plex, else the default from page 1
                language = (old.language if old and old.language
                            else plex_lang if plex_lang not in ("", "xn") else default_lang)
                self._add(_LibraryRow(self, kind, sec["title"], sec, old.local_root if old else "", managed,
                                      bool(old and old.default), language, count))
            for kind in KINDS:
                self.pick_default(kind)
            self.completeChanged.emit()

        run_async(self, load, loaded, lambda m: self.info.setText(f"Fehler: {m}"))

    def chosen(self) -> list[LibraryConfig]:
        return [r.to_config() for r in self.rows if r.managed]

    def isComplete(self) -> bool:
        managed = [r for r in self.rows if r.managed]
        kinds = {r.kind for r in managed}
        return kinds == {"movie", "show"} and all(r.valid() for r in managed)


class DonePage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Fertig")
        self.setSubTitle("So ist ShelfSort eingerichtet. Mit „Fertig“ wird gespeichert.")
        self.summary = _label()
        self.lang_hint = _label("", BAD)
        self.lang_fix = QPushButton()
        self.lang_fix.clicked.connect(self._adopt_language)
        self._mismatched = []
        lay = QVBoxLayout(self)
        lay.addWidget(self.summary)
        lay.addWidget(self.lang_hint)
        lay.addWidget(self.lang_fix, 0, Qt.AlignLeft)
        lay.addStretch()
        lay.addWidget(_label("Alles lässt sich später über <i>Einrichten …</i> im Menü ändern.", GRAY))

    @staticmethod
    def _section(title: str, body: str) -> str:
        return (f'<p style="margin-top:12px; margin-bottom:2px"><span style="color:gray">{title.upper()}</span></p>'
                f"{body}")

    def initializePage(self) -> None:
        wiz = self.wizard()
        welcome: WelcomePage = wiz.page(PAGE_WELCOME)
        libs: LibrariesPage = wiz.page(PAGE_LIBS)
        server: ServerPage = wiz.page(PAGE_SERVER)
        html = []

        if libs.plex and server.server():
            html.append(self._section("Plex", f"<b>{server.server().name}</b> &nbsp;·&nbsp; {server.url}"))
        else:
            html.append(self._section("Plex", "nicht verbunden – Scan, Plex-Abgleich und Specials-Check sind aus"))
        html.append(self._section("Sprache", f"App: <b>{welcome.app.currentText()}</b>"))

        managed = [r for r in libs.rows if r.managed]
        # titles should be in the language the library uses in Plex, else file names and Plex disagree
        self._mismatched = [r for r in managed if r.plex_language
                            and not _same_language(r.plex_language, r.lang.currentData())]
        rows = []
        for row in managed:
            lib = row.to_config()
            warn = " ⚠" if row in self._mismatched else ""
            plex_lang = language_name(row.plex_language) if row.plex_language else "–"
            rows.append(f"<tr><td><b>{lib.title}</b></td><td>{KINDS[lib.kind]}</td>"
                        f"<td>{'✓ Standard' if lib.default else ''}</td><td>{lib.local_root}</td>"
                        f"<td>{language_name(lib.language)}{warn}</td><td>{plex_lang}</td></tr>")
        table = ('<table cellspacing="0" cellpadding="4" width="100%">'
                 '<tr style="color:gray"><td>Bibliothek</td><td>Typ</td><td>Neue Importe</td><td>Ordner</td>'
                 '<td>Titel</td><td>in Plex</td></tr>' + "".join(rows) + "</table>")
        html.append(self._section("Bibliotheken", table))
        self.summary.setText("".join(html))

        self.lang_hint.setVisible(bool(self._mismatched))
        self.lang_fix.setVisible(bool(self._mismatched))
        if self._mismatched:
            names = ", ".join(f"<b>{r.title}</b> ({language_name(r.plex_language)} in Plex)" for r in self._mismatched)
            self.lang_hint.setText(f"Titelsprache weicht von Plex ab: {names}. Dann heißen Dateien anders, als Plex "
                                   f"sie anzeigt – gewollt z. B. nur, wenn Plex selbst falsch eingestellt ist.")
            self.lang_fix.setText("Titelsprache an Plex angleichen")

    def _adopt_language(self) -> None:
        for row in self._mismatched:
            row.lang.setCurrentIndex(max(0, row.lang.findData(row.plex_language)))
        self.initializePage()


class SetupWizard(QWizard):
    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("ShelfSort einrichten")
        self.setWizardStyle(QWizard.ModernStyle)
        self.resize(860, 580)
        self.setPage(PAGE_WELCOME, WelcomePage(cfg))
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
        welcome: WelcomePage = self.page(PAGE_WELCOME)
        c.app_language = welcome.app.currentData()
        c.language = welcome.metadata_language
        c.tmdb_key = self.page(PAGE_TMDB).key.text().strip()
        login: PlexLoginPage = self.page(PAGE_PLEX)
        libs: LibrariesPage = self.page(PAGE_LIBS)
        server: ServerPage = self.page(PAGE_SERVER)
        c.set_libs(libs.chosen())
        if libs.plex and not login.skip.isChecked():
            c.plex_token = server.server().access_token
            c.plex_url = server.url
            c.plex_server_name = server.server().name
        else:
            c.plex_token = c.plex_url = c.plex_server_name = ""
        c.save()
        super().accept()
