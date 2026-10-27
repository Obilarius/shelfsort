# ShelfSort

**Heruntergeladene Filme und Serien in die Plex-Bibliothek einsortieren – so benannt, wie Plex es erwartet, mit den Folgennummern, die Plex wirklich verwendet.**

ShelfSort ist eine kleine Desktop-App für Windows und Linux. Download-Ordner wählen: ShelfSort erkennt jeden Film und jede Folge, sucht sie auf TMDB, zeigt vorher, was passieren wird, und verschiebt die Dateien mit sauberen Namen in die Plex-Bibliothek. Die vorhandene Bibliothek kann es ebenfalls prüfen und korrigieren.

[English](README.md) · [Download](https://github.com/Obilarius/shelfsort/releases/latest) · [Changelog](CHANGELOG.md)

> ShelfSort ist ein unabhängiges Projekt und kein Produkt von Plex, Inc. „Plex“ ist eine Marke von Plex, Inc.

## Was anders ist

Die meisten Umbenenner nummerieren Folgen so wie TMDB oder TheTVDB. Plex nummeriert aber nach der **Episoden-Reihenfolge, die für die Serie eingestellt ist** – und die ist bei vielen Serien nicht die Standard-Reihenfolge (Doctor Who nach BBC iPlayer, Krimiserien nach DVD, Kinderserien, bei denen TMDB und TheTVDB unterschiedlich zählen). Eine nach der „falschen“ Reihenfolge benannte Datei landet in Plex bei der falschen Folge oder gar nicht.

ShelfSort fragt den Plex-Server, welche Reihenfolge jede Serie nutzt, und benennt die Dateien passend:

- **Plex-Abgleich** – vergleicht jede Folge der Bibliothek mit der Folgenliste, die Plex für die Serie verwendet, und schlägt korrigierte Nummern vor, z. B. ein Weihnachtsspecial von `S07E00` nach `S06E14` oder eine um eins verschobene Staffel.
- **Specials-Check** – Plex überspringt Staffel 0 bei „Weiter schauen“. ShelfSort zeigt pro Serie, welche der in Plex verfügbaren Reihenfolgen die Specials in die normalen Staffeln einsortiert, und stellt die Serie auf Wunsch um.

## Funktionen

- **Import aus Download-Ordnern** – inklusive Unterordnern; wilde Release-Namen (`Some.Movie.2016.German.DL.1080p.BluRay.x264.mkv`) werden zerlegt. Untertitel wandern mit.
- **Du entscheidest** – jede geplante Umbenennung steht vorher in der Liste. Grün = sicherer Treffer (vorausgewählt), Gelb = bitte prüfen, Rot = Konflikt. Falscher Treffer? Doppelklick und selbst auf TMDB suchen, mit Covern und Beschreibung.
- **Sichere Übertragung** – über Laufwerke hinweg wird nach `*.partial` kopiert, die Größe geprüft und erst dann das Original gelöscht. Fortschritt, Geschwindigkeit und Restzeit werden angezeigt; Abbrechen lässt das Original unangetastet.
- **Bibliothek prüfen** – falsche Ordner- und Dateinamen, fehlendes Jahr oder TMDB-ID, Folgen im falschen Staffelordner, fehlende Folgentitel, doppelte Einträge, leere Ordner.
- **Mehrere Bibliotheken** – z. B. „Filme“, „Kinder“, „Serien“; pro Typ eine Standard-Bibliothek für Neues, jede mit eigener Titelsprache (praktisch für eine OV-Bibliothek).
- **Rückgängig** – jeder Lauf wird aufgezeichnet; **Verlauf** zeigt ihn und stellt alles wieder her.
- **Plex-Scan** – danach werden nur die geänderten Ordner neu eingelesen.
- Oberfläche auf **Deutsch und Englisch**.

Namensschema (das von Plex empfohlene):

| | Beispiel |
|---|---|
| Film | `Filme/Blade Runner 2049 (2017) {tmdb-335984}/Blade Runner 2049 (2017).mkv` |
| Folge | `Serien/Doctor Who {tmdb-57243}/Season 06/Doctor Who - S06E01 - The Impossible Astronaut.mkv` |

## Installation

**Windows 10/11:** `ShelfSort-<Version>-windows-x64.zip` unter [Releases](https://github.com/Obilarius/shelfsort/releases/latest) herunterladen, irgendwohin entpacken und `ShelfSort.exe` starten. Kein Installer; außerhalb des Ordners landen nur die Einstellungen.

**Linux (x64):** `ShelfSort-<Version>-linux-x64.tar.xz` herunterladen, dann

```bash
tar -xf ShelfSort-*-linux-x64.tar.xz
```

und `ShelfSort/ShelfSort` starten. Gebaut unter Ubuntu 22.04, läuft also dort und auf neueren Distributionen.

**Aus dem Quellcode** (jedes System mit Python 3.12): siehe [CONTRIBUTING.md](CONTRIBUTING.md).

## Erste Schritte

Beim ersten Start fragt ein Assistent nach:

1. **Sprache** – der App und der Titel (Film- und Folgennamen).
2. **TMDB-API-Key** – kostenlos: Konto auf [themoviedb.org](https://www.themoviedb.org/signup) anlegen, dann *Einstellungen → API* und einen Key beantragen („Developer“, private Nutzung). Den „API-Schlüssel“ oder das „API-Lesezugriffstoken“ einfügen – beides geht.
3. **Plex-Anmeldung** – öffnet plex.tv im Browser. ShelfSort bekommt nur einen Zugangsschlüssel, nie das Passwort. Ohne Plex geht es auch; dann funktionieren Umbenennen und Verschieben, aber kein Plex-Scan, Plex-Abgleich oder Specials-Check.
4. **Server** – wird über das Plex-Konto gefunden; ShelfSort testet, welche Adresse von diesem Computer aus erreichbar ist.
5. **Bibliotheken** – die Film- und Serien-Bibliotheken anhaken, die ShelfSort verwalten soll. Es findet selbst, wo deren Ordner auf diesem Computer liegen (Plex sieht vielleicht `/data/movies`, dieser Computer `X:\Medien\movies`), und prüft das an echten Dateien.

Danach: **Import** → Download-Ordner wählen → **Scannen** → Liste prüfen → **Übertragen**.

Alles lässt sich später unter **Einstellungen** ändern, dort startet auch der Assistent erneut.

## Häufige Fragen

**Windows meldet „Der Computer wurde durch Windows geschützt“.**
Das Programm ist nicht signiert (das kostet jedes Jahr Geld). *Weitere Informationen → Trotzdem ausführen* klicken. Die Builds erstellt GitHub Actions direkt aus dem Quellcode dieses Repos.

**Linux: startet nicht / „could not load the Qt platform plugin xcb“.**
Die XCB-Cursor-Bibliothek installieren, die neuere Qt-Versionen brauchen: `sudo apt install libxcb-cursor0` (Debian/Ubuntu) oder `sudo dnf install xcb-util-cursor` (Fedora). Aus einem Terminal gestartet, zeigt es die Fehlermeldung.

**Löscht ShelfSort etwas?**
Nur zweierlei, und nur nach Rückfrage: Release-Ordner, die nach dem Import leer sind, gehen in den **Papierkorb**; leere Ordner aus *Bibliothek prüfen* sind nie vorausgewählt und werden nach einer eigenen Warnung endgültig gelöscht (Netzlaufwerke haben keinen Papierkorb).

**Etwas ist schiefgegangen – kann ich zurück?**
**Verlauf** listet jeden Lauf mit allen Änderungen. *Rückgängig machen* bringt Dateien und Ordner zurück. Was sich seitdem verändert hat, wird übersprungen, nie überschrieben.

**Eine Folge hat die falsche Nummer.**
In Plex nachsehen, welche Episoden-Reihenfolge die Serie nutzt (*Bearbeiten → Erweitert → Episodenreihenfolge*) – ShelfSort richtet sich danach. Der Reiter *Specials* zeigt die Reihenfolgen nebeneinander.

**Wo liegen die Einstellungen? Wie deinstalliere ich?**
Einstellungen, Verlauf und Log-Datei liegen in `%APPDATA%\ShelfSort` (Windows) bzw. `~/.config/ShelfSort` (Linux). Zum Deinstallieren den Programmordner und diesen Ordner löschen.

**Etwas funktioniert nicht.**
Bitte ein [Issue anlegen](https://github.com/Obilarius/shelfsort/issues) und die Log-Datei anhängen (*Verlauf → Log-Datei öffnen*). Vorher Privates entfernen; sie enthält Datei- und Ordnernamen.

## Datenschutz

ShelfSort hat keine Telemetrie und kein eigenes Konto. Es spricht mit:

- **TMDB** (`api.themoviedb.org`, `image.tmdb.org`) – Titel suchen, Cover laden, mit deinem eigenen API-Key.
- **Plex** – `plex.tv` für Anmeldung und Serversuche, deinem eigenen Plex-Server und Plex’ Metadatendienst `metadata.provider.plex.tv` für die Episoden-Reihenfolgen.

TMDB-Key und Plex-Token liegen nur in der Einstellungsdatei auf deinem Computer.

## Gut zu wissen

- Plex’ Metadatendienst ist **nicht offiziell dokumentiert** und kann sich ändern. Fällt er aus, kommen Folgentitel von TMDB und der Plex-Abgleich wird mit einem Hinweis übersprungen – Import und Namensprüfung laufen weiter.
- This product uses the TMDB API but is not endorsed or certified by TMDB.

## Unterstützen

ShelfSort ist kostenlos und bleibt es – keine Bezahlfunktionen, keine Werbung. Wenn es dir Zeit spart, kannst du mir einen Kaffee spendieren. <!-- TODO: Spendenlink -->

## Lizenz

MIT, siehe [LICENSE](LICENSE). Verwendete Bibliotheken und ihre Lizenzen: [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).
