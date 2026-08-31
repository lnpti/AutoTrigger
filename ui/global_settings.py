"""
Painel de Configurações Globais — inline (sem janela pop-up).

TXT monitorado + dispositivos padrão. Salva no Config e dispara on_saved().
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QFileDialog, QCheckBox, QSpinBox,
)

import audio_manager as _audio
import emailer
import telegram_notifier
from ui.theme import COLORS
from ui.widgets import hline, LabeledRow

# Cache de dispositivos no nível do módulo (evita re-enumerar a cada abertura)
_DEV_CACHE = {"inputs": None, "outputs": None}


class GlobalSettings(QWidget):
    def __init__(self, config, on_saved: Callable, log: Callable | None = None):
        super().__init__()
        self._config = config
        self._on_saved = on_saved
        self._log = log or (lambda msg, level="info": None)
        self._inputs: list = []
        self._outputs: list = []
        self._build()
        self._load()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        title = QLabel("⚙  Configurações Globais")
        title.setObjectName("h2")
        root.addWidget(title)
        root.addWidget(hline())

        # TXT
        txt_host = QWidget(); txt_l = QHBoxLayout(txt_host)
        txt_l.setContentsMargins(0, 0, 0, 0)
        self._txt = QLineEdit()
        browse = QPushButton("📁"); browse.setObjectName("icon")
        browse.clicked.connect(self._browse_txt)
        txt_l.addWidget(self._txt, 1); txt_l.addWidget(browse)
        root.addWidget(LabeledRow("Arquivo TXT", txt_host, label_w=120))

        sec = QLabel("DISPOSITIVOS PADRÃO")
        sec.setObjectName("section")
        root.addSpacing(6)
        root.addWidget(sec)

        self._in_combo = QComboBox()
        self._out_combo = QComboBox()
        refresh = QPushButton("↻  Recarregar dispositivos")
        refresh.setObjectName("ghost")
        refresh.clicked.connect(lambda: self._load_devices(force=True))
        root.addWidget(LabeledRow("Entrada (mic)", self._in_combo, label_w=120))
        root.addWidget(LabeledRow("Saída (player)", self._out_combo, label_w=120))
        root.addWidget(refresh, alignment=Qt.AlignLeft)

        # ── Alertas por email ──────────────────────────────────────────────────
        root.addSpacing(6)
        sec_mail = QLabel("ALERTAS POR E-MAIL")
        sec_mail.setObjectName("section")
        root.addWidget(sec_mail)

        self._mail_enabled = QCheckBox("Ativar alertas por e-mail")
        root.addWidget(self._mail_enabled)

        self._smtp_host = QLineEdit()
        self._smtp_host.setPlaceholderText("ex.: smtp.gmail.com")
        self._smtp_port = QSpinBox()
        self._smtp_port.setRange(1, 65535)
        self._smtp_port.setMaximumWidth(110)
        self._use_tls = QCheckBox("Usar TLS (STARTTLS)")

        port_host = QWidget(); port_l = QHBoxLayout(port_host)
        port_l.setContentsMargins(0, 0, 0, 0)
        port_l.addWidget(self._smtp_port)
        port_l.addSpacing(12)
        port_l.addWidget(self._use_tls)
        port_l.addStretch(1)

        self._mail_user = QLineEdit()
        self._mail_pass = QLineEdit()
        self._mail_pass.setEchoMode(QLineEdit.Password)
        self._mail_from = QLineEdit()
        self._mail_from.setPlaceholderText("remetente@dominio.com")
        self._mail_to = QLineEdit()
        self._mail_to.setPlaceholderText("destino1@x.com, destino2@y.com")

        root.addWidget(LabeledRow("Servidor SMTP", self._smtp_host, label_w=120))
        root.addWidget(LabeledRow("Porta / TLS", port_host, label_w=120))
        root.addWidget(LabeledRow("Usuário", self._mail_user, label_w=120))
        root.addWidget(LabeledRow("Senha", self._mail_pass, label_w=120))
        root.addWidget(LabeledRow("Remetente", self._mail_from, label_w=120))
        root.addWidget(LabeledRow("Destinatários", self._mail_to, label_w=120))

        ev_box = QWidget(); ev_l = QHBoxLayout(ev_box)
        ev_l.setContentsMargins(0, 0, 0, 0)
        self._ev_start = QCheckBox("Início")
        self._ev_done = QCheckBox("Fim")
        self._ev_error = QCheckBox("Erro/cancelamento")
        self._ev_stream = QCheckBox("Queda/reconexão de stream")
        for cb in (self._ev_start, self._ev_done, self._ev_error, self._ev_stream):
            ev_l.addWidget(cb)
        ev_l.addStretch(1)
        root.addWidget(_lbl_section("Eventos que disparam e-mail"))
        root.addWidget(ev_box)

        test_btn = QPushButton("✉  Enviar e-mail de teste")
        test_btn.clicked.connect(self._send_test_email)
        root.addWidget(test_btn, alignment=Qt.AlignLeft)

        # ── Alertas por Telegram ─────────────────────────────────────────────────
        root.addSpacing(6)
        sec_tg = QLabel("ALERTAS POR TELEGRAM")
        sec_tg.setObjectName("section")
        root.addWidget(sec_tg)

        self._tg_enabled = QCheckBox("Ativar alertas por Telegram")
        root.addWidget(self._tg_enabled)

        self._tg_token = QLineEdit()
        self._tg_token.setEchoMode(QLineEdit.Password)
        self._tg_token.setPlaceholderText("token do bot (fala com @BotFather)")
        self._tg_chat = QLineEdit()
        self._tg_chat.setPlaceholderText("chat_id (fala com @userinfobot)")

        root.addWidget(LabeledRow("Bot Token", self._tg_token, label_w=120))
        root.addWidget(LabeledRow("Chat ID", self._tg_chat, label_w=120))

        tg_ev_box = QWidget(); tg_ev_l = QHBoxLayout(tg_ev_box)
        tg_ev_l.setContentsMargins(0, 0, 0, 0)
        self._tg_ev_start = QCheckBox("Início")
        self._tg_ev_done = QCheckBox("Fim")
        self._tg_ev_error = QCheckBox("Erro/cancelamento")
        self._tg_ev_stream = QCheckBox("Queda/reconexão de stream")
        for cb in (self._tg_ev_start, self._tg_ev_done, self._tg_ev_error, self._tg_ev_stream):
            tg_ev_l.addWidget(cb)
        tg_ev_l.addStretch(1)
        root.addWidget(_lbl_section("Eventos que disparam Telegram"))
        root.addWidget(tg_ev_box)

        tg_test_btn = QPushButton("📨  Enviar Telegram de teste")
        tg_test_btn.clicked.connect(self._send_test_telegram)
        root.addWidget(tg_test_btn, alignment=Qt.AlignLeft)

        root.addStretch(1)

        btns = QHBoxLayout()
        btns.addStretch(1)
        save = QPushButton("Salvar configurações")
        save.setObjectName("primary")
        save.clicked.connect(self._save)
        btns.addWidget(save)
        root.addLayout(btns)

    def _load(self):
        g = self._config.get_global()
        self._txt.setText(g.get("txt_file_path", ""))
        self._load_devices()
        self._load_email(g.get("email", {}) or {})
        self._load_telegram(g.get("telegram", {}) or {})

    def _load_email(self, e: dict):
        self._mail_enabled.setChecked(bool(e.get("enabled", False)))
        self._smtp_host.setText(e.get("smtp_host", ""))
        self._smtp_port.setValue(int(e.get("smtp_port", 587) or 587))
        self._use_tls.setChecked(bool(e.get("use_tls", True)))
        self._mail_user.setText(e.get("username", ""))
        self._mail_pass.setText(e.get("password", ""))
        self._mail_from.setText(e.get("from_addr", ""))
        self._mail_to.setText(e.get("to_addrs", ""))
        ev = e.get("events", {}) or {}
        self._ev_start.setChecked(bool(ev.get("start", True)))
        self._ev_done.setChecked(bool(ev.get("done", True)))
        self._ev_error.setChecked(bool(ev.get("error", True)))
        self._ev_stream.setChecked(bool(ev.get("stream_reconnect", True)))

    def _load_telegram(self, t: dict):
        self._tg_enabled.setChecked(bool(t.get("enabled", False)))
        self._tg_token.setText(t.get("bot_token", ""))
        self._tg_chat.setText(t.get("chat_id", ""))
        ev = t.get("events", {}) or {}
        self._tg_ev_start.setChecked(bool(ev.get("start", True)))
        self._tg_ev_done.setChecked(bool(ev.get("done", True)))
        self._tg_ev_error.setChecked(bool(ev.get("error", True)))
        self._tg_ev_stream.setChecked(bool(ev.get("stream_reconnect", True)))

    def _gather_telegram_cfg(self) -> dict:
        return {
            "enabled": self._tg_enabled.isChecked(),
            "bot_token": self._tg_token.text().strip(),
            "chat_id": self._tg_chat.text().strip(),
            "events": {
                "start": self._tg_ev_start.isChecked(),
                "done": self._tg_ev_done.isChecked(),
                "error": self._tg_ev_error.isChecked(),
                "stream_reconnect": self._tg_ev_stream.isChecked(),
            },
        }

    def _send_test_telegram(self):
        cfg = self._gather_telegram_cfg()
        if not telegram_notifier.is_configured(cfg):
            self._log("📨 Preencha o token do bot e o chat ID antes de testar.", "warn")
            return
        self._log("📨 Enviando Telegram de teste…", "info")
        telegram_notifier.notify_async(
            cfg,
            "AutoTrigger V10 — mensagem de teste. Se você recebeu, os alertas "
            "estão configurados corretamente.",
            log=self._log,
        )

    def _gather_email_cfg(self) -> dict:
        return {
            "enabled": self._mail_enabled.isChecked(),
            "smtp_host": self._smtp_host.text().strip(),
            "smtp_port": self._smtp_port.value(),
            "use_tls": self._use_tls.isChecked(),
            "username": self._mail_user.text().strip(),
            "password": self._mail_pass.text(),
            "from_addr": self._mail_from.text().strip(),
            "to_addrs": self._mail_to.text().strip(),
            "events": {
                "start": self._ev_start.isChecked(),
                "done": self._ev_done.isChecked(),
                "error": self._ev_error.isChecked(),
                "stream_reconnect": self._ev_stream.isChecked(),
            },
        }

    def _send_test_email(self):
        cfg = self._gather_email_cfg()
        if not emailer.is_configured(cfg):
            self._log("📧 Preencha servidor SMTP, remetente e destinatário antes de testar.", "warn")
            return
        self._log("📧 Enviando e-mail de teste…", "info")
        emailer.notify_async(
            cfg,
            "AutoTrigger V10 — e-mail de teste",
            "Este é um e-mail de teste do AutoTrigger V10. "
            "Se você recebeu, os alertas estão configurados corretamente.",
            log=self._log,
        )

    def _load_devices(self, force: bool = False):
        if force or _DEV_CACHE["inputs"] is None:
            try:
                _DEV_CACHE["inputs"] = _audio.list_input_devices()
                _DEV_CACHE["outputs"] = _audio.list_output_devices()
            except Exception:
                _DEV_CACHE["inputs"] = _DEV_CACHE["outputs"] = []
        self._inputs = _DEV_CACHE["inputs"] or []
        self._outputs = _DEV_CACHE["outputs"] or []

        g = self._config.get_global()
        self._fill_combo(self._in_combo, self._inputs, g.get("default_input_device_id", ""))
        self._fill_combo(self._out_combo, self._outputs, g.get("default_output_device_id", ""))

    @staticmethod
    def _fill_combo(combo: QComboBox, devices: list, cur_id: str):
        combo.clear()
        names = [d["name"] for d in devices] or ["(nenhum)"]
        combo.addItems(names)
        for i, d in enumerate(devices):
            if d["id"] == cur_id:
                combo.setCurrentIndex(i)
                break

    def _browse_txt(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Selecionar arquivo TXT", "",
            "Arquivos TXT (*.txt);;Todos (*.*)",
        )
        if path:
            self._txt.setText(path)

    def _save(self):
        g = self._config.get_global()
        g["txt_file_path"] = self._txt.text().strip()
        for d in self._inputs:
            if d["name"] == self._in_combo.currentText():
                g["default_input_device_id"] = d["id"]
                g["default_input_device_name"] = d["name"]
                break
        for d in self._outputs:
            if d["name"] == self._out_combo.currentText():
                g["default_output_device_id"] = d["id"]
                g["default_output_device_name"] = d["name"]
                break
        g["email"] = self._gather_email_cfg()
        g["telegram"] = self._gather_telegram_cfg()
        self._config.update_global(g)
        self._config.save()
        self._on_saved()


def _lbl_section(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("muted")
    return lab
