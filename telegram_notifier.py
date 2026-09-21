"""
Envio de alertas por Telegram via Bot API (requests — já é dependência do app).

Suporta VÁRIOS contatos (cada um com nome + chat_id) usando o mesmo bot. O
envio nunca deve bloquear o engine/UI: use notify_async() para disparar em
thread daemon. Falha de Telegram (ou de um dos contatos) não interrompe a
sequência nem os demais envios.

Formato da config:
    {"enabled": bool, "bot_token": str,
     "contacts": [{"name": str, "chat_id": str, "enabled": bool}, ...],
     "events": {...}}
"""
from __future__ import annotations

import threading

import requests

_API_BASE = "https://api.telegram.org/bot{token}/sendMessage"


def active_contacts(cfg: dict) -> list:
    """Contatos que devem receber: habilitados e com chat_id preenchido.

    Tolera o formato antigo (um único `chat_id` solto), caso a config ainda
    não tenha sido migrada pelo Config.
    """
    if not cfg:
        return []
    out = []
    for c in cfg.get("contacts", []) or []:
        chat_id = str(c.get("chat_id", "")).strip()
        if chat_id and c.get("enabled", True):
            out.append({"name": (c.get("name") or "").strip() or chat_id,
                        "chat_id": chat_id})
    legacy = str(cfg.get("chat_id", "")).strip()
    if legacy and not out and not cfg.get("contacts"):
        out.append({"name": "Contato", "chat_id": legacy})
    return out


def is_configured(cfg: dict) -> bool:
    """True se há o mínimo para enviar (token do bot e ao menos um contato)."""
    if not cfg:
        return False
    return bool(cfg.get("bot_token", "").strip() and active_contacts(cfg))


# Travessões "bonitos" que o Windows/Telegram/Word colocam no lugar do "-" ao copiar.
_DASHES = str.maketrans({"−": "-", "–": "-", "—": "-", "‒": "-"})

# chat_id digitado (normalizado) -> forma que o Telegram aceitou. Evita tentar de novo.
_RESOLVED: dict = {}


def _normalize_chat_id(raw) -> str:
    return "".join(str(raw).translate(_DASHES).split())


def _chat_id_candidates(chat_id: str) -> list:
    """Formas de escrever o mesmo chat, da mais provável à menos.

    O Telegram usa IDs diferentes por tipo: usuário = número puro; grupo =
    "-número"; supergrupo/canal = "-100número". Quem digita costuma esquecer
    (ou colocar a mais) o "-". Por isso, se o ID digitado não for aceito,
    tentamos as outras formas (só quando o erro é "chat not found").
    """
    cid = _normalize_chat_id(chat_id)
    digits = cid.lstrip("-")
    if cid.startswith("@") or not digits.isdigit():
        return [cid]
    out = [_RESOLVED.get(cid, cid)]
    if not cid.startswith("-"):
        alts = [f"-{digits}", f"-100{digits}"]
    elif not digits.startswith("100"):
        alts = [digits, f"-100{digits}"]
    else:
        alts = []
    return out + [a for a in alts if a not in out]


def _post_message(token: str, chat_id: str, text: str) -> tuple[bool, str, bool]:
    """Um envio. Retorna (ok, erro, vale_tentar_outra_forma_do_id)."""
    try:
        resp = requests.post(
            _API_BASE.format(token=token),
            json={"chat_id": chat_id, "text": text},
            timeout=15,
        )
        if resp.status_code == 200 and resp.json().get("ok"):
            return True, "", False
        try:
            desc = resp.json().get("description", resp.text)
        except Exception:
            desc = resp.text
        return False, f"HTTP {resp.status_code}: {desc}", (
            resp.status_code == 400 and "chat not found" in str(desc).lower())
    except Exception as exc:
        return False, str(exc), False


def send_telegram(cfg: dict, text: str, chat_id: str | None = None,
                  log=None) -> tuple[bool, str]:
    """Envia uma mensagem síncrona para UM chat. Retorna (ok, mensagem_de_erro).

    Se `chat_id` não for dado, usa o primeiro contato ativo. O chat_id pode
    ser digitado com ou sem "-" (ver _chat_id_candidates).
    """
    token = cfg.get("bot_token", "").strip()
    if chat_id is None:
        contacts = active_contacts(cfg)
        chat_id = contacts[0]["chat_id"] if contacts else ""
    chat_id = _normalize_chat_id(chat_id)

    if not token:
        return False, "Token do bot não configurado."
    if not chat_id:
        return False, "Chat ID não configurado."

    first_err = ""
    tried = []
    already_known = chat_id in _RESOLVED
    for cand in _chat_id_candidates(chat_id):
        ok, err, retry = _post_message(token, cand, text)
        if ok:
            if cand != chat_id:
                _RESOLVED[chat_id] = cand
                if log and not already_known:   # avisa só na descoberta, não a cada envio
                    log(f"📨 chat_id '{chat_id}' foi aceito como '{cand}' "
                        f"(grupos usam '-', usuários não); usando essa forma.", "info")
            return True, ""
        first_err = first_err or err
        tried.append(cand)
        if not retry:
            break
    if len(tried) > 1:
        first_err += f" (tentei: {', '.join(tried)})"
    return False, first_err


def notify_async(cfg: dict, text: str, log=None, contacts: list | None = None) -> None:
    """Dispara o envio em thread daemon, um contato por vez.

    `contacts` (lista de {"name","chat_id"}) substitui os contatos ativos da
    config -- usado pelo botão "Testar" de um contato específico. Loga
    sucesso/falha POR CONTATO (pelo nome) se `log` dado.
    """
    targets = contacts if contacts is not None else active_contacts(cfg)

    def _run():
        for c in targets:
            ok, err = send_telegram(cfg, text, chat_id=c["chat_id"], log=log)
            if log:
                if ok:
                    log(f"📨 Telegram enviado para {c['name']}: {text[:60]}", "info")
                else:
                    log(f"📨 Falha ao enviar Telegram para {c['name']}: {err}", "warn")

    threading.Thread(target=_run, daemon=True, name="telegram").start()
