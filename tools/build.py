"""Builds ShelfSort with PyInstaller (one folder, not one file: starts faster, fewer antivirus false
positives, and the LGPL libraries stay replaceable files) and zips it.

    python tools/build.py

Result: dist/ShelfSort/ and dist/ShelfSort-<version>-<platform>.zip
Works on Windows, Linux and macOS - each platform builds its own version.
"""
from __future__ import annotations

import importlib.metadata as md
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"
APP = DIST / "ShelfSort"
sys.path.insert(0, str(ROOT))
from shelfsort import __version__  # noqa: E402

# runtime dependencies whose license texts ship with the program
PACKAGES = ["PySide6", "PySide6_Essentials", "shiboken6", "guessit", "rebulk", "babelfish", "python-dateutil",
            "six", "requests", "urllib3", "idna", "charset-normalizer", "certifi", "Send2Trash"]


def platform_tag() -> str:
    system = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
    machine = platform.machine().lower().replace("amd64", "x64").replace("x86_64", "x64")
    return f"{system}-{machine}"


def windows_version_file() -> Path:
    nums = (tuple(int(x) for x in re.findall(r"\d+", __version__)) + (0, 0, 0, 0))[:4]
    text = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={nums}, prodvers={nums}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('040704b0', [
      StringStruct('CompanyName', 'ShelfSort'),
      StringStruct('FileDescription', 'ShelfSort'),
      StringStruct('FileVersion', '{__version__}'),
      StringStruct('InternalName', 'ShelfSort'),
      StringStruct('LegalCopyright', 'MIT License'),
      StringStruct('OriginalFilename', 'ShelfSort.exe'),
      StringStruct('ProductName', 'ShelfSort'),
      StringStruct('ProductVersion', '{__version__}')])]),
    VarFileInfo([VarStruct('Translation', [0x0407, 1200])])]
)
"""
    path = BUILD / "version_info.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def run_pyinstaller() -> None:
    entry = BUILD / "shelfsort_main.py"
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text("import shelfsort.__main__  # noqa: F401  (starts the app)\n", encoding="utf-8")
    sep = os.pathsep
    args = [
        sys.executable, "-m", "PyInstaller", str(entry),
        "--name", "ShelfSort", "--windowed", "--onedir", "--noconfirm", "--clean",
        "--distpath", str(DIST), "--workpath", str(BUILD / "pyinstaller"), "--specpath", str(BUILD),
        "--paths", str(ROOT),
        "--add-data", f"{ROOT / 'shelfsort' / 'assets'}{sep}shelfsort/assets",
        # guessit/babelfish read data files and load plugins dynamically
        "--collect-data", "guessit", "--collect-data", "babelfish",
        "--collect-submodules", "guessit", "--collect-submodules", "babelfish", "--collect-submodules", "rebulk",
        "--collect-submodules", "shelfsort",
    ]
    if sys.platform == "win32":
        args += ["--icon", str(ROOT / "shelfsort" / "assets" / "icon.ico"), "--version-file", str(windows_version_file())]
    elif sys.platform == "darwin":
        args += ["--icon", str(ROOT / "shelfsort" / "assets" / "icon.png")]
    subprocess.run(args, check=True, cwd=ROOT)


QT_NOTICE = """PySide6 / shiboken6 (Qt for Python) and the Qt libraries in this folder
are used under the GNU Lesser General Public License v3 (LGPL-3.0-only).
See LGPL-3.0.txt and GPL-3.0.txt in this folder.

They are included unmodified as separate files and can be replaced with other
compatible versions. Source code:
  Qt for Python: https://code.qt.io/cgit/pyside/pyside-setup.git
  Qt:            https://download.qt.io/official_releases/qt/
"""

# Qt parts a widgets app does not use (software OpenGL, Qt Quick/QML, PDF) - ~30 MB
PRUNE = ["opengl32sw.dll", "Qt6Pdf.*", "Qt6Qml*", "Qt6Quick*", "plugins/imageformats/qpdf.*", "qml"]


def prune_qt() -> None:
    qt = next((p for p in APP.rglob("PySide6") if p.is_dir()), None)
    if not qt:
        return
    for pattern in PRUNE:
        for p in qt.glob(pattern):
            shutil.rmtree(p) if p.is_dir() else p.unlink()


def copy_licenses() -> None:
    for name in ("LICENSE", "THIRD_PARTY_LICENSES.md", "README.md"):
        shutil.copy2(ROOT / name, APP / name)
    target = APP / "licenses"
    target.mkdir(exist_ok=True)
    for pkg in PACKAGES:
        try:
            dist = md.distribution(pkg)
        except md.PackageNotFoundError:
            print(f"  (nicht installiert: {pkg})")
            continue
        files = [f for f in dist.files or []
                 if re.search(r"(LICEN[CS]E|COPYING|NOTICE)", f.name, re.IGNORECASE) and ".dist-info" in str(f)
                 and "Commercial" not in f.name]  # the Qt wheels name a commercial licence we don't use
        for f in files:
            src = Path(dist.locate_file(f))
            if src.is_file():
                shutil.copy2(src, target / f"{dist.metadata['Name']}-{src.name}")
    # LGPL libraries (PySide6/Qt, guessit): licence texts + where to get the source
    lgpl = Path(md.distribution("guessit").locate_file(
        next(f for f in md.distribution("guessit").files if f.name == "LICENSE")))
    shutil.copy2(lgpl, target / "LGPL-3.0.txt")
    (target / "PySide6-Qt-NOTICE.txt").write_text(QT_NOTICE, encoding="utf-8")
    gpl = ROOT / "licenses" / "GPL-3.0.txt"
    if gpl.exists():
        shutil.copy2(gpl, target / "GPL-3.0.txt")
    else:
        print("  WARNUNG: licenses/GPL-3.0.txt fehlt im Repo – LGPL-3.0 verlangt den GPL-Text dazu")


def selftest() -> None:
    exe = APP / ("ShelfSort.exe" if sys.platform == "win32" else "ShelfSort")
    if sys.platform == "darwin" and not exe.exists():
        exe = DIST / "ShelfSort.app" / "Contents" / "MacOS" / "ShelfSort"
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
    result = subprocess.run([str(exe), "--selftest"], env=env, timeout=120)
    if result.returncode != 0:
        sys.exit(f"Selbsttest der gebauten App fehlgeschlagen (Exit-Code {result.returncode})")
    print("Selbsttest ok")


def main() -> None:
    shutil.rmtree(APP, ignore_errors=True)
    run_pyinstaller()
    prune_qt()
    copy_licenses()
    selftest()
    archive = shutil.make_archive(str(DIST / f"ShelfSort-{__version__}-{platform_tag()}"), "zip", DIST, "ShelfSort")
    size = sum(f.stat().st_size for f in APP.rglob("*") if f.is_file()) / 1024 / 1024
    print(f"\nFertig: {APP} ({size:.0f} MB)\n        {archive} ({Path(archive).stat().st_size / 1024 / 1024:.0f} MB)")


if __name__ == "__main__":
    main()
