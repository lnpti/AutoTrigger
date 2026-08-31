"""
Envio de alertas por Telegram via Bot API (requests — já é dependência do app).

O envio nunca deve bloquear o engine/UI: use notify_async() para disparar em
thread daemon. Falha de Telegram não interrompe a sequência.
"""
from __future__ import annotations

import threading

import requests

_API_BASE = "https://api.telegram.org/bot{token}/sendMessage"


def is_configured(cfg: dict) -> bool:
    """True se há o mínimo para enviar (token do bot e chat_id)."""
    if not cfg:
        return False
    return bool(cfg.get("bot_token", "").strip() and cfg.get("chat_id", "").strip())


def send_telegram(cfg: dict, text: str) -> tuple[bool, str]:
    """Envia uma mensagem síncrona. Retorna (ok, mensagem_de_erro)."""
    token = cfg.get("bot_token", "").strip()
    chat_id = cfg.get("chat_id", "").strip()

    if not token:
        return False, "Token do bot não configurado."
    if not chat_id:
        return False, "Chat ID não configurado."

    try:
        resp = requests.post(
            _API_BASE.format(token=token),
            json={"chat_id": chat_id, "text": text},
            timeout=15,
        )
        if resp.status_code == 200 and resp.json().get("ok"):
            return True, ""
        try:
            desc = resp.json().get("description", resp.text)
        except Exception:
            desc = resp.text
        return False, f"HTTP {resp.status_code}: {desc}"
    except Exception as exc:
        return False, str(exc)


def notify_async(cfg: dict, text: str, log=None) -> None:
    """Dispara send_telegram em thread daemon. Loga sucesso/falha se `log` dado."""
    def _run():
        ok, err = send_telegram(cfg, text)
        if log:
            if ok:
                log(f"📨 Telegram enviado: {text[:60]}", "info")
            else:
                log(f"📨 Falha ao enviar Telegram: {err}", "warn")

    threading.Thread(target=_run, daemon=True, name="telegram").start()
