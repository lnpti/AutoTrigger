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
        elif isinstance(a, (bytes, bytearray)):
            tags += "b"; data += struct.pack(">i", len(a)) + bytes(a) + b"\x00" * (-len(a) % 4)
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
            elif t == "b":
                size = struct.unpack(">i", data[pos:pos + 4])[0]
                if size < 0 or pos + 4 + size > len(data):
                    return None
                args.append(bytes(data[pos + 4:pos + 4 + size]))
                pos += 4 + size + (-size % 4)
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


def set_float(host: str, port: int, address: str, value: float, timeout: float = 0.8,
              retries: int = 3, tol: float = 0.004) -> bool:
    """Grava um float (0..1) e CONFIRMA (eco ou leitura de volta, com tolerância)."""
    def _same(got):
        return (got is not None and got[:1] and isinstance(got[0], (int, float))
                and abs(float(got[0]) - float(value)) <= tol)
    sock = _open(host)
    try:
        for _ in range(max(1, retries)):
            try:
                sock.sendto(osc_message(address, float(value)), (host, int(port)))
            except (OSError, UnicodeError) as exc:
                raise X32Error(f"não consegui falar com '{host}': {exc}")
            if _same(_wait(sock, address, timeout)):
                return True
            try:
                sock.sendto(osc_message(address), (host, int(port)))
            except OSError:
                continue
            if _same(_wait(sock, address, timeout)):
                return True
        return False
    finally:
        sock.close()


# ── fader (volume) ───────────────────────────────────────────────────────────────
# O fader da X32 é um float 0..1 com curva própria: 0.0 = -infinito, 0.75 = 0 dB, 1.0 = +10 dB.

def db_to_fader(db: float) -> float:
    db = max(-90.0, min(10.0, float(db)))
    if db >= -10:
        f = (db + 30.0) / 40.0
    elif db >= -30:
        f = (db + 50.0) / 80.0
    elif db >= -60:
        f = (db + 70.0) / 160.0
    else:
        f = (db + 90.0) / 480.0
    return max(0.0, min(1.0, f))


def fader_to_db(f: float) -> float:
    f = max(0.0, min(1.0, float(f)))
    if f >= 0.5:
        return f * 40.0 - 30.0
    if f >= 0.25:
        return f * 80.0 - 50.0
    if f >= 0.0625:
        return f * 160.0 - 70.0
    return f * 480.0 - 90.0 if f > 0 else -90.0


def fader_address(kind: str, number: int) -> str:
    """Endereço OSC do fader do alvo ("/ch/05/mix/fader", "/dca/2/fader")."""
    return target_address(kind, number)[:-2] + "fader"      # troca o "on" final por "fader"


def set_channel(host: str, port: int, kind: str, number: int, on: bool,
                timeout: float = 0.8, retries: int = 3, fader_db: float | None = None) -> tuple:
    """Liga (on=True) ou desliga/muta (on=False) o alvo. (ok, detalhe).

    Ao LIGAR com `fader_db` (ex.: 0.0), primeiro coloca o fader nesse nível (com o canal
    ainda mudo, sem estalo) e só depois liga: ligar um canal com o fader no mínimo não
    adianta. Se só o ajuste do fader falhar, liga mesmo assim e avisa no detalhe (ATENÇÃO).
    """
    host = (host or "").strip()
    if not host:
        return False, "IP da mesa não configurado"
    port = port or DEFAULT_PORT
    try:
        address = target_address(kind, number)
        warn = ""
        fader_txt = ""
        if on and fader_db is not None:
            if set_float(host, port, fader_address(kind, number), db_to_fader(fader_db), timeout, retries):
                fader_txt = f", fader em {fader_db:g} dB"
            else:
                warn = f"; ATENÇÃO: não consegui colocar o fader em {fader_db:g} dB"
        if set_int(host, port, address, 1 if on else 0, timeout, retries):
            return True, "confirmado pela mesa" + fader_txt + warn
        return False, f"a mesa em {host}:{port} não respondeu (IP, rede ou OSC desligado?)"
    except ValueError as exc:
        return False, str(exc)
    except X32Error as exc:
        return False, str(exc)


def get_state(host: str, port: int, kind: str, number: int, timeout: float = 0.8,
              retries: int = 2) -> dict | None:
    """Estado atual do alvo: {"on": 0/1, "fader": float 0..1 ou None}; None se a mesa não respondeu."""
    host = (host or "").strip()
    if not host:
        return None
    try:
        on = query(host, port or DEFAULT_PORT, target_address(kind, number), timeout, retries)
        if not on or not isinstance(on[0], int):
            return None
        fd = query(host, port or DEFAULT_PORT, fader_address(kind, number), timeout, retries)
    except (ValueError, X32Error):
        return None
    fader = float(fd[0]) if fd and isinstance(fd[0], (int, float)) else None
    return {"on": int(on[0]), "fader": fader}


def test_toggle(host: str, port: int, kind: str, number: int, fader_db: float | None,
                hold: float = 1.5, report=None) -> tuple:
    """Teste de ligar/desligar PELO APP: guarda o estado, DESLIGA, espera `hold` s, LIGA
    (com o fader em `fader_db`, se dado), espera `hold` s e VOLTA ao estado original (ligado/
    desligado e posição do fader). Mesmo se algo falhar no meio, tenta restaurar.
    Devolve (ok, texto). `report(texto)` recebe o andamento."""
    say = report or (lambda _t: None)
    host = (host or "").strip()
    if not host:
        return False, "informe o IP da mesa em Configurações Globais"
    port = port or DEFAULT_PORT
    try:
        label = target_label(kind, number)
    except ValueError as exc:
        return False, str(exc)
    orig = get_state(host, port, kind, number)
    if orig is None:
        return False, f"a mesa em {host}:{port} não respondeu"
    steps = []
    ok = True
    try:
        say(f"desligando {label}…")
        good, why = set_channel(host, port, kind, number, False)
        if not good:
            return False, f"não consegui desligar {label}: {why}"
        steps.append("desligou")
        time.sleep(hold)
        say(f"ligando {label}" + (f" em {fader_db:g} dB…" if fader_db is not None else "…"))
        good, why = set_channel(host, port, kind, number, True, fader_db=fader_db)
        if not good:
            ok = False
            return False, f"desligou, mas não consegui ligar {label}: {why}"
        steps.append("ligou" + (f" com o fader em {fader_db:g} dB" if fader_db is not None else ""))
        if "ATENÇÃO" in why:
            ok = False
            steps[-1] += " (⚠ fader não confirmado)"
        time.sleep(hold)
    finally:
        # volta ao que estava (mesmo em falha): fader e ligado/desligado
        try:
            if fader_db is not None and orig.get("fader") is not None:
                set_float(host, port, fader_address(kind, number), orig["fader"])
            if not orig["on"]:
                set_int(host, port, target_address(kind, number), 0)
            elif steps and steps[0] == "desligou" and len(steps) == 1:
                set_int(host, port, target_address(kind, number), 1)   # falhou no meio: reabre
        except (ValueError, X32Error):
            pass
    estado = "ligado" if orig["on"] else "desligado"
    return ok, f"{label}: " + ", ".join(steps) + f" — voltou ao estado original ({estado})"


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


# ── medidores (nível de áudio) ───────────────────────────────────────────────────
#
# A mesa manda os níveis só para quem "assina": `/meters ,siii "/meters/N" <a> <b> <fator>`.
# A assinatura vale ~10 s (renovamos). A resposta é um blob: tamanho (big-endian), depois
# um int32 little-endian com a QUANTIDADE e os floats little-endian (nível linear, 1.0 = 0 dBFS).
#
# ATENÇÃO (ainda não conferido numa mesa real): usamos /meters/1 e assumimos que os 32
# primeiros valores são os níveis de entrada dos canais 1-32 (pré-fader). Se a mesa
# organizar diferente, só METER_SOURCES precisa mudar. `sample_meters` (botão "Testar
# medidor") mostra o que a mesa realmente manda, para conferir.

METER_ID = 1
METER_SOURCES = {"ch": 0}        # tipo -> posição do canal 1 dentro do blob
SILENCE_DB = -90.0


def meter_index(kind: str, number: int) -> int:
    """Posição do alvo no blob de medidores. Só canais de entrada (1-32) podem ser vigiados."""
    _check(kind, number)
    if kind not in METER_SOURCES:
        raise ValueError("só canais de entrada (1-32) podem ser vigiados")
    return METER_SOURCES[kind] + int(number) - 1


def parse_meter_blob(blob: bytes) -> list:
    """Floats (nível linear) de um blob de medidores; [] se vier malformado."""
    if len(blob) < 4:
        return []
    count = struct.unpack("<i", blob[:4])[0]
    avail = (len(blob) - 4) // 4
    n = avail if not 0 <= count <= avail else count
    return list(struct.unpack("<%df" % n, blob[4:4 + 4 * n]))


def to_db(level: float) -> float:
    """Nível linear (1.0 = 0 dBFS) -> dB; SILENCE_DB para silêncio/valores inválidos."""
    import math
    if not isinstance(level, (int, float)) or level != level or level <= 0:
        return SILENCE_DB
    return max(SILENCE_DB, 20.0 * math.log10(level))


class MeterStream:
    """Assina os medidores da mesa e entrega o nível (dB) de um canal.

    `level_db(timeout)` -> dB, ou None se nada chegou no prazo. Renova a assinatura sozinho.
    Nunca levanta exceção por rede ruim: devolve None.
    """

    RENEW_EVERY = 6.0

    def __init__(self, host: str, port: int, kind: str = "ch", number: int = 1):
        self.host = (host or "").strip()
        self.port = int(port or DEFAULT_PORT)
        self.index = meter_index(kind, number)
        self._sock = _open(self.host)
        self._renewed = 0.0
        self.last_count = 0

    def _subscribe(self):
        try:
            # fator de tempo 1 = atualização a cada ~50 ms
            self._sock.sendto(osc_message("/meters", "/meters/%d" % METER_ID, 0, 0, 1),
                              (self.host, self.port))
        except (OSError, UnicodeError):
            pass
        self._renewed = time.time()

    def level_db(self, timeout: float = 0.5):
        if time.time() - self._renewed >= self.RENEW_EVERY:
            self._subscribe()
        deadline = time.time() + timeout
        latest = None
        while True:
            left = deadline - time.time()
            if left <= 0:
                break
            self._sock.settimeout(left if latest is None else 0.001)
            try:
                data, _ = self._sock.recvfrom(8192)
            except (socket.timeout, OSError):
                break
            parsed = parse_osc(data)
            if not parsed or parsed[0] != "/meters/%d" % METER_ID or not parsed[1]:
                continue
            vals = parse_meter_blob(parsed[1][0]) if isinstance(parsed[1][0], bytes) else []
            self.last_count = len(vals)
            if self.index < len(vals):
                latest = to_db(vals[self.index])     # fica com o mais recente do que já chegou
        return latest

    def close(self):
        try:
            self._sock.close()
        except OSError:
            pass


def sample_meters(host: str, port: int, kind: str, number: int, seconds: float = 1.5):
    """Lê o medidor por `seconds` e devolve (pico_dB, quantidade_de_valores) ou None se a mesa
    não mandou nada. Só leitura: não altera a mesa."""
    host = (host or "").strip()
    if not host:
        return None
    try:
        ms = MeterStream(host, port or DEFAULT_PORT, kind, number)
    except (ValueError, X32Error):
        return None
    try:
        end, peak = time.time() + seconds, None
        while time.time() < end:
            db = ms.level_db(0.3)
            if db is not None:
                peak = db if peak is None else max(peak, db)
        return None if peak is None else (peak, ms.last_count)
    finally:
        ms.close()
