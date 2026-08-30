"""
Ponte de threads entre o backend (worker threads) e a UI Qt (GUI thread).

Os callbacks do engine/runner são chamados de threads de trabalho. Em Qt, a UI só
pode ser tocada na GUI thread. Signals emitidos de outra thread são entregues via
fila na thread do receptor (Qt::QueuedConnection automática), então este QObject
serve de "marshaller": o backend emite, a UI recebe nos slots já na thread certa.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class EngineBridge(QObject):
    # (seq_id, state_name, step_idx)
    runner_update = Signal(str, str, int)
    # (seq_id, step_idx, elapsed, total)
    tick = Signal(str, int, float, float)
    # (msg, level)
    log_message = Signal(str, str)

    # ── adaptadores que o engine espera (callables) ─────────────────────────────

    def on_runner_update(self, seq_id: str, state_name: str, step_idx: int):
        self.runner_update.emit(seq_id, state_name, int(step_idx))

    def on_tick(self, seq_id: str, step_idx: int, elapsed: float, total: float):
        self.tick.emit(seq_id, int(step_idx), float(elapsed), float(total))

    def on_log(self, msg: str, level: str = "info"):
        self.log_message.emit(str(msg), str(level))
