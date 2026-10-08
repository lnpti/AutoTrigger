"""
Medidor de nível de áudio: pico (0..1) do que ESTE processo (o VLC embutido)
está tocando numa saída do Windows. Usado pelo watchdog de stream (player.py)
para detectar stream MUDO -- o VLC continua em "Playing" mesmo quando o servidor
manda só silêncio, então o estado do VLC sozinho não pega esse caso.

Usa o medidor da sessão de áudio do próprio processo (IAudioMeterInformation),
não o da placa inteira: outro programa tocando na mesma saída não engana a medida.
Todas as chamadas COM devem ser feitas na MESMA thread (a do monitor de stream).
"""
import gc
import os
from ctypes import cast, POINTER

import comtypes
from comtypes import CLSCTX_ALL
from pycaw.pycaw import (
    AudioUtilities, IAudioSessionManager2, IAudioSessionControl2,
    IAudioMeterInformation,
)

_SESSION_ACTIVE = 1


class SessionPeakMeter:
    def __init__(self, get_device_id):
        """get_device_id() -> ID da saída a medir ("" = saída padrão do Windows)."""
        self._get_device_id = get_device_id
        self._meter = None
        self.errors = 0

    def peak(self):
        """Pico recente (0.0..1.0), ou None se não há como medir agora (o VLC
        ainda não abriu a saída, ou erro de COM)."""
        try:
            if self._meter is None:
                self._meter = self._find_meter(self._get_device_id())
                if self._meter is None:
                    return None
            return float(self._meter.GetPeakValue())
        except Exception:
            self._meter = None
            self.errors += 1
            return None

    def reset(self):
        """Descarta a sessão atual (chamar depois de recriar o player: a sessão
        antiga morre e o medidor dela passaria a ler 0 para sempre)."""
        self._meter = None
        gc.collect()

    def close(self):
        self.reset()

    @staticmethod
    def _find_meter(device_id: str):
        import applog
        try:
            comtypes.CoInitialize()
        except OSError:
            pass
        applog.trace("medidor: procurando sessão de áudio do processo ...")
        enumerator = AudioUtilities.GetDeviceEnumerator()
        if device_id:
            device = enumerator.GetDevice(device_id)
        else:
            device = enumerator.GetDefaultAudioEndpoint(0, 1)  # eRender, eMultimedia
        manager = cast(
            device.Activate(IAudioSessionManager2._iid_, CLSCTX_ALL, None),
            POINTER(IAudioSessionManager2))
        sessions = manager.GetSessionEnumerator()
        pid = os.getpid()
        for i in range(sessions.GetCount()):
            ctl = sessions.GetSession(i)
            ctl2 = ctl.QueryInterface(IAudioSessionControl2)
            if ctl2.GetProcessId() == pid and ctl2.GetState() == _SESSION_ACTIVE:
                applog.trace("medidor: sessão encontrada")
                return ctl.QueryInterface(IAudioMeterInformation)
        return None
