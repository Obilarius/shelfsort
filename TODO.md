# TODO bis zur Veröffentlichung

Ziel: kostenlos und Open Source auf GitHub, mit Spenden-Link (Buy Me a Coffee o. Ä.). Für Leute mit dem gleichen Problem – Downloads Plex-gerecht benennen, Folgen passend zur Plex-Reihenfolge nummerieren, Specials in den Ablauf bringen.

## 1. Rechtliches & Außendarstellung

- [ ] **Neuer Name ohne „Plex“** – Markenrichtlinien von Plex. „… für Plex“ in der Beschreibung ist ok, im Produktnamen nicht.
- [ ] **Lizenz wählen** und `LICENSE` anlegen (z. B. MIT oder GPL-3.0). PySide6 und guessit sind LGPL – passt zu beidem, Lizenztexte der Abhängigkeiten in der Exe mitliefern (`THIRD_PARTY_LICENSES`).
- [ ] **TMDB-Hinweis** in App (Über-Dialog) und README, mit TMDB-Logo: „This product uses the TMDB API but is not endorsed or certified by TMDB.“ Nicht-kommerziell ist die Nutzung kostenlos; Spenden-Link vorher kurz mit den TMDB-Bedingungen abgleichen.
- [ ] **Jeder Nutzer trägt seinen eigenen TMDB-Key ein** (so wie jetzt) – keinen eigenen Key in die Exe packen.
- [ ] **Plex-Metadatendienst ist inoffiziell** (`metadata.provider.plex.tv`): in README erwähnen; wenn er ausfällt, sauber auf TMDB zurückfallen und das im Log/UI anzeigen statt Fehler.
- [ ] **Neutrale Beispiele** in README und Screenshots – keine Scene-Release-Namen.

## 2. Einrichtung ohne Bastelei

- [ ] **Plex-Login per PIN** (`plex.tv/link`) statt Token aus der XML kopieren.
- [ ] **Server automatisch finden** (Liste der Server des Accounts über plex.tv), Auswahl falls mehrere.
- [ ] **Bibliotheken aus Plex auswählen** statt Ordnerpfade eintippen.
- [ ] **Pfad-Zuordnung** lokal ↔ Server (`X:\plex_media\movies` ↔ `/data/movies`), mit Vorschlag und Test – die jetzige Zuordnung über gleiche Ordnernamen passt nicht bei jedem.
- [ ] **Einrichtungs-Assistent** beim ersten Start (TMDB-Key, Plex-Login, Bibliotheken, Sprache).

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
- [ ] **Mehrere Bibliotheken pro Typ** (z. B. „Filme“ und „Kinderfilme“), Import-Ziel wählbar.
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
