"""Release helper for GitHub Actions.

    python tools/release_notes.py v0.2.0           prints the CHANGELOG.md section of 0.2.0
    python tools/release_notes.py --check v0.2.0   fails unless the tag matches __version__
                                                   and CHANGELOG.md has a section for it
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from shelfsort import __version__  # noqa: E402


def section(version: str) -> str | None:
    """Text under '## 0.2.0' (optionally '## [0.2.0] - date') up to the next '## '."""
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    m = re.search(rf"^## \[?{re.escape(version)}\]?[^\n]*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    return m.group(1).strip() if m else None


def main(argv: list[str]) -> None:
    check = "--check" in argv
    tags = [a for a in argv if not a.startswith("--")]
    if len(tags) != 1:
        sys.exit(__doc__)
    version = tags[0].removeprefix("v")
    notes = section(version)
    if check:
        if version != __version__:
            sys.exit(f"Tag {tags[0]} passt nicht zu __version__ = {__version__}")
        if not notes:
            sys.exit(f"CHANGELOG.md hat keinen Abschnitt '## {version}'")
        print(f"ok: {version}")
        return
    sys.stdout.reconfigure(encoding="utf-8")
    print(notes or f"ShelfSort {version}")


if __name__ == "__main__":
    main(sys.argv[1:])
