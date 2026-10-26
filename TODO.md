# TODO bis zur Veröffentlichung

Ziel: kostenlos und Open Source auf GitHub, mit Spenden-Link (Buy Me a Coffee o. Ä.). Für Leute mit dem gleichen Problem – Downloads Plex-gerecht benennen, Folgen passend zur Plex-Reihenfolge nummerieren, Specials in den Ablauf bringen.

## 1. Rechtliches & Außendarstellung

- [x] **Neuer Name ohne „Plex“** – ShelfSort. Paket `shelfsort`, Start über `ShelfSort.bat`, Einstellungen in `%APPDATA%\ShelfSort` (alte werden übernommen).
- [x] **Lizenz** – MIT (`LICENSE`), Abhängigkeiten in `THIRD_PARTY_LICENSES.md`.
- [ ] **Volle Lizenztexte der Abhängigkeiten** in die Exe packen (`licenses/`-Ordner) – beim Exe-Build (Abschnitt 3).
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
- [x] **Einrichtungs-Assistent** beim ersten Start und über „Einrichten …“.
- [ ] **PIN-Anmeldung einmal komplett von Hand testen** (Browser-Schritt lässt sich nicht automatisch testen).
- [x] Sprache im Assistenten: App-Sprache (Englisch folgt) und Sprache der Titel, mit Hinweis wenn sie nicht zur Plex-Bibliothek passt.

## 3. Installation & Updates

- [ ] **Exe bauen** (PyInstaller oder Nuitka), Icon, Versionsnummer.
- [ ] **GitHub Actions**: Tests bei jedem Push, Exe-Build bei Release-Tag.
- [ ] **GitHub Releases** mit Exe/Zip und Changelog.
- [ ] **Update-Hinweis** in der App (neueste Release-Version über die GitHub-API prüfen).
- [ ] *Optional:* Code-Signatur gegen die SmartScreen-Warnung – kostet Geld; bis dahin in der README erklären („Weitere Informationen → Trotzdem ausführen“).
- [ ] *Optional:* macOS/Linux – „anderes Laufwerk?“ beim Verschieben über das Dateisystem (`st_dev`) statt Laufwerksbuchstaben erkennen, Startskripte.

## 4. Flexibilität

- [ ] **Englische Oberfläche** + Übersetzungsmöglichkeit (Qt-Übersetzungen oder einfache String-Tabelle); Sprache der Metadaten einstellbar (jetzt fest `de-DE`).
- [ ] **Namensschema einstellbar**: Serienordner mit/ohne Jahr, `Season`/`Staffel`, ID-Format (`{tmdb-}`, `{tvdb-}`, `{imdb-}`), Episodentitel ja/nein.
- [x] **Mehrere Bibliotheken pro Typ** – im Assistenten anhaken, je ein Standard für Filme und Serien, Ziel per Rechtsklick; Prüfung, Plex-Abgleich, Specials und Scan über alle.
- [ ] **Weitere Fälle**: Anime mit absoluter Nummerierung, Filme mit Edition (`{edition-…}`), 3D, Extras-Ordner, mehrteilige Filme testen.

## 5. Sicherheit & Stabilität

- [ ] **Rückgängig-Funktion** mit dauerhaftem Protokoll (jede Umbenennung/Verschiebung als Eintrag, „letzten Lauf rückgängig machen“).
- [ ] **Log-Datei** in `%APPDATA%` und Knopf „Log öffnen“ – für Support-Anfragen.
- [ ] **Randfälle**: Pfade über 260 Zeichen, Netzabbruch während der Kopie, fehlende Schreibrechte, volle Platte (vor dem Kopieren freien Platz prüfen).
- [ ] **Große Bibliotheken**: Prüfung mit tausenden Folgen testen, Abbrechen auch beim Scannen.
- [ ] **Mehr Tests** mit echten Release-Namen-Mustern (anonymisiert).

## 6. Optik & Bedienung

- [ ] Optische Feinarbeit (eigene Liste).
- [ ] Hell-/Dunkel-Modus prüfen, hohe DPI, Tastaturbedienung.
- [ ] Über-Dialog: Version, Lizenz, TMDB-Hinweis, Link zu GitHub und Spenden-Link.

## 7. Veröffentlichung

- [ ] README für Fremde umschreiben: Was macht es, für wen, Screenshots/GIF, Installation, erste Schritte, FAQ (SmartScreen, TMDB-Key besorgen, Plex-Login).
- [ ] `CONTRIBUTING.md` und Issue-Vorlagen (Bug/Wunsch).
- [ ] Spenden-Link (Buy Me a Coffee / Ko-fi / GitHub Sponsors) in README und App.
- [ ] Erste Ankündigung, z. B. auf r/PleX – Schwerpunkt auf dem, was andere Tools nicht können: Plex-Abgleich nach der eingestellten Reihenfolge und der Specials-Check.

## Später / Ideen

- [ ] Playlist „Serie – komplett“ in Ausstrahlungsreihenfolge für Serien, bei denen keine Reihenfolge die Specials einsortiert.
- [ ] Upgrade ersetzen: bessere Qualität eines vorhandenen Films anbieten statt nur „schon vorhanden“.
- [ ] Ordner überwachen (automatischer Import, wenn ein Download fertig ist).
