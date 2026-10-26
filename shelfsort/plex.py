"""Talking to the user's Plex Media Server: libraries, sample files, targeted scans."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import requests


@dataclass
class LibraryMap:
    """A local library folder and the Plex library it belongs to.

    section_key/server_root come from the setup (e.g. "1", "/data/movies"). Without them the
    library is found by the folder name (older configs).
    """
    local_root: Path
    section_key: str | None = None
    server_root: str | None = None


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
             "agent": d.get("agent", ""),  # ".none" agents: personal videos without online metadata
             "language": d.get("language", ""),  # metadata language of the library, e.g. "de-DE"
             "locations": [loc["path"] for loc in d.get("Location", [])]}
            for d in data.get("Directory", [])
        ]

    def sample_files(self, section: dict, count: int = 8) -> list[str]:
        """Paths (as the server sees them) of a few video files of a library - for checking a path mapping."""
        leaf_type = 4 if section["type"] == "show" else 1  # episodes / movies
        data = self._get(f"/library/sections/{section['key']}/all", type=leaf_type,
                         **{"X-Plex-Container-Start": 0, "X-Plex-Container-Size": count})
        files = []
        for item in data.get("MediaContainer", {}).get("Metadata", []):
            for media in item.get("Media", []):
                for part in media.get("Part", []):
                    if part.get("file"):
                        files.append(part["file"])
        return files

    @staticmethod
    def _basename(server_path: str) -> str:
        return server_path.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1].lower()

    @staticmethod
    def _join(server_root: str, rel: Path) -> str:
        sep = "\\" if re.match(r"^[A-Za-z]:\\", server_root) or server_root.startswith("\\\\") else "/"
        return sep.join([server_root.rstrip("\\/"), *rel.parts])

    def _targets(self, lib: LibraryMap, sections: list[dict]) -> list[tuple[dict, str]]:
        if lib.section_key and lib.server_root:
            s = next((s for s in sections if s["key"] == lib.section_key), None)
            return [(s, lib.server_root)] if s else []
        name = lib.local_root.name.lower()
        return [(s, loc) for s in sections for loc in s["locations"] if self._basename(loc) == name]

    def refresh(self, changed: set[Path], libs: list[LibraryMap], full: bool = False) -> list[str]:
        """Scan only the touched movie/show folders in their Plex library."""
        sections = self.sections()
        msgs: list[str] = []
        for lib in libs:
            root = lib.local_root
            mine = [p for p in changed if p == root or root in p.parents]
            if not mine:
                continue
            targets = self._targets(lib, sections)
            if not targets:
                msgs.append(f"Keine Plex-Bibliothek für „{root}“ gefunden – bitte in den Einstellungen zuordnen "
                            f"oder manuell scannen.")
                continue
            for s, server_root in targets:
                if full:
                    self._get(f"/library/sections/{s['key']}/refresh")
                    msgs.append(f"Plex: Bibliothek „{s['title']}“ wird komplett gescannt")
                    continue
                tops = {root / p.relative_to(root).parts[0] for p in mine if p != root}
                for top in sorted(tops):
                    self._get(f"/library/sections/{s['key']}/refresh",
                              path=self._join(server_root, top.relative_to(root)))
                    msgs.append(f"Plex: scanne {s['title']} › {top.name}")
        return msgs
