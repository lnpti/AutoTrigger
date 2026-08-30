"""
Logging central do AutoTrigger V10.

- Grava em arquivo rotativo em <data_dir>/logs/autotrigger.log, onde data_dir é a
  mesma pasta resolvida para o config (ao lado do .exe ou %APPDATA%).
- Expõe um log_callback(msg, level) compatível com o restante do app
  (engine/runner/player usam essa assinatura).
- Permite registrar um "sink" de UI (ex.: a LogView Qt) que recebe (msg, level).
- Instala sys.excepthook e threading.excepthook para capturar erros não tratados.
"""
from __future__ import annotations

import logging
import os
import sys
import threading
import traceback
from logging.handlers import RotatingFileHandler
from typing import Callable, Optional

_LEVEL_MAP = {
    "info": logging.INFO,
    "success": logging.INFO,
    "warn": logging.WARNING,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}

_logger: Optional[logging.Logger] = None
_ui_sink: Optional[Callable[[str, str], None]] = None
_sink_lock = threading.Lock()


def _resolve_log_dir() -> str:
    """Pasta de logs ao lado do config (reaproveita a lógica do config.py)."""
    try:
        import config
        base = os.path.dirname(config.CONFIG_FILE)
    except Exception:
        base = os.path.dirname(os.path.abspath(__file__))
    log_dir = os.path.join(base, "logs")
    try:
        os.makedirs(log_dir, exist_ok=True)
    except OSError:
        pass
    return log_dir


def init(level: int = logging.INFO) -> logging.Logger:
    """Inicializa o logger (idempotente) e instala os excepthooks."""
    global _logger
    if _logger is not None:
        return _logger

    logger = logging.getLogger("autotrigger")
    logger.setLevel(level)
    logger.propagate = False

    log_path = os.path.join(_resolve_log_dir(), "autotrigger.log")
    try:
        fh = RotatingFileHandler(
            log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        fh.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S"
        ))
        logger.addHandler(fh)
    except Exception as exc:  # nunca impedir o app de subir por causa de log
        print(f"[applog] Não foi possível abrir o arquivo de log: {exc}")

    # Também ecoa no console em dev
    if not getattr(sys, "frozen", False):
        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        logger.addHandler(ch)

    _logger = logger
    _install_excepthooks()
    logger.info("==== AutoTrigger iniciado | log em %s ====", log_path)
    return logger


def set_ui_sink(fn: Optional[Callable[[str, str], None]]):
    """Define (ou remove) o destino de UI que recebe (msg, level)."""
    global _ui_sink
    with _sink_lock:
        _ui_sink = fn


def log(msg: str, level: str = "info"):
    """log_callback padrão do app. Grava no arquivo e repassa para a UI."""
    if _logger is None:
        init()
    _logger.log(_LEVEL_MAP.get(level, logging.INFO), msg)
    with _sink_lock:
        sink = _ui_sink
    if sink is not None:
        try:
            sink(msg, level)
        except Exception:
            pass


def _install_excepthooks():
    def _hook(exc_type, exc_value, exc_tb):
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        if _logger is not None:
            _logger.error("Exceção não tratada:\n%s", text)
        else:
            print(text)

    sys.excepthook = _hook

    def _thread_hook(args):
        text = "".join(traceback.format_exception(
            args.exc_type, args.exc_value, args.exc_traceback
        ))
        if _logger is not None:
            _logger.error("Exceção em thread '%s':\n%s",
                          getattr(args.thread, "name", "?"), text)
        else:
            print(text)

    try:
        threading.excepthook = _thread_hook
    except Exception:
        pass
