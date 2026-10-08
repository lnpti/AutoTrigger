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

_log = lambda msg, level="info": print(f"[AudioManager][{level}] {msg}")


def set_log(fn):
    """Define o callback de log (msg, level). Ver applog.log — thread-safe."""
    global _log
    _log = fn


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
        _log(f"Erro ao enumerar dispositivos ({data_flow}): {exc}", "error")
    return result


def get_device_name(device_id: str) -> str:
    """Nome amigável do dispositivo pelo ID, ou o próprio ID se não resolver."""
    if not device_id:
        return device_id
    _ensure_com()
    try:
        enumerator = AudioUtilities.GetDeviceEnumerator()
        imm_device = enumerator.GetDevice(device_id)
        dev = AudioUtilities.CreateDevice(imm_device)
        if dev and dev.FriendlyName:
            return dev.FriendlyName
    except Exception:
        pass
    return device_id


def list_input_devices() -> list:
    """Retorna lista de dispositivos de entrada (microfone, line-in) ativos."""
    return _enumerate_devices(EDataFlow.eCapture)


def list_output_devices() -> list:
    """Retorna lista de dispositivos de saída ativos."""
    return _enumerate_devices(EDataFlow.eRender)


def find_device_by_name(name: str, kind: str | None = None) -> dict | None:
    """Dispositivo ATIVO com esse nome amigável, ou None.

    O ID do Windows muda quando o driver é reinstalado, a placa USB troca de
    porta ou a configuração vem de outro PC; o nome continua o mesmo.
    kind: "capture" (entradas), "render" (saídas) ou None (procura nas duas).
    """
    if not name or not name.strip():
        return None
    flows = {"capture": [EDataFlow.eCapture], "render": [EDataFlow.eRender]}.get(
        kind, [EDataFlow.eCapture, EDataFlow.eRender])
    candidates = [d for fl in flows for d in _enumerate_devices(fl)]
    for d in candidates:
        if d["name"] == name:
            return d
    wanted = name.strip().casefold()
    for d in candidates:
        if d["name"].strip().casefold() == wanted:
            return d
    return None


def kind_from_id(device_id: str) -> str | None:
    """"capture"/"render" pelo prefixo do ID do Windows ({0.0.1.…} = entrada,
    {0.0.0.…} = saída); None se não reconhecer."""
    if device_id.startswith("{0.0.1."):
        return "capture"
    if device_id.startswith("{0.0.0."):
        return "render"
    return None


def _endpoint_volume(device_id: str):
    enumerator = AudioUtilities.GetDeviceEnumerator()
    imm_device = enumerator.GetDevice(device_id)
    interface = imm_device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(interface, POINTER(IAudioEndpointVolume))


def set_device_mute(device_id: str, mute: bool, device_name: str = "") -> bool:
    """
    Muta ou desmuta um dispositivo. O NOME é a referência principal (o ID do
    Windows muda com driver/porta USB/outro PC): se `device_name` for dado e
    houver um dispositivo ativo com ele, usa o ID atual desse dispositivo; senão
    usa o `device_id` salvo.
    Retorna True se bem-sucedido.
    """
    if not device_id:
        return False
    import applog
    acao = "mutar" if mute else "desmutar"
    applog.trace(f"{acao}: CoInitialize ...")
    _ensure_com()
    try:
        applog.trace(f"{acao}: obtendo dispositivo ...")
        alt = find_device_by_name(device_name, kind_from_id(device_id)) if device_name else None
        if alt and alt["id"] != device_id:
            _log(f"O ID de '{device_name}' mudou neste PC; usando o ID atual "
                 f"(encontrado pelo nome).", "warn")
            device_id = alt["id"]
        volume = _endpoint_volume(device_id)
        applog.trace(f"{acao}: SetMute ...")
        volume.SetMute(1 if mute else 0, None)
        applog.trace(f"{acao}: concluído")
        with _ledger_lock:
            if mute:
                _muted_by_app.add(device_id)
            else:
                _muted_by_app.discard(device_id)
        return True
    except Exception as exc:
        hint = (f" — '{device_name}' não está ativo neste PC (placa conectada? "
                f"driver instalado?)" if device_name else "")
        _log(f"Erro ao {acao} dispositivo '{device_id}': {exc}{hint}", "error")
        return False


def restore_app_mutes() -> list:
    """
    Desmuta APENAS os dispositivos que este app mutou e ainda não desmutou.
    Chamado ao fechar o app. Retorna uma lista de {"id", "name"} dos
    dispositivos restaurados (vazia se nenhum). Dispositivos cujo mute não
    foi dado pelo app permanecem intocados.
    """
    with _ledger_lock:
        pending = list(_muted_by_app)
    restored = []
    for device_id in pending:
        if set_device_mute(device_id, False):
            restored.append({"id": device_id, "name": get_device_name(device_id)})
    if restored:
        names = ", ".join(d["name"] for d in restored)
        _log(f"{len(restored)} dispositivo(s) desmutado(s) ao sair "
             f"(estavam mutados pelo app): {names}", "warn")
    return restored


def mute_device(device_id: str) -> bool:
    return set_device_mute(device_id, True)


def unmute_device(device_id: str) -> bool:
    return set_device_mute(device_id, False)
