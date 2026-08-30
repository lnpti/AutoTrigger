"""
Gerencia dispositivos de áudio do Windows via pycaw / Windows Core Audio API.
- Lista entradas (capture) e saídas (render)
- Muta / desmuta dispositivos de entrada por device_id
"""
import threading

import comtypes
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from pycaw.constants import EDataFlow
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL

_DEVICE_STATE_ACTIVE = 1

# Ledger dos dispositivos que ESTE app mutou e ainda não desmutou.
# Garante que, ao fechar, só desmutamos o que nós mesmos mutamos —
# nunca alteramos um dispositivo cujo mute não foi dado pelo app.
_muted_by_app: set = set()
_ledger_lock = threading.Lock()


def _ensure_com():
    """Garante que COM está inicializado na thread atual."""
    try:
        comtypes.CoInitialize()
    except OSError:
        pass


def _enumerate_devices(data_flow: EDataFlow) -> list:
    """
    Enumera dispositivos de áudio ativos para o fluxo indicado.
    Retorna lista de {'id': str, 'name': str}.
    """
    _ensure_com()
    result = []
    try:
        enumerator = AudioUtilities.GetDeviceEnumerator()
        collection = enumerator.EnumAudioEndpoints(data_flow.value, _DEVICE_STATE_ACTIVE)
        count = collection.GetCount()
        for i in range(count):
            imm_device = collection.Item(i)
            dev = AudioUtilities.CreateDevice(imm_device)
            if dev and dev.FriendlyName:
                result.append({"id": dev.id, "name": dev.FriendlyName})
    except Exception as exc:
        print(f"[AudioManager] Erro ao enumerar dispositivos ({data_flow}): {exc}")
    return result


def list_input_devices() -> list:
    """Retorna lista de dispositivos de entrada (microfone, line-in) ativos."""
    return _enumerate_devices(EDataFlow.eCapture)


def list_output_devices() -> list:
    """Retorna lista de dispositivos de saída ativos."""
    return _enumerate_devices(EDataFlow.eRender)


def set_device_mute(device_id: str, mute: bool) -> bool:
    """
    Muta ou desmuta um dispositivo pelo seu Windows MMDevice ID.
    Retorna True se bem-sucedido.
    """
    if not device_id:
        return False
    _ensure_com()
    try:
        enumerator = AudioUtilities.GetDeviceEnumerator()
        imm_device = enumerator.GetDevice(device_id)
        interface = imm_device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        volume.SetMute(1 if mute else 0, None)
        with _ledger_lock:
            if mute:
                _muted_by_app.add(device_id)
            else:
                _muted_by_app.discard(device_id)
        return True
    except Exception as exc:
        action = "mutar" if mute else "desmutar"
        print(f"[AudioManager] Erro ao {action} dispositivo '{device_id}': {exc}")
        return False


def restore_app_mutes() -> int:
    """
    Desmuta APENAS os dispositivos que este app mutou e ainda não desmutou.
    Chamado ao fechar o app. Retorna quantos dispositivos foram restaurados.
    Dispositivos cujo mute não foi dado pelo app permanecem intocados.
    """
    with _ledger_lock:
        pending = list(_muted_by_app)
    count = 0
    for device_id in pending:
        if set_device_mute(device_id, False):
            count += 1
    if count:
        print(f"[AudioManager] {count} dispositivo(s) desmutado(s) ao sair.")
    return count


def mute_device(device_id: str) -> bool:
    return set_device_mute(device_id, True)


def unmute_device(device_id: str) -> bool:
    return set_device_mute(device_id, False)
