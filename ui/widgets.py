"""
Widgets reutilizáveis da UI (estética broadcast console).
"""
from __future__ import annotations

from datetime import datetime
from typing import Callable, Optional

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QTextCursor, QPixmap, QPainter
from PySide6.QtWidgets import (
    QWidget, QLabel, QLineEdit, QHBoxLayout, QVBoxLayout, QPlainTextEdit,
    QFrame, QSizePolicy,
)

from ui.theme import COLORS, STATE_COLORS, LEVEL_COLORS
from timeparse import parse_secs, fmt_hint


def form_field(widget: QWidget) -> QWidget:
    """
    Envolve um widget "cru" (QLineEdit/QComboBox/QSpinBox) num host com layout
    próprio, para uso como campo de QFormLayout.

    Contorna um bug do Qt/PySide6 em telas com escala fracionária do Windows
    (125%, 150%...): quando esses widgets são adicionados como campo direto de
    uma QFormLayout, a altura da linha é calculada errado e as linhas colapsam/
    sobrepõem. Um host com QHBoxLayout força o Qt a calcular a altura da linha
    pelo layout (correto) em vez do sizeHint do estilo (bugado nesse cenário).
    """
    host = QWidget()
    lay = QHBoxLayout(host)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.addWidget(widget)
    return host


def drag_handle() -> QLabel:
    """Alça de arraste ("≡") -- só ela inicia o arrastar-e-soltar da linha/
    card, pra clique em qualquer outro ponto não mover nada por engano."""
    h = QLabel("≡")
    h.setObjectName("drag_handle")
    h.setFixedWidth(20)
    h.setAlignment(Qt.AlignCenter)
    h.setCursor(Qt.OpenHandCursor)
    h.setStyleSheet(f"color:{COLORS['text_dim']}; font-size:15px; font-weight:700;")
    return h


class DragList(QWidget):
    """Lista vertical de cards com arrastar-e-soltar controlado na unha
    (mouse press/move/release), sem QListWidget nem QDrag do Qt.

    Histórico: a primeira versão usava QListWidget + arraste nativo do Qt
    (QAbstractItemView.InternalMove / QDrag). Mover os itens do MODELO ao
    vivo durante o arraste (pra abrir espaço conforme o cursor passa por
    cima) derruba o processo -- o Qt não sustenta uma QDrag ativa enquanto
    o modelo que a originou está sendo alterado por baixo. Aqui esse
    problema não existe: é só um QVBoxLayout normal, e reordenar widgets
    dentro de um layout durante um mouseMoveEvent é uma operação comum e
    segura do Qt -- sem QDrag envolvido em nenhum momento.

    O item arrastado literalmente some do fluxo (fica oculto) e um retrato
    seu (translúcido) acompanha o cursor; no lugar dele fica um espaçador
    do mesmo tamanho, que vai pulando de posição conforme o cursor passa
    por cima dos outros cards -- é isso que "abre espaço" ao vivo.

    Cada item precisa expor uma alça de arraste (ver drag_handle()) cujo
    mousePressEvent chame `drag_list.begin_drag(widget, global_pos)`.
    """

    reordered = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(6)
        # Absorve o espaço sobrando (ex.: dentro de um QScrollArea maior que
        # o conteúdo) -- sem isso, com só 1-2 cards, o Qt estica o último
        # pra preencher tudo, já que ele não tem "Fixed" como política
        # vertical. Precisa continuar sendo o ÚLTIMO item do layout sempre
        # -- add_item/begin_drag/mouseReleaseEvent inserem antes dele.
        self._lay.addStretch(1)
        self._items: list = []  # [(key, widget), ...] na ordem atual
        self._drag_key = None
        self._drag_widget: Optional[QWidget] = None
        self._drag_offset = None
        self._spacer: Optional[QWidget] = None
        self._ghost: Optional[QLabel] = None

    def set_spacing(self, px: int):
        self._lay.setSpacing(px)

    # ── conteúdo ─────────────────────────────────────────────────────────────

    def add_item(self, key, widget: QWidget):
        self._lay.insertWidget(len(self._items), widget)
        self._items.append((key, widget))

    def clear_items(self):
        for _, w in self._items:
            self._lay.removeWidget(w)
            w.deleteLater()
        self._items = []

    def remove_item(self, key) -> Optional[QWidget]:
        """Remove (sem destruir) o widget associado a `key`. Quem chamou é
        responsável por deletá-lo (mesmo padrão de QListWidget.takeItem)."""
        for i, (k, w) in enumerate(self._items):
            if k == key:
                self._items.pop(i)
                self._lay.removeWidget(w)
                return w
        return None

    def ordered_keys(self) -> list:
        return [k for k, _ in self._items]

    def count(self) -> int:
        return len(self._items)

    # ── arraste ──────────────────────────────────────────────────────────────

    def begin_drag(self, widget: QWidget, global_pos):
        if self._drag_widget is not None:
            return
        index = -1
        key = None
        for i, (k, w) in enumerate(self._items):
            if w is widget:
                key, index = k, i
                break
        if index == -1:
            return

        self._drag_key = key
        self._drag_widget = widget
        self._drag_offset = widget.mapFromGlobal(global_pos)

        pm = widget.grab()
        ghost_pm = QPixmap(pm.size())
        ghost_pm.fill(Qt.transparent)
        painter = QPainter(ghost_pm)
        painter.setOpacity(0.85)
        painter.drawPixmap(0, 0, pm)
        painter.end()

        self._ghost = QLabel(self.window())
        self._ghost.setPixmap(ghost_pm)
        self._ghost.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._ghost.setAttribute(Qt.WA_ShowWithoutActivating)
        self._ghost.resize(pm.size())
        self._position_ghost(global_pos)
        self._ghost.show()
        self._ghost.raise_()

        self._spacer = QWidget()
        self._spacer.setFixedHeight(widget.height())
        self._lay.removeWidget(widget)
        self._lay.insertWidget(index, self._spacer)
        widget.hide()

        self.grabMouse()

    def _position_ghost(self, global_pos):
        if self._ghost is None:
            return
        top_left = self.window().mapFromGlobal(global_pos - self._drag_offset)
        self._ghost.move(top_left)

    def _update_spacer_position(self, global_pos):
        if self._spacer is None:
            return
        pos_in_self = self.mapFromGlobal(global_pos)
        # itemAt(i).widget() vem None para o addStretch() do fim -- precisa
        # excluir também, senão w.y()/w.height() abaixo quebra com
        # AttributeError.
        real_widgets = [
            self._lay.itemAt(i).widget()
            for i in range(self._lay.count())
            if self._lay.itemAt(i).widget() not in (None, self._spacer)
        ]
        target = len(real_widgets)
        for i, w in enumerate(real_widgets):
            mid = w.y() + w.height() // 2
            if pos_in_self.y() < mid:
                target = i
                break
        if self._lay.indexOf(self._spacer) != target:
            self._lay.removeWidget(self._spacer)
            self._lay.insertWidget(target, self._spacer)

    def mouseMoveEvent(self, e):
        if self._drag_widget is None:
            super().mouseMoveEvent(e)
            return
        gp = e.globalPosition().toPoint()
        self._position_ghost(gp)
        self._update_spacer_position(gp)
        e.accept()

    def mouseReleaseEvent(self, e):
        if self._drag_widget is None:
            super().mouseReleaseEvent(e)
            return
        self.releaseMouse()
        widget = self._drag_widget
        key = self._drag_key
        self._drag_widget = None
        self._drag_key = None

        if self._ghost is not None:
            self._ghost.deleteLater()
            self._ghost = None

        target = self._lay.count() - 1
        if self._spacer is not None:
            target = self._lay.indexOf(self._spacer)
            self._lay.removeWidget(self._spacer)
            self._spacer.deleteLater()
            self._spacer = None
        if target == -1:
            target = self._lay.count()

        self._lay.insertWidget(target, widget)
        widget.show()

        self._items = [(k, w) for k, w in self._items if w is not widget]
        self._items.insert(target, (key, widget))

        e.accept()
        self.reordered.emit()


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
