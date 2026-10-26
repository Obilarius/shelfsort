"""User interface translations.

The German text in the code is the key; other languages live in shelfsort/i18n/<lang>.json as
{"German text": "translation"}. Missing entries fall back to German.

    tr("Datei {n} von {total}", n=3, total=12)

- Placeholders use str.format names. Literal braces in a text that has placeholders are doubled.
- Never call tr() at import time (module constants): the language is set later. Mark such texts with
  N_("…") instead and call tr() where they are shown - N_ only lets the translation check find them.
"""
from __future__ import annotations

import json
from pathlib import Path

DIR = Path(__file__).parent / "i18n"
SOURCE = "de"
LANGUAGES = [("de", "Deutsch"), ("en", "English")]  # app languages (names in their own language)

_lang = SOURCE
_catalog: dict[str, str] = {}


def set_language(lang: str | None) -> str:
    """Switch the UI language; unknown languages fall back to German. Returns the language used."""
    global _lang, _catalog
    lang = (lang or SOURCE).split("-")[0].lower()
    path = DIR / f"{lang}.json"
    if lang != SOURCE and path.exists():
        _lang, _catalog = lang, json.loads(path.read_text(encoding="utf-8"))
    else:
        _lang, _catalog = SOURCE, {}
    return _lang


def language() -> str:
    return _lang


def system_language() -> str:
    """German for a German system, English otherwise (the only two so far)."""
    from PySide6.QtCore import QLocale
    return "de" if QLocale.system().language() == QLocale.German else "en"


def tr(text: str, /, **values) -> str:  # "/": a placeholder may be called {text} too
    out = _catalog.get(text, text) if _catalog else text
    return out.format(**values) if values else out


def N_(text: str) -> str:
    """Marks a text for translation without translating it yet (for constants)."""
    return text
