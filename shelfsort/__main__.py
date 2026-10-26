import sys


def selftest() -> int:
    """Checks that a built ShelfSort has everything it needs (used by the build and CI).

    Exit code 0 = ok. Never touches the user's settings or files.
    """
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from pathlib import Path

    from PySide6.QtWidgets import QApplication

    from . import __version__
    from .parse import parse_release

    checks = []
    p = parse_release(Path("Doctor.Who.2005.S07E06.German.DL.1080p.WEB.x264-GRP.mkv"))
    checks.append(("guessit", p.title == "Doctor Who" and p.season == 7 and p.episodes == [6]))
    from . import i18n
    i18n.set_language("en")
    checks.append(("i18n", i18n.tr("Abbrechen") == "Cancel"))
    i18n.set_language("de")
    assets = Path(__file__).parent / "assets"
    checks.append(("assets", all((assets / n).exists() for n in ("icon.png", "tmdb.svg"))))
    app = QApplication([])
    from PySide6.QtGui import QImageReader
    checks.append(("svg", b"svg" in [bytes(f) for f in QImageReader.supportedImageFormats()]))
    from .details import DetailsPanel
    DetailsPanel()  # builds widgets incl. network manager
    checks.append(("qt", True))
    del app
    lines = [f"ShelfSort {__version__} selftest"] + [f"  {name}: {'ok' if ok else 'FEHLER'}" for name, ok in checks]
    if sys.stdout:  # a windowed exe has no console
        print("\n".join(lines))
    return 0 if all(ok for _, ok in checks) else 1


if "--selftest" in sys.argv:
    sys.exit(selftest())

from .gui import main  # noqa: E402

main()
