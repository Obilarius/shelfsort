"""Settings and about dialogs."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QLayout, QLineEdit, QMessageBox,
                               QPushButton, QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from . import i18n, naming
from .config import Config
from .i18n import N_, tr
from .naming_widget import NamingWidget
from .setup_widgets import (GRAY, LanguageFields, LibrariesWidget, PlexLoginWidget, ServerWidget, TmdbKeyWidget,
                            fit_to_screen, label)

ASSETS = Path(__file__).parent / "assets"


def _tab(*widgets, stretch: bool = True) -> QWidget:
    w = QWidget()
    lay = QVBoxLayout(w)
    for x in widgets:
        if isinstance(x, QLayout):
            lay.addLayout(x)
        else:
            lay.addWidget(x)
    if stretch:
        lay.addStretch()
    return w


class SettingsDialog(QDialog):
    """Everything can be changed here directly; the setup wizard uses the same building blocks."""

    TAB_GENERAL, TAB_NAMING, TAB_PLEX, TAB_LIBRARIES, TAB_TMDB = range(5)

    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Einstellungen"))
        fit_to_screen(self, 900, 600)
        self.cfg = cfg
        self.start_wizard = False  # set when the user asks for the setup wizard instead
        self.language_changed = False

        # general
        self.languages = LanguageFields(cfg)
        self.min_mb = QSpinBox()
        self.min_mb.setRange(0, 10000)
        self.min_mb.setSuffix(" MB")
        self.min_mb.setValue(cfg.min_video_mb)
        size_form = QFormLayout()
        size_form.addRow(tr("Videos ignorieren unter"), self.min_mb)
        wizard_btn = QPushButton(tr("Einrichtungsassistent starten"))
        wizard_btn.clicked.connect(self._open_wizard)
        general = _tab(self.languages,
                       label(tr("Die Sprache der Titel gilt für Bibliotheken ohne eigene Sprache; jede Bibliothek "
                                "lässt sich unter <i>Bibliotheken</i> einzeln umstellen."), GRAY),
                       size_form,
                       label(tr("Videos unter dieser Größe (z. B. Samples) übersieht der Import."), GRAY))
        self.check_updates = QCheckBox(tr("Beim Start nach neuen Versionen suchen"))
        self.check_updates.setChecked(cfg.check_updates)
        general.layout().addWidget(self.check_updates)
        general.layout().addWidget(label(tr("Einmal am Tag eine kurze Anfrage an GitHub; heruntergeladen wird nichts. "
                                            "Eine neue Version erscheint unten rechts im Fenster."), GRAY))
        general.layout().addWidget(label(tr("Alles noch einmal Schritt für Schritt einrichten:"), GRAY))
        general.layout().addWidget(wizard_btn, 0, Qt.AlignLeft)

        # Plex
        self.login = PlexLoginWidget(cfg, allow_logout=True)
        self.servers = ServerWidget(cfg)
        self.login.token_changed.connect(self.servers.load)
        self.servers.changed.connect(self._server_changed)
        self.manual = QGroupBox(tr("Erweitert: Server-Adresse und Token von Hand"))
        self.manual.setCheckable(True)
        self.manual.setChecked(False)
        self.manual_url = QLineEdit(cfg.plex_url)
        self.manual_token = QLineEdit(cfg.plex_token)
        self.manual_token.setEchoMode(QLineEdit.PasswordEchoOnEdit)
        mform = QFormLayout(self.manual)
        mform.addRow(tr("Plex-URL"), self.manual_url)
        mform.addRow(tr("Plex-Token"), self.manual_token)
        plex = _tab(self.login, label(tr("Server"), "font-weight: bold; margin-top: 10px"), self.servers,
                    self.manual)

        # libraries (loaded when the tab is opened - needs the server)
        self.libraries = LibrariesWidget(cfg)
        self.libs_touched = False
        libraries = _tab(self.libraries, stretch=False)

        # TMDB
        self.tmdb = TmdbKeyWidget(cfg)
        test = QPushButton(tr("Key prüfen"))
        test.clicked.connect(self.tmdb.validate)
        logo = QUrl.fromLocalFile(str(ASSETS / "tmdb.svg")).toString()
        tmdb = _tab(self.tmdb)
        tmdb.layout().insertWidget(1, test, 0, Qt.AlignLeft)
        tmdb.layout().addWidget(label(f'<img src="{logo}" width="90"><br>This product uses TMDB and the TMDB APIs '
                                      f'but is not endorsed, certified, or otherwise approved by TMDB.', GRAY))

        self.tabs = QTabWidget()
        self.naming = NamingWidget(naming.scheme_from_config(cfg))
        names = _tab(self.naming)
        for widget, title in ((general, N_("Allgemein")), (names, N_("Namen")), (plex, "Plex"),
                              (libraries, N_("Bibliotheken")), (tmdb, "TMDB")):
            self.tabs.addTab(widget, tr(title))
        self.tabs.currentChanged.connect(self._tab_changed)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText(tr("Speichern"))
        buttons.button(QDialogButtonBox.Cancel).setText(tr("Abbrechen"))
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(self.tabs, 1)
        lay.addWidget(buttons)

        if self.login.token:
            self.servers.load(self.login.token)
        else:
            self.servers.load("")

    # --- libraries follow the chosen server ---

    def _wanted_plex(self):
        if self.manual.isChecked() and self.manual_url.text().strip() and self.manual_token.text().strip():
            from .plex import Plex
            return Plex(self.manual_url.text().strip(), self.manual_token.text().strip())
        return self.servers.plex()

    def _load_libraries(self) -> None:
        plex = self._wanted_plex()
        if self.login.token and not plex and not self.manual.isChecked():
            self.libraries.info.setText(tr("Warte auf den Plex-Server …"))
            return  # _server_changed loads once the server answers
        key = (plex.url, plex.token) if plex else None
        if self.libs_touched and key == self.libraries.loaded_for:
            return
        self.libs_touched = True
        self.libraries.load(plex, self.languages.metadata_language)

    def _tab_changed(self, index: int) -> None:
        if index == self.TAB_LIBRARIES:
            self._load_libraries()

    def _server_changed(self) -> None:
        if self.tabs.currentIndex() == self.TAB_LIBRARIES and self.servers.url:
            self._load_libraries()

    # --- actions ---

    def _open_wizard(self) -> None:
        self.start_wizard = True
        self.reject()  # nothing is saved; the main window opens the wizard

    def _save(self) -> None:
        if self.libs_touched and not self.libraries.is_complete():
            self.tabs.setCurrentIndex(self.TAB_LIBRARIES)
            QMessageBox.warning(self, tr("Einstellungen"),
                                tr("Bitte mindestens eine Film- und eine Serien-Bibliothek mit gültigem Ordner wählen."))
            return
        c = self.cfg
        self.language_changed = self.languages.app_language != i18n.language()
        c.app_language = self.languages.app_language
        c.language = self.languages.metadata_language
        c.min_video_mb = self.min_mb.value()
        c.check_updates = self.check_updates.isChecked()
        s = self.naming.scheme()
        c.naming_ids, c.naming_show_year, c.naming_season = s.ids, s.show_year, s.season
        c.naming_episode_titles, c.naming_nfo = s.episode_titles, s.nfo
        naming.set_scheme(s)
        c.tmdb_key = self.tmdb.key
        if self.manual.isChecked():
            c.plex_url = self.manual_url.text().strip()
            c.plex_token = self.manual_token.text().strip()
        elif not self.login.token:
            c.plex_token = c.plex_server_name = ""
        elif self.servers.server() and self.servers.url:
            s = self.servers.server()
            c.plex_token, c.plex_url, c.plex_server_name = s.access_token, self.servers.url, s.name
        else:
            c.plex_token = self.login.token  # server not reachable right now: keep the known address
        if self.libs_touched:
            c.set_libs(self.libraries.chosen())
        c.save()
        self.accept()


ABOUT_HTML = N_("""
<h2>ShelfSort {version}</h2>
<p>Benennt Filme und Serien so, wie Plex sie erwartet, verschiebt sie in die Bibliothek und
prüft Folgennummern gegen die in Plex eingestellte Reihenfolge.</p>
<p>Freie Software unter der MIT-Lizenz. Verwendete Bibliotheken und ihre Lizenzen:
siehe <i>THIRD_PARTY_LICENSES.md</i>.</p>
<p><a href="https://github.com/Obilarius/shelfsort">Projektseite auf GitHub</a> – Fehler melden, Wünsche, neue Versionen<br>
Kostenlos, ohne Werbung. Gefällt dir ShelfSort? <a href="https://ko-fi.com/obilarius">Spendier mir einen Kaffee</a> ☕</p>
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
