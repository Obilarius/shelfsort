"""First-start setup: languages, TMDB key, Plex sign-in, server, libraries.

The pages wrap the building blocks from setup_widgets, which the settings dialog uses as well.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QCheckBox, QPushButton, QVBoxLayout, QWizard, QWizardPage

from .config import KINDS, Config, language_name
from .i18n import N_, tr
from .setup_widgets import (BAD, GRAY, LanguageFields, LibrariesWidget, PlexLoginWidget, ServerWidget, TmdbKeyWidget,
                            fit_to_screen, label, same_language)

PAGE_WELCOME, PAGE_TMDB, PAGE_PLEX, PAGE_SERVER, PAGE_LIBS, PAGE_DONE = range(6)


class WelcomePage(QWizardPage):
    def __init__(self, cfg: Config, start_meta: str | None = None):
        super().__init__()
        self.setTitle(tr("Willkommen bei ShelfSort"))
        self.setSubTitle(tr("Ein paar Schritte, dann kann es losgehen."))
        self.languages = LanguageFields(cfg, start_meta)
        # switch the UI right away: the rest of the wizard should already be in the new language
        self.languages.app_changed.connect(self._app_language_changed)
        lay = QVBoxLayout(self)
        lay.addWidget(label(tr("ShelfSort benennt Filme und Serien so, wie Plex sie erwartet, verschiebt sie in "
                               "deine Bibliothek und hält Folgennummern passend zur Reihenfolge in Plex.")))
        lay.addSpacing(8)
        lay.addWidget(self.languages)
        lay.addWidget(label(tr("Die <b>Sprache der Titel</b> bestimmt Film-, Serien- und Folgentitel in den "
                               "Dateinamen. Bibliotheken aus Plex bekommen automatisch ihre Plex-Sprache, und jede "
                               "Bibliothek lässt sich einzeln umstellen (z. B. Englisch für eine OV-Bibliothek). "
                               "Diese Einstellung gilt für alles andere."), GRAY))
        lay.addStretch()

    def _app_language_changed(self, lang: str) -> None:
        wiz = self.wizard()
        wiz.language_switch = (lang, self.languages.metadata_language)
        wiz.done(SetupWizard.LANGUAGE_CHANGED)  # the main window reopens the wizard in the new language


class TmdbPage(QWizardPage):
    def __init__(self, cfg: Config):
        super().__init__()
        self.setTitle(tr("TMDB-Zugang"))
        self.setSubTitle(tr("Titel, Jahre, Cover und Beschreibungen kommen von The Movie Database (TMDB)."))
        self.tmdb = TmdbKeyWidget(cfg)
        self.tmdb.changed.connect(self.completeChanged)
        lay = QVBoxLayout(self)
        lay.addWidget(self.tmdb)
        lay.addStretch()
        lay.addWidget(label("This product uses TMDB and the TMDB APIs but is not endorsed, certified, or "
                            "otherwise approved by TMDB.", GRAY))

    def isComplete(self) -> bool:
        return bool(self.tmdb.key)

    def validatePage(self) -> bool:
        return self.tmdb.validate()


class PlexLoginPage(QWizardPage):
    def __init__(self, cfg: Config):
        super().__init__()
        self.setTitle(tr("Bei Plex anmelden"))
        self.setSubTitle(tr("Für den Scan nach dem Verschieben, den Plex-Abgleich und den Specials-Check."))
        self.login = PlexLoginWidget(cfg)
        self.login.token_changed.connect(lambda _: self.completeChanged.emit())
        self.skip = QCheckBox(tr("Ohne Plex weiter (nur Umbenennen und Verschieben)"))
        self.skip.toggled.connect(lambda _: self.completeChanged.emit())
        lay = QVBoxLayout(self)
        lay.addWidget(self.login)
        lay.addStretch()
        lay.addWidget(self.skip)

    @property
    def token(self) -> str:
        return self.login.token

    def isComplete(self) -> bool:
        return bool(self.token) or self.skip.isChecked()

    def nextId(self) -> int:
        return PAGE_LIBS if self.skip.isChecked() else PAGE_SERVER


class ServerPage(QWizardPage):
    def __init__(self, cfg: Config):
        super().__init__()
        self.setTitle(tr("Plex-Server"))
        self.setSubTitle(tr("Welcher Server enthält deine Bibliotheken?"))
        self.servers = ServerWidget(cfg)
        self.servers.changed.connect(self.completeChanged)
        lay = QVBoxLayout(self)
        lay.addWidget(self.servers)
        lay.addStretch()

    def initializePage(self) -> None:
        self.servers.load(self.wizard().page(PAGE_PLEX).token)

    def isComplete(self) -> bool:
        return bool(self.servers.url)


class LibrariesPage(QWizardPage):
    def __init__(self, cfg: Config):
        super().__init__()
        self.setTitle(tr("Bibliotheken"))
        self.libraries = LibrariesWidget(cfg)
        self.libraries.changed.connect(self.completeChanged)
        lay = QVBoxLayout(self)
        lay.addWidget(self.libraries)

    def initializePage(self) -> None:
        wiz = self.wizard()
        use_plex = not wiz.page(PAGE_PLEX).skip.isChecked()
        plex = wiz.page(PAGE_SERVER).servers.plex() if use_plex else None
        self.setSubTitle(tr("Welche Plex-Bibliotheken soll ShelfSort verwalten – und wo liegen ihre Ordner?") if plex
                         else tr("Wo liegen deine Filme und Serien?"))
        self.libraries.load(plex, wiz.page(PAGE_WELCOME).languages.metadata_language)

    def isComplete(self) -> bool:
        return self.libraries.is_complete()


class DonePage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle(tr("Alles bereit"))  # not "Fertig": that is the button, English needs two words
        self.setSubTitle(tr("So ist ShelfSort eingerichtet. Mit „Fertig“ wird gespeichert."))
        self.summary = label()
        self.lang_hint = label("", BAD)
        self.lang_fix = QPushButton()
        self.lang_fix.clicked.connect(self._adopt_language)
        self._mismatched = []
        lay = QVBoxLayout(self)
        lay.addWidget(self.summary)
        lay.addWidget(self.lang_hint)
        lay.addWidget(self.lang_fix, 0, Qt.AlignLeft)
        lay.addStretch()
        lay.addWidget(label(tr("Alles lässt sich später unter <i>Einstellungen</i> ändern."), GRAY))

    @staticmethod
    def _section(title: str, body: str) -> str:
        return (f'<p style="margin-top:12px; margin-bottom:2px"><span style="color:gray">{title.upper()}</span></p>'
                f"{body}")

    def initializePage(self) -> None:
        wiz = self.wizard()
        welcome: WelcomePage = wiz.page(PAGE_WELCOME)
        libs = wiz.page(PAGE_LIBS).libraries
        server = wiz.page(PAGE_SERVER).servers
        html = []

        if libs.plex and server.server():
            html.append(self._section("Plex", f"<b>{server.server().name}</b> &nbsp;·&nbsp; {server.url}"))
        else:
            html.append(self._section("Plex", tr("nicht verbunden – Scan, Plex-Abgleich und Specials-Check sind aus")))
        html.append(self._section(tr("Sprache"), tr("App: <b>{language}</b>",
                                                    language=welcome.languages.app.currentText())))

        managed = [r for r in libs.rows if r.managed]
        # titles should be in the language the library uses in Plex, else file names and Plex disagree
        self._mismatched = [r for r in managed if r.plex_language
                            and not same_language(r.plex_language, r.lang.currentData())]
        rows = []
        for row in managed:
            lib = row.to_config()
            warn = " ⚠" if row in self._mismatched else ""
            plex_lang = language_name(row.plex_language) if row.plex_language else "–"
            rows.append(f"<tr><td><b>{lib.title}</b></td><td>{tr(KINDS[lib.kind])}</td>"
                        f"<td>{tr('✓ Standard') if lib.default else ''}</td><td>{lib.local_root}</td>"
                        f"<td>{language_name(lib.language)}{warn}</td><td>{plex_lang}</td></tr>")
        table = ('<table cellspacing="0" cellpadding="4" width="100%">'
                 '<tr style="color:gray">'
                 + "".join(f"<td>{tr(h)}</td>" for h in (N_("Bibliothek"), N_("Typ"), N_("Neue Importe"),
                                                          N_("Ordner"), N_("Titel"), N_("in Plex")))
                 + "</tr>" + "".join(rows) + "</table>")
        html.append(self._section(tr("Bibliotheken"), table))
        self.summary.setText("".join(html))

        self.lang_hint.setVisible(bool(self._mismatched))
        self.lang_fix.setVisible(bool(self._mismatched))
        if self._mismatched:
            names = ", ".join(tr("<b>{title}</b> ({language} in Plex)", title=r.title,
                                 language=language_name(r.plex_language)) for r in self._mismatched)
            self.lang_hint.setText(tr("Titelsprache weicht von Plex ab: {names}. Dann heißen Dateien anders, als "
                                      "Plex sie anzeigt – gewollt z. B. nur, wenn Plex selbst falsch eingestellt ist.",
                                      names=names))
            self.lang_fix.setText(tr("Titelsprache an Plex angleichen"))

    def _adopt_language(self) -> None:
        for row in self._mismatched:
            row.lang.setCurrentIndex(max(0, row.lang.findData(row.plex_language)))
        self.initializePage()


class SetupWizard(QWizard):
    LANGUAGE_CHANGED = 2  # exec() result: app language picked on page 1, reopen in that language

    def __init__(self, cfg: Config, parent=None, start_meta: str | None = None):
        super().__init__(parent)
        self.cfg = cfg
        self.language_switch: tuple[str, str] | None = None  # (app language, title language)
        self.setWindowTitle(tr("ShelfSort einrichten"))
        self.setWizardStyle(QWizard.ModernStyle)
        logo = QPixmap(str(Path(__file__).parent / "assets" / "icon.png"))
        if not logo.isNull():
            self.setPixmap(QWizard.LogoPixmap, logo.scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        fit_to_screen(self, 860, 580)
        self.setPage(PAGE_WELCOME, WelcomePage(cfg, start_meta))
        self.setPage(PAGE_TMDB, TmdbPage(cfg))
        self.setPage(PAGE_PLEX, PlexLoginPage(cfg))
        self.setPage(PAGE_SERVER, ServerPage(cfg))
        self.setPage(PAGE_LIBS, LibrariesPage(cfg))
        self.setPage(PAGE_DONE, DonePage())
        self.setButtonText(QWizard.NextButton, tr("Weiter >"))
        self.setButtonText(QWizard.BackButton, tr("< Zurück"))
        self.setButtonText(QWizard.FinishButton, tr("Fertig"))
        self.setButtonText(QWizard.CancelButton, tr("Abbrechen"))

    def accept(self) -> None:
        c = self.cfg
        languages = self.page(PAGE_WELCOME).languages
        c.app_language = languages.app_language
        c.language = languages.metadata_language
        c.tmdb_key = self.page(PAGE_TMDB).tmdb.key
        libs = self.page(PAGE_LIBS).libraries
        server = self.page(PAGE_SERVER).servers
        c.set_libs(libs.chosen())
        if libs.plex and not self.page(PAGE_PLEX).skip.isChecked():
            c.plex_token = server.server().access_token
            c.plex_url = server.url
            c.plex_server_name = server.server().name
        else:
            c.plex_token = c.plex_url = c.plex_server_name = ""
        c.save()
        super().accept()
