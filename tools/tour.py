"""Screenshots of every view for design work: main tabs, specials, match dialog, history, settings, wizard.

    python tools/tour.py <out dir> [light|dark]

Uses the demo library of tools/screenshots.py (Windows: spare drive letter, real TMDB with the key from
your settings, Plex off). Nothing in your settings or library is touched.
"""
from __future__ import annotations

import copy
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import screenshots as demo  # noqa: E402


def main() -> None:
    out = Path(sys.argv[1])
    mode = sys.argv[2] if len(sys.argv) > 2 else "dark"
    out.mkdir(parents=True, exist_ok=True)
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from shelfsort import history
    from shelfsort.config import Config, LibraryConfig
    from shelfsort.executor import TransferInfo

    real = Config.load()
    tmp = Path(tempfile.mkdtemp(prefix="shelfsort-tour-"))
    drive = demo.free_drive()
    demo.make_demo(tmp)
    subprocess.run(["subst", drive, str(tmp)], check=True)
    try:
        base = Path(drive + "\\")
        cfg = copy.deepcopy(real)
        cfg.app_language, cfg.language, cfg.plex_token, cfg.min_video_mb = "de", "de-DE", "", 0
        cfg.last_import_dir = str(base / "Downloads")
        cfg.set_libs([LibraryConfig("movie", "Filme", str(base / "Library" / "Movies"), default=True),
                      LibraryConfig("show", "Serien", str(base / "Library" / "TV Shows"), default=True)])
        Config.load = classmethod(lambda cls: copy.deepcopy(cfg))
        Config.save = lambda self: None
        history.HISTORY_DIR = tmp / "history"
        real_runs = history.runs
        history.runs = lambda directory=None: real_runs(directory or tmp / "history")

        from shelfsort.dialogs import SettingsDialog
        from shelfsort.gui import MainWindow, apply_language
        from shelfsort.history_dialog import HistoryDialog
        from shelfsort.match_dialog import MatchDialog
        from shelfsort.plex_sync import OrderingOption, PlexShow, SpecialsReport
        from shelfsort.tmdb import TMDB
        from shelfsort.wizard import SetupWizard

        app = QApplication(sys.argv)
        app.styleHints().setColorScheme(Qt.ColorScheme.Light if mode == "light" else Qt.ColorScheme.Dark)
        apply_language("de")
        w = MainWindow(first_start_wizard=False)
        w.resize(1500, 860)
        w.show()

        def shot(widget, name, settle=0.5):
            demo.wait(app, w, settle)
            widget.grab().save(str(out / f"{name}.png"))

        w.scan_import()
        demo.wait(app, w)
        t = w.import_table
        row = next(i for i, it in enumerate(t.items) if "blade" in it.source.name.lower())
        t.selectRow(row)
        t.details.show_item(t.items[row])
        shot(w, "01_import", 4)

        w.panel.start(6)
        w.panel.update_transfer(TransferInfo(2, 6, "Arrival (2016).mkv", 3 * 2**30, 8 * 2**30, 11 * 2**30, 40 * 2**30))
        shot(w, "02_transfer")
        w.panel.hide()

        w.tabs.setCurrentIndex(1)
        w.opt_empty.setChecked(True)
        w.scan_audit()
        demo.wait(app, w)
        t = w.audit_table
        if t.items:
            t.selectRow(0)
            t.details.show_item(t.items[0])
        shot(w, "03_check", 4)

        show = PlexShow("Doctor Who", "1", "plex://show/1", "tvdbAiring", base / "Library" / "TV Shows" / "Doctor Who",
                        options=[("tvdbAiring", "TheTVDB (Aired)"), ("tvdbDvd", "TheTVDB (DVD)")])
        reports = [SpecialsReport(show, [f"S00E{i:02d} Special {i}" for i in range(1, 9)], [
            OrderingOption("tvdbDvd", "TheTVDB (DVD)", in_flow=[f"S00E{i:02d} → S0{i}E14" for i in range(1, 6)],
                           still_special=["S00E06", "S00E07"], missing=["S00E08"])])]
        w.tabs.setCurrentIndex(2)
        w.specials.set_reports(reports)
        w.specials.table.selectRow(0)
        shot(w, "04_specials")

        tmdb = TMDB(cfg.tmdb_key, "de-DE")
        dlg = MatchDialog(tmdb, "movie", "Dune", None, parent=w)
        dlg.show()
        shot(dlg, "05_match", 4)
        dlg.reject()

        j = history.Journal(history.HISTORY_DIR, "Import: Downloads")
        j.moved(base / "Downloads" / "a.mkv", base / "Library" / "Movies" / "Arrival (2016)" / "Arrival (2016).mkv", 4)
        j.trashed(base / "Downloads" / "Arrival.2016")
        j.close()
        h = HistoryDialog(w)
        h.show()
        shot(h, "06_history")
        h.reject()

        s = SettingsDialog(w.cfg, w)
        s.show()
        shot(s, "07_settings_general")
        s.tabs.setCurrentIndex(s.TAB_NAMING)
        shot(s, "08_settings_names")
        s.reject()

        wiz = SetupWizard(w.cfg, w)
        wiz.show()
        shot(wiz, "09_wizard_welcome")
        wiz.next()
        shot(wiz, "10_wizard_tmdb")
        wiz.reject()
        w.close()
        print("saved to", out)
    finally:
        subprocess.run(["subst", drive, "/d"])
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
