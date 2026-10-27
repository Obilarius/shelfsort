"""Small visual building blocks shared by the windows: status badges, primary buttons, empty-table hints."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPalette
from PySide6.QtWidgets import (QApplication, QProxyStyle, QPushButton, QStyle, QStyledItemDelegate,
                               QStyleOptionViewItem, QTableWidget)

PRIMARY_QSS = """
QPushButton#primary {
    background: palette(highlight); color: palette(highlighted-text);
    border: 1px solid palette(highlight); border-radius: 4px; padding: 5px 16px; font-weight: 600;
}
QPushButton#primary:hover { background: palette(link); border-color: palette(link); }
QPushButton#primary:disabled { background: palette(mid); border-color: palette(mid); color: palette(base); }
"""


def primary(button: QPushButton) -> QPushButton:
    """The one main action of a screen ("Scan", "Transfer"): filled with the accent colour."""
    button.setObjectName("primary")
    return button


class TableDelegate(QStyledItemDelegate):
    """A table row drawn as one item (Windows 11 otherwise marks every cell of the selected row), and
    the status columns as rounded badges in their colour instead of filled cells."""

    def __init__(self, parent=None, badge_columns: tuple[int, ...] = ()):
        super().__init__(parent)
        self.badge_columns = badge_columns

    def paint(self, painter: QPainter, option, index) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.state &= ~QStyle.State_HasFocus
        # the selection as a plain tint over the whole row (see RowStyle)
        if opt.state & QStyle.State_Selected:
            opt.state &= ~QStyle.State_Selected
            tint = QColor(opt.palette.color(QPalette.Highlight))
            tint.setAlpha(70)
            painter.fillRect(opt.rect, tint)
        col = index.column()
        widget = opt.widget
        style = widget.style() if widget else QApplication.style()
        if col not in self.badge_columns:
            style.drawControl(QStyle.CE_ItemViewItem, opt, painter, widget)
            return
        brush = index.data(Qt.BackgroundRole)
        color = brush.color() if isinstance(brush, QBrush) else None
        # selection/hover background without the cell colour, then the badge on top
        text = opt.text
        opt.text = ""
        opt.backgroundBrush = QBrush(Qt.NoBrush)
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, widget)
        if not text:
            return
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        fm = opt.fontMetrics
        w, h = fm.horizontalAdvance(text) + 14, fm.height() + 4
        r = QRectF(opt.rect.x() + 4, opt.rect.center().y() - h / 2 + 1, w, h)
        if color is not None and color.alpha():
            fill = QColor(color)
            fill.setAlpha(min(255, color.alpha() * 2))  # the table colours are faint; badges may be bolder
            painter.setPen(Qt.NoPen)
            painter.setBrush(fill)
            painter.drawRoundedRect(r, h / 2, h / 2)
        painter.setPen(opt.palette.color(QPalette.Text))
        painter.drawText(r, Qt.AlignCenter, text)
        painter.restore()

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        if index.column() in self.badge_columns:
            size.setWidth(size.width() + 18)
        return size


class RowStyle(QProxyStyle):
    """Windows 11 paints a row panel with an accent mark behind every cell of a selected table row -
    in a table that reads as a stray bar in front of each value. The delegate draws the selection."""

    def drawPrimitive(self, element, option, painter, widget=None) -> None:
        if element == QStyle.PE_PanelItemViewRow:
            return
        super().drawPrimitive(element, option, painter, widget)


def setup_table(table: QTableWidget, badge_columns: tuple[int, ...] = ()) -> None:
    style = RowStyle()
    style.setParent(table)  # the table does not own a style set with setStyle
    table.setStyle(style)
    table.setItemDelegate(TableDelegate(table, badge_columns))


class HintTable(QTableWidget):
    """Table that says what to do while it is empty."""

    hint = ""

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self.rowCount() or not self.hint:
            return
        p = QPainter(self.viewport())
        color = self.palette().color(QPalette.Text)
        color.setAlpha(120)
        p.setPen(color)
        p.drawText(self.viewport().rect().adjusted(40, 0, -40, 0), Qt.AlignCenter | Qt.TextWordWrap, self.hint)
        p.end()
