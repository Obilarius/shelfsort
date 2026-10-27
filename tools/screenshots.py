"""Screenshots for the README, made with made-up demo files instead of a real library.

    python tools/screenshots.py

Builds a small download folder and library of empty files, maps it to a spare drive letter
(Windows `subst`, so no personal paths show up), runs the real import scan and library check
against TMDB with the TMDB key from your settings (Plex stays off) and saves
docs/screenshots/import.png and check.png. Nothing in your settings or library is touched.
"""
from __future__ import annotations

import copy
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "screenshots"
sys.path.insert(0, str(ROOT))

# release names as they come out of downloads; folder -> files
DOWNLOADS = {
    "Blade.Runner.2049.2017.1080p.BluRay.x264-DEMO": ["blade.runner.2049.2017.1080p.bluray.x264-demo.mkv",
                                                      "blade.runner.2049.2017.1080p.bluray.x264-demo.en.srt"],
    "Arrival.2016.2160p.UHD.BluRay.x265-DEMO": ["Arrival.2016.2160p.UHD.BluRay.x265-DEMO.mkv"],
    "The.Martian.2015.EXTENDED.1080p.BluRay.x264-DEMO": ["the.martian.2015.extended.1080p.bluray.x264-demo.mkv"],
    "Inception.2010.1080p.BluRay.x264-DEMO": ["Inception.2010.1080p.BluRay.x264-DEMO.mkv"],
    "Severance.S02.1080p.WEB.h264-DEMO": [f"Severance.S02E0{n}.1080p.WEB.h264-DEMO.mkv" for n in (1, 2, 3)],
    "": ["the.bear.s03e01.720p.web.h264-demo.mkv", "Dune.mkv"],
}
# what is already in the library: correct entries plus a few mistakes for the library check
LIBRARY = [
    "Movies/Inception (2010) {tmdb-27205}/Inception (2010).mkv",
    "Movies/Interstellar.2014.1080p.BluRay.x264-DEMO/Interstellar.2014.1080p.BluRay.x264-DEMO.mkv",
    "Movies/The Prestige (2006)/prestige.mkv",
    "Movies/Old download/sample.txt",
    "TV Shows/Severance {tmdb-95396}/Season 01/Severance - S01E01 - Good News About Hell.mkv",
    "TV Shows/Severance {tmdb-95396}/Season 01/Severance.S01E02.1080p.WEB.h264-DEMO.mkv",
    "TV Shows/Severance {tmdb-95396}/Season 02/Severance - S01E03 - In Perpetuity.mkv",
    "TV Shows/The Bear/Season 1/The.Bear.S01E01.mkv",
]


def free_drive() -> str:
    used = {p[0] for p in os.listdrives()} if hasattr(os, "listdrives") else set()
    for letter in "SRQPOTUVW":
        if letter not in used and not Path(f"{letter}:/").exists():
            return letter + ":"
    sys.exit("Kein freier Laufwerksbuchstabe")


def make_demo(base: Path) -> None:
    for folder, files in DOWNLOADS.items():
        d = base / "Downloads" / folder
        d.mkdir(parents=True, exist_ok=True)
        for f in files:
            (d / f).write_bytes(b"demo")
    for rel in LIBRARY:
        p = base / "Library" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"demo")


def wait(app, window, seconds: float = 0.0) -> None:
    """Until the background task is done, then a little longer for the covers."""
    while window._thread is not None:
        app.processEvents()
        time.sleep(0.02)
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


def main() -> None:
    if sys.platform != "win32":
        sys.exit("Nur unter Windows (subst)")
    from PySide6.QtWidgets import QApplication

    from shelfsort import config
    from shelfsort.config import Config, LibraryConfig

    real = Config.load()
    if not real.tmdb_key:
        sys.exit("Kein TMDB-Key in den Einstellungen")

    tmp = Path(tempfile.mkdtemp(prefix="shelfsort-demo-"))
    drive = free_drive()
    make_demo(tmp)
    subprocess.run(["subst", drive, str(tmp)], check=True)
    try:
        base = Path(drive + "\\")
        demo = copy.deepcopy(real)
        demo.app_language, demo.language = "en", "en-US"
        demo.plex_token, demo.plex_server_name = "", ""
        demo.min_video_mb = 0
        demo.last_import_dir = str(base / "Downloads")
        demo.set_libs([
            LibraryConfig("movie", "Movies", str(base / "Library" / "Movies"), default=True),
            LibraryConfig("show", "TV Shows", str(base / "Library" / "TV Shows"), default=True),
        ])
        Config.load = classmethod(lambda cls: copy.deepcopy(demo))
        Config.save = lambda self: None

        from shelfsort.gui import MainWindow, apply_language
        app = QApplication(sys.argv)
        apply_language("en")
        w = MainWindow(first_start_wizard=False)
        w.resize(1500, 860)
        w.show()
        OUT.mkdir(parents=True, exist_ok=True)

        w.log_view.clear()
        w.scan_import()
        wait(app, w)
        table = w.import_table
        row = next(i for i, it in enumerate(table.items) if "blade" in it.source.name.lower())
        table.selectRow(row)
        table.details.show_item(table.items[row])
        wait(app, w, 4)
        w.grab().save(str(OUT / "import.png"))

        w.tabs.setCurrentIndex(1)
        w.opt_empty.setChecked(True)
        w.opt_plex.setChecked(False)
        w.log_view.clear()
        w.scan_audit()
        wait(app, w)
        table = w.audit_table
        row = next((i for i, it in enumerate(table.items) if "interstellar" in it.source.name.lower()), 0)
        table.selectRow(row)
        table.details.show_item(table.items[row])
        wait(app, w, 4)
        w.grab().save(str(OUT / "check.png"))
        w.close()
        print(f"Gespeichert: {OUT / 'import.png'}, {OUT / 'check.png'}")
    finally:
        subprocess.run(["subst", drive, "/d"])
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
