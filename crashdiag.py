"""
Diagnóstico de quedas e travamentos do AutoTrigger.

Três peças, todas gravando na pasta de logs (ao lado do autotrigger.log):

1. crash.log  -- `faulthandler` grava a PILHA DE TODAS AS THREADS quando o
   processo sofre uma queda nativa (violação de acesso, etc.), coisa que o
   Python normalmente NÃO consegue registrar (o app simplesmente some).

2. last_session.txt -- marcador "sessão em andamento". Se na próxima abertura
   ele ainda disser "running", a sessão anterior NÃO terminou normalmente
   (queda, kill, energia): isso vai para o autotrigger.log como aviso. Cobre
   também as quedas que o faulthandler não consegue capturar.

3. Vigia de travamento -- a interface (thread principal) dá um "sinal de vida"
   a cada 0,5 s; se ficar >8 s sem sinal, a pilha de todas as threads é gravada
   no crash.log (mostra ONDE travou) e um aviso vai para o log.
"""
from __future__ import annotations

import atexit
import faulthandler
import json
import os
import threading
import time
from datetime import datetime

_crash_file = None
_state_path = None
_clean_marked = False
_MAX_CRASH_LOG = 500_000  # bytes; acima disso gira para crash.log.1


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _read_state(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _write_state(**fields):
    if not _state_path:
        return
    try:
        with open(_state_path, "w", encoding="utf-8") as f:
            json.dump(fields, f, ensure_ascii=False)
    except Exception:
        pass


def _pid_alive(pid) -> bool:
    try:
        import psutil
        return psutil.pid_exists(int(pid))
    except Exception:
        return False


def install(log_dir: str, version: str, log) -> None:
    """Liga o faulthandler, avisa se a sessão anterior caiu e marca esta como
    "em andamento". Chamar UMA vez, depois de confirmar que é a instância
    principal. Nunca levanta exceção (diagnóstico não pode derrubar o app)."""
    global _crash_file, _state_path
    try:
        crash_path = os.path.join(log_dir, "crash.log")
        _state_path = os.path.join(log_dir, "last_session.txt")

        prev = _read_state(_state_path)
        if prev.get("status") == "running" and int(prev.get("pid", 0)) != os.getpid() \
                and not _pid_alive(prev.get("pid", 0)):
            log(f"⚠ A sessão anterior (v{prev.get('version', '?')}, iniciada em "
                f"{prev.get('started', '?')}, PID {prev.get('pid', '?')}) NÃO foi "
                f"encerrada normalmente: o app caiu ou foi finalizado à força. "
                f"Se foi queda nativa, a pilha está em {crash_path}.", "warn")

        try:
            if os.path.exists(crash_path) and os.path.getsize(crash_path) > _MAX_CRASH_LOG:
                os.replace(crash_path, crash_path + ".1")
        except OSError:
            pass
        _crash_file = open(crash_path, "a", encoding="utf-8", buffering=1)
        _crash_file.write(f"\n===== sessão iniciada {_now()} | v{version} | "
                          f"PID {os.getpid()} =====\n")
        faulthandler.enable(file=_crash_file, all_threads=True)

        _write_state(pid=os.getpid(), version=version, started=_now(), status="running")
        atexit.register(mark_clean, "encerramento normal")
    except Exception as exc:
        try:
            log(f"Diagnóstico de queda indisponível: {exc}", "warn")
        except Exception:
            pass


def mark_clean(reason: str = "") -> None:
    """Marca a sessão como encerrada normalmente (chamado no atexit e antes do
    os._exit da atualização automática)."""
    global _clean_marked
    if _clean_marked or not _state_path:
        return
    _clean_marked = True
    st = _read_state(_state_path)
    _write_state(pid=st.get("pid", os.getpid()), version=st.get("version", ""),
                 started=st.get("started", ""), status="clean",
                 ended=_now(), reason=reason)
    try:
        if _crash_file:
            _crash_file.write(f"===== sessão encerrada {_now()} ({reason}) =====\n")
            _crash_file.flush()
    except Exception:
        pass


def dump_threads(header: str) -> None:
    """Grava a pilha de todas as threads no crash.log (uso manual/watchdog)."""
    if not _crash_file:
        return
    try:
        _crash_file.write(f"\n--- {_now()} | {header} ---\n")
        faulthandler.dump_traceback(file=_crash_file, all_threads=True)
        _crash_file.flush()
    except Exception:
        pass


def start_freeze_watchdog(app, log, threshold: float = 8.0):
    """Vigia a thread da interface. Deve ser chamada na thread principal, com
    o QApplication já criado. Retorna o QTimer (mantido vivo pelo `app`)."""
    from PySide6.QtCore import QTimer

    beat = {"t": time.monotonic()}
    timer = QTimer(app)
    timer.setInterval(500)
    timer.timeout.connect(lambda: beat.__setitem__("t", time.monotonic()))
    timer.start()

    def _watch():
        frozen, dumped_long = False, False
        while True:
            time.sleep(1.0)
            age = time.monotonic() - beat["t"]
            if age > threshold and not frozen:
                frozen = True
                log(f"⚠ A interface parou de responder há {age:.0f}s — gravando "
                    f"a pilha das threads em crash.log.", "warn")
                dump_threads(f"interface sem responder há {age:.0f}s")
            elif frozen and not dumped_long and age > 30:
                dumped_long = True
                dump_threads(f"interface AINDA sem responder ({age:.0f}s)")
            elif frozen and age <= threshold:
                frozen, dumped_long = False, False
                log("Interface voltou a responder.", "info")

    threading.Thread(target=_watch, daemon=True, name="freeze-watchdog").start()
    return timer
