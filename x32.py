"""
Controle de canais da mesa Behringer X32 / Midas M32 por OSC sobre UDP (porta 10023).

Só o necessário: ligar/desligar (mutar) um canal e ler o nome/identificação da mesa.
Sem dependência nova (socket + struct). O botão ON da mesa aceso = canal LIGADO
(aberto); "desligar canal" = mutar (`/ch/NN/mix/on 0`).

UDP perde pacote, então cada ajuste é CONFIRMADO: espera o eco da mesa (ou lê o
valor de volta) e tenta de novo, até `retries` vezes. Falha nunca levanta exceção
para quem chama: devolve (False, motivo).
"""
from __future__ import annotations

import socket
import struct
import time

DEFAULT_PORT = 10023

# tipo -> (nome, quantidade máxima [0 = sem número], endereço do ON, endereço do nome)
TARGETS = {
    "ch":      ("Canal",      32, "/ch/{n:02d}/mix/on",      "/ch/{n:02d}/config/name"),
    "auxin":   ("Aux In",      8, "/auxin/{n:02d}/mix/on",   "/auxin/{n:02d}/config/name"),
    "fxrtn":   ("Retorno FX",  8, "/fxrtn/{n:02d}/mix/on",   "/fxrtn/{n:02d}/config/name"),
    "bus":     ("Bus",        16, "/bus/{n:02d}/mix/on",     "/bus/{n:02d}/config/name"),
    "mtx":     ("Matrix",      6, "/mtx/{n:02d}/mix/on",     "/mtx/{n:02d}/config/name"),
    "dca":     ("DCA",         8, "/dca/{n}/on",             "/dca/{n}/config/name"),
    "main_st": ("Main LR",     0, "/main/st/mix/on",         ""),
    "main_m":  ("Main Mono",   0, "/main/m/mix/on",          ""),
}
_SHORT = {"ch": "Ch", "auxin": "Aux In", "fxrtn": "FX", "bus": "Bus", "mtx": "Mtx", "dca": "DCA",
          "main_st": "Main LR", "main_m": "Main Mono"}


class X32Error(Exception):
    pass


# ── endereços ────────────────────────────────────────────────────────────────────

def max_number(kind: str) -> int:
    return TARGETS[kind][1]


def _check(kind: str, number: int) -> int:
    if kind not in TARGETS:
        raise ValueError(f"tipo de alvo desconhecido: {kind}")
    mx = TARGETS[kind][1]
    if mx == 0:
        return 0
    n = int(number)
    if not 1 <= n <= mx:
        raise ValueError(f"{TARGETS[kind][0]} {n} fora do intervalo (1-{mx})")
    return n


def target_address(kind: str, number: int) -> str:
    """Endereço OSC do ON do alvo ("/ch/05/mix/on")."""
    n = _check(kind, number)
    return TARGETS[kind][2].format(n=n)


def name_address(kind: str, number: int) -> str:
    n = _check(kind, number)
    tpl = TARGETS[kind][3]
    return tpl.format(n=n) if tpl else ""


def target_label(kind: str, number: int) -> str:
    """"Ch 05", "Bus 03", "DCA 2", "Main LR"."""
    n = _check(kind, number)
    if TARGETS[kind][1] == 0:
        return _SHORT[kind]
    return f"{_SHORT[kind]} {n:02d}" if kind != "dca" else f"{_SHORT[kind]} {n}"


# ── OSC mínimo ───────────────────────────────────────────────────────────────────

def _pad(b: bytes) -> bytes:
    return b + b"\x00" * (4 - len(b) % 4)       # sempre com ao menos 1 nulo


def osc_message(address: str, *args) -> bytes:
    """Mensagem OSC 1.0. Sem argumentos = pedido de leitura (a mesa responde com o valor)."""
    msg = _pad(address.encode("utf-8"))
    if not args:
        return msg
    tags, data = ",", b""
    for a in args:
        if isinstance(a, bool):
            a = int(a)
        if isinstance(a, int):
            tags += "i"; data += struct.pack(">i", a)
        elif isinstance(a, float):
            tags += "f"; data += struct.pack(">f", a)
        else:
            tags += "s"; data += _pad(str(a).encode("utf-8"))
    return msg + _pad(tags.encode()) + data


def parse_osc(data: bytes):
    """(endereço, [argumentos]) ou None se não for uma mensagem OSC compreensível."""
    try:
        if not data.startswith(b"/"):
            return None
        end = data.index(b"\x00")
        addr = data[:end].decode("utf-8", "replace")
        pos = end + 4 - (end % 4)
        if pos >= len(data):
            return addr, []
        tend = data.index(b"\x00", pos)
        tags = data[pos:tend].decode("ascii", "replace")
        pos = tend + 4 - ((tend - pos) % 4)
        args = []
        for t in tags[1:]:
            if t == "i":
                args.append(struct.unpack(">i", data[pos:pos + 4])[0]); pos += 4
            elif t == "f":
                args.append(struct.unpack(">f", data[pos:pos + 4])[0]); pos += 4
            elif t == "s":
                e = data.index(b"\x00", pos)
                args.append(data[pos:e].decode("utf-8", "replace"))
                pos = e + 4 - ((e - pos) % 4)
            else:
                return addr, args           # tipo que não usamos (blob...)
        return addr, args
    except (ValueError, struct.error):
        return None


# ── conversa com a mesa ──────────────────────────────────────────────────────────

def _open(host: str):
    try:
        return socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    except OSError as exc:
        raise X32Error(f"sem rede: {exc}")


def _wait(sock, want: str, timeout: float):
    """Espera uma resposta com o endereço `want`; None se não vier no prazo."""
    deadline = time.time() + timeout
    while True:
        left = deadline - time.time()
        if left <= 0:
            return None
        sock.settimeout(left)
        try:
            data, _ = sock.recvfrom(4096)
        except socket.timeout:
            return None
        except OSError:
            return None
        parsed = parse_osc(data)
        if parsed and parsed[0] == want:
            return parsed[1]


def query(host: str, port: int, address: str, timeout: float = 0.8, retries: int = 3):
    """Lê um valor da mesa. Devolve a lista de argumentos ou None (sem resposta)."""
    sock = _open(host)
    try:
        for _ in range(max(1, retries)):
            try:
                sock.sendto(osc_message(address), (host, int(port)))
            except (OSError, UnicodeError) as exc:
                raise X32Error(f"não consegui falar com '{host}': {exc}")
            got = _wait(sock, address, timeout)
            if got is not None:
                return got
        return None
    finally:
        sock.close()


def set_int(host: str, port: int, address: str, value: int, timeout: float = 0.8,
            retries: int = 3) -> bool:
    """Grava um inteiro e CONFIRMA (eco da mesa ou leitura de volta)."""
    sock = _open(host)
    try:
        for _ in range(max(1, retries)):
            try:
                sock.sendto(osc_message(address, int(value)), (host, int(port)))
            except (OSError, UnicodeError) as exc:
                raise X32Error(f"não consegui falar com '{host}': {exc}")
            echo = _wait(sock, address, timeout)
            if echo is not None and echo[:1] == [int(value)]:
                return True
            try:
                sock.sendto(osc_message(address), (host, int(port)))
            except OSError:
                continue
            back = _wait(sock, address, timeout)
            if back is not None and back[:1] == [int(value)]:
                return True
        return False
    finally:
        sock.close()


def set_channel(host: str, port: int, kind: str, number: int, on: bool,
                timeout: float = 0.8, retries: int = 3) -> tuple:
    """Liga (on=True) ou desliga/muta (on=False) o alvo. (ok, detalhe)."""
    host = (host or "").strip()
    if not host:
        return False, "IP da mesa não configurado"
    try:
        address = target_address(kind, number)
        if set_int(host, port or DEFAULT_PORT, address, 1 if on else 0, timeout, retries):
            return True, "confirmado pela mesa"
        return False, f"a mesa em {host}:{port} não respondeu (IP, rede ou OSC desligado?)"
    except ValueError as exc:
        return False, str(exc)
    except X32Error as exc:
        return False, str(exc)


def read_name(host: str, port: int, kind: str, number: int, timeout: float = 0.8,
              retries: int = 2) -> str | None:
    """Nome do canal na mesa ("" se sem nome, None se não respondeu / sem nome p/ o tipo)."""
    try:
        addr = name_address(kind, number)
        if not addr or not (host or "").strip():
            return None
        got = query(host.strip(), port or DEFAULT_PORT, addr, timeout, retries)
    except (ValueError, X32Error):
        return None
    if not got:
        return None if got is None else ""
    return str(got[0]).strip()


def info(host: str, port: int = DEFAULT_PORT, timeout: float = 1.0, retries: int = 2) -> dict | None:
    """Identificação da mesa ({"version","server","model","firmware"}) ou None."""
    try:
        got = query((host or "").strip(), port or DEFAULT_PORT, "/info", timeout, retries)
    except X32Error:
        return None
    if not got:
        return None
    got = list(got) + [""] * 4
    return {"version": got[0], "server": got[1], "model": got[2], "firmware": got[3]}
