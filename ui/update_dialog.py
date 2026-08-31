"""
Dialog de atualização disponível (Qt). Integra com Updater.apply_update.
"""
from __future__ import annotations

import threading

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextBrowser, QPushButton,
    QProgressBar,
)

from ui.theme import COLORS


class UpdateDialog(QDialog):
    # download roda em thread de background (Updater.apply_update) -- o
    # progresso precisa chegar na GUI thread via signal (thread-safe), nunca
    # tocando os widgets direto de outra thread (QTimer.singleShot chamado de
    # fora da GUI thread não é seguro e podia derrubar o processo no meio do
    # download de arquivos grandes).
    _progress_changed = Signal(int)

    def __init__(self, parent, update_info, on_confirm):
        super().__init__(parent)
        self._info = update_info
        self._on_confirm = on_confirm
        self._downloading = False
        self._progress_changed.connect(self._on_progress)

        self.setWindowTitle("Atualização Disponível")
        self.setMinimumSize(500, 400)
        self.setStyleSheet(parent.styleSheet() if parent else "")
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(8)

        title = QLabel("🚀  Nova versão disponível!")
        title.setObjectName("h1")
        lay.addWidget(title)
        sub = QLabel(f"v{self._info.version} está pronta para instalar.")
        sub.setObjectName("muted")
        lay.addWidget(sub)

        notes = QTextBrowser()
        notes.setPlainText(self._info.notes or "Sem notas de versão.")
        lay.addWidget(notes, 1)

        self._progress_lbl = QLabel("")
        self._progress_lbl.setObjectName("dim")
        lay.addWidget(self._progress_lbl)
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.hide()
        lay.addWidget(self._progress)

        btns = QHBoxLayout()
        btns.addStretch(1)
        later = QPushButton("Agora não")
        later.setObjectName("ghost")
        later.clicked.connect(self.reject)
        self._go = QPushButton("⬇  Baixar e Instalar")
        self._go.setObjectName("primary")
        self._go.clicked.connect(self._start)
        btns.addWidget(later)
        btns.addWidget(self._go)
        lay.addLayout(btns)

    def _start(self):
        if self._downloading:
            return
        self._downloading = True
        self._go.setEnabled(False)
        self._go.setText("Baixando…")
        self._progress.show()

        threading.Thread(
            target=lambda: self._on_confirm(self._info, self._progress_changed.emit),
            daemon=True, name="updater-apply",
        ).start()

    def _on_progress(self, pct: int):
        self._progress.setValue(pct)
        self._progress_lbl.setText(f"Baixando… {pct}%")
