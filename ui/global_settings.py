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
        root.addWidget(LabeledRow("Bot Token", self._tg_token, label_w=120))

        root.addWidget(_lbl_section(
            "Contatos que recebem os alertas (cada um com o próprio chat_id — "
            "peça para a pessoa falar com @userinfobot)"))
        self._tg_contacts_box = QVBoxLayout()
        self._tg_contacts_box.setSpacing(6)
        self._tg_rows: list = []
        root.addLayout(self._tg_contacts_box)
        add_contact = QPushButton("＋  Adicionar contato")
        add_contact.setObjectName("ghost")
        add_contact.clicked.connect(lambda: self._add_tg_contact())
        root.addWidget(add_contact, alignment=Qt.AlignLeft)

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

        tg_test_btn = QPushButton("📨  Enviar Telegram de teste (todos os contatos)")
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
        for row in list(self._tg_rows):
            self._remove_tg_row(row)
        contacts = t.get("contacts", []) or []
        for c in contacts:
            self._add_tg_contact(c)
        if not contacts:
            self._add_tg_contact()  # começa com uma linha vazia pra preencher
        ev = t.get("events", {}) or {}
        self._tg_ev_start.setChecked(bool(ev.get("start", True)))
        self._tg_ev_done.setChecked(bool(ev.get("done", True)))
        self._tg_ev_error.setChecked(bool(ev.get("error", True)))
        self._tg_ev_stream.setChecked(bool(ev.get("stream_reconnect", True)))

    def _add_tg_contact(self, contact: dict | None = None):
        row = _TgContactRow(
            contact or {"name": "", "chat_id": "", "enabled": True},
            on_test=self._send_test_telegram_to,
            on_remove=self._remove_tg_row,
        )
        self._tg_rows.append(row)
        self._tg_contacts_box.addWidget(row)

    def _remove_tg_row(self, row):
        if row in self._tg_rows:
            self._tg_rows.remove(row)
        self._tg_contacts_box.removeWidget(row)
        row.deleteLater()

    def _gather_telegram_cfg(self) -> dict:
        contacts = [r.value() for r in self._tg_rows]
        # Linhas totalmente vazias (ex.: a linha inicial não preenchida) não
        # viram contato.
        contacts = [c for c in contacts if c["name"] or c["chat_id"]]
        return {
            "enabled": self._tg_enabled.isChecked(),
            "bot_token": self._tg_token.text().strip(),
            "contacts": contacts,
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
            self._log("📨 Preencha o token do bot e ao menos um contato (com chat ID, "
                      "habilitado) antes de testar.", "warn")
            return
        self._log("📨 Enviando Telegram de teste…", "info")
        for c in telegram_notifier.active_contacts(cfg):
            self._send_test_telegram_to(c)

    def _send_test_telegram_to(self, contact: dict):
        """Teste para UM contato (botão da própria linha), usando o token
        digitado na tela (mesmo antes de salvar)."""
        cfg = self._gather_telegram_cfg()
        name = (contact.get("name") or "").strip() or contact.get("chat_id", "")
        if not cfg["bot_token"] or not str(contact.get("chat_id", "")).strip():
            self._log("📨 Preencha o token do bot e o chat ID deste contato antes de testar.", "warn")
            return
        telegram_notifier.notify_async(
            cfg,
            f"AutoTrigger V10 — mensagem de teste para {name}. Se você recebeu, "
            "os alertas estão configurados corretamente.",
            log=self._log,
            contacts=[{"name": name, "chat_id": str(contact["chat_id"]).strip()}],
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
    lab.setWordWrap(True)
    return lab


class _TgContactRow(QWidget):
    """Uma linha de contato do Telegram: [✓ ativo] [nome] [chat_id] [testar] [remover]."""

    def __init__(self, contact: dict, on_test: Callable, on_remove: Callable):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        self._enabled = QCheckBox()
        self._enabled.setToolTip("Contato ativo (desmarque para pausar os alertas dele)")
        self._enabled.setChecked(bool(contact.get("enabled", True)))
        self._name = QLineEdit(contact.get("name", ""))
        self._name.setPlaceholderText("nome (ex.: João — plantão)")
        self._chat = QLineEdit(str(contact.get("chat_id", "")))
        self._chat.setPlaceholderText("chat_id")

        test = QPushButton("📨"); test.setObjectName("icon")
        test.setToolTip("Enviar mensagem de teste só para este contato")
        test.clicked.connect(lambda: on_test(self.value()))
        rm = QPushButton("✕"); rm.setObjectName("icon_danger")
        rm.setToolTip("Remover contato")
        rm.clicked.connect(lambda: on_remove(self))

        lay.addWidget(self._enabled)
        lay.addWidget(self._name, 2)
        lay.addWidget(self._chat, 2)
        lay.addWidget(test)
        lay.addWidget(rm)

    def value(self) -> dict:
        return {
            "name": self._name.text().strip(),
            "chat_id": self._chat.text().strip(),
            "enabled": self._enabled.isChecked(),
        }
