# Changelog

Each release gets a section `## <version>`; the release workflow publishes it as the release notes.

## 0.1.0

First public version.

- Import from download folders: movies and episodes are recognised from their file names, matched on TMDB, renamed the way Plex expects and moved into the library (copied safely across drives, with progress and cancel).
- Library check: wrong folder and file names, episodes in the wrong season folder, missing episode titles, duplicates and empty folders.
- Plex sync: episode numbers follow the episode order set for the show in Plex (e.g. TheTVDB DVD or BBC iPlayer order).
- Specials check: shows which episode order puts a show's specials into the regular seasons and switches it in Plex.
- Several movie and show libraries, each with its own title language; Plex login in the browser, server and folders found automatically.
- History with undo for every run, log file for bug reports.
- German and English user interface.
