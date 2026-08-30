"""
Envio de alertas por email via SMTP (smtplib — biblioteca padrão).

Suporta SMTP comum (porta 587 + STARTTLS) e SMTP_SSL (porta 465).
O envio nunca deve bloquear o engine/UI: use notify_async() para disparar
em thread daemon. Falha de email não interrompe a sequência.
"""
from __future__ import annotations

import smtplib
import threading
from email.message import EmailMessage


def _parse_recipients(raw: str) -> list[str]:
    """Aceita destinatários separados por vírgula, ponto-e-vírgula ou espaço."""
    if not raw:
        return []
    parts = raw.replace(";", ",").replace(" ", ",").split(",")
    return [p.strip() for p in parts if p.strip()]


def is_configured(cfg: dict) -> bool:
    """True se há o mínimo para enviar (host, remetente e ao menos 1 destino)."""
    if not cfg:
        return False
    return bool(
        cfg.get("smtp_host", "").strip()
        and cfg.get("from_addr", "").strip()
        and _parse_recipients(cfg.get("to_addrs", ""))
    )


def send_email(cfg: dict, subject: str, body: str) -> tuple[bool, str]:
    """Envia um email síncrono. Retorna (ok, mensagem_de_erro)."""
    host = cfg.get("smtp_host", "").strip()
    port = int(cfg.get("smtp_port", 587) or 587)
    use_tls = bool(cfg.get("use_tls", True))
    username = cfg.get("username", "").strip()
    password = cfg.get("password", "")
    from_addr = cfg.get("from_addr", "").strip()
    recipients = _parse_recipients(cfg.get("to_addrs", ""))

    if not host:
        return False, "Servidor SMTP não configurado."
    if not from_addr:
        return False, "Remetente (from) não configurado."
    if not recipients:
        return False, "Nenhum destinatário configurado."

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = ", ".join(recipients)
    msg.set_content(body)

    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=20) as server:
                if username:
                    server.login(username, password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=20) as server:
                server.ehlo()
                if use_tls:
                    server.starttls()
                    server.ehlo()
                if username:
                    server.login(username, password)
                server.send_message(msg)
        return True, ""
    except Exception as exc:
        return False, str(exc)


def notify_async(cfg: dict, subject: str, body: str, log=None) -> None:
    """Dispara send_email em thread daemon. Loga sucesso/falha se `log` dado."""
    def _run():
        ok, err = send_email(cfg, subject, body)
        if log:
            if ok:
                log(f"📧 Email enviado: {subject}", "info")
            else:
                log(f"📧 Falha ao enviar email: {err}", "warn")

    threading.Thread(target=_run, daemon=True, name="emailer").start()
