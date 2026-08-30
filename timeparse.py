"""
Utilitários de tempo e de agenda compartilhados pela UI e pelo motor.

- parse_secs / fmt_secs: conversão flexível de tempo (h/m/s) <-> segundos.
- is_armed_today: avalia se uma sequência está "armada" para o dia atual.
"""
from __future__ import annotations

import re
from datetime import datetime


# ── tempo ──────────────────────────────────────────────────────────────────────

def fmt_secs(seconds) -> str:
    """Converte segundos em string legível: '1h 30m', '5m 30s', '45s'."""
    s = int(seconds or 0)
    if s <= 0:
        return "0s"
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    parts = []
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}m")
    if sec:
        parts.append(f"{sec}s")
    return " ".join(parts) if parts else "0s"


def parse_secs(text: str) -> int:
    """
    Converte texto flexível em segundos. Aceita:
      '1h 30m', '1h30m15s', '2h', '5m 30s', '90', '5:30', '1:05:30'.
    Retorna 0 se não conseguir interpretar.
    """
    if text is None:
        return 0
    text = str(text).strip().lower()
    if not text:
        return 0

    # Formato relógio: H:M:S ou M:S
    if ":" in text:
        parts = text.split(":")
        try:
            nums = [int(p) for p in parts]
        except ValueError:
            return 0
        if len(nums) == 3:
            return nums[0] * 3600 + nums[1] * 60 + nums[2]
        if len(nums) == 2:
            return nums[0] * 60 + nums[1]
        if len(nums) == 1:
            return nums[0]
        return 0

    # Formato com sufixos h/m/s (em qualquer combinação)
    if re.search(r"[hms]", text):
        total = 0
        found = False
        for value, unit in re.findall(r"(\d+)\s*([hms])", text):
            found = True
            v = int(value)
            if unit == "h":
                total += v * 3600
            elif unit == "m":
                total += v * 60
            else:
                total += v
        if found:
            return total
        return 0

    # Número puro = segundos
    try:
        return int(float(text))
    except ValueError:
        return 0


def fmt_hint(seconds: int) -> str:
    """Texto de confirmação ao vivo: '→ 1h 30m 0s (5400s)'."""
    s = int(seconds or 0)
    return f"→ {fmt_secs(s)}  ({s}s)"


# ── agenda ─────────────────────────────────────────────────────────────────────

WEEKDAY_LABELS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]


def is_armed_today(seq: dict, now: datetime | None = None) -> bool:
    """
    Retorna True se a sequência deve ficar armada (escutando a keyword) hoje.
    schedule = {"mode": "always"|"weekdays"|"dates", "weekdays":[0..6], "dates":[...] }
      - weekdays: 0 = segunda ... 6 = domingo (datetime.weekday()).
      - dates: lista de 'YYYY-MM-DD'.
    Sem schedule (ou mode 'always') → sempre armada.
    """
    sched = seq.get("schedule")
    if not sched:
        return True
    mode = sched.get("mode", "always")
    if mode == "always":
        return True

    now = now or datetime.now()
    if mode == "weekdays":
        days = sched.get("weekdays", [])
        return now.weekday() in days
    if mode == "dates":
        today = now.strftime("%Y-%m-%d")
        return today in sched.get("dates", [])
    return True
