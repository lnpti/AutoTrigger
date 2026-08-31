"""
Envio e captura de hotkeys globais do sistema.

- send_hotkey: envia para a janela em foco (comportamento padrão).
- send_hotkey_to_window: foca uma janela alvo por título, envia a hotkey e
  devolve o foco à janela anterior. Resolve o caso em que o software de rádio
  precisa estar em primeiro plano para receber a tecla.
- list_window_titles: lista janelas visíveis (para escolher a janela alvo na UI).
"""
import ctypes
import time

import applog

SPI_GETSCREENSAVERRUNNING = 0x0072


def _is_screensaver_running() -> bool:
    """True se o protetor de tela do Windows estiver ativo no momento."""
    try:
        running = ctypes.c_int(0)
        ctypes.windll.user32.SystemParametersInfoW(
            SPI_GETSCREENSAVERRUNNING, 0, ctypes.byref(running), 0
        )
        return bool(running.value)
    except Exception:
        return False


def _dismiss_screensaver():
    """
    Encerra o protetor de tela simulando um pequeno movimento do mouse, para que
    a janela alvo consiga voltar ao primeiro plano e receber a hotkey.

    Não desbloqueia a estação de trabalho: se a opção "exibir tela de login ao
    retomar" estiver marcada, o Windows tranca a sessão (área de trabalho segura)
    e nenhuma automação de mouse/teclado alcança as janelas normais — isso exige
    a senha do usuário e é esperado que falhe aqui.
    """
    if not _is_screensaver_running():
        return
    applog.log("Protetor de tela ativo — encerrando antes da hotkey.", "warn")
    try:
        import win32api
        x, y = win32api.GetCursorPos()
        win32api.SetCursorPos((x + 1, y))
        time.sleep(0.05)
        win32api.SetCursorPos((x, y))
    except Exception as exc:
        applog.log(f"Falha ao simular atividade do mouse: {exc}", "warn")
        return
    for _ in range(20):  # até ~2s para o protetor fechar
        if not _is_screensaver_running():
            return
        time.sleep(0.1)
    if _is_screensaver_running():
        applog.log("Protetor de tela continua ativo (provável tela de login/"
                    "bloqueio) — a hotkey pode não chegar à janela alvo.", "warn")


def send_hotkey(hotkey_str: str) -> bool:
    """
    Envia uma hotkey global para o sistema operacional (janela em foco).
    Exemplos: 'ctrl+f1', 'alt+f4', 'ctrl+shift+s'
    Retorna True se bem-sucedido.
    """
    if not hotkey_str:
        return False
    try:
        _dismiss_screensaver()
        import keyboard
        time.sleep(0.15)  # Pequena pausa para garantir contexto de janela
        keyboard.send(hotkey_str)
        return True
    except Exception as exc:
        applog.log(f"Erro ao enviar hotkey '{hotkey_str}': {exc}", "error")
        return False


def send_hotkey_to_window(hotkey_str: str, window_title: str) -> bool:
    """
    Foca a janela cujo título contém `window_title` (case-insensitive),
    envia a hotkey e restaura o foco da janela anterior.

    Se a janela não for encontrada (ou o pywin32 não estiver disponível),
    cai no envio simples via send_hotkey().
    """
    if not hotkey_str:
        return False
    if not window_title:
        return send_hotkey(hotkey_str)

    try:
        import win32gui
        import win32con
    except Exception:
        applog.log("pywin32 indisponível — enviando para janela ativa.", "warn")
        return send_hotkey(hotkey_str)

    _dismiss_screensaver()

    hwnd = _find_window(window_title)
    if not hwnd:
        applog.log(f"Janela '{window_title}' não encontrada — enviando para "
                    f"janela ativa.", "warn")
        return send_hotkey(hotkey_str)

    prev = win32gui.GetForegroundWindow()
    try:
        focused = _focus_window(hwnd)
        if not focused:
            applog.log(
                f"Não foi possível confirmar o foco na janela '{window_title}' "
                f"(o Windows pode ter bloqueado a troca de foco) — a hotkey "
                f"pode não chegar lá.", "warn"
            )
        time.sleep(0.12)
        import keyboard
        keyboard.send(hotkey_str)
        time.sleep(0.08)
        return True
    except Exception as exc:
        applog.log(f"Erro ao enviar para '{window_title}': {exc}", "error")
        return False
    finally:
        # Devolve o foco à janela anterior
        try:
            if prev and prev != hwnd:
                _focus_window(prev)
        except Exception:
            pass


def list_window_titles() -> list:
    """Retorna títulos de janelas visíveis com título (ordenados, sem duplicar)."""
    try:
        import win32gui
    except Exception:
        return []

    titles = []

    def _cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        t = win32gui.GetWindowText(hwnd)
        if t and t not in titles:
            titles.append(t)

    try:
        win32gui.EnumWindows(_cb, None)
    except Exception:
        return []
    return sorted(titles, key=str.lower)


# ── internals ──────────────────────────────────────────────────────────────────

def _find_window(title_substr: str):
    """HWND da 1ª janela visível cujo título contém `title_substr`."""
    import win32gui
    needle = title_substr.lower()
    match = []

    def _cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        t = win32gui.GetWindowText(hwnd)
        if t and needle in t.lower():
            match.append(hwnd)

    win32gui.EnumWindows(_cb, None)
    return match[0] if match else None


def _focus_window(hwnd) -> bool:
    """
    Restaura (se minimizada) e traz a janela ao primeiro plano. Retorna True
    se o foco foi realmente confirmado.

    O Windows bloqueia processos em segundo plano de "roubar" o foco de outro
    app (proteção antifoco-stealing) -- nesse caso `SetForegroundWindow` só
    pisca o ícone na barra de tarefas e retorna sucesso sem lançar exceção,
    então o app achava que tinha focado quando na verdade não tinha (a hotkey
    ia pra janela errada, silenciosamente). Isso fica mais provável logo após
    dispensar o protetor de tela, já que o "último input real" não veio do
    usuário. `AttachThreadInput` contorna essa proteção de forma confiável:
    ao anexar a thread deste processo à thread da janela em foco atual (e à
    da janela alvo), o Windows trata os dois como "o mesmo input source" e
    permite a troca de foco de verdade.
    """
    import win32gui
    import win32con
    import win32process
    import win32api

    try:
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    except Exception:
        pass

    cur_thread = win32api.GetCurrentThreadId()
    fg_hwnd = win32gui.GetForegroundWindow()
    fg_thread = win32process.GetWindowThreadProcessId(fg_hwnd)[0] if fg_hwnd else 0
    target_thread = win32process.GetWindowThreadProcessId(hwnd)[0]

    attached = []
    for tid in (fg_thread, target_thread):
        if tid and tid != cur_thread:
            try:
                win32process.AttachThreadInput(cur_thread, tid, True)
                attached.append(tid)
            except Exception:
                pass
    try:
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass
        try:
            win32gui.BringWindowToTop(hwnd)
        except Exception:
            pass
    finally:
        for tid in attached:
            try:
                win32process.AttachThreadInput(cur_thread, tid, False)
            except Exception:
                pass

    return win32gui.GetForegroundWindow() == hwnd


def capture_hotkey() -> str:
    """
    Aguarda e captura a próxima combinação de teclas pressionada.
    Retorna a string da hotkey (ex: 'ctrl+f1') ou string vazia em caso de erro.
    """
    try:
        import keyboard
        hk = keyboard.read_hotkey(suppress=False)
        return hk
    except Exception as exc:
        print(f"[HotkeySender] Erro ao capturar hotkey: {exc}")
        return ""
