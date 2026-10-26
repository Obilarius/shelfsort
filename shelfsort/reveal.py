"""Showing a file in the system's file manager and playing a video with the default player."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices

from .parse import is_video, walk_videos


def main_video(path: Path) -> Path | None:
    """The video a row is about: the file itself, or the first video in a folder."""
    if path.is_file():
        return path if is_video(path) else None
    if path.is_dir():
        videos = walk_videos(path)
        return videos[0] if videos else None
    return None


def show_in_folder(path: Path) -> None:
    """Open the file manager at the file (selected) or folder."""
    if not path.exists():
        path = next((p for p in path.parents if p.exists()), path)
    if sys.platform == "win32" and path.is_file():
        subprocess.Popen(["explorer", "/select,", str(path)])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(path)] if path.is_file() else ["open", str(path)])
    else:
        folder = path if path.is_dir() else path.parent
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))


def play(path: Path) -> bool:
    """Open a video with the default player; False if there is no video."""
    video = main_video(path)
    if not video:
        return False
    if sys.platform == "win32":
        os.startfile(str(video))  # noqa: S606 - the user's own file with their default player
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(video)))
    return True
