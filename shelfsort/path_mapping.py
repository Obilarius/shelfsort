"""Finding where a Plex library folder (as the server sees it) lives on this computer.

The server may say "/data/movies" while the same folder is "X:\\plex_media\\movies" here. A candidate
is only trusted if real files of the library exist under it.
"""
from __future__ import annotations

import os
import string
from dataclasses import dataclass
from pathlib import Path


@dataclass
class MappingGuess:
    local_root: Path
    hits: int
    total: int

    @property
    def ok(self) -> bool:
        return self.total > 0 and self.hits == self.total


def _parts(server_path: str) -> list[str]:
    return [p for p in server_path.replace("\\", "/").split("/") if p and not p.endswith(":")]


def relative(server_file: str, server_root: str) -> list[str] | None:
    """'/data/movies/A (2020)/a.mkv', '/data/movies' -> ['A (2020)', 'a.mkv']"""
    f, r = _parts(server_file), _parts(server_root)
    if [p.lower() for p in f[:len(r)]] != [p.lower() for p in r]:
        return None
    return f[len(r):]


def verify(local_root: Path, server_root: str, samples: list[str]) -> MappingGuess:
    hits = 0
    for s in samples:
        rel = relative(s, server_root)
        if rel and local_root.joinpath(*rel).exists():
            hits += 1
    return MappingGuess(local_root, hits, len(samples))


def _drives() -> list[Path]:
    if os.name != "nt":
        return [Path("/")]
    return [Path(f"{d}:\\") for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]


def candidates(server_root: str) -> list[Path]:
    """Local folders that could be the server's library folder."""
    out: list[Path] = []
    direct = Path(server_root)
    if direct.is_dir():  # Plex runs on this computer, or the path is the same
        out.append(direct)
    parts = _parts(server_root)
    if not parts:
        return out
    for drive in _drives():
        # suffixes of the server path on every drive: /data/movies -> X:\data\movies, X:\movies
        for i in range(len(parts)):
            out.append(drive.joinpath(*parts[i:]))
        # one level deeper: X:\plex_media\movies
        try:
            for sub in drive.iterdir():
                if sub.is_dir() and not sub.name.startswith(("$", ".")):
                    out.append(sub / parts[-1])
        except OSError:
            pass
    seen, result = set(), []
    for c in out:
        key = str(c).lower()
        if key not in seen:
            seen.add(key)
            try:
                if c.is_dir():
                    result.append(c)
            except OSError:
                pass
    return result


def suggest(server_root: str, samples: list[str]) -> MappingGuess | None:
    """Best local folder for a server library folder, judged by how many sample files exist there."""
    best = None
    for c in candidates(server_root):
        guess = verify(c, server_root, samples)
        if best is None or guess.hits > best.hits:
            best = guess
        if guess.ok:
            break
    return best if best and best.hits else None
