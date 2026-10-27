"""Building blocks shared by the setup wizard and the settings dialog.

Each block is a plain widget with a `changed` signal; the wizard wraps them in pages, the settings
dialog in tabs - so both look and behave the same.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QLocale, QObject, QRunnable, Qt, QThreadPool, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QFileDialog, QFormLayout, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton, QRadioButton, QVBoxLayout, QWidget)

from . import i18n, plex_auth
from .config import KINDS, METADATA_LANGUAGES, Config, LibraryConfig
from .i18n import tr
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
            result, error = self.fn(), None
        except Exception as e:
            result, error = None, str(e)
            logging.getLogger("shelfsort").warning("Background job failed: %s", e, exc_info=True)
        try:
            if error is None:
                self.relay.done.emit(result)
            else:
                self.relay.failed.emit(error)
        except RuntimeError:
            pass  # the widget was closed meanwhile (e.g. dialog cancelled) - nobody waits for the result


def run_async(owner: QObject, fn: Callable, ok: Callable, err: Callable | None = None) -> None:
    QThreadPool.globalInstance().start(_Job(fn, _Relay(owner, ok, err)))


def fit_to_screen(w: QWidget, width: int, height: int) -> None:
    """Preferred size, but at most 90 % of the screen - with 150-200 % display scaling a fixed
    1400x820 window would be larger than a full-HD screen."""
    screen = w.screen()
    if screen is not None:
        area = screen.availableGeometry()
        width, height = min(width, int(area.width() * 0.9)), min(height, int(area.height() * 0.9))
    w.resize(width, height)


def label(text: str = "", style: str = "") -> QLabel:
    lab = QLabel(text)
    lab.setWordWrap(True)
    lab.setTextFormat(Qt.RichText)
    lab.setOpenExternalLinks(True)
    if style:
        lab.setStyleSheet(style)
    return lab


def same_language(a: str, b: str) -> bool:
    return (a or "").split("-")[0].lower() == (b or "").split("-")[0].lower()


def _status(lab: QLabel, text: str, style: str) -> None:
    lab.setText(text)
    lab.setStyleSheet(style)


# --- languages ----------------------------------------------------------------------------

class LanguageFields(QWidget):
    """App language + default title language."""
    app_changed = Signal(str)

    def __init__(self, cfg: Config, start_meta: str | None = None):
        super().__init__()
        system = QLocale.system().name().replace("_", "-")  # e.g. "de-DE"
        self.app = QComboBox()
        for code, name in i18n.LANGUAGES:  # names stay in their own language
            self.app.addItem(name, code)
        self.app.setCurrentIndex(max(0, self.app.findData(i18n.language())))
        self.app.currentIndexChanged.connect(lambda _: self.app_changed.emit(self.app.currentData()))

        self.meta = QComboBox()
        for code, name in METADATA_LANGUAGES:
            self.meta.addItem(f"{tr(name)}  ({code})", code)
        self.set_metadata_language(start_meta or (cfg.language if cfg.is_set_up else system))

        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 0)
        form.addRow(tr("Sprache der App"), self.app)
        form.addRow(tr("Sprache der Titel"), self.meta)  # default; each library can override it

    @property
    def app_language(self) -> str:
        return self.app.currentData()

    @property
    def metadata_language(self) -> str:
        return self.meta.currentData()

    def set_metadata_language(self, code: str) -> None:
        idx = self.meta.findData(code)
        if idx < 0:
            idx = next((i for i in range(self.meta.count()) if same_language(self.meta.itemData(i), code)), -1)
        if idx < 0:
            self.meta.addItem(code, code)
            idx = self.meta.count() - 1
        self.meta.setCurrentIndex(idx)


# --- TMDB ---------------------------------------------------------------------------------

class TmdbKeyWidget(QWidget):
    changed = Signal()

    def __init__(self, cfg: Config):
        super().__init__()
        self.key_edit = QLineEdit(cfg.tmdb_key)
        self.key_edit.setPlaceholderText(tr("API-Key (v3) oder Lese-Token (v4)"))
        self.key_edit.setEchoMode(QLineEdit.PasswordEchoOnEdit)
        self.key_edit.textChanged.connect(lambda _: (self.status.setText(""), self.changed.emit()))
        self.status = label()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(label(tr('Der Key ist kostenlos: Konto auf <a href="https://www.themoviedb.org/signup">'
                               'themoviedb.org</a> anlegen → Einstellungen → <a href="https://www.themoviedb.org/'
                               'settings/api">API</a> → Key beantragen (Typ „Developer“, private Nutzung).')))
        lay.addWidget(self.key_edit)
        lay.addWidget(self.status)

    @property
    def key(self) -> str:
        return self.key_edit.text().strip()

    def validate(self) -> bool:
        """Tries the key against TMDB (short request); shows the result."""
        try:
            TMDB(self.key).search_movie("Matrix")
        except Exception as e:
            _status(self.status, tr("Key funktioniert nicht: {error}", error=e), BAD)
            return False
        _status(self.status, tr("✓ Key funktioniert."), OK)
        return True


# --- Plex account -------------------------------------------------------------------------

class PlexLoginWidget(QWidget):
    """Sign in on plex.tv in the browser (PIN flow); shows which account is signed in."""
    token_changed = Signal(str)

    def __init__(self, cfg: Config, allow_logout: bool = False):
        super().__init__()
        self.cfg = cfg
        self.token = cfg.plex_token
        self.pin = None
        self.timer = QTimer(self)
        self.timer.setInterval(2000)
        self.timer.timeout.connect(self._poll)

        self.login = QPushButton(tr("Bei Plex anmelden …"))
        self.login.clicked.connect(self._start)
        self.logout = QPushButton(tr("Abmelden"))
        self.logout.clicked.connect(self._logout)
        self.logout.setVisible(allow_logout and bool(self.token))
        self._allow_logout = allow_logout
        self.status = label()
        buttons = QHBoxLayout()
        buttons.addWidget(self.login)
        buttons.addWidget(self.logout)
        buttons.addStretch()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(label(tr("Die Anmeldung läuft auf plex.tv in deinem Browser – ShelfSort sieht dein Passwort "
                               "nicht, sondern bekommt nur einen Zugangsschlüssel für deinen Server.")))
        lay.addLayout(buttons)
        lay.addWidget(self.status)
        if self.token:
            self._signed_in(tr("Bereits angemeldet. Zum Wechseln des Kontos erneut anmelden."))

    def _signed_in(self, text: str) -> None:
        _status(self.status, text, OK)
        self.login.setText(tr("Erneut anmelden …"))
        self.logout.setVisible(self._allow_logout)
        token, cid = self.token, self.cfg.ensure_client_id()

        def named(name):
            if self.token == token:
                self.status.setText(tr("{text} Konto: <b>{name}</b> – falls das nicht dein Server-Konto ist "
                                       "(z. B. ein Plex-Home-Benutzer), im Browser abmelden und erneut anmelden.",
                                       text=text, name=name))

        run_async(self, lambda: plex_auth.account_name(cid, token), named)

    def _logout(self) -> None:
        self.token = ""
        self.timer.stop()
        self.pin = None
        _status(self.status, tr("Abgemeldet – Scan, Plex-Abgleich und Specials-Check sind aus."), GRAY)
        self.login.setText(tr("Bei Plex anmelden …"))
        self.logout.setVisible(False)
        self.token_changed.emit("")

    def _start(self) -> None:
        cid = self.cfg.ensure_client_id()
        self.login.setEnabled(False)
        _status(self.status, tr("Verbinde mit plex.tv …"), GRAY)

        def started(pin):
            self.pin = pin
            QDesktopServices.openUrl(QUrl(plex_auth.auth_url(cid, pin)))
            self.status.setText(tr("Im Browser anmelden und ShelfSort erlauben – dieses Fenster wartet darauf …"))
            self.timer.start()

        def failed(msg):
            self.login.setEnabled(True)
            _status(self.status, tr("plex.tv nicht erreichbar: {error}", error=msg), BAD)

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
                self._signed_in(tr("Angemeldet."))
                self.token_changed.emit(token)

        run_async(self, lambda: plex_auth.check_pin(cid, pin), checked)


# --- Plex server --------------------------------------------------------------------------

class ServerWidget(QWidget):
    """Servers of the account (first reachable address) or an address entered by hand."""
    changed = Signal()

    def __init__(self, cfg: Config):
        super().__init__()
        self.cfg = cfg
        self.token = ""
        self.servers: list[plex_auth.Server] = []
        self.url: str | None = None
        self.combo = QComboBox()
        self.combo.currentIndexChanged.connect(self._test)
        self.status = label()
        # fallback: server address by hand (e.g. when plex.tv doesn't list the server)
        self.manual = QLineEdit(cfg.plex_url if cfg.plex_url and "localhost" not in cfg.plex_url else "")
        self.manual.setPlaceholderText(tr("z. B. http://192.168.1.5:32400"))
        self.manual_btn = QPushButton(tr("Verbinden"))
        self.manual_btn.clicked.connect(self._manual)
        manual_row = QHBoxLayout()
        manual_row.addWidget(self.manual, 1)
        manual_row.addWidget(self.manual_btn)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.combo)
        lay.addWidget(self.status)
        lay.addSpacing(12)
        lay.addWidget(label(tr("Server nicht in der Liste? Adresse von Hand eingeben:"), GRAY))
        lay.addLayout(manual_row)

    def server(self) -> plex_auth.Server | None:
        i = self.combo.currentIndex()
        return self.servers[i] if 0 <= i < len(self.servers) else None

    def plex(self) -> Plex | None:
        s = self.server()
        return Plex(self.url, s.access_token) if s and self.url else None

    def load(self, token: str) -> None:
        """Look up the account's servers (in the background)."""
        self.token = token
        self.combo.clear()
        self.servers, self.url = [], None
        self.changed.emit()
        if not token:
            _status(self.status, tr("Nicht bei Plex angemeldet."), GRAY)
            return
        cid = self.cfg.ensure_client_id()
        _status(self.status, tr("Suche Server …"), GRAY)

        def lookup():
            devices = plex_auth.resources(cid, token)
            return devices, plex_auth.servers(cid, token, devices), plex_auth.account_name(cid, token)

        def found(result):
            devices, servers, account = result
            if servers:
                self._fill(servers)
                return
            names = ", ".join(sorted({d.get("name", "?") for d in devices})) or tr("keine")
            _status(self.status, tr(
                "Im Konto <b>{account}</b> ist kein Plex Media Server zu sehen "
                "({n} Geräte: {names}).<br>Ist das das Konto, dem der Server gehört? Sonst "
                "zurück und mit dem richtigen Konto anmelden – oder unten die Adresse eingeben.",
                account=account, n=len(devices), names=names), BAD)

        run_async(self, lookup, found, lambda m: _status(self.status, tr("Fehler: {error}", error=m), BAD))

    def _fill(self, servers: list[plex_auth.Server]) -> None:
        self.servers = servers
        self.combo.blockSignals(True)
        self.combo.clear()
        for s in servers:
            self.combo.addItem(s.name + ("" if s.owned else "  " + tr("(geteilt)")))
        idx = next((i for i, s in enumerate(servers) if s.name == self.cfg.plex_server_name), 0)
        self.combo.setCurrentIndex(idx)
        self.combo.blockSignals(False)
        self._test()

    def _manual(self) -> None:
        url, token = self.manual.text().strip(), self.token
        if not url:
            return
        _status(self.status, tr("Verbinde mit {url} …", url=url), GRAY)

        def connected(server):
            if server:
                self._fill([server])
            else:
                _status(self.status, tr("{url} antwortet nicht oder lässt diesen Plex-Zugang nicht zu.", url=url), BAD)

        run_async(self, lambda: plex_auth.manual_server(url, token), connected)

    def _test(self, _=None) -> None:
        s = self.server()
        if not s:
            return
        self.url = None
        self.changed.emit()
        _status(self.status, tr("Teste Verbindung zu {server} …", server=s.name), GRAY)

        def tested(url):
            if self.server() is not s:
                return
            self.url = url
            if url:
                _status(self.status, tr("Erreichbar über {url}", url=url), OK)
            else:
                _status(self.status, tr("Server ist gerade nicht erreichbar."), BAD)
            self.changed.emit()

        run_async(self, lambda: plex_auth.best_connection(s), tested)


# --- libraries ----------------------------------------------------------------------------

class _LibraryRow:
    """One library: managed yes/no, local folder (found automatically), title language, default."""

    def __init__(self, owner: "LibrariesWidget", kind: str, title: str, section: dict | None,
                 local: str, managed: bool, default: bool, language: str, count: int | None = None):
        self.owner, self.kind, self.title, self.section = owner, kind, title, section
        self.count = count or 0
        self.samples: list[str] = []
        self.searched = False
        self.check = QCheckBox(f"{title}" + (f"  ({', '.join(section['locations'])})" if section else ""))
        self.check.setChecked(managed)
        self.check.setEnabled(section is not None)  # without Plex both rows are required
        self.check.toggled.connect(self._toggled)
        if count is None:
            kind_text = tr(KINDS[kind])
        elif kind == "movie":
            kind_text = tr("{n} Filme", n=count)
        else:
            kind_text = tr("{n} Serien", n=count)
        self.kind_label = QLabel(kind_text)
        self.kind_label.setStyleSheet(GRAY)
        # title language of this library (an OV library may want English titles)
        self.lang = QComboBox()
        for code, name in METADATA_LANGUAGES:
            self.lang.addItem(tr(name), code)
        if self.lang.findData(language) < 0:
            self.lang.addItem(language, language)
        self.lang.setCurrentIndex(self.lang.findData(language))
        self.lang.setToolTip(tr("Sprache der Titel für diese Bibliothek"))
        self.lang.currentIndexChanged.connect(lambda _: self._verify())
        self.default = QRadioButton(tr("Standard"))
        self.default.setToolTip(tr("Neue Filme werden hierhin importiert.") if kind == "movie"
                                else tr("Neue Serien werden hierhin importiert."))
        self.default.setChecked(default)
        self.path = QLineEdit(local)
        self.path.setPlaceholderText(tr("Ordner auf diesem Computer"))
        self.browse = QPushButton("…")
        self.browse.setFixedWidth(32)
        self.browse.clicked.connect(self._browse)
        self.status = label("", GRAY)
        self.path.textChanged.connect(lambda _: self._verify())
        owner.groups[kind].addButton(self.default)

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
                self.owner.pick_default(self.kind)
        elif not self.searched:
            self.search()
        else:
            self._verify()
        self.owner.changed.emit()

    def search(self) -> None:
        """Fetch sample files from Plex and find the folder on this computer (in the background)."""
        plex = self.owner.plex
        self.searched = True
        if not self.section or not plex:
            self._verify()
            return
        s, root = self.section, self.server_root()
        current = self.path.text().strip()  # read here: widgets only in the GUI thread
        _status(self.status, tr("Suche den Ordner auf diesem Computer …"), GRAY)

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

        run_async(self.owner, work, done, lambda m: self.status.setText(tr("Fehler: {error}", error=m)))

    def _browse(self) -> None:
        d = QFileDialog.getExistingDirectory(self.owner, tr("Ordner wählen"), self.path.text())
        if d:
            self.path.setText(str(Path(d)))

    def valid(self) -> bool:
        p = self.path.text().strip()
        return bool(p) and Path(p).is_dir()

    def _verify(self) -> None:
        if not self.managed:
            return
        local = self.path.text().strip()
        if not local:
            _status(self.status, tr("Ordner fehlt."), BAD)
        elif not Path(local).is_dir():
            _status(self.status, tr("Ordner nicht gefunden."), BAD)
        elif self.samples:
            g = verify(Path(local), self.server_root(), self.samples)
            if g.ok:
                _status(self.status, tr("✓ Passt: {hits} von {total} Beispieldateien aus Plex gefunden.",
                                        hits=g.hits, total=g.total), OK)
            else:
                _status(self.status, tr("Nur {hits} von {total} Beispieldateien gefunden – ist das wirklich "
                                        "der Ordner von „{folder}“?", hits=g.hits, total=g.total,
                                        folder=self.server_root()), BAD)
        else:
            _status(self.status, tr("Ordner vorhanden."), GRAY)
        self.owner.changed.emit()

    def to_config(self) -> LibraryConfig:
        return LibraryConfig(self.kind, self.title, self.path.text().strip(),
                             self.section["key"] if self.section else "", self.server_root(),
                             self.default.isChecked(), self.lang.currentData())


class LibrariesWidget(QWidget):
    """All libraries: from Plex (check the ones to manage) or, without Plex, two folders."""
    changed = Signal()

    def __init__(self, cfg: Config):
        super().__init__()
        self.cfg = cfg
        self.plex: Plex | None = None
        self.loaded_for: object = None  # what the list was built for (to reload only when needed)
        self.rows: list[_LibraryRow] = []
        self.groups = {"movie": QButtonGroup(self), "show": QButtonGroup(self)}
        self.info = label()
        self.grid = QGridLayout()
        self.grid.setColumnStretch(2, 1)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
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

    def load(self, plex: Plex | None, default_lang: str) -> None:
        """Build the list - from Plex's libraries, or two plain folders without Plex."""
        self._clear()
        self.plex = plex
        self.loaded_for = (plex.url, plex.token) if plex else None
        if not plex:
            self.info.setText(tr("Wo liegen deine Filme und Serien?"))
            for kind in ("movie", "show"):
                lib = self.cfg.default_lib(kind)
                self._add(_LibraryRow(self, kind, KINDS[kind], None, lib.local_root if lib else "", True, True,
                                      (lib.language if lib and lib.language else default_lang)))
            self.changed.emit()
            return
        self.info.setText(tr("ShelfSort sucht die Ordner selbst und prüft sie an echten Dateien aus Plex (der "
                             "Server kann einen anderen Pfad sehen, z. B. <i>/data/movies</i>, als dieser Computer, "
                             "z. B. <i>X:\\Medien\\movies</i>). Pro Typ ist eine Bibliothek <b>Standard</b> für neue "
                             "Importe; neue Folgen vorhandener Serien landen immer bei ihrer Serie."))
        known = {lib.section_key: lib for lib in self.cfg.libs if lib.section_key}
        by_folder = {Path(lib.local_root).name.lower(): lib for lib in self.cfg.libs}

        def fetch():
            sections = [s for s in plex.sections() if s["type"] in KINDS]
            return [(s, plex.section_size(s)) for s in sections]

        def fetched(result):
            if self.plex is not plex:
                return  # reloaded meanwhile
            for sec, count in result:
                kind = "movie" if sec["type"] == "movie" else "show"
                old = known.get(sec["key"]) or next(
                    (by_folder[Plex._basename(l)] for l in sec["locations"] if Plex._basename(l) in by_folder), None)
                personal = sec.get("agent", "").endswith(".none")  # e.g. "Andere Videos"
                managed = old is not None if self.cfg.libs else not personal
                plex_lang = sec.get("language", "")
                # saved choice, else the language the library uses in Plex, else the default title language
                language = (old.language if old and old.language
                            else plex_lang if plex_lang not in ("", "xn") else default_lang)
                self._add(_LibraryRow(self, kind, sec["title"], sec, old.local_root if old else "", managed,
                                      bool(old and old.default), language, count))
            for kind in KINDS:
                self.pick_default(kind)
            self.changed.emit()

        run_async(self, fetch, fetched, lambda m: self.info.setText(tr("Fehler: {error}", error=m)))

    def chosen(self) -> list[LibraryConfig]:
        return [r.to_config() for r in self.rows if r.managed]

    def is_complete(self) -> bool:
        managed = [r for r in self.rows if r.managed]
        return {r.kind for r in managed} == {"movie", "show"} and all(r.valid() for r in managed)
