"""
Janela principal Qt — AutoTrigger V10 (estética broadcast console).

Layout em janela única:
  ┌ top bar: logo · monitor · versão/update ─────────────────────┐
  ├ sidebar (sequências) │ stack: detalhe / config global ───────┤
  ├ log em tempo real (rodapé) ──────────────────────────────────┤
  └──────────────────────────────────────────────────────────────┘
"""
from __future__ import annotations

import os
import sys
from typing import Dict, Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QStackedWidget, QScrollArea, QSplitter,
)

from version import __version__
from timeparse import fmt_secs
from ui.theme import COLORS, STATE_COLORS
from ui.widgets import LogView, StatusDot, hline
from ui.sequence_detail import SequenceDetail
from ui.global_settings import GlobalSettings


def _asset_icon() -> Optional[QIcon]:
    base = sys._MEIPASS if getattr(sys, "frozen", False) else \
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ico = os.path.join(base, "assets", "icon.ico")
    return QIcon(ico) if os.path.exists(ico) else None


class SequenceCard(QFrame):
    """Card de sequência na sidebar."""
    def __init__(self, seq: dict, on_click):
        super().__init__()
        self.setObjectName("raised")
        self._sid = seq["id"]
        self._on_click = on_click
        self.setCursor(Qt.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(8)
        self._dot = StatusDot("idle")
        lay.addWidget(self._dot)
        col = QVBoxLayout(); col.setSpacing(0)
        self._name = QLabel(seq.get("name", ""))
        self._name.setStyleSheet("font-weight:700;")
        self._kw = QLabel(f"⌁ {seq.get('keyword_trigger','')}")
        self._kw.setObjectName("dim")
        col.addWidget(self._name); col.addWidget(self._kw)
        lay.addLayout(col, 1)
        self._selected = False
        self._armed = True
        self._repaint()

    def mousePressEvent(self, _e):
        self._on_click(self._sid)

    def set_selected(self, v: bool):
        self._selected = v
        self._repaint()

    def set_state(self, state: str):
        self._dot.set_state(state)

    def set_armed(self, armed: bool):
        self._armed = armed
        kw = self._kw.text().split("  ·")[0]
        self._kw.setText(kw if armed else kw + "  · fora de agenda")
        self._kw.setStyleSheet(
            f"color:{COLORS['text_dim'] if armed else COLORS['warn']}; font-size:11px;")

    def update_seq(self, seq: dict):
        self._name.setText(seq.get("name", ""))
        self._kw.setText(f"⌁ {seq.get('keyword_trigger','')}")

    def _repaint(self):
        bg = COLORS["bg3"] if self._selected else COLORS["bg2"]
        border = COLORS["cyan"] if self._selected else COLORS["border"]
        self.setStyleSheet(
            f"QFrame#raised {{ background:{bg}; border:1px solid {border};"
            f" border-radius:10px; }}")


class MainWindow(QMainWindow):
    def __init__(self, config, engine, player):
        super().__init__()
        self._config = config
        self._engine = engine
        self._player = player
        self._cards: Dict[str, SequenceCard] = {}
        self._selected_id: Optional[str] = None
        self._pending_update = None
        self._updater = None
        self._quit_fn = None

        self.setWindowTitle("AutoTrigger V10")
        self.resize(1040, 720)
        self.setMinimumSize(880, 560)
        ico = _asset_icon()
        if ico:
            self.setWindowIcon(ico)

        self._build()
        self._load_sequences()
        QTimer.singleShot(150, self._apply_output_device)
        QTimer.singleShot(500, self._auto_start_monitor)
        QTimer.singleShot(3000, self._init_updater)
        QTimer.singleShot(600_000, self._daily_recheck)

    # ── build ───────────────────────────────────────────────────────────────────

    def _build(self):
        root = QWidget(); root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._build_topbar())

        # corpo: splitter sidebar | stack
        body = QSplitter(Qt.Horizontal)
        body.setHandleWidth(1)
        body.addWidget(self._build_sidebar())
        self._stack = QStackedWidget()
        self._detail = SequenceDetail(
            self._config, self._engine, self._on_seq_changed,
            on_deleted=self._delete_sequence,
            on_duplicated=self._duplicate_sequence,
        )
        self._global = GlobalSettings(self._config, self._on_global_saved, log=self.on_log)
        self._placeholder = self._build_placeholder()
        self._stack.addWidget(self._placeholder)   # 0
        self._stack.addWidget(self._detail)        # 1
        self._stack.addWidget(self._global)        # 2
        body.addWidget(self._stack)
        body.setStretchFactor(0, 0)
        body.setStretchFactor(1, 1)
        body.setSizes([260, 780])
        outer.addWidget(body, 1)

        # log
        outer.addWidget(self._build_logdock())

        # status bar
        self.statusBar().showMessage("Pronto.")
        self.statusBar().setStyleSheet(
            f"color:{COLORS['text_dim']}; background:{COLORS['bg1']};"
            f" border-top:1px solid {COLORS['border']};")

    def _build_topbar(self) -> QWidget:
        bar = QFrame(); bar.setObjectName("topbar"); bar.setFixedHeight(56)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 8, 12, 8)
        logo = QLabel("⚡  AutoTrigger V10")
        logo.setObjectName("h1")
        lay.addWidget(logo)
        credit = QLabel("by RobsonDV")
        credit.setObjectName("dim")
        lay.addWidget(credit, alignment=Qt.AlignBottom)
        lay.addStretch(1)

        self._monitor_dot = StatusDot("error")
        self._monitor_lbl = QLabel("Monitor parado")
        self._monitor_lbl.setObjectName("muted")
        self._monitor_btn = QPushButton("▶  Iniciar Monitor")
        self._monitor_btn.setObjectName("success")
        self._monitor_btn.clicked.connect(self._toggle_monitor)
        lay.addWidget(self._monitor_dot)
        lay.addWidget(self._monitor_lbl)
        lay.addSpacing(8)
        lay.addWidget(self._monitor_btn)
        lay.addSpacing(12)

        self._update_btn = QPushButton(f"v{__version__}")
        self._update_btn.setObjectName("ghost")
        self._update_btn.clicked.connect(self._check_updates_manual)
        lay.addWidget(self._update_btn)
        return bar

    def _build_sidebar(self) -> QWidget:
        side = QFrame(); side.setObjectName("sidebar")
        side.setMinimumWidth(220); side.setMaximumWidth(360)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(10, 12, 10, 10)
        lay.setSpacing(8)
        title = QLabel("SEQUÊNCIAS"); title.setObjectName("section")
        lay.addWidget(title)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        host = QWidget()
        self._cards_box = QVBoxLayout(host)
        self._cards_box.setContentsMargins(0, 0, 0, 0)
        self._cards_box.setSpacing(6)
        self._cards_box.addStretch(1)
        scroll.setWidget(host)
        lay.addWidget(scroll, 1)

        new_btn = QPushButton("＋  Nova Sequência")
        new_btn.setObjectName("primary")
        new_btn.clicked.connect(self._new_sequence)
        lay.addWidget(new_btn)

        cfg_btn = QPushButton("⚙  Configurações Globais")
        cfg_btn.clicked.connect(self._show_global)
        lay.addWidget(cfg_btn)
        return side

    def _build_placeholder(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addStretch(1)
        msg = QLabel("Selecione uma sequência à esquerda\nou crie uma nova.")
        msg.setObjectName("dim")
        msg.setAlignment(Qt.AlignCenter)
        lay.addWidget(msg)
        lay.addStretch(1)
        return w

    def _build_logdock(self) -> QWidget:
        wrap = QFrame()
        wrap.setStyleSheet(f"background:{COLORS['bg1']}; border-top:1px solid {COLORS['border']};")
        wrap.setFixedHeight(180)
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(10, 6, 10, 8)
        lay.setSpacing(4)
        head = QLabel("📋  Log em tempo real")
        head.setObjectName("dim")
        lay.addWidget(head)
        self._log = LogView()
        lay.addWidget(self._log, 1)
        return wrap

    # ── engine signal slots (chamados via bridge na GUI thread) ──────────────────

    def on_runner_update(self, seq_id: str, state_name: str, step_idx: int):
        if seq_id in self._cards:
            self._cards[seq_id].set_state(state_name)
        if self._selected_id == seq_id and self._stack.currentWidget() is self._detail:
            self._detail.set_runner_state(state_name, step_idx)

    def on_tick(self, seq_id: str, step_idx: int, elapsed: float, total: float):
        if self._selected_id == seq_id and self._stack.currentWidget() is self._detail:
            self._detail.set_tick(step_idx, elapsed, total)

    def on_log(self, msg: str, level: str = "info"):
        self._log.append_line(msg, level)

    # ── sequences ────────────────────────────────────────────────────────────────

    def _load_sequences(self):
        # limpa
        for c in self._cards.values():
            c.deleteLater()
        self._cards.clear()
        seqs = self._config.get_sequences()
        for seq in seqs:
            self._add_card(seq)
        self._refresh_armed()
        if seqs:
            self._select_seq(seqs[0]["id"])
        else:
            self._stack.setCurrentWidget(self._placeholder)

    def _add_card(self, seq: dict):
        card = SequenceCard(seq, self._select_seq)
        # insere antes do stretch
        self._cards_box.insertWidget(self._cards_box.count() - 1, card)
        self._cards[seq["id"]] = card

    def _select_seq(self, seq_id: str):
        seq = self._config.get_sequence_by_id(seq_id)
        if not seq:
            return
        for sid, card in self._cards.items():
            card.set_selected(sid == seq_id)
        self._selected_id = seq_id
        self._detail.set_sequence(seq)
        self._stack.setCurrentWidget(self._detail)
        runner = self._engine.get_runner(seq_id)
        if runner:
            self._detail.set_runner_state(runner.state.value, runner.current_step)

    def _new_sequence(self):
        seq = self._config.new_sequence_template()
        self._config.add_sequence(seq)
        self._config.save()
        self._engine.reload_sequences()
        self._add_card(seq)
        self._refresh_armed()
        self._select_seq(seq["id"])
        self.on_log("Nova sequência criada — defina nome, keyword e etapas.", "success")

    def _duplicate_sequence(self, seq_id: str):
        import copy, uuid
        orig = self._config.get_sequence_by_id(seq_id)
        if not orig:
            return
        dup = copy.deepcopy(orig)
        dup["id"] = str(uuid.uuid4())[:8]
        dup["name"] = orig.get("name", "Sequência") + " (cópia)"
        self._config.add_sequence(dup)
        self._config.save()
        self._engine.reload_sequences()
        self._add_card(dup)
        self._refresh_armed()
        self._select_seq(dup["id"])
        self.on_log(f"Sequência duplicada: '{dup['name']}'.", "success")

    def _delete_sequence(self, seq_id: str):
        seq = self._config.get_sequence_by_id(seq_id)
        name = seq.get("name", seq_id) if seq else seq_id
        self._engine.cancel(seq_id)
        self._config.delete_sequence(seq_id)
        self._config.save()
        self._engine.reload_sequences()
        if seq_id in self._cards:
            self._cards[seq_id].deleteLater()
            del self._cards[seq_id]
        self._selected_id = None
        self.on_log(f"Sequência excluída: '{name}'.", "warn")
        remaining = self._config.get_sequences()
        if remaining:
            self._select_seq(remaining[0]["id"])
        else:
            self._stack.setCurrentWidget(self._placeholder)

    def _on_seq_changed(self, seq: dict):
        if seq["id"] in self._cards:
            self._cards[seq["id"]].update_seq(seq)
        self._refresh_armed()

    def _refresh_armed(self):
        for seq in self._config.get_sequences():
            if seq["id"] in self._cards:
                self._cards[seq["id"]].set_armed(self._engine.is_seq_armed_today(seq))

    def _show_global(self):
        for card in self._cards.values():
            card.set_selected(False)
        self._selected_id = None
        self._global._load()
        self._stack.setCurrentWidget(self._global)

    def _on_global_saved(self):
        self.on_log("Configurações globais salvas.", "success")
        self._engine.reload_sequences()
        self._apply_output_device()
        self._refresh_armed()

    # ── monitor ──────────────────────────────────────────────────────────────────

    def _apply_output_device(self):
        dev = self._config.get_global().get("default_output_device_id", "")
        if dev:
            try:
                self._player.set_output_device(dev)
            except Exception:
                pass

    def _auto_start_monitor(self):
        if self._config.get_global().get("txt_file_path", ""):
            self._do_start_monitor()

    def _toggle_monitor(self):
        if self._engine.is_monitor_running():
            self._engine.stop_monitor()
            self._monitor_btn.setText("▶  Iniciar Monitor")
            self._monitor_btn.setObjectName("success")
            self._monitor_btn.setStyleSheet("")  # reaplica QSS por objectName
            self._monitor_dot.set_state("error")
            self._monitor_lbl.setText("Monitor parado")
            self.on_log("Monitor parado.", "warn")
        else:
            self._do_start_monitor()
        self._restyle(self._monitor_btn)

    def _do_start_monitor(self):
        if self._engine.start_monitor():
            self._monitor_btn.setText("⏹  Parar Monitor")
            self._monitor_btn.setObjectName("danger")
            self._monitor_dot.set_state("running")
            self._monitor_lbl.setText("Monitor ativo")
            self.on_log(f"Monitor ativo: {self._config.get_global().get('txt_file_path','')}",
                        "success")
        else:
            self.on_log("Falha ao iniciar monitor. Verifique o caminho do TXT.", "error")
        self._restyle(self._monitor_btn)

    @staticmethod
    def _restyle(w):
        w.style().unpolish(w); w.style().polish(w)

    def _daily_recheck(self):
        try:
            self._engine.reload_sequences()
            self._refresh_armed()
        finally:
            QTimer.singleShot(600_000, self._daily_recheck)

    # ── updater ──────────────────────────────────────────────────────────────────

    def _init_updater(self):
        try:
            from updater import Updater
            self._updater = Updater(log_callback=self.on_log)
            self._updater.check_async(
                on_update_available=lambda info: self._show_update_badge(info)
            )
        except Exception as exc:
            self.on_log(f"Auto-update: {exc}", "warn")

    def _show_update_badge(self, info):
        self._pending_update = info
        self._update_btn.setText(f"🔔 v{info.version} disponível")
        self._update_btn.setObjectName("primary")
        self._restyle(self._update_btn)

    def _check_updates_manual(self):
        if self._pending_update:
            self._open_update_dialog(self._pending_update)
            return
        if not self._updater:
            return
        self._update_btn.setText("Verificando…")
        self._updater.check_async(
            on_update_available=lambda info: [self._show_update_badge(info),
                                              self._open_update_dialog(info)],
            on_up_to_date=lambda: self._update_btn.setText(f"v{__version__} ✓"),
            on_error=lambda _e: self._update_btn.setText(f"v{__version__}"),
        )

    def _open_update_dialog(self, info):
        from ui.update_dialog import UpdateDialog
        UpdateDialog(self, info, on_confirm=self._updater.apply_update).exec()

    # ── lifecycle ────────────────────────────────────────────────────────────────

    def log(self, msg: str, level: str = "info"):
        self.on_log(msg, level)

    def closeEvent(self, event):
        # Fecha para a bandeja (não encerra). main.py controla o quit real via tray.
        event.ignore()
        self.hide()
