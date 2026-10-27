# TODO bis zur Veröffentlichung

Ziel: kostenlos und Open Source auf GitHub, mit Spenden-Link (Buy Me a Coffee o. Ä.). Für Leute mit dem gleichen Problem – Downloads Plex-gerecht benennen, Folgen passend zur Plex-Reihenfolge nummerieren, Specials in den Ablauf bringen.

## 1. Rechtliches & Außendarstellung

- [x] **Neuer Name ohne „Plex“** – ShelfSort. Paket `shelfsort`, Start über `ShelfSort.bat`, Einstellungen in `%APPDATA%\ShelfSort` (alte werden übernommen).
- [x] **Lizenz** – MIT (`LICENSE`), Abhängigkeiten in `THIRD_PARTY_LICENSES.md`.
- [x] **Volle Lizenztexte der Abhängigkeiten** im `licenses/`-Ordner der App (inkl. LGPL-3.0 und Qt-Hinweis).
- [x] **GPL-3.0-Text** liegt in `licenses/GPL-3.0.txt` (LGPL-3.0 verlangt ihn dazu).
- [x] **TMDB-Hinweis** im Über-Dialog und in der README.
- [x] **TMDB-Logo** („Alt short“) im Über-Dialog, Hinweis im offiziellen Wortlaut. Liegt in `shelfsort/assets/` – beim Exe-Build mitnehmen.
- [x] **Spenden-Link** mit den TMDB-Bedingungen abgeglichen: freiwillige Spenden für ein kostenloses Open-Source-Tool sind kein Hauptzweck „Einnahmen“ → ok. Dabei bleiben: keine Funktionen hinter Spenden, keine Werbung.
- [x] **Jeder Nutzer trägt seinen eigenen TMDB-Key ein** – kein Key im Code; Standardwerte (Server, Ordner) sind jetzt neutral.
- [x] **Plex-Metadatendienst ist inoffiziell**: in README erklärt; fällt er aus, kommen Folgentitel von TMDB, Plex-Abgleich und Specials-Check melden das einmal statt pro Serie.
- [x] **Neutrale Beispiele** in README, Code-Kommentaren und Tests. Screenshots folgen mit der README für Fremde (Abschnitt 7).

## 2. Einrichtung ohne Bastelei

- [x] **Plex-Login per PIN** – offizieller Ablauf über app.plex.tv im Browser (`plex_auth.py`).
- [x] **Server automatisch finden** – Server des Kontos über plex.tv, erste erreichbare Adresse (lokal vor remote).
- [x] **Bibliotheken aus Plex auswählen** – Filme/Serien-Bibliothek im Assistenten; Scan und Plex-Abgleich nutzen die gewählte Bibliothek statt gleicher Ordnernamen.
- [x] **Pfad-Zuordnung** lokal ↔ Server – automatischer Vorschlag, geprüft an Beispieldateien aus Plex (`path_mapping.py`).
- [x] **Einrichtungs-Assistent** beim ersten Start und über „Einrichten“.
- [x] **PIN-Anmeldung von Hand getestet** – klappt; Plex zeigt dabei seinen üblichen „Sicherheits-Alarm“ für Fremd-Apps, in der FAQ erklärt.
- [x] Sprache im Assistenten: App-Sprache (Englisch folgt), Standard-Titelsprache und Titelsprache pro Bibliothek (vorbelegt aus Plex, z. B. Englisch für OV), Hinweis bei Abweichung von Plex.
- [x] Standard-Bibliothek bei Neueinrichtung: die größte pro Typ; Anzahl Filme/Serien wird angezeigt.

## 3. Installation & Updates

- [x] **Exe bauen** – `tools/build.py` (PyInstaller, Ordner-Build), Icon, Versionsinfo, Selbsttest, ZIP; ~38 MB gezippt.
- [x] **GitHub Actions**: Tests bei jedem Push (Windows + Linux), Build und Release bei Tag `v*` (`.github/workflows/`). Erster Lauf auf GitHub steht noch aus.
- [x] **GitHub Releases** mit Zip (Windows) und tar.xz (Linux), Text aus `CHANGELOG.md`; Tag muss zu `__version__` passen.
- [x] **Update-Hinweis**: einmal am Tag `releases/latest` über die GitHub-API, Hinweis unten rechts mit „Herunterladen“ / „Überspringen“, abschaltbar in den Einstellungen (`update.py`). Funktioniert erst, wenn das Repo öffentlich ist.
- [ ] *Optional:* Code-Signatur gegen die SmartScreen-Warnung – kostet Geld; bis dahin in der README erklären („Weitere Informationen → Trotzdem ausführen“).
- [x] Linux/macOS im Code: Einstellungsordner (`~/.config`), „anderes Laufwerk?“ über das Dateisystem, Pfad-Suche in `/mnt`, `/media`, `/Volumes`.
- [x] Linux-Build in GitHub Actions (Ubuntu 22.04 für breite Kompatibilität).
- [ ] Linux-Build einmal auf einem echten Linux-Desktop testen.
- [ ] *Optional/später:* macOS-Build (ohne Apple-Entwicklerkonto nur unsigniert, Nutzer müssen die App manuell freigeben).

## 4. Flexibilität

- [x] **Englische Oberfläche** – `tr()` mit Übersetzungen in `shelfsort/i18n/en.json` (300 Texte), Qt-eigene Texte übersetzt, Sprache nach Windows, Wechsel ohne Neustart; Test prüft Vollständigkeit.
- [ ] Englische Texte einmal in Ruhe durchklicken und Formulierungen glätten (vor allem Hinweise in der Tabelle).
- [ ] **Namensschema einstellbar**: Serienordner mit/ohne Jahr, `Season`/`Staffel`, ID-Format (`{tmdb-}`, `{tvdb-}`, `{imdb-}`), Episodentitel ja/nein.
- [x] **Mehrere Bibliotheken pro Typ** – im Assistenten anhaken, je ein Standard für Filme und Serien, Ziel per Rechtsklick; Prüfung, Plex-Abgleich, Specials und Scan über alle.
- [ ] **Weitere Fälle**: Anime mit absoluter Nummerierung, Filme mit Edition (`{edition-…}`), 3D, Extras-Ordner, mehrteilige Filme testen.

## 5. Sicherheit & Stabilität

- [x] **Rückgängig-Funktion** – jeder Lauf wird sofort mitgeschrieben (`%APPDATA%\ShelfSort\history`, die letzten 50); **Verlauf** zeigt die Läufe und macht einen rückgängig. Seitdem Verändertes wird übersprungen, gelöschte leere Ordner neu angelegt, Papierkorb nur als Hinweis.
- [x] **Log-Datei** `%APPDATA%\ShelfSort\logs\shelfsort.log` (1 MB, 3 alte Stände) mit allem aus dem Log-Fenster, Fehlerdetails und Abstürzen; Knopf „Log-Datei öffnen“ im Verlauf.
- [x] **Randfälle**: vor dem Lauf Schreibrechte und freien Platz prüfen (sonst nichts anfassen); Netzabbruch bricht den Lauf ab statt jede weitere Datei scheitern zu lassen; gesperrtes Original → Kopie bleibt, Hinweis; Pfade über 260 Zeichen ohne Windows-Langpfade → Konflikt.
- [ ] Übriggebliebene `*.partial`/`*.shelfsort-tmp` (z. B. nach Netzabbruch) unter „Bibliothek prüfen“ anzeigen.
- [ ] **Große Bibliotheken**: Prüfung mit tausenden Folgen testen, Abbrechen auch beim Scannen.
- [ ] **Mehr Tests** mit echten Release-Namen-Mustern (anonymisiert).

## 6. Optik & Bedienung

- [ ] Optische Feinarbeit (eigene Liste).
- [ ] Hell-/Dunkel-Modus prüfen, hohe DPI, Tastaturbedienung.
- [x] Über-Dialog: Version, Lizenz, TMDB-Hinweis, Link zu GitHub und Spenden-Link.

## 7. Veröffentlichung

- [x] README für Fremde: englisch (`README.md`) und deutsch (`README.de.md`) – was es macht, Installation, erste Schritte, FAQ, Datenschutz. Entwicklerteil in `CONTRIBUTING.md`.
- [x] Screenshots für die README (`docs/screenshots/`, erzeugt mit `tools/screenshots.py` aus Beispieldaten).
- [x] `CONTRIBUTING.md` und Issue-Vorlagen (Bug/Wunsch, `.github/ISSUE_TEMPLATE/`).
- [x] Spenden-Link: Ko-fi (`ko-fi.com/obilarius`) in beiden READMEs, im Über-Dialog und als Sponsor-Knopf (`.github/FUNDING.yml`).
- [ ] Erste Ankündigung, z. B. auf r/PleX – Schwerpunkt auf dem, was andere Tools nicht können: Plex-Abgleich nach der eingestellten Reihenfolge und der Specials-Check.

## Später / Ideen

- [ ] Playlist „Serie – komplett“ in Ausstrahlungsreihenfolge für Serien, bei denen keine Reihenfolge die Specials einsortiert.
- [ ] Upgrade ersetzen: bessere Qualität eines vorhandenen Films anbieten statt nur „schon vorhanden“.
- [ ] Ordner überwachen (automatischer Import, wenn ein Download fertig ist).

### Jellyfin und Kodi (erst bei Nachfrage nach 0.1.0)

- [ ] **Stufe 1 – Benennen:** Namensschema mit Vorlagen für Plex (`{tmdb-…}`), Jellyfin (`[tmdbid-…]`) und Kodi (saubere Namen, optional `.nfo`). Deckt sich mit „Namensschema einstellbar“ (Abschnitt 4). Ca. eine Sitzung.
- [ ] **Stufe 2 – Jellyfin anbinden:** Server-URL + API-Key statt Plex-Login, Bibliotheken und Ordner über die API, vorhandene Pfad-Zuordnung wiederverwenden, gezielter Scan pro Ordner nach dem Verschieben. Test-Server per Docker. Ca. ein bis zwei Sitzungen.
- [ ] **Stufe 2 – Kodi anbinden:** Scan über JSON-RPC (muss in Kodi aktiviert sein); Kodi läuft meist auf dem Abspielgerät, oft mehrere Geräte – Einrichtung fummeliger.
- [ ] **Stufe 3 – Abgleich der Episoden-Reihenfolge** für Jellyfin (Reihenfolge pro Serie) bzw. Kodi (TMDB-Episodengruppen im Scraper) – Gegenstück zu Plex-Abgleich und Specials-Check, praktisch ein eigenes Projekt.
