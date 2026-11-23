"""
Proteção contra o sumiço da pasta temporária do PyInstaller (`_MEIxxxxxx`).

O .exe (onefile) extrai Python e bibliotecas numa pasta `_MEI...` em %TEMP%. Uma limpeza
de temporários (Windows, antivírus) pode apagá-la COM O APP ABERTO: o que já foi carregado
continua funcionando, mas qualquer `import`/codificação carregada DEPOIS falha com
"[Errno 2] No such file or directory: ...\\_MEIxxxx\\base_library.zip". Foi assim que a
atualização falhou no estúdio ("não foi possível preparar a instalação").

Aqui: (1) `warm_up()` carrega no início o que o app pode precisar mais tarde;
(2) `ascii_bytes()` converte texto sem passar pelo sistema de codificações;
(3) `start_watch()` avisa no log (uma vez) se a pasta sumir.
"""
from __future__ import annotations

import os
import sys
import threading

_ENCODINGS = ("ascii", "utf-8", "utf_8_sig", "latin-1", "cp1252", "cp850", "cp437",
              "mbcs", "utf-16", "utf-16-le", "idna", "raw_unicode_escape", "unicode_escape")
_MODULES = ("ctypes", "ctypes.wintypes", "subprocess", "tempfile", "shutil", "json",
            "hashlib", "zipfile", "csv", "struct", "socket", "ssl", "urllib.request",
            "email.mime.text", "email.mime.multipart", "smtplib", "logging.handlers")


def warm_up() -> list:
    """Carrega codificações e módulos usados só em momentos raros (atualização, e-mail...).
    Devolve a lista do que NÃO deu para carregar (normalmente vazia)."""
    import codecs
    import importlib
    failed = []
    for enc in _ENCODINGS:
        try:
            codecs.lookup(enc)
            "a".encode(enc, "replace")
        except Exception:      # mbcs só existe no Windows etc.: não é problema
            pass
    for mod in _MODULES:
        try:
            importlib.import_module(mod)
        except ModuleNotFoundError:
            pass                 # este app não empacota o módulo: nada a pré-carregar
        except Exception as exc:
            failed.append(f"{mod} ({exc})")
    return failed


def ascii_bytes(text: str) -> bytes:
    """Texto -> bytes ASCII (o que não for ASCII vira '?') SEM usar o sistema de
    codificações (que pode precisar ler arquivos da pasta temporária já apagada)."""
    return bytes(ord(c) if ord(c) < 128 else 63 for c in text)


def runtime_dir() -> str | None:
    """Pasta `_MEI...` deste processo (None quando não é o .exe empacotado)."""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", None)
    return None


def runtime_ok() -> tuple:
    """(ok, detalhe). Fora do .exe empacotado sempre (True, "")."""
    d = runtime_dir()
    if not d:
        return True, ""
    if not os.path.isdir(d):
        return False, f"a pasta temporária do app sumiu ({d})"
    zp = os.path.join(d, "base_library.zip")
    if not os.path.isfile(zp):
        return False, f"faltam arquivos na pasta temporária do app ({zp})"
    return True, ""


def start_watch(log, every: float = 300.0):
    """Thread que confere a pasta temporária a cada `every` s e avisa UMA vez no log
    se ela sumir. `log(msg, level)`."""
    def _run():
        stop = threading.Event()
        warned = False
        while not stop.wait(every):
            ok, why = runtime_ok()
            if not ok and not warned:
                warned = True
                try:
                    log(f"⚠ {why}. Provavelmente uma limpeza de temporários (Windows/antivírus) "
                        f"apagou os arquivos do app em execução. Ele segue funcionando, mas a "
                        f"atualização automática pode falhar: reinicie o app quando puder "
                        f"(Sair pela bandeja e abrir de novo).", "warn")
                except Exception:
                    pass
            elif ok:
                warned = False
    t = threading.Thread(target=_run, daemon=True, name="runtime-guard")
    t.start()
    return t
