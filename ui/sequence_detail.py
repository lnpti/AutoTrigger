"""
Painel de detalhe da sequência — edição inline, sem pop-ups.

Página 0: visão/edição da sequência (nome, keyword, atraso, agenda, etapas, ações).
Página 1: editor de etapa (StepEditor) — exibido no mesmo painel.

A lista de etapas também é o "fluxo visual": durante a execução as linhas são
realçadas (ativa/concluída/erro).
"""
from __future__ import annotations

import copy
from datetime import datetime
from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QFrame, QStackedWidget, QButtonGroup,
    QRadioButton, QCheckBox, QSizePolicy,
)

from timeparse import fmt_secs, WEEKDAY_LABELS, is_armed_today
from ui.theme import COLORS, STEP_ICONS, STATE_COLORS
from ui.widgets import TimeField, StatusDot, Chip, hline
from ui.step_editor import StepEditor, _TYPE_LABELS

_STEP_BG = {"pending": COLORS["bg1"], "active": "#0d2a52",
            "done": "#0d3320", "error": "#3a0d18"}
_STEP_BORDER = {"pending": COLORS["border"], "active": COLORS["cyan"],
                "done": COLORS["green_dk"], "error": COLORS["error"]}

_STATE_TEXTS = {
    "idle":      ("● Aguardando", COLORS["text_dim"]),
    "running":   ("● Executando", COLORS["green"]),
    "done":      ("✓ Concluída",  COLORS["cyan"]),
    "error":     ("✗ Erro",       COLORS["error"]),
    "cancelled": ("⏹ Cancelado",  COLORS["warn"]),
}


class SequenceDetail(QWidget):
    def __init__(self, config, engine, on_changed: Callable,
                 on_deleted: Callable = None, on_duplicated: Callable = None):
        super().__init__()
        self._config = config
        self._engine = engine
        self._on_changed = on_changed
        self._on_deleted = on_deleted
        self._on_duplicated = on_duplicated
        self._seq: dict = {}
        self._step_rows: list = []
        self._editing_idx: Optional[int] = None
        self._build()

    # ── build ───────────────────────────────────────────────────────────────────

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._stack = QStackedWidget()
        outer.addWidget(self._stack)

        # Página 0 — view
        self._view = QScrollArea()
        self._view.setWidgetResizable(True)
        host = QWidget()
        self._stack.addWidget(self._view)
        self._view.setWidget(host)

        v = QVBoxLayout(host)
        v.setContentsMargins(18, 16, 18, 16)
        v.setSpacing(12)

        # Cabeçalho: nome + status + ações
        head = QHBoxLayout()
        self._name = QLineEdit()
        self._name.setPlaceholderText("Nome da sequência")
        self._name.setStyleSheet("font-size:17px; font-weight:700;")
        self._name.editingFinished.connect(self._save_fields)
        head.addWidget(self._name, 1)

        self._status = QLabel("")
        head.addWidget(self._status)
        v.addLayout(head)

        # Linha de ações
        actions = QHBoxLayout()
        self._run_btn = QPushButton("▶  Rodar agora")
        self._run_btn.setObjectName("success")
        self._run_btn.clicked.connect(self._run_now)
        self._rehearse_btn = QPushButton("🧪  Ensaio")
        self._rehearse_btn.clicked.connect(self._rehearse)
        self._cancel_btn = QPushButton("⏹  Cancelar")
        self._cancel_btn.setObjectName("danger")
        self._cancel_btn.clicked.connect(self._cancel)
        self._cancel_btn.hide()
        self._timer = QLabel("")
        self._timer.setStyleSheet(f"color:{COLORS['warn']}; font-weight:700;")
        actions.addWidget(self._run_btn)
        actions.addWidget(self._rehearse_btn)
        actions.addWidget(self._cancel_btn)
        actions.addSpacing(10)
        actions.addWidget(self._timer)
        actions.addStretch(1)
        self._dup_btn = QPushButton("⧉  Duplicar")
        self._dup_btn.setObjectName("ghost")
        self._dup_btn.setToolTip("Criar uma cópia desta sequência")
        self._dup_btn.clicked.connect(self._duplicate)
        self._del_seq_btn = QPushButton("🗑  Excluir")
        self._del_seq_btn.setObjectName("danger")
        self._del_seq_btn.setToolTip("Excluir esta sequência")
        self._del_seq_btn.clicked.connect(self._delete)
        actions.addWidget(self._dup_btn)
        actions.addWidget(self._del_seq_btn)
        v.addLayout(actions)

        v.addWidget(hline())

        # Gatilho + atraso
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)
        grid.addWidget(_lbl("Keyword (TXT)"), 0, 0)
        self._kw = QLineEdit()
        self._kw.setPlaceholderText("ex: ESPORTE")
        self._kw.editingFinished.connect(self._save_fields)
        grid.addWidget(self._kw, 0, 1)
        grid.addWidget(_lbl("Atraso após gatilho"), 1, 0)
        self._delay = TimeField(0)
        self._delay.changed.connect(self._save_fields_debounced)
        grid.addWidget(self._delay, 1, 1)
        self._enabled = QCheckBox("Sequência habilitada")
        self._enabled.stateChanged.connect(lambda _=0: self._save_fields())
        grid.addWidget(self._enabled, 2, 1)
        grid.setColumnStretch(1, 1)
        v.addLayout(grid)

        # Agenda
        v.addWidget(_section("📅  AGENDA"))
        self._sched = _ScheduleEditor(on_change=self._save_fields)
        v.addWidget(self._sched)

        # Etapas
        steps_bar = QHBoxLayout()
        steps_bar.addWidget(_section("ETAPAS"))
        steps_bar.addStretch(1)
        add = QPushButton("＋  Adicionar etapa")
        add.setObjectName("primary")
        add.clicked.connect(self._add_step)
        steps_bar.addWidget(add)
        v.addLayout(steps_bar)

        self._steps_host = QVBoxLayout()
        self._steps_host.setSpacing(6)
        steps_wrap = QWidget()
        steps_wrap.setLayout(self._steps_host)
        v.addWidget(steps_wrap)
        v.addStretch(1)

        # Página 1 — editor de etapa
        self._editor = StepEditor(on_done=self._step_editor_done)
        self._stack.addWidget(self._editor)

    # ── load ─────────────────────────────────────────────────────────────────────

    def set_sequence(self, seq: dict):
        self._seq = copy.deepcopy(seq)
        self._stack.setCurrentIndex(0)
        self._name.setText(seq.get("name", ""))
        self._kw.setText(seq.get("keyword_trigger", ""))
        self._delay.set_seconds(int(seq.get("trigger_delay_seconds", 0) or 0))
        self._enabled.blockSignals(True)
        self._enabled.setChecked(seq.get("enabled", True))
        self._enabled.blockSignals(False)
        self._sched.load(seq.get("schedule") or {"mode": "always"})
        self._rebuild_steps()
        self._set_status("idle", -1)

    def seq_id(self) -> str:
        return self._seq.get("id", "")

    # ── save ─────────────────────────────────────────────────────────────────────

    def _save_fields_debounced(self):
        # TimeField emite muito; salva direto (barato o suficiente)
        self._save_fields()

    def _save_fields(self):
        if not self._seq:
            return
        self._seq["name"] = self._name.text().strip() or "Sequência"
        self._seq["keyword_trigger"] = self._kw.text().strip().upper()
        self._seq["trigger_delay_seconds"] = self._delay.seconds()
        self._seq["enabled"] = self._enabled.isChecked()
        self._seq["schedule"] = self._sched.value()
        self._persist()

    def _persist(self):
        self._config.update_sequence(copy.deepcopy(self._seq))
        self._config.save()
        self._engine.reload_sequences()
        self._on_changed(self._seq)

    # ── steps ────────────────────────────────────────────────────────────────────

    def _rebuild_steps(self):
        while self._steps_host.count():
            item = self._steps_host.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._step_rows = []
        steps = self._seq.get("steps", [])
        if not steps:
            empty = QLabel("Nenhuma etapa. Clique em '＋ Adicionar etapa'.")
            empty.setObjectName("dim")
            self._steps_host.addWidget(empty)
            return
        for i, step in enumerate(steps):
            row = self._make_step_row(i, step, len(steps))
            self._steps_host.addWidget(row)
            self._step_rows.append(row)

    def _make_step_row(self, idx: int, step: dict, n: int) -> QFrame:
        f = QFrame()
        f.setObjectName("raised")
        lay = QHBoxLayout(f)
        lay.setContentsMargins(10, 7, 8, 7)
        lay.setSpacing(8)

        icon = STEP_ICONS.get(step.get("type", ""), "▸")
        num = QLabel(f"{idx + 1}")
        num.setObjectName("dim"); num.setFixedWidth(16)
        ic = QLabel(icon); ic.setFixedWidth(22)
        lay.addWidget(num); lay.addWidget(ic)

        info = QVBoxLayout(); info.setSpacing(0)
        label = QLabel(step.get("label") or step.get("type", "?"))
        label.setStyleSheet("font-weight:600;")
        sub = QLabel(f"{_TYPE_LABELS.get(step.get('type',''),'')}  ·  {_summary(step)}")
        sub.setObjectName("dim")
        info.addWidget(label); info.addWidget(sub)
        lay.addLayout(info, 1)

        for txt, slot, oid, tip in (
            ("▶", lambda: self._engine.test_step(step), "icon", "Testar esta etapa"),
            ("✎", lambda: self._edit_step(idx), "icon", "Editar etapa"),
            ("↑", lambda: self._move_step(idx, -1), "icon", "Mover para cima"),
            ("↓", lambda: self._move_step(idx, +1), "icon", "Mover para baixo"),
            ("✕", lambda: self._del_step(idx), "icon_danger", "Excluir etapa"),
        ):
            b = QPushButton(txt); b.setObjectName(oid)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            if txt == "↑" and idx == 0:
                b.setEnabled(False)
            if txt == "↓" and idx == n - 1:
                b.setEnabled(False)
            lay.addWidget(b)

        f._base_status = "pending"
        self._paint_row(f, "pending")
        return f

    def _paint_row(self, row: QFrame, status: str):
        row.setStyleSheet(
            f"QFrame#raised {{ background:{_STEP_BG[status]}; "
            f"border:1px solid {_STEP_BORDER[status]}; border-radius:10px; }}"
        )

    def _add_step(self):
        self._editing_idx = None
        self._editor.load_step({"type": "hotkey", "label": "Nova etapa"})
        self._stack.setCurrentIndex(1)

    def _edit_step(self, idx: int):
        steps = self._seq.get("steps", [])
        if 0 <= idx < len(steps):
            self._editing_idx = idx
            self._editor.load_step(steps[idx])
            self._stack.setCurrentIndex(1)

    def _step_editor_done(self, step: Optional[dict]):
        self._stack.setCurrentIndex(0)
        if step is None:
            return
        steps = self._seq.setdefault("steps", [])
        if self._editing_idx is None:
            steps.append(step)
        else:
            steps[self._editing_idx] = step
        self._persist()
        self._rebuild_steps()

    def _move_step(self, idx: int, d: int):
        steps = self._seq.get("steps", [])
        j = idx + d
        if 0 <= j < len(steps):
            steps[idx], steps[j] = steps[j], steps[idx]
            self._persist()
            self._rebuild_steps()

    def _del_step(self, idx: int):
        steps = self._seq.get("steps", [])
        if 0 <= idx < len(steps):
            del steps[idx]
            self._persist()
            self._rebuild_steps()

    # ── execução / actions ──────────────────────────────────────────────────────

    def _run_now(self):
        self._engine.run_now(self.seq_id())

    def _rehearse(self):
        self._engine.rehearse(self.seq_id())

    def _cancel(self):
        self._engine.cancel(self.seq_id())

    def _delete(self):
        from PySide6.QtWidgets import QMessageBox
        name = self._seq.get("name", "")
        resp = QMessageBox.question(
            self, "Excluir sequência",
            f"Excluir a sequência '{name}'?\nEsta ação não pode ser desfeita.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if resp == QMessageBox.Yes and self._on_deleted:
            self._on_deleted(self.seq_id())

    def _duplicate(self):
        if self._on_duplicated:
            self._on_duplicated(self.seq_id())

    # ── runtime updates (chamados pela MainWindow) ───────────────────────────────

    def set_runner_state(self, state_name: str, step_idx: int):
        self._set_status(state_name, step_idx)

    def set_tick(self, step_idx: int, elapsed: float, total: float):
        e_m, e_s = divmod(int(elapsed), 60)
        t_m, t_s = divmod(int(total), 60)
        prefix = "⏳ Atraso" if step_idx == -1 else "⏱"
        self._timer.setText(f"{prefix}  {e_m:02d}:{e_s:02d} / {t_m:02d}:{t_s:02d}")

    def _set_status(self, state: str, step_idx: int):
        txt, col = _STATE_TEXTS.get(state, ("", COLORS["text_dim"]))
        self._status.setText(txt)
        self._status.setStyleSheet(f"color:{col}; font-weight:600;")
        running = state == "running"
        self._cancel_btn.setVisible(running)
        self._run_btn.setVisible(not running)
        self._rehearse_btn.setVisible(not running)
        if not running:
            self._timer.setText("")
        # realça as linhas
        n = len(self._step_rows)
        for i, row in enumerate(self._step_rows):
            if state == "done" and step_idx >= n:
                self._paint_row(row, "done")
            elif i < step_idx:
                self._paint_row(row, "done")
            elif i == step_idx:
                self._paint_row(row, "error" if state == "error" else
                                ("pending" if state == "cancelled" else "active"))
            else:
                self._paint_row(row, "pending")


# ── editor de agenda ─────────────────────────────────────────────────────────────

class _ScheduleEditor(QFrame):
    def __init__(self, on_change: Callable):
        super().__init__()
        self.setObjectName("panel")
        self._on_change = on_change
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(8)

        modes = QHBoxLayout()
        self._group = QButtonGroup(self)
        self._radios = {}
        for val, txt in (("always", "Sempre"),
                         ("weekdays", "Dias da semana"),
                         ("dates", "Datas específicas")):
            r = QRadioButton(txt)
            self._radios[val] = r
            self._group.addButton(r)
            r.toggled.connect(self._on_mode)
            modes.addWidget(r)
        modes.addStretch(1)
        lay.addLayout(modes)

        self._wd_host = QWidget()
        wd = QHBoxLayout(self._wd_host)
        wd.setContentsMargins(0, 0, 0, 0)
        self._wd = []
        for lbl in WEEKDAY_LABELS:
            c = QCheckBox(lbl)
            c.stateChanged.connect(lambda _=0: self._on_change())
            self._wd.append(c)
            wd.addWidget(c)
        wd.addStretch(1)
        lay.addWidget(self._wd_host)

        self._dates_host = QWidget()
        dl = QVBoxLayout(self._dates_host)
        dl.setContentsMargins(0, 0, 0, 0)
        add_bar = QHBoxLayout()
        self._date_in = QLineEdit(); self._date_in.setPlaceholderText("AAAA-MM-DD")
        self._date_in.setMaximumWidth(140)
        add_btn = QPushButton("＋ Adicionar data"); add_btn.setObjectName("ghost")
        add_btn.clicked.connect(self._add_date)
        add_bar.addWidget(self._date_in); add_bar.addWidget(add_btn); add_bar.addStretch(1)
        dl.addLayout(add_bar)
        self._dates_chips = QHBoxLayout()
        self._dates_chips.setSpacing(6)
        chips_wrap = QWidget(); chips_wrap.setLayout(self._dates_chips)
        dl.addWidget(chips_wrap)
        lay.addWidget(self._dates_host)

        self._dates: list = []

    def load(self, sched: dict):
        mode = sched.get("mode", "always")
        self._radios.get(mode, self._radios["always"]).setChecked(True)
        for i, c in enumerate(self._wd):
            c.blockSignals(True)
            c.setChecked(i in sched.get("weekdays", []))
            c.blockSignals(False)
        self._dates = list(sched.get("dates", []))
        self._rebuild_chips()
        self._update_visibility()

    def value(self) -> dict:
        mode = "always"
        for v, r in self._radios.items():
            if r.isChecked():
                mode = v; break
        return {
            "mode": mode,
            "weekdays": [i for i, c in enumerate(self._wd) if c.isChecked()],
            "dates": list(self._dates),
        }

    def _on_mode(self, _checked):
        self._update_visibility()
        self._on_change()

    def _update_visibility(self):
        v = self.value()["mode"]
        self._wd_host.setVisible(v == "weekdays")
        self._dates_host.setVisible(v == "dates")

    def _add_date(self):
        txt = self._date_in.text().strip()
        try:
            datetime.strptime(txt, "%Y-%m-%d")
        except ValueError:
            return
        if txt not in self._dates:
            self._dates.append(txt); self._dates.sort()
            self._date_in.clear()
            self._rebuild_chips()
            self._on_change()

    def _rebuild_chips(self):
        while self._dates_chips.count():
            item = self._dates_chips.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        for d in self._dates:
            btn = QPushButton(f"{d}  ✕")
            btn.setObjectName("ghost")
            btn.clicked.connect(lambda _=0, dd=d: self._del_date(dd))
            self._dates_chips.addWidget(btn)
        self._dates_chips.addStretch(1)

    def _del_date(self, d: str):
        if d in self._dates:
            self._dates.remove(d)
            self._rebuild_chips()
            self._on_change()


# ── helpers ──────────────────────────────────────────────────────────────────────

def _lbl(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("muted")
    lab.setFixedWidth(150)
    return lab


def _section(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("section")
    return lab


def _summary(step: dict) -> str:
    import os
    t = step.get("type", "")
    if t in ("mute", "unmute", "open_channel", "close_channel"):
        return (step.get("device_name") or step.get("device_id", ""))[:34]
    if t == "hotkey":
        s = step.get("hotkey", "")
        tw = step.get("target_window", "")
        return s + (f"  → {tw[:16]}" if tw else "")
    if t == "play_audio":
        return os.path.basename(step.get("file", ""))[:34]
    if t == "stream":
        return f"{step.get('url','')[:22]} · {fmt_secs(step.get('duration_seconds',0))}"
    if t == "wait_time":
        return fmt_secs(step.get("seconds", 0))
    if t == "wait_keyword":
        return step.get("keyword", "")
    return ""
