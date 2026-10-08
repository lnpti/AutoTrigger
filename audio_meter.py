"""
Medidor de nível de áudio: pico (0..1) do que ESTE processo (o VLC embutido)
está tocando numa saída do Windows. Usado pelo watchdog de stream (player.py)
para detectar stream MUDO -- o VLC continua em "Playing" mesmo quando o servidor
manda só silêncio, então o estado do VLC sozinho não pega esse caso.

Usa o medidor da sessão de áudio do próprio processo (IAudioMeterInformation),
não o da placa inteira: outro programa tocando na mesma saída não engana a medida.
A sessão é procurada primeiro na saída esperada e, se não estiver lá, nas demais
saídas ativas -- assim também dá para saber EM QUAL placa o áudio está saindo
(`location`). Todas as chamadas COM devem ser feitas na MESMA thread (a do
monitor de stream).
"""
import gc
import os
import time
from ctypes import cast, POINTER

import comtypes
from comtypes import CLSCTX_ALL
from pycaw.pycaw import (
    AudioUtilities, IAudioSessionManager2, IAudioSessionControl2,
    IAudioMeterInformation,
)

_SESSION_ACTIVE = 1
_RETRY_EVERY = 2.0   # s entre buscas quando a sessão ainda não existe


class SessionPeakMeter:
    def __init__(self, get_device_id):
        """get_device_id() -> ID da saída esperada ("" = saída padrão do Windows)."""
        self._get_device_id = get_device_id
        self._meter = None
        self._next_try = 0.0
        self.errors = 0
        self.location = None      # (id, nome) da saída onde a sessão foi achada
        self.last_problem = ""    # por que não mediu (para o log)

    def peak(self):
        """Pico recente (0.0..1.0), ou None se não há como medir agora (o VLC
        ainda não abriu a saída, ou erro de COM -- ver `last_problem`)."""
        try:
            if self._meter is None:
                if time.monotonic() < self._next_try:
                    return None
                self._meter = self._find_meter()
                if self._meter is None:
                    self._next_try = time.monotonic() + _RETRY_EVERY
                    return None
            return float(self._meter.GetPeakValue())
        except Exception as exc:
            self._meter = None
            self.errors += 1
            self.last_problem = f"{type(exc).__name__}: {exc}"
            self._next_try = time.monotonic() + _RETRY_EVERY
            return None

    def reset(self):
        """Descarta a sessão atual (chamar depois de recriar o player: a sessão
        antiga morre e o medidor dela passaria a ler 0 para sempre)."""
        self._meter = None
        self.location = None
        self._next_try = 0.0
        gc.collect()

    def close(self):
        self.reset()

    def _find_meter(self):
        import applog
        try:
            comtypes.CoInitialize()
        except OSError:
            pass
        applog.trace("medidor: procurando sessão de áudio do processo ...")
        enumerator = AudioUtilities.GetDeviceEnumerator()
        expected_id = self._get_device_id()

        devices = []   # (id, nome, IMMDevice); a esperada primeiro
        if expected_id:
            try:
                devices.append((expected_id, "", enumerator.GetDevice(expected_id)))
            except Exception as exc:
                self.last_problem = f"saída esperada inacessível ({exc})"
        else:
            try:
                imm = enumerator.GetDefaultAudioEndpoint(0, 1)  # eRender, eMultimedia
                devices.append((AudioUtilities.CreateDevice(imm).id, "", imm))
            except Exception as exc:
                self.last_problem = f"saída padrão inacessível ({exc})"
        try:
            coll = enumerator.EnumAudioEndpoints(0, 1)  # eRender, ativas
            for i in range(coll.GetCount()):
                imm = coll.Item(i)
                dev = AudioUtilities.CreateDevice(imm)
                if dev and all(dev.id != d[0] for d in devices):
                    devices.append((dev.id, dev.FriendlyName or "", imm))
        except Exception as exc:
            self.last_problem = f"não consegui listar as saídas ({exc})"

        pid = os.getpid()
        seen = []
        for dev_id, name, imm in devices:
            meter, sessions = self._scan(imm, pid)
            if not name:
                try:
                    name = AudioUtilities.CreateDevice(imm).FriendlyName or dev_id
                except Exception:
                    name = dev_id
            if meter is not None:
                self.location = (dev_id, name)
                self.last_problem = ""
                applog.trace(f"medidor: sessão encontrada em '{name}'")
                return meter
            seen.append(f"{name}: {sessions or 'sem sessões'}")
        self.last_problem = (f"nenhuma sessão ativa do processo {pid} em nenhuma saída "
                             f"({'; '.join(seen) or 'sem saídas'})")[:400]
        return None

    @staticmethod
    def _scan(imm_device, pid):
        """(medidor | None, resumo das sessões). Uma sessão problemática (de outro
        programa) não pode abortar a busca pela nossa."""
        manager = cast(
            imm_device.Activate(IAudioSessionManager2._iid_, CLSCTX_ALL, None),
            POINTER(IAudioSessionManager2))
        sessions = manager.GetSessionEnumerator()
        summary = []
        for i in range(sessions.GetCount()):
            try:
                ctl = sessions.GetSession(i)
                ctl2 = ctl.QueryInterface(IAudioSessionControl2)
                spid, state = ctl2.GetProcessId(), ctl2.GetState()
                summary.append(f"pid {spid} {'ativa' if state == _SESSION_ACTIVE else 'inativa'}")
                if spid == pid and state == _SESSION_ACTIVE:
                    return ctl.QueryInterface(IAudioMeterInformation), summary
            except Exception as exc:
                summary.append(f"sessão {i} ilegível ({type(exc).__name__})")
        return None, summary
