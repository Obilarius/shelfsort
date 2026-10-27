"""Prominent progress panel shown while a plan is being executed."""
from __future__ import annotations

import time
from collections import deque

from PySide6.QtCore import Signal, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout

from .executor import TransferInfo
from .i18n import tr


def fmt_bytes(n: float) -> str:
    for unit, size in (("GB", 1024 ** 3), ("MB", 1024 ** 2), ("KB", 1024)):
        if n >= size:
            return f"{n / size:.1f} {unit}".replace(".", ",")
    return f"{int(n)} B"


def fmt_duration(sec: float) -> str:
    sec = int(sec)
    if sec < 60:
        return f"{sec} s"
    if sec < 3600:
        return f"{sec // 60}:{sec % 60:02d} min"
    return f"{sec // 3600}:{sec % 3600 // 60:02d} h"


class TransferPanel(QFrame):
    cancel_requested = Signal()
    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("transferPanel")
        # explicit bar styling: the Windows 11 style draws progress bars as thin lines
        self.setStyleSheet("""
            #transferPanel { border: 1px solid palette(mid); border-radius: 6px; }
            QProgressBar { border: 1px solid palette(mid); border-radius: 5px; background: palette(base);
                           text-align: center; }
            QProgressBar::chunk { background-color: palette(highlight); border-radius: 4px; }
            QProgressBar#overall { min-height: 22px; max-height: 22px; font-weight: bold; }
            QProgressBar#file { min-height: 6px; max-height: 6px; }
        """)

        self.title = QLabel()
        f = QFont(self.title.font())
        f.setPointSizeF(f.pointSizeF() * 1.1)
        f.setBold(True)
        self.title.setFont(f)

        self.overall = QProgressBar()
        self.overall.setObjectName("overall")
        self.overall.setRange(0, 1000)
        self.file_bar = QProgressBar()
        self.file_bar.setObjectName("file")
        self.file_bar.setTextVisible(False)
        self.file_bar.setRange(0, 1000)
        self.file_label = QLabel()
        self.file_label.setStyleSheet("color: gray")
        self.stats = QLabel()
        self.stats.setStyleSheet("color: gray")

        self.cancel_btn = QPushButton(tr("Abbrechen"))
        self.cancel_btn.setToolTip(tr("Laufende Kopie wird verworfen, das Original bleibt. Rest wird nicht angefasst."))
        self.cancel_btn.clicked.connect(self._cancel)
        self.close_btn = QPushButton(tr("Schließen"))
        self.close_btn.clicked.connect(self._close)

        # row 1: what is happening, numbers, button - row 2: overall bar - row 3: current file
        head = QHBoxLayout()
        head.addWidget(self.title)
        head.addSpacing(12)
        head.addWidget(self.stats, 1)
        head.addWidget(self.cancel_btn)
        head.addWidget(self.close_btn)
        file_row = QHBoxLayout()
        file_row.addWidget(self.file_label)
        file_row.addWidget(self.file_bar, 1)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(6)
        lay.addLayout(head)
        lay.addWidget(self.overall)
        lay.addLayout(file_row)
        self.hide()

    # --- lifecycle ---

    def start(self, count: int) -> None:
        self.count = count
        self.done = self.failed = 0
        self.t0 = time.monotonic()
        self.samples: deque[tuple[float, int]] = deque()
        self.last: TransferInfo | None = None
        self.title.setText(tr("Übertrage {count} Einträge …", count=count))
        self.overall.setValue(0)
        self.overall.setFormat("0 %")
        self.file_bar.setValue(0)
        self.file_label.setText("")
        self.stats.setText("")
        self.cancel_btn.setEnabled(True)
        self.cancel_btn.show()
        self.close_btn.hide()
        self.show()

    def item_finished(self, state: str) -> None:
        if state == "done":
            self.done += 1
        elif state == "error":
            self.failed += 1
        self._refresh_stats()
        if not (self.last and self.last.all_total):
            self._set_overall((self.done + self.failed) / max(self.count, 1))

    @Slot(object)
    def update_transfer(self, info: TransferInfo) -> None:
        self.last = info
        self.title.setText(tr("Datei {n} von {total}", n=info.item_no, total=info.item_count))
        self.file_label.setText(
            f"{info.name}   ·   {fmt_bytes(info.file_done)} / {fmt_bytes(info.file_total)}")
        self.file_bar.setValue(int(info.file_done * 1000 / info.file_total) if info.file_total else 1000)
        if info.all_total:
            now = time.monotonic()
            self.samples.append((now, info.all_done))
            while len(self.samples) > 2 and now - self.samples[0][0] > 8:
                self.samples.popleft()
            self._set_overall(info.all_done / info.all_total,
                              f"{fmt_bytes(info.all_done)} / {fmt_bytes(info.all_total)}")
        else:
            self._set_overall((info.item_no - 1) / max(info.item_count, 1))
        self._refresh_stats()

    def finish(self, cancelled: bool) -> str:
        elapsed = fmt_duration(time.monotonic() - self.t0)
        if cancelled:
            text = tr("Abgebrochen – {done} erledigt, Rest unverändert ({elapsed})", done=self.done, elapsed=elapsed)
        else:
            text = tr("Fertig – {done} erledigt, {failed} Fehler ({elapsed})", done=self.done, failed=self.failed,
                      elapsed=elapsed)
            self._set_overall(1.0, fmt_bytes(self.last.all_total) if self.last and self.last.all_total else "")
            self.file_bar.setValue(1000)
        self.title.setText(text)
        self.stats.setText("")
        self.cancel_btn.hide()
        self.close_btn.show()
        return text

    # --- helpers ---

    def percent(self) -> int:
        return self.overall.value() // 10

    def _set_overall(self, frac: float, extra: str = "") -> None:
        self.overall.setValue(int(min(max(frac, 0), 1) * 1000))
        self.overall.setFormat(f"{int(frac * 100)} %" + (f"   ·   {extra}" if extra else ""))

    def _refresh_stats(self) -> None:
        parts = []
        info = self.last
        if info and info.all_total and len(self.samples) >= 2:
            (t0, b0), (t1, b1) = self.samples[0], self.samples[-1]
            if t1 > t0 and b1 > b0:
                speed = (b1 - b0) / (t1 - t0)
                parts.append(f"{fmt_bytes(speed)}/s")
                parts.append(tr("noch ca. {time}", time=fmt_duration((info.all_total - info.all_done) / speed)))
        parts.append(tr("{count} erledigt", count=self.done))
        if self.failed:
            parts.append(tr("{count} Fehler", count=self.failed))
        self.stats.setText("   ·   ".join(parts))

    def _cancel(self) -> None:
        self.cancel_btn.setEnabled(False)
        self.title.setText(tr("Breche ab …"))
        self.cancel_requested.emit()

    def _close(self) -> None:
        self.hide()
        self.closed.emit()
