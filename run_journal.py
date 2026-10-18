"""
Diário das sequências em execução, para RETOMAR depois de uma queda.

Grava em `run_journal.json` (pasta de logs) em que etapa cada sequência está e,
para etapas com duração (stream, espera), o instante em que terminam. Saída
normal apaga a entrada (concluída, cancelada, "Sair"); se o app cair, a entrada
fica e a próxima abertura decide se retoma (ver SequenceEngine.resume_interrupted).
`last_seen` é atualizado a cada poucos segundos, então "há quanto tempo o app
caiu" não depende de quanto durava a etapa.
"""
from __future__ import annotations

import json
import os
import threading
import time

import applog

_lock = threading.Lock()
_runs: dict = {}


def _path() -> str:
    return os.path.join(applog.log_dir(), "run_journal.json")


def _save() -> None:
    try:
        tmp = _path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"runs": _runs, "saved": time.time()}, f, ensure_ascii=False)
        os.replace(tmp, _path())
    except OSError:
        pass


def begin(seq_id: str, name: str, resumes: int = 0) -> None:
    with _lock:
        _runs[seq_id] = {"seq_id": seq_id, "name": name, "started_at": time.time(),
                         "last_seen": time.time(), "phase": "delay", "step": -1,
                         "step_type": "", "phase_end": None, "resumes": resumes}
        _save()


def update(seq_id: str, phase: str, step: int, step_type: str = "",
           phase_end: float | None = None) -> None:
    with _lock:
        run = _runs.get(seq_id)
        if run is None:
            return
        run.update(phase=phase, step=step, step_type=step_type, phase_end=phase_end,
                   last_seen=time.time())
        _save()


def end(seq_id: str) -> None:
    with _lock:
        if _runs.pop(seq_id, None) is not None:
            _save()


def clear() -> None:
    """Saída pedida pelo usuário: nada deve ser retomado."""
    with _lock:
        _runs.clear()
        _save()


def touch(live_end=None) -> None:
    """Marca que o app está vivo. `live_end(entry) -> epoch|None` devolve o término
    ao vivo da etapa atual (o stream pode ter ganhado/perdido tempo)."""
    with _lock:
        if not _runs:
            return
        now = time.time()
        for run in _runs.values():
            run["last_seen"] = now
            if live_end is not None:
                try:
                    end_at = live_end(run)
                except Exception:
                    end_at = None
                if end_at:
                    run["phase_end"] = end_at
        _save()


def load() -> dict:
    """Entradas gravadas por uma sessão anterior ({} se não há ou ilegível)."""
    try:
        with open(_path(), encoding="utf-8") as f:
            return dict(json.load(f).get("runs", {}))
    except (OSError, ValueError, AttributeError):
        return {}
