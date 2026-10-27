# Changelog

Each release gets a section `## <version>`; the release workflow publishes it as the release notes.

## 0.3.0

- **Upgrades** – if an imported movie is already in your library, ShelfSort compares the two copies (resolution, then source – e.g. 2160p over 1080p, Blu-ray over WEB, remux over rip) and offers to replace the old file with a better one. A worse or equal copy is marked as a conflict. Never preselected; the confirmation lists every movie that will be replaced, and the old file is deleted only after the new one is completely copied and verified. If the existing file's name says nothing about its quality, the note shows both file sizes so you can decide.
- **High-DPI screens** – at 150–200 % display scaling, the main window and dialogs could be larger than the screen. They now open at most 90 % of the screen size.
- **Keyboard** – in the lists, Space ticks or unticks the selected rows, Enter opens the match dialog.

## 0.2.1

- **Leftovers of interrupted transfers** – *Check library* with “Empty folders and leftovers” now also finds incomplete `*.partial` copies (offered for deletion – the original was never deleted) and files left under a temporary `*.shelfsort-tmp` name (they get their name back). Never preselected; a `.partial` younger than 15 minutes is left alone in case a transfer is still running.
- **Clearer English texts** – consistent terms (“episode ordering”, specials moving “into the regular seasons”), “sign-in” instead of “token”, and a number of awkward phrasings reworded.

## 0.2.0

- **Naming templates for Plex, Jellyfin and Kodi** – *Settings → Names* chooses how new folders and files are named: Plex (`{tmdb-…}`, the default as before), Jellyfin (`[tmdbid-…]`, year in show folders), Kodi (no ID in the name) – or each part by hand: ID style, year in show folders, `Season`/`Staffel`, episode titles.
- **.nfo files for Kodi** – with the Kodi template, new movies get a `.nfo` and new shows a `tvshow.nfo` with the TMDB link, so Kodi knows exactly which title it is. Existing `.nfo` files are never overwritten; undo removes the ones ShelfSort created.
- **Existing folders in any format** – `{tmdb-…}`, `[tmdbid-…]` and folders without an ID are all recognised, so new episodes join their show whatever named it. After switching templates, *Check library* suggests renaming the existing folders (nothing happens without asking).
- **Movie editions and 3D** – Director's Cut, Extended, Final Cut, Unrated, IMAX, 3D and others get their own file next to the regular version (`Aliens (1986) {edition-Director's Cut}.mkv`) instead of being reported as a duplicate.
- **Extras** – folders like `Bonus`, `Special Features` or `Making of` and Plex extras such as `Arrival (2016)-trailer.mkv` are no longer taken for the movie itself.
- Fixed: `Blade.Runner.1982.The.Final.Cut…` was recognised as a TV episode.

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
