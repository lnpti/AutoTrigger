"""
Widgets reutilizáveis da UI (estética broadcast console).
"""
from __future__ import annotations

from datetime import datetime
from typing import Callable, Optional

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QWidget, QLabel, QLineEdit, QHBoxLayout, QVBoxLayout, QPlainTextEdit,
    QFrame, QSizePolicy,
)

from ui.theme import COLORS, STATE_COLORS, LEVEL_COLORS
from timeparse import parse_secs, fmt_hint


def hline() -> QFrame:
    ln = QFrame()
    ln.setFrameShape(QFrame.HLine)
    ln.setStyleSheet(f"color:{COLORS['border']}; background:{COLORS['border']}; max-height:1px;")
    return ln


class StatusDot(QLabel):
    """Bolinha colorida de estado."""
    def __init__(self, state: str = "idle"):
        super().__init__("●")
        self.setFixedWidth(16)
        self.set_state(state)

    def set_state(self, state: str):
        self.setStyleSheet(f"color:{STATE_COLORS.get(state, COLORS['text_dim'])}; font-size:14px;")


class Chip(QLabel):
    """Etiqueta compacta (agenda, contagem de etapas, etc.)."""
    def __init__(self, text: str, color: Optional[str] = None):
        super().__init__(text)
        col = color or COLORS["cyan"]
        self.setStyleSheet(
            f"color:{col}; background:{COLORS['bg2']}; border:1px solid {COLORS['border2']};"
            f"border-radius:9px; padding:2px 9px; font-size:11px;"
        )
        self.setAlignment(Qt.AlignCenter)


class TimeField(QWidget):
    """
    Entrada de tempo flexível (h/m/s) com hint ao vivo do total interpretado.
    .seconds() -> int ; .set_seconds(int).
    """
    changed = Signal()

    def __init__(self, seconds: int = 0, placeholder: str = "ex: 15s, 1m 30s, 1h"):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self._edit = QLineEdit()
        self._edit.setPlaceholderText(placeholder)
        self._edit.setMaximumWidth(140)
        self._hint = QLabel()
        self._hint.setObjectName("dim")
        lay.addWidget(self._edit)
        lay.addWidget(self._hint)
        lay.addStretch(1)
        from timeparse import fmt_secs
        self._edit.setText(fmt_secs(seconds) if seconds else "")
        self._edit.textChanged.connect(self._refresh)
        self._refresh()

    def _refresh(self):
        secs = parse_secs(self._edit.text())
        col = COLORS["error"] if secs <= 0 else COLORS["green"]
        self._hint.setText(fmt_hint(secs))
        self._hint.setStyleSheet(f"color:{col}; font-size:11px;")
        self.changed.emit()

    def seconds(self) -> int:
        return parse_secs(self._edit.text())

    def set_seconds(self, s: int):
        from timeparse import fmt_secs
        self._edit.setText(fmt_secs(s) if s else "")


class LabeledRow(QWidget):
    """Rótulo à esquerda + widget à direita."""
    def __init__(self, label: str, field: QWidget, label_w: int = 110):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lab = QLabel(label)
        lab.setObjectName("muted")
        lab.setFixedWidth(label_w)
        lab.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        lay.addWidget(lab)
        lay.addWidget(field, 1)


class LogView(QPlainTextEdit):
    """Log colorido por nível, com timestamp."""
    def __init__(self):
        super().__init__()
        self.setObjectName("log")
        self.setReadOnly(True)
        self.setMaximumBlockCount(2000)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def append_line(self, msg: str, level: str = "info"):
        color = LEVEL_COLORS.get(level, COLORS["text_hi"])
        ts = datetime.now().strftime("%H:%M:%S")
        html = (
            f'<span style="color:{COLORS["text_dim"]}">[{ts}]</span> '
            f'<span style="color:{color}">{_esc(msg)}</span>'
        )
        self.appendHtml(html)
        self.moveCursor(QTextCursor.End)


def _esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
