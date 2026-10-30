"""
Atualização automática de madrugada: procura versão nova na hora configurada
(padrão 4h) e INSTALA sozinha, sem ninguém na frente.

Regras de segurança:
  - só instala com nenhuma sequência rodando (e confere de novo logo antes de
    trocar o .exe); se estiver ocupado, espera terminar, até o fim da janela de 2 h;
  - não tenta quando a pasta do app exige administrador (o UAC ficaria esperando
    alguém clicar) nem rodando do código-fonte (só no .exe instalado);
  - uma tentativa por janela: depois de instalar, achar o app em dia ou falhar, só
    volta a tentar na janela do dia seguinte (nada de laço de tentativas).
Depois da troca, a versão nova avisa (log + Telegram/e-mail) que foi atualizada ou
que a atualização não chegou a instalar (ver report_previous).
"""
from __future__ import annotations

import json
import os
import sys
import threading
from datetime import datetime, timedelta

_WINDOW_MIN = 120      # tenta durante 2 h a partir da hora configurada
_RETRY_CHECK_MIN = 10  # sem rede: confere de novo depois de tantos minutos


def _marker_path() -> str:
    import applog
    return os.path.join(applog.log_dir(), "auto_update.json")


class AutoUpdateScheduler:
    def __init__(self, get_global, is_busy, log, updater, notify=None,
                 now=datetime.now, frozen: bool | None = None,
                 version: str | None = None, marker_path: str | None = None):
        self._get_global = get_global
        self._is_busy = is_busy
        self._log = log
        self._updater = updater
        self._notify = notify or (lambda text: None)
        self._now = now
        self._frozen = getattr(sys, "frozen", False) if frozen is None else frozen
        if version is None:
            from version import __version__ as version
        self._version = version
        self._marker_path = marker_path
        self._lock = threading.Lock()
        self._window = None        # id da janela atual (data em que ela começou)
        self._state = "check"      # check -> checking -> (pending|done)
        self._pending = None       # UpdateInfo achado, esperando a hora certa de instalar
        self._working = False      # instalando agora
        self._retry_at = None      # sem rede: não conferir antes disso
        self._busy_logged = False

    # ── agendamento (chamar a cada ~1 min, na thread da GUI) ─────────────────────

    def tick(self) -> None:
        g = self._get_global() or {}
        if not (self._frozen and g.get("auto_update", True)):
            return
        hour = int(g.get("auto_update_hour", 4)) % 24
        now = self._now()
        since = (now.hour * 60 + now.minute - hour * 60) % 1440
        if since >= _WINDOW_MIN:           # fora da janela
            with self._lock:
                if self._pending is not None and not self._working:
                    self._log("Atualização automática adiada para a próxima madrugada: "
                              "ainda havia sequência rodando.", "warn")
                    self._pending = None
                    self._state = "done"
            return
        window = (now - timedelta(minutes=since)).date().isoformat()
        with self._lock:
            if window != self._window:     # janela nova: começa do zero
                self._window, self._state, self._pending = window, "check", None
                self._working, self._retry_at, self._busy_logged = False, None, False
            if self._working or self._state in ("done", "checking"):
                return
            if self._pending is not None:
                info = self._pending
            else:
                if self._retry_at is not None and now < self._retry_at:
                    return
                self._state = "checking"
                info = None
        if info is not None:
            self._try_apply(info)
        else:
            self._updater.check_async(
                on_update_available=self._found,
                on_up_to_date=self._up_to_date,
                on_error=self._check_error,
            )

    # ── resultado da checagem (vêm de thread de fundo) ──────────────────────────

    def _found(self, info) -> None:
        with self._lock:
            self._pending = info
            self._state = "pending"
        self._log(f"Atualização automática: versão v{info.version} encontrada.", "info")
        self._try_apply(info)

    def _up_to_date(self) -> None:
        with self._lock:
            self._state = "done"
        self._log("Atualização automática: o app já está na versão mais nova.", "info")

    def _check_error(self, msg: str) -> None:
        with self._lock:
            self._state = "check"
            self._retry_at = self._now() + timedelta(minutes=_RETRY_CHECK_MIN)
        self._log(f"Atualização automática: não consegui checar ({msg}); tento de novo em "
                  f"{_RETRY_CHECK_MIN} min.", "warn")

    # ── instalação ──────────────────────────────────────────────────────────────

    def _try_apply(self, info) -> None:
        if self._is_busy():
            if not self._busy_logged:
                self._busy_logged = True
                self._log(f"Atualização automática: v{info.version} pronta, mas há sequência "
                          f"rodando — espero terminar.", "warn")
            return
        with self._lock:
            if self._working:
                return
            self._working = True
        threading.Thread(target=self._apply, args=(info,), daemon=True, name="auto-update").start()

    def _apply(self, info) -> None:
        marker = self._marker_path or _marker_path()
        try:
            with open(marker, "w", encoding="utf-8") as f:
                json.dump({"from": self._version, "to": info.version,
                           "at": self._now().isoformat(timespec="seconds")}, f)
        except OSError:
            pass
        self._log(f"Atualização automática: instalando v{info.version}…", "info")
        try:
            # Sucesso encerra o processo (os._exit) e nunca volta daqui.
            result = self._updater.apply_update(
                info, unattended=True, before_install=lambda: not self._is_busy())
        except Exception as exc:
            result = f"erro: {exc}"
        with self._lock:
            self._working = False
            if result == "busy":
                self._busy_logged = False      # começou uma sequência: espera e tenta de novo
            else:
                self._state = "done"
        if result == "busy":
            try:
                os.remove(marker)
            except OSError:
                pass
            return
        try:
            os.remove(marker)
        except OSError:
            pass
        reason = {"elevation": "a pasta do app exige administrador",
                  }.get(result, "veja o log do app")
        self._log(f"Atualização automática para v{info.version} NÃO foi concluída: {reason}.", "error")
        self._notify(f"⚠ A atualização automática do AutoTrigger para v{info.version} não foi "
                     f"concluída ({reason}). O app continua na v{self._version}.")


def report_previous(version: str, log, notify, marker_path: str | None = None) -> None:
    """Chamar na abertura: se a versão ANTERIOR deixou o marcador de atualização
    automática, diz se deu certo (a versão agora é a nova) ou não."""
    path = marker_path or _marker_path()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return
    try:
        os.remove(path)
    except OSError:
        pass
    old, new = data.get("from", "?"), data.get("to", "?")
    if version == new:
        log(f"✅ Atualizado automaticamente de v{old} para v{new}.", "success")
        notify(f"✅ AutoTrigger atualizado automaticamente: v{old} → v{new}.")
    else:
        log(f"⚠ A atualização automática para v{new} não chegou a instalar "
            f"(o app continua na v{version}).", "warn")
        notify(f"⚠ A atualização automática do AutoTrigger para v{new} não chegou a instalar: "
               f"o app continua na v{version}.")


def make_notifier(config, log):
    """Função que manda um aviso por Telegram e e-mail (se configurados), com o local
    do app na frente. Ignora as caixas de eventos: avisos de atualização são raros."""
    import emailer
    import telegram_notifier

    def notify(text: str) -> None:
        g = config.get_global()
        loc = g.get("location", "")
        tg = g.get("telegram", {}) or {}
        if tg.get("enabled") and telegram_notifier.is_configured(tg):
            telegram_notifier.notify_async(tg, telegram_notifier.with_location(text, loc), log=log)
        em = g.get("email", {}) or {}
        if em.get("enabled") and emailer.is_configured(em):
            subject, body = emailer.with_location(text.split("\n")[0][:90], text, loc)
            emailer.notify_async(em, subject, body, log=log)

    return notify
