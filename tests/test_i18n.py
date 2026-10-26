"""Every text in the UI has an English translation with the same placeholders."""
import ast
import json
import string
from pathlib import Path

from shelfsort import i18n

SRC = Path(__file__).resolve().parent.parent / "shelfsort"


def texts_in_code() -> dict[str, str]:
    """All literals passed to tr()/N_() -> 'file:line'."""
    found = {}
    for path in SRC.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("tr", "N_")
                    and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                found.setdefault(node.args[0].value, f"{path.name}:{node.lineno}")
    return found


def fields(text: str) -> set[str]:
    return {f for _, f, _, _ in string.Formatter().parse(text) if f}


def test_english_catalog_is_complete():
    catalog = json.loads((SRC / "i18n" / "en.json").read_text(encoding="utf-8"))
    code = texts_in_code()
    missing = [f"{where}: {t!r}" for t, where in code.items() if t not in catalog]
    assert not missing, "Ohne englische Übersetzung:\n" + "\n".join(missing)
    wrong = [f"{code[t]}: {t!r} -> {catalog[t]!r}" for t in code if fields(t) != fields(catalog[t])]
    assert not wrong, "Platzhalter passen nicht:\n" + "\n".join(wrong)


def test_no_unused_translations():
    catalog = json.loads((SRC / "i18n" / "en.json").read_text(encoding="utf-8"))
    unused = sorted(set(catalog) - set(texts_in_code()))
    assert not unused, "Übersetzungen ohne Text im Code:\n" + "\n".join(unused)


def test_tr_and_fallback():
    try:
        assert i18n.set_language("en") == "en"
        assert i18n.tr("Abbrechen") == "Cancel"
        assert i18n.tr("gibt es nicht {x}", x=1) == "gibt es nicht 1"  # unknown -> German
        assert i18n.tr("{text} {name}", text="a", name="b") == "a b"  # placeholder named like the parameter
        assert i18n.set_language("xx") == "de" and i18n.tr("Abbrechen") == "Abbrechen"
    finally:
        i18n.set_language("de")
