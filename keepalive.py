"""
Modo "manter sempre rodando": se o app fechar SEM você ter pedido (queda,
"Finalizar tarefa", falta de memória...), um vigia o reabre sozinho.

O vigia é um .bat escondido e independente (não segura o .exe -- não atrapalha a
atualização automática) que espera o PID do app sumir. Ele NÃO reabre quando a
saída foi pedida: "Sair" na bandeja, atualização automática, opção desligada ou
desligamento/logoff do Windows -- todos criam o arquivo `keepalive.stop` (ver
request_stop). Para não ficar reabrindo um app que cai ao abrir, desiste depois de
_MAX_RELAUNCHES reaberturas seguidas sem o app ficar estável (mark_stable).

Arquivos (na pasta de logs): keepalive.bat, keepalive.stop, keepalive.count,
keepalive.hb (batimento do vigia), keepalive.log (o que o vigia fez).
"""
from __future__ import annotations

import os
import subprocess
import time

import applog
import startup

_MAX_RELAUNCHES = 5
_POLL_PINGS = 3        # ~2 s entre checagens do vigia
_RELAUNCH_PINGS = 6    # ~5 s de espera antes de reabrir
_HEARTBEAT_STALE = 20.0
_RESPAWN_GRACE = 20.0
_last_spawn = 0.0


def _dir() -> str:
    return applog.log_dir()


def _path(name: str) -> str:
    return os.path.join(_dir(), name)


def request_stop() -> None:
    """Diz ao vigia para NÃO reabrir o app (saída pedida pelo usuário)."""
    try:
        with open(_path("keepalive.stop"), "w", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S"))
    except OSError:
        pass


def _clear_stop() -> None:
    try:
        os.remove(_path("keepalive.stop"))
    except OSError:
        pass


def relaunch_count() -> int:
    """Quantas reaberturas seguidas o vigia fez (0 = abertura normal)."""
    try:
        with open(_path("keepalive.count"), encoding="utf-8") as f:
            return int(f.read().strip() or 0)
    except (OSError, ValueError):
        return 0


def mark_stable() -> None:
    """O app ficou estável: zera o contador de reaberturas seguidas."""
    try:
        os.remove(_path("keepalive.count"))
    except OSError:
        pass


def guardian_alive() -> bool:
    try:
        return time.time() - os.path.getmtime(_path("keepalive.hb")) < _HEARTBEAT_STALE
    except OSError:
        return False


def _bat_text(pid: int, app_cmd: str) -> str:
    return f"""@chcp 65001 >nul
@echo off
set PYINSTALLER_RESET_ENVIRONMENT=1
set "STOP={_path('keepalive.stop')}"
set "COUNT={_path('keepalive.count')}"
set "HB={_path('keepalive.hb')}"
set "LOG={_path('keepalive.log')}"
:wait
if exist "%STOP%" goto fim
type nul > "%HB%"
tasklist /FI "PID eq {pid}" 2>NUL | find "{pid}" >NUL
if errorlevel 1 goto caiu
ping -n {_POLL_PINGS} 127.0.0.1 >NUL
goto wait
:caiu
REM Espera um pouco: se o Windows esta desligando, este script morre junto antes
REM de reabrir; e da tempo da saida pedida (Sair/atualizacao) criar o .stop.
ping -n {_RELAUNCH_PINGS} 127.0.0.1 >NUL
if exist "%STOP%" goto fim
set N=0
if exist "%COUNT%" set /p N=<"%COUNT%"
if %N% GEQ {_MAX_RELAUNCHES} goto desistiu
set /a N+=1
>"%COUNT%" echo %N%
>>"%LOG%" echo %date% %time% - o app fechou sem pedido; reabrindo (tentativa %N% de {_MAX_RELAUNCHES})
start "" {app_cmd}
goto fim
:desistiu
>>"%LOG%" echo %date% %time% - o app caiu {_MAX_RELAUNCHES} vezes seguidas sem ficar estavel; vigia desistiu
:fim
del "%HB%" >NUL 2>&1
"""


def ensure_running(pid: int | None = None, app_cmd: str | None = None) -> bool:
    """Garante que o vigia está rodando para este app (sobe se não estiver).
    True se há vigia (já existia ou foi iniciado)."""
    global _last_spawn
    if guardian_alive():
        return True
    if _last_spawn and time.monotonic() - _last_spawn < _RESPAWN_GRACE:
        return True  # acabou de subir; o primeiro batimento ainda não apareceu
    _clear_stop()
    try:
        bat = _path("keepalive.bat")
        with open(bat, "w", encoding="utf-8", newline="\r\n") as f:
            f.write(_bat_text(pid or os.getpid(), app_cmd or startup.app_command()))
        subprocess.Popen(
            # "cmd /c" explícito: sem ele o `start` abre o .bat com "cmd /K", que fica
            # vivo (sem fazer nada) depois que o vigia termina -- um processo vazado
            # por vigia. O `start` solta o vigia da árvore do app (sobrevive a
            # "Finalizar árvore de processos").
            ["cmd.exe", "/c", "start", "", "/b", "cmd.exe", "/c", bat],
            creationflags=subprocess.CREATE_NO_WINDOW,
            close_fds=True,
        )
        _last_spawn = time.monotonic()
        return True
    except Exception as exc:
        applog.log(f"Modo sempre ligado: não consegui iniciar o vigia ({exc}).", "warn")
        return False


def apply(enabled: bool) -> None:
    """Liga/desliga o modo conforme a configuração (chamado ao abrir e ao salvar)."""
    global _last_spawn
    if enabled:
        ensure_running()
    else:
        _last_spawn = 0.0
        if guardian_alive():
            request_stop()
