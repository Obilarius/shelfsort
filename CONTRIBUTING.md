# Contributing

Bug reports, ideas and pull requests are welcome. For bugs, please attach the log file (*History → Open log file*, with anything private removed). For larger changes, open an issue first so we can talk about it.

## Running from source

Python 3.12:

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt      # Windows: .venv\Scripts\pip
.venv/bin/python -m shelfsort                   # Windows: ShelfSort.bat
```

Settings live outside the repository (`%APPDATA%\ShelfSort`, `~/.config/ShelfSort`), so a source checkout uses the same settings as an installed copy.

## Tests

```bash
.venv/bin/python -m pytest
```

GitHub Actions runs them on Windows and Linux for every push and pull request. Tests never talk to TMDB or Plex – use fakes (see `tests/test_plex.py`).

## Project layout

| File | Purpose |
|---|---|
| `gui.py`, `details.py`, `match_dialog.py`, `transfer_panel.py`, `specials_tab.py`, `dialogs.py`, `history_dialog.py` | user interface |
| `wizard.py`, `setup_widgets.py` | setup wizard and the parts it shares with the settings |
| `importer.py`, `audit.py` | plan for an import or a library check |
| `executor.py` | carrying out a plan: rename, copy, delete, clean up |
| `history.py`, `applog.py` | run history and undo, log file |
| `parse.py`, `naming.py`, `matcher.py` | taking release names apart, naming scheme, judging TMDB matches |
| `tmdb.py`, `plex.py`, `plex_sync.py`, `plex_auth.py`, `path_mapping.py`, `posters.py` | TMDB, Plex server, Plex episode orderings, Plex sign-in, server ↔ local paths, images |

Everything that changes files goes through a plan (`plan.py`) that the user sees first; nothing is renamed without that step.

## Translations

The German text in the code is the key: `tr("Abbrechen")`. Translations are in `shelfsort/i18n/<language>.json`. To add a language, copy `en.json`, translate the values and add the language to `LANGUAGES` in `shelfsort/i18n.py`. `tests/test_i18n.py` checks that every text in the code is translated and the `{placeholders}` match.

## Building

```bash
.venv/bin/pip install pyinstaller
.venv/bin/python tools/build.py
```

Result: `dist/ShelfSort/` and `dist/ShelfSort-<version>-<platform>.zip` (Linux: `.tar.xz`). The script runs the built app with `--selftest`, copies the license texts of all libraries into `licenses/` and lists the largest files. The icon is drawn by `tools/make_icon.py`.

## Releasing

1. Raise `__version__` in `shelfsort/__init__.py`.
2. Add a section `## <version>` to `CHANGELOG.md`.
3. Commit, then tag and push: `git tag v0.2.0` and `git push origin v0.2.0`.

The release workflow checks that tag, version and changelog match, runs the tests, builds Windows and Linux (on Ubuntu 22.04, so it runs on newer distributions too) and publishes the GitHub release with the changelog section as text. *Actions → Release → Run workflow* only builds, as a test.
