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
    QComboBox, QPushButton, QFileDialog, QFrame, QDoubleSpinBox, QSpinBox,
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
import x32 as _x32
from player import GAIN_DB_MIN, GAIN_DB_MAX
from step_runner import step_gain_db
from timeparse import parse_secs, fmt_secs
from ui.theme import COLORS
from ui.widgets import TimeField, hline, form_field

STEP_TYPES = [
    ("mute",          "🔇  Mute Dispositivo"),
    ("unmute",        "🔊  Unmute Dispositivo"),
    ("open_channel",  "📻  Abrir Canal (mute linha)"),
    ("close_channel", "🔕  Fechar Canal (unmute linha)"),
    ("hotkey",        "⌨  Enviar Hotkey"),
    ("play_audio",    "🎵  Tocar Áudio"),
    ("stream",        "📡  Streaming"),
    ("x32_channel",    "🎚  Mesa X32 — ligar/desligar canal"),
    ("wait_time",     "⏳  Aguardar Tempo"),
    ("wait_keyword",  "🔍  Aguardar Keyword"),
]
_TYPE_LABELS = {t: lbl for t, lbl in STEP_TYPES}
_LABEL_TO_TYPE = {lbl: t for t, lbl in STEP_TYPES}
_MISSING_PREFIX = "⚠ "   # item do combo p/ dispositivo salvo que não existe neste PC
_MANUAL_STREAM = "✏  Outra URL (digitar)"


class StepEditor(QWidget):
    # emitido pela thread de captura → atualiza o campo na GUI thread
    _hotkey_captured = Signal(str)
    _x32_name_ready = Signal(str)

    def __init__(self, on_done: Callable[[Optional[dict]], None],
                 streams_provider: Optional[Callable[[], list]] = None,
                 x32_provider: Optional[Callable[[], dict]] = None):
        super().__init__()
        self._on_done = on_done
        self._streams_provider = streams_provider or (lambda: [])
        self._x32_provider = x32_provider or (lambda: {})
        self._streams: list = []
        self._step: dict = {}
        self._devices: list = []
        self._build()
        self._hotkey_captured.connect(self._on_hotkey_captured)
        self._x32_name_ready.connect(self._on_x32_name)

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
            saved_name = s.get("device_name", "")
            found = False
            for i, d in enumerate(self._devices):  # nome primeiro: o ID muda, o nome não
                if saved_name and d["name"] == saved_name:
                    combo.setCurrentIndex(i); found = True
                    break
            if not found:
                for i, d in enumerate(self._devices):
                    if cur and d["id"] == cur:
                        combo.setCurrentIndex(i); found = True
                        break
            if not found and (cur or saved_name):
                # Placa do passo ausente neste PC: mostra isso (em vez de fingir que
                # o 1º da lista é o escolhido); o _save mantém o dispositivo salvo.
                combo.insertItem(0, f"{_MISSING_PREFIX}{saved_name or cur} (não encontrado)")
                combo.setCurrentIndex(0)
            self._w["device"] = combo
            self._form.addRow(_lbl("Dispositivo"), form_field(combo))
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
            self._streams = [x for x in (self._streams_provider() or [])
                             if str(x.get("url", "")).strip()]
            combo = QComboBox()
            for st in self._streams:
                combo.addItem(st.get("name") or st["url"], st["id"])
            combo.addItem(_MANUAL_STREAM, "")
            cur = combo.findData(s.get("stream_id")) if s.get("stream_id") else -1
            if cur >= 0:
                combo.setCurrentIndex(cur)
            elif s.get("url") or not self._streams:
                combo.setCurrentIndex(combo.count() - 1)   # URL manual (ou cadastro removido)
            self._w["stream"] = combo
            self._form.addRow(_lbl("Streaming"), form_field(combo))
            hint = QLabel("")
            hint.setObjectName("dim")
            hint.setWordWrap(True)
            self._form.addRow(QLabel(""), hint)
            url = QLineEdit(s.get("url", ""))
            url.setPlaceholderText("https://…/stream.m3u")
            self._w["url"] = url
            url_lbl, url_host = _lbl("URL"), form_field(url)
            self._form.addRow(url_lbl, url_host)

            def _sync_stream(_=0):
                sid = combo.currentData()
                manual = not sid
                url_lbl.setVisible(manual)
                url_host.setVisible(manual)
                if manual:
                    hint.setText("" if self._streams else
                                 "Cadastre streamings em Configurações Globais para reutilizá-los "
                                 "em várias etapas.")
                else:
                    st = next((x for x in self._streams if x["id"] == sid), None)
                    hint.setText(str(st["url"]) if st else "")

            combo.currentIndexChanged.connect(_sync_stream)
            _sync_stream()
            dur = TimeField(int(s.get("duration_seconds", 300)))
            self._w["dur"] = dur
            self._form.addRow(_lbl("Duração"), dur)
            vol_host = QWidget(); vol_l = QHBoxLayout(vol_host)
            vol_l.setContentsMargins(0, 0, 0, 0)
            vol = QDoubleSpinBox()
            vol.setRange(GAIN_DB_MIN, GAIN_DB_MAX)
            vol.setDecimals(1)
            vol.setSingleStep(0.5)
            vol.setSuffix(" dB")
            vol.setMaximumWidth(110)
            vol.setValue(step_gain_db(s))
            vol_hint = QLabel("0 dB = normal · máx. +6 dB (limite do VLC)")
            vol_hint.setObjectName("dim")
            vol_l.addWidget(vol); vol_l.addWidget(vol_hint); vol_l.addStretch(1)
            self._w["volume"] = vol
            self._form.addRow(_lbl("Ganho de volume"), vol_host)
            self._add_label_row(s, default="Stream")

        elif t == "x32_channel":
            cfg = self._x32_provider() or {}
            host = str(cfg.get("host", "") or "").strip()
            act = QComboBox()
            act.addItem("Desligar o canal (mutar)", "off")
            act.addItem("Ligar o canal", "on")
            act.setCurrentIndex(max(0, act.findData(s.get("action", "off"))))
            self._w["x32_action"] = act
            self._form.addRow(_lbl("Ação"), form_field(act))
            kind = QComboBox()
            for k, (name, _mx, _a, _n) in _x32.TARGETS.items():
                kind.addItem(name, k)
            kind.setCurrentIndex(max(0, kind.findData(s.get("target", "ch"))))
            self._w["x32_kind"] = kind
            self._form.addRow(_lbl("Tipo"), form_field(kind))
            num_host = QWidget(); num_l = QHBoxLayout(num_host)
            num_l.setContentsMargins(0, 0, 0, 0)
            num = QSpinBox()
            num.setMaximumWidth(90)
            self._w["x32_number"] = num
            check = QPushButton("🔎  Ler o nome na mesa")
            check.setObjectName("ghost")
            check.setToolTip("Só LÊ o nome do canal na mesa (não altera nada) para você "
                             "conferir que é o canal certo.")
            name_lbl = QLabel("")
            name_lbl.setObjectName("dim")
            self._w["x32_name"] = name_lbl
            num_l.addWidget(num); num_l.addWidget(check); num_l.addWidget(name_lbl, 1)
            self._num_row_label = _lbl("Número")
            self._form.addRow(self._num_row_label, num_host)
            self._x32_num_host = num_host

            def _kind_changed(_=0):
                mx = _x32.max_number(kind.currentData())
                self._num_row_label.setVisible(mx > 0)
                num_host.setVisible(mx > 0)
                if mx > 0:
                    num.setRange(1, mx)
                name_lbl.setText("")

            kind.currentIndexChanged.connect(_kind_changed)
            num.valueChanged.connect(lambda _=0: name_lbl.setText(""))
            check.clicked.connect(self._read_x32_name)
            _kind_changed()
            num.setValue(int(s.get("number", 1) or 1))
            hint = QLabel(f"Mesa: {host or '⚠ configure o IP em Configurações Globais'}. "
                          "'Desligar' muta o canal (botão ON apagado); 'Ligar' reabre.")
            hint.setObjectName("dim"); hint.setWordWrap(True)
            self._form.addRow("", hint)
            self._add_label_row(s, default="")

        elif t == "wait_time":
            secs = TimeField(int(s.get("seconds", 60)))
            self._w["secs"] = secs
            self._form.addRow(_lbl("Duração"), secs)
            self._add_label_row(s, default="Aguardar")

        elif t == "wait_keyword":
            kw = QLineEdit(s.get("keyword", ""))
            self._w["keyword"] = kw
            self._form.addRow(_lbl("Keyword"), form_field(kw))
            self._add_label_row(s, default="Aguardar keyword")

    def _add_label_row(self, s: dict, default: str = ""):
        lbl = QLineEdit(s.get("label", default))
        self._w["label"] = lbl
        self._form.addRow(_lbl("Rótulo"), form_field(lbl))

    # ── actions ────────────────────────────────────────────────────────────────────

    def _read_x32_name(self):
        """Lê (só leitura) o nome do canal na mesa, numa thread para não travar a tela."""
        cfg = self._x32_provider() or {}
        host = str(cfg.get("host", "") or "").strip()
        port = int(cfg.get("port", _x32.DEFAULT_PORT) or _x32.DEFAULT_PORT)
        kind = self._w["x32_kind"].currentData()
        number = self._w["x32_number"].value()
        if not host:
            self._x32_name_ready.emit("⚠ informe o IP da mesa em Configurações Globais")
            return
        self._w["x32_name"].setText("lendo…")

        def _run():
            name = _x32.read_name(host, port, kind, number)
            if name is None:
                if _x32.name_address(kind, number) == "":
                    self._x32_name_ready.emit("(este tipo não tem nome para ler)")
                else:
                    self._x32_name_ready.emit("⚠ a mesa não respondeu")
            else:
                self._x32_name_ready.emit(f"“{name}”" if name else "(canal sem nome na mesa)")

        threading.Thread(target=_run, daemon=True, name="x32-read-name").start()

    def _on_x32_name(self, text: str):
        lab = self._w.get("x32_name")
        if lab is not None:
            lab.setText(text)

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
            if name.startswith(_MISSING_PREFIX):   # não trocou a placa: mantém a salva
                dev_id = self._step.get("device_id", "")
                name = self._step.get("device_name", "") or dev_id
            else:
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
            sid = w["stream"].currentData()
            st = next((x for x in self._streams if x["id"] == sid), None) if sid else None
            if st:
                # Escolheu um streaming cadastrado: a etapa guarda o id (a URL vem do
                # cadastro na hora de rodar) e uma cópia do nome/URL como reserva.
                step["stream_id"] = st["id"]
                step["stream_name"] = st.get("name", "")
                step["url"] = str(st["url"]).strip()
            else:
                step["url"] = w["url"].text().strip()
            step["duration_seconds"] = w["dur"].seconds()
            step["gain_db"] = round(w["volume"].value(), 1)
            step["label"] = label or (f"Streaming - {step['stream_name']}"
                                      if step.get("stream_name") else "Stream")
        elif t == "x32_channel":
            step["action"] = w["x32_action"].currentData()
            step["target"] = w["x32_kind"].currentData()
            step["number"] = w["x32_number"].value() if _x32.max_number(step["target"]) else 0
            what = _x32.target_label(step["target"], step["number"])
            step["label"] = label or f"{'Ligar' if step['action'] == 'on' else 'Desligar'} {what} (X32)"
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
