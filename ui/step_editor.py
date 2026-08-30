"""
Editor de UMA etapa — widget inline (sem janela pop-up).

É exibido dentro do painel de detalhe (QStackedWidget). Chama on_done(step|None)
ao salvar (dict) ou cancelar (None).
"""
from __future__ import annotations

import copy
import os
import threading
from typing import Callable, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QFileDialog, QFrame,
)


class WindowCombo(QComboBox):
    """
    Seletor (não-editável) de janela alvo. Clicar abre a lista de janelas/programas
    abertos AGORA (recarrega no clique). O valor é o título da janela;
    "" = enviar para a janela em foco.
    """
    def __init__(self):
        super().__init__()
        self.setEditable(False)
        self._reload()

    def _reload(self):
        sel = self.value()
        self.blockSignals(True)
        self.clear()
        self.addItem("⌁  (janela em foco)", "")
        try:
            titles = _hotkey.list_window_titles()
        except Exception:
            titles = []
        for t in titles:
            self.addItem(t, t)
        # garante que o valor salvo apareça mesmo se a janela não estiver aberta
        if sel and sel not in titles:
            self.addItem(f"{sel}  (não aberta)", sel)
        self.set_value(sel)
        self.blockSignals(False)

    def showPopup(self):
        self._reload()
        super().showPopup()

    def value(self) -> str:
        data = self.currentData()
        return data if data is not None else ""

    def set_value(self, title: str):
        idx = self.findData(title or "")
        self.setCurrentIndex(idx if idx >= 0 else 0)

import audio_manager as _audio
import hotkey_sender as _hotkey
from timeparse import parse_secs, fmt_secs
from ui.theme import COLORS
from ui.widgets import TimeField, hline

STEP_TYPES = [
    ("mute",          "🔇  Mute Dispositivo"),
    ("unmute",        "🔊  Unmute Dispositivo"),
    ("open_channel",  "📻  Abrir Canal (mute linha)"),
    ("close_channel", "🔕  Fechar Canal (unmute linha)"),
    ("hotkey",        "⌨  Enviar Hotkey"),
    ("play_audio",    "🎵  Tocar Áudio"),
    ("stream",        "📡  Streaming"),
    ("wait_time",     "⏳  Aguardar Tempo"),
    ("wait_keyword",  "🔍  Aguardar Keyword"),
]
_TYPE_LABELS = {t: lbl for t, lbl in STEP_TYPES}
_LABEL_TO_TYPE = {lbl: t for t, lbl in STEP_TYPES}


class StepEditor(QWidget):
    # emitido pela thread de captura → atualiza o campo na GUI thread
    _hotkey_captured = Signal(str)

    def __init__(self, on_done: Callable[[Optional[dict]], None]):
        super().__init__()
        self._on_done = on_done
        self._step: dict = {}
        self._devices: list = []
        self._build()
        self._hotkey_captured.connect(self._on_hotkey_captured)

    # ── build ───────────────────────────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        title = QLabel("Editar etapa")
        title.setObjectName("h2")
        root.addWidget(title)

        # Tipo
        type_row = QHBoxLayout()
        lab = QLabel("Tipo")
        lab.setObjectName("muted")
        lab.setFixedWidth(110)
        self._type_combo = QComboBox()
        self._type_combo.addItems([lbl for _, lbl in STEP_TYPES])
        self._type_combo.currentIndexChanged.connect(self._rebuild_fields)
        type_row.addWidget(lab)
        type_row.addWidget(self._type_combo, 1)
        root.addLayout(type_row)

        root.addWidget(hline())

        # Campos dinâmicos
        self._form_host = QWidget()
        self._form = QFormLayout(self._form_host)
        self._form.setContentsMargins(0, 0, 0, 0)
        self._form.setHorizontalSpacing(14)
        self._form.setVerticalSpacing(10)
        self._form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        root.addWidget(self._form_host)

        root.addStretch(1)

        # Botões
        btns = QHBoxLayout()
        btns.addStretch(1)
        cancel = QPushButton("Cancelar")
        cancel.setObjectName("ghost")
        cancel.clicked.connect(lambda: self._on_done(None))
        save = QPushButton("Salvar etapa")
        save.setObjectName("primary")
        save.clicked.connect(self._save)
        btns.addWidget(cancel)
        btns.addWidget(save)
        root.addLayout(btns)

    # ── load ─────────────────────────────────────────────────────────────────────

    def load_step(self, step: dict):
        self._step = copy.deepcopy(step or {"type": "hotkey"})
        self._load_devices()
        t = self._step.get("type", "hotkey")
        self._type_combo.blockSignals(True)
        self._type_combo.setCurrentText(_TYPE_LABELS.get(t, STEP_TYPES[4][1]))
        self._type_combo.blockSignals(False)
        self._rebuild_fields()

    def _load_devices(self):
        try:
            inputs = _audio.list_input_devices()
            outputs = _audio.list_output_devices()
            seen, devs = set(), []
            for d in inputs + outputs:
                if d["id"] not in seen:
                    seen.add(d["id"])
                    devs.append(d)
            self._devices = devs
        except Exception:
            self._devices = []

    # ── dynamic fields ────────────────────────────────────────────────────────────

    def _clear_form(self):
        while self._form.rowCount():
            self._form.removeRow(0)

    def _rebuild_fields(self):
        self._clear_form()
        t = _LABEL_TO_TYPE.get(self._type_combo.currentText(), "hotkey")
        s = self._step
        self._w = {}  # widgets desta etapa

        if t in ("mute", "unmute", "open_channel", "close_channel"):
            combo = QComboBox()
            names = [d["name"] for d in self._devices] or ["(nenhum)"]
            combo.addItems(names)
            cur = s.get("device_id", "")
            for i, d in enumerate(self._devices):
                if d["id"] == cur or d["name"] == s.get("device_name", ""):
                    combo.setCurrentIndex(i)
                    break
            self._w["device"] = combo
            self._form.addRow(_lbl("Dispositivo"), combo)
            self._add_label_row(s)

        elif t == "hotkey":
            hk_host = QWidget(); hk_l = QHBoxLayout(hk_host)
            hk_l.setContentsMargins(0, 0, 0, 0)
            hk = QLineEdit(s.get("hotkey", ""))
            cap = QPushButton("Capturar"); cap.clicked.connect(self._capture_hotkey)
            hk_l.addWidget(hk, 1); hk_l.addWidget(cap)
            self._w["hotkey"] = hk
            self._form.addRow(_lbl("Hotkey"), hk_host)

            tw_host = QWidget(); tw_l = QHBoxLayout(tw_host)
            tw_l.setContentsMargins(0, 0, 0, 0)
            target = WindowCombo()
            target.set_value(s.get("target_window", ""))
            refresh = QPushButton("↻"); refresh.setObjectName("icon")
            refresh.setToolTip("Recarregar lista de janelas")
            refresh.clicked.connect(target._reload)
            tw_l.addWidget(target, 1); tw_l.addWidget(refresh)
            self._w["target"] = target
            self._form.addRow(_lbl("Janela alvo"), tw_host)
            hint = QLabel("Clique no campo para escolher uma janela aberta. "
                          "Vazio = janela em foco; preenchido = foca essa janela, "
                          "envia e devolve o foco.")
            hint.setObjectName("dim"); hint.setWordWrap(True)
            self._form.addRow("", hint)
            self._add_label_row(s)

        elif t == "play_audio":
            fa_host = QWidget(); fa_l = QHBoxLayout(fa_host)
            fa_l.setContentsMargins(0, 0, 0, 0)
            path = QLineEdit(s.get("file", ""))
            browse = QPushButton("📁"); browse.setObjectName("icon")
            browse.clicked.connect(lambda: self._browse_audio(path))
            fa_l.addWidget(path, 1); fa_l.addWidget(browse)
            self._w["file"] = path
            self._form.addRow(_lbl("Arquivo"), fa_host)
            self._add_label_row(s, default="Áudio")

        elif t == "stream":
            url = QLineEdit(s.get("url", ""))
            self._w["url"] = url
            self._form.addRow(_lbl("URL"), url)
            dur = TimeField(int(s.get("duration_seconds", 300)))
            self._w["dur"] = dur
            self._form.addRow(_lbl("Duração"), dur)
            self._add_label_row(s, default="Stream")

        elif t == "wait_time":
            secs = TimeField(int(s.get("seconds", 60)))
            self._w["secs"] = secs
            self._form.addRow(_lbl("Duração"), secs)
            self._add_label_row(s, default="Aguardar")

        elif t == "wait_keyword":
            kw = QLineEdit(s.get("keyword", ""))
            self._w["keyword"] = kw
            self._form.addRow(_lbl("Keyword"), kw)
            self._add_label_row(s, default="Aguardar keyword")

    def _add_label_row(self, s: dict, default: str = ""):
        lbl = QLineEdit(s.get("label", default))
        self._w["label"] = lbl
        self._form.addRow(_lbl("Rótulo"), lbl)

    # ── actions ────────────────────────────────────────────────────────────────────

    def _capture_hotkey(self):
        hk_widget = self._w.get("hotkey")
        if not hk_widget:
            return
        hk_widget.setText("Pressione a tecla/combinação…")
        hk_widget.setEnabled(False)

        def _run():
            try:
                val = _hotkey.capture_hotkey()
            except Exception:
                val = ""
            self._hotkey_captured.emit(val)

        threading.Thread(target=_run, daemon=True, name="capture-hotkey").start()

    def _on_hotkey_captured(self, val: str):
        hk_widget = self._w.get("hotkey")
        if not hk_widget:
            return
        hk_widget.setEnabled(True)
        if val:
            hk_widget.setText(val)
        else:
            hk_widget.setText("")
            hk_widget.setPlaceholderText("falha ao capturar — digite manualmente")

    def _browse_audio(self, edit: QLineEdit):
        path, _ = QFileDialog.getOpenFileName(
            self, "Selecionar áudio", "",
            "Áudio (*.mp3 *.wav *.ogg *.flac *.aac);;Todos (*.*)",
        )
        if path:
            edit.setText(path)

    def _save(self):
        t = _LABEL_TO_TYPE.get(self._type_combo.currentText(), "hotkey")
        w = self._w
        step = {"type": t}
        label = w["label"].text().strip() if "label" in w else ""

        if t in ("mute", "unmute", "open_channel", "close_channel"):
            name = w["device"].currentText()
            dev_id = ""
            for d in self._devices:
                if d["name"] == name:
                    dev_id = d["id"]; break
            step["device_id"] = dev_id
            step["device_name"] = name
            step["label"] = label or name
        elif t == "hotkey":
            step["hotkey"] = w["hotkey"].text().strip()
            step["target_window"] = w["target"].value().strip()
            step["label"] = label or step["hotkey"]
        elif t == "play_audio":
            step["file"] = w["file"].text().strip()
            step["label"] = label or "Áudio"
        elif t == "stream":
            step["url"] = w["url"].text().strip()
            step["duration_seconds"] = w["dur"].seconds()
            step["label"] = label or "Stream"
        elif t == "wait_time":
            step["seconds"] = w["secs"].seconds()
            step["label"] = label or "Aguardar"
        elif t == "wait_keyword":
            step["keyword"] = w["keyword"].text().strip().upper()
            step["label"] = label or f"Aguardar {step['keyword']}"

        self._on_done(step)


def _lbl(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("muted")
    lab.setFixedWidth(110)
    return lab
