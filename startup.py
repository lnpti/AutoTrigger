"""
"Iniciar com o Windows": liga/desliga a entrada em
HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run (por usuário, sem admin).

O valor "AutoTriggerV10" é o MESMO que o instalador cria quando o usuário marca
"Iniciar automaticamente com o Windows" -- então as duas coisas se enxergam.
Rodando do código-fonte (dev) usa outro nome ("AutoTriggerV10-dev") para nunca
sobrescrever a entrada do app instalado com um comando de desenvolvimento.
"""
import os
import sys

try:
    import winreg
except ImportError:  # não-Windows
    winreg = None

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _value_name() -> str:
    return "AutoTriggerV10" if getattr(sys, "frozen", False) else "AutoTriggerV10-dev"


def app_command() -> str:
    """Linha de comando que o Windows executa no login."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    interp = pyw if os.path.exists(pyw) else sys.executable
    main_py = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")
    return f'"{interp}" "{main_py}"'


def is_supported() -> bool:
    return winreg is not None


def is_enabled(value_name: str | None = None) -> bool:
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
            winreg.QueryValueEx(k, value_name or _value_name())
        return True
    except OSError:
        return False


def set_enabled(enabled: bool, value_name: str | None = None,
                command: str | None = None) -> bool:
    """Liga (grava/atualiza o comando) ou desliga (remove). True se deu certo."""
    if winreg is None:
        return False
    name = value_name or _value_name()
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0,
                                winreg.KEY_SET_VALUE) as k:
            if enabled:
                winreg.SetValueEx(k, name, 0, winreg.REG_SZ, command or app_command())
            else:
                try:
                    winreg.DeleteValue(k, name)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False
