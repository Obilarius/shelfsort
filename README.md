# ShelfSort

Kleine GUI für Windows, die Filme und Serien so benennt, wie Plex sie erwartet, sie in die Bibliothek verschiebt – und die bestehende Bibliothek auf falsche Namen, falsche Folgennummern und leere Ordner prüft.

> ShelfSort ist ein unabhängiges Projekt und kein Produkt von Plex, Inc. „Plex“ ist eine Marke von Plex, Inc.

## Start

`ShelfSort.bat` doppelklicken. Beim ersten Start führt ein Assistent durch die Einrichtung (später erneut über **Einrichten …** im Menü):

1. **Sprache** – App-Sprache (bisher Deutsch) und Sprache der Titel. Die Titelsprache sollte zur Sprache der Plex-Bibliotheken passen; die Übersicht am Ende weist auf Abweichungen hin.
2. **TMDB-Key** eintragen – kostenlos auf themoviedb.org (Einstellungen → API).
3. **Bei Plex anmelden** – die Anmeldung läuft auf plex.tv im Browser, ShelfSort bekommt nur den Zugangsschlüssel, nie das Passwort. Ohne Plex geht es auch („Ohne Plex weiter“), dann fehlen Scan, Plex-Abgleich und Specials-Check.
4. **Server wählen** – ShelfSort findet die Server des Kontos und testet, welche Adresse erreichbar ist.
5. **Bibliotheken wählen** – alle Film- und Serien-Bibliotheken aus Plex anhaken, die ShelfSort verwalten soll (z. B. „Filme“, „Disney“, „Serien“). ShelfSort sucht selbst, wo ihr Ordner auf diesem Computer liegt (der Server sieht z. B. `/data/movies`, hier ist es `X:\Medien\movies`), und prüft das an echten Dateien. Pro Typ ist eine Bibliothek **Standard** für neue Importe. Bibliotheken für eigene Videos („Andere Videos“) sind standardmäßig nicht angehakt.

Unter **Einstellungen** lässt sich alles auch von Hand ändern (z. B. Mindestgröße für Videos, Sprache der Metadaten). Die Einstellungen liegen in `%APPDATA%\ShelfSort\config.json`, nicht im Repo.

Einrichtung auf einem neuen Rechner:

```
py -3.12 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

## Schema

| | Beispiel |
|---|---|
| Film | `movies\F1 - Der Film (2025) {tmdb-911430}\F1 - Der Film (2025).mkv` |
| Folge | `tvshows\Die wilden Siebziger {tmdb-52}\Season 05\Die wilden Siebziger - S05E04 - Die Wechseljahre.mkv` |

- Bestehende Film- und Serienordner (per TMDB-ID erkannt) werden weiterverwendet – in jeder verwalteten Bibliothek. Neue Folgen landen also bei ihrer Serie, auch wenn die in „Disney“ statt „Serien“ liegt. Neues kommt in die Standard-Bibliothek; per Rechtsklick → **Ziel-Bibliothek** lässt sich das für markierte Zeilen ändern.
- Staffelordner (`Season 05` / `Staffel 13`) werden weiterverwendet.
- Die Folgennummer kommt aus dem Dateinamen, der Folgentitel aus Plex: bei Serien in der Bibliothek in der dort eingestellten Reihenfolge (z. B. Doctor Who „TheTVDB (BBC iPlayer)“), bei neuen Serien in der Standard-Reihenfolge der Bibliothek – also so, wie Plex sie nach dem Import nummeriert. TMDB zählt manchmal anders (Bluey S03E49 ist dort ein Special). Nur ohne Plex-Token oder wenn Plex die Serie nicht kennt, kommt der Titel von TMDB.
- Dateien mit Kürzel vor dem Titel (`abc-show.s03e02…`) werden über den Ordnernamen bzw. ohne Kürzel erkannt.
- Untertitel (`Film.de.forced.srt`) wandern mit.
- Für Windows verbotene Zeichen werden ersetzt: `F1: Der Film` → `F1 - Der Film`.

## Import

Ordner wählen oder ins Fenster ziehen → alle Unterordner werden gescannt. Film oder Serie wird am Dateinamen erkannt, nicht am Ordner; auch technische Dateinamen wie `Some.Movie.2016.German.DL.1080p.BluRay.x264.mkv` werden zerlegt.

- **Grün (Bereit):** sicherer Treffer, vorausgewählt.
- **Gelb (Prüfen):** unsicherer Treffer, ähnlicher Ordner oder Film schon vorhanden, Folge in Plex-Reihenfolge unbekannt – nicht vorausgewählt.
- **Rot (Konflikt):** Ziel existiert bereits.

Rechts zeigt der Detail-Bereich zur markierten Zeile Cover, Titel, Jahr, Bewertung, Beschreibung und Link zu TMDB, bei Folgen zusätzlich Folgentitel, Szenenbild und Folgenbeschreibung. Mit den Pfeiltasten durch die Liste gehen.

Falscher Treffer → Doppelklick oder „Anderen Treffer wählen…“: TMDB-Suche mit Covern und Beschreibung, Jahr optional (findet mit Jahr nichts, wird ohne gesucht), bei Folgen auch Staffel/Folge.

„Übertragen“ kopiert nach `*.partial`, prüft die Größe, benennt um und löscht erst dann das Original. Leere Release-Ordner gehen in den Papierkorb. Danach scannt Plex nur die betroffenen Ordner.

Während der Übertragung zeigt ein Panel oben Gesamt- und Dateifortschritt, Geschwindigkeit und Restzeit; die Tabelle zeigt live, welche Zeile läuft. „Abbrechen“ verwirft die laufende Kopie, das Original bleibt, der Rest wird nicht angefasst.

## Bibliothek prüfen

Optionen:

- **Filme:** fehlendes Jahr / TMDB-ID im Ordnernamen, Dateiname ≠ Ordnername, doppelte Filme (Konflikt).
- **Serien:** Release-Namen bei Folgen, Folgen im falschen Staffelordner, fehlende Folgentitel.
- **Leere Ordner:** Ordner ohne Video. Werden **nie** vorausgewählt und auf dem Netzlaufwerk endgültig gelöscht (eigene Warnung).
- **Plex-Abgleich (Folgennummern):** vergleicht jede Folge mit der Folgenliste, die Plex für die Serie verwendet (inkl. Folgen ohne Datei), und schlägt korrigierte Nummern vor – z. B. Weihnachtsspecials von `S07E00` nach `S06E14`, oder eine um eins verschobene Staffel. Titel werden deutsch und englisch verglichen. Verschoben wird nur, wenn der Titel eindeutig zu einer anderen Folge passt; bei bloß anders übersetzten Titeln bleibt die Folge, wo sie ist. Braucht den Plex-Token.
- **Episodentitel übernehmen:** ersetzt vorhandene Titel durch die von Plex/TMDB (sonst bleiben sie, wie sie sind).

Saubere Ordnernamen werden direkt als Titel gesucht (`10 Cloverfield Lane`, `Blade Runner 2049`), Release-Namen werden zerlegt. Umschreibungen ohne Umlaute (`Einoede`) werden auch mit Umlauten gesucht.

Ketten-Umbenennungen (E06→E07, E05→E06, …) laufen über Zwischennamen, damit nichts kollidiert. Ist eine Zielnummer durch eine Datei belegt, die nicht verschoben wird, gibt es einen Konflikt statt einer doppelten Folge. Wurden Ordner umbenannt, scannt Plex danach die ganze Bibliothek.

## Specials

Specials in Staffel 0 überspringt Plex bei „Weiter schauen“. Manche Episoden-Reihenfolgen (TheTVDB DVD, BBC iPlayer, …) sortieren sie in die normalen Staffeln ein – Plex kann das nur über die Reihenfolge, nicht pro Folge.

„Serien prüfen“ geht alle Serien mit Specials durch und zeigt pro Serie, welche der in Plex verfügbaren Reihenfolgen wie viele Specials in den Ablauf bringt, wie viele Special bleiben und wie viele es dort gar nicht gibt (z. B. Making-ofs – vorhandene Dateien dafür kann Plex danach nicht mehr zuordnen). Unten stehen die Specials einzeln, mit ihrer neuen Nummer.

Angehakte Serien → „Reihenfolge in Plex umstellen“: stellt die Reihenfolge der Serie in Plex um, lädt die Metadaten neu und startet den Plex-Abgleich für genau diese Serien. Die neuen Dateinummern erscheinen unter „Bibliothek prüfen“ und werden erst nach Prüfen und „Ausführen“ umbenannt.

## Projektstruktur

| Datei | Inhalt |
|---|---|
| `gui.py`, `details.py`, `match_dialog.py`, `transfer_panel.py`, `specials_tab.py`, `dialogs.py` | Oberfläche |
| `importer.py`, `audit.py` | Plan für Import bzw. Bibliotheksprüfung |
| `executor.py` | Ausführen: Umbenennen, Kopieren, Löschen, Aufräumen |
| `parse.py`, `naming.py`, `matcher.py` | Release-Namen zerlegen, Namensschema, TMDB-Treffer bewerten |
| `tmdb.py`, `plex.py`, `plex_sync.py`, `posters.py` | TMDB, Plex-Scan, Plex-Folgenlisten und Reihenfolgen, Bilder |

## Datenquellen & Lizenz

- **TMDB:** This product uses TMDB and the TMDB APIs but is not endorsed, certified, or otherwise approved by TMDB. Jeder Nutzer trägt seinen eigenen, kostenlosen TMDB-API-Key ein.
- **Plex:** ShelfSort spricht mit deinem eigenen Plex Media Server. Für den Plex-Abgleich, den Specials-Check und Folgentitel in Plex-Reihenfolge nutzt es zusätzlich Plex' Metadatendienst (`metadata.provider.plex.tv`). Dieser Dienst ist **nicht offiziell dokumentiert** und kann sich jederzeit ändern. Fällt er aus, kommen Folgentitel von TMDB und der Plex-Abgleich wird mit einem Hinweis übersprungen – Import und Namensprüfung laufen weiter.
- **Lizenz:** MIT, siehe `LICENSE`. Verwendete Bibliotheken und ihre Lizenzen: `THIRD_PARTY_LICENSES.md`.

## Tests

```
.venv\Scripts\python -m pytest
```
