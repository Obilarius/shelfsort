# Changelog

Each release gets a section `## <version>`; the release workflow publishes it as the release notes.

## 0.1.1

- **Cancel during scans** – the import scan, the library check and the specials check now have a Cancel button. Import and library check keep what they found so far.
- **Checks before a run** – write access and free space on the target drive are checked first; if something is missing, nothing is touched and you see why (e.g. “Not enough space on X:\Media: 48.3 GB needed, 12.1 GB free”).
- **Network share lost during a transfer** – the run stops right away instead of failing every remaining file; originals stay untouched.
- **Original in use** (e.g. still open in a player) – the verified copy counts as done, with a note to delete the original by hand.
- **Paths over 260 characters** – on Windows without long path support, such targets are marked as conflicts in the list instead of failing during the transfer.

## 0.1.0

First public version.

- Import from download folders: movies and episodes are recognised from their file names, matched on TMDB, renamed the way Plex expects and moved into the library (copied safely across drives, with progress and cancel).
- Library check: wrong folder and file names, episodes in the wrong season folder, missing episode titles, duplicates and empty folders.
- Plex sync: episode numbers follow the episode order set for the show in Plex (e.g. TheTVDB DVD or BBC iPlayer order).
- Specials check: shows which episode order puts a show's specials into the regular seasons and switches it in Plex.
- Several movie and show libraries, each with its own title language; Plex login in the browser, server and folders found automatically.
- History with undo for every run, log file for bug reports.
- German and English user interface.
