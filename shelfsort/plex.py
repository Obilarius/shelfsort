"""Telling the Plex server to scan changed folders."""
from __future__ import annotations

import re
from pathlib import Path

import requests


class Plex:
    def __init__(self, url: str, token: str):
        self.url = url.rstrip("/")
        self.token = token

    def _get(self, endpoint: str, **params) -> dict:
        # 'endpoint', not 'path': the refresh call passes Plex's own 'path' query parameter
        r = requests.get(self.url + endpoint, params=params, timeout=15,
                         headers={"X-Plex-Token": self.token, "Accept": "application/json"})
        r.raise_for_status()
        return r.json() if r.content else {}

    def _put(self, endpoint: str, **params) -> None:
        r = requests.put(self.url + endpoint, params=params, timeout=15,
                         headers={"X-Plex-Token": self.token, "Accept": "application/json"})
        r.raise_for_status()

    def sections(self) -> list[dict]:
        data = self._get("/library/sections").get("MediaContainer", {})
        return [
            {"key": d["key"], "title": d.get("title", ""), "type": d.get("type", ""),
             "locations": [loc["path"] for loc in d.get("Location", [])]}
            for d in data.get("Directory", [])
        ]

    @staticmethod
    def _basename(server_path: str) -> str:
        return server_path.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1].lower()

    @staticmethod
    def _join(server_root: str, rel: Path) -> str:
        sep = "\\" if re.match(r"^[A-Za-z]:\\", server_root) or server_root.startswith("\\\\") else "/"
        return sep.join([server_root.rstrip("\\/"), *rel.parts])

    def refresh(self, changed: set[Path], roots: list[Path], full: bool = False) -> list[str]:
        """Scan only the touched movie/show folders. Local root 'X:\\...\\movies' is mapped to the
        Plex library location with the same last folder name."""
        sections = self.sections()
        msgs: list[str] = []
        for root in roots:
            hits = [(s, loc) for s in sections for loc in s["locations"] if self._basename(loc) == root.name.lower()]
            mine = [p for p in changed if p == root or root in p.parents]
            if not mine:
                continue
            if not hits:
                msgs.append(f"Keine Plex-Bibliothek mit Ordner „{root.name}“ gefunden – bitte manuell scannen.")
                continue
            for s, loc in hits:
                if full:
                    self._get(f"/library/sections/{s['key']}/refresh")
                    msgs.append(f"Plex: Bibliothek „{s['title']}“ wird komplett gescannt")
                    continue
                tops = {root / p.relative_to(root).parts[0] for p in mine if p != root}
                for top in sorted(tops):
                    server_path = self._join(loc, top.relative_to(root))
                    self._get(f"/library/sections/{s['key']}/refresh", path=server_path)
                    msgs.append(f"Plex: scanne {s['title']} › {top.name}")
        return msgs
