"""
AutoTrigger V10 — Entry point (PySide6/Qt).
Inicializa logging, backend, ponte de threads, janela e bandeja.
"""
import sys
import os

# Compatibilidade com PyInstaller (recursos bundled)
if getattr(sys, "frozen", False):
    BASE_DIR = sys._MEIPASS  # type: ignore[attr-defined]
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _setup_bundled_vlc():
    """Aponta o python-vlc para o libVLC embutido no .exe (antes de importar vlc)."""
    if not getattr(sys, "frozen", False):
        return
    libvlc = os.path.join(BASE_DIR, "libvlc.dll")
    plugins = os.path.join(BASE_DIR, "plugins")
    if os.path.exists(libvlc):
        os.environ["PYTHON_VLC_LIB_PATH"] = libvlc
        os.environ["PATH"] = BASE_DIR + os.pathsep + os.environ.get("PATH", "")
        try:
            os.add_dll_directory(BASE_DIR)
        except Exception:
            pass
    if os.path.isdir(plugins):
        os.environ["PYTHON_VLC_MODULE_PATH"] = plugins
        os.environ["VLC_PLUGIN_PATH"] = plugins


_setup_bundled_vlc()

# COM antes de qualquer import de pycaw
import comtypes
try:
    comtypes.CoInitialize()
except OSError:
    pass

import applog
applog.init()

import ctypes

_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001
_ES_DISPLAY_REQUIRED = 0x00000002


def _suppress_screensaver_and_sleep():
    """
    Impede o protetor de tela e a suspensão do Windows enquanto o app estiver
    aberto (SetThreadExecutionState). Isso é mais confiável do que tentar
    fechar o protetor DEPOIS que ele já ativou: em algumas máquinas (política
    de inatividade/domínio) o protetor troca para uma área de trabalho segura
    assim que ativa, e nenhuma automação de mouse/teclado consegue atravessar
    isso sem a senha real do usuário -- melhor nunca deixar ativar.
    """
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(
            _ES_CONTINUOUS | _ES_SYSTEM_REQUIRED | _ES_DISPLAY_REQUIRED
        )
    except Exception as exc:
        applog.log(f"Não foi possível suprimir o protetor de tela: {exc}", "warn")


def _restore_screensaver_and_sleep():
    """Devolve o comportamento normal de energia/protetor de tela ao fechar."""
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(_ES_CONTINUOUS)
    except Exception:
        pass

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon, QAction, QGuiApplication
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PySide6.QtNetwork import QLocalServer, QLocalSocket

# Nome do canal local usado para detectar instância já em execução (ver
# _activate_running_instance / _SingleInstanceServer abaixo).
_SINGLE_INSTANCE_KEY = "AutoTriggerV10_SingleInstance"

# Em telas com escala fracionária (125%, 150%, 175%), a política padrão do Qt
# arredonda o fator de escala (ex.: 125% -> 100%) para o layout dos widgets,
# mas o texto é desenhado na escala real do Windows -> campos/labels desalinhados.
# PassThrough usa o fator real (1.25x) tanto no layout quanto no texto.
QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
    Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
)

from config import Config
import audio_manager as _audio
from player import AudioPlayer
from file_monitor import FileMonitor
from sequence_engine import SequenceEngine
from ui.theme import apply_theme
from ui.qt_bridge import EngineBridge
from ui.main_window import MainWindow, _asset_icon


def _activate_running_instance() -> bool:
    """
    Tenta avisar uma instância já em execução para se mostrar (via socket
    local nomeado). Retorna True se conseguiu -- nesse caso, ESTE processo
    (a instância nova) deve encerrar sem abrir mais nada.
    """
    socket = QLocalSocket()
    socket.connectToServer(_SINGLE_INSTANCE_KEY)
    if socket.waitForConnected(200):
        socket.write(b"show")
        socket.flush()
        socket.waitForBytesWritten(200)
        socket.disconnectFromServer()
        return True
    return False


def _start_single_instance_server(on_show) -> QLocalServer:
    """
    Escuta no canal local: quando uma nova instância tentar abrir (e desistir
    via _activate_running_instance), chama `on_show()` nesta instância.
    Precisa manter a referência retornada viva até o app fechar.
    """
    # Remove um socket "órfão" deixado por uma execução anterior que crashou
    # sem fechar limpo (senão o listen() abaixo falharia achando que já tem
    # uma instância rodando).
    QLocalServer.removeServer(_SINGLE_INSTANCE_KEY)
    server = QLocalServer()
    server.listen(_SINGLE_INSTANCE_KEY)

    def _on_new_connection():
        conn = server.nextPendingConnection()
        if conn is None:
            return
        conn.waitForReadyRead(200)
        conn.readAll()
        conn.disconnectFromServer()
        on_show()

    server.newConnection.connect(_on_new_connection)
    return server


def _build_tray(app, window, on_quit) -> QSystemTrayIcon:
    icon = _asset_icon() or window.windowIcon()
    tray = QSystemTrayIcon(icon, parent=app)
    tray.setToolTip("AutoTrigger V10")
    menu = QMenu()
    act_open = QAction("Abrir", menu)
    act_open.triggered.connect(lambda: (window.showNormal(), window.raise_(),
                                        window.activateWindow()))
    act_quit = QAction("Sair", menu)
    act_quit.triggered.connect(on_quit)
    menu.addAction(act_open)
    menu.addSeparator()
    menu.addAction(act_quit)
    tray.setContextMenu(menu)

    def _activated(reason):
        if reason == QSystemTrayIcon.Trigger:  # clique simples
            window.showNormal(); window.raise_(); window.activateWindow()

    tray.activated.connect(_activated)
    tray.show()
    return tray


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # fecha p/ bandeja

    if _activate_running_instance():
        # Já tem uma instância rodando (ícone na bandeja) -- ela acabou de
        # ser avisada pra se mostrar. Não abre uma segunda janela/instância.
        return

    _suppress_screensaver_and_sleep()

    apply_theme(app)
    ico = _asset_icon()
    if ico:
        app.setWindowIcon(ico)

    config = Config()
    player = AudioPlayer()
    file_monitor = FileMonitor()
    engine = SequenceEngine(config, player, file_monitor)

    # Ponte de threads: callbacks do backend → signals na GUI thread
    bridge = EngineBridge()
    applog.set_ui_sink(bridge.on_log)
    engine.set_log(applog.log)
    try:
        player.set_log(applog.log)
    except Exception:
        pass
    _audio.set_log(applog.log)
    engine.set_on_runner_update(bridge.on_runner_update)
    engine.set_on_tick(bridge.on_tick)

    window = MainWindow(config=config, engine=engine, player=player)
    bridge.runner_update.connect(window.on_runner_update)
    bridge.tick.connect(window.on_tick)
    bridge.log_message.connect(window.on_log)

    # Verificação VLC
    if not player.is_vlc_available():
        window.on_log("AVISO: VLC não disponível. Reprodução/stream desabilitados.", "error")

    def _quit():
        try:
            single_instance_server.close()
        except Exception:
            pass
        _restore_screensaver_and_sleep()
        restored = []
        try:
            file_monitor.stop()
            engine.cancel_all()
            engine.stop_monitor()
            restored = _audio.restore_app_mutes()
            player.release()
        except Exception:
            pass

        if restored:
            # audio_manager.restore_app_mutes() já registrou isso no log
            # (applog.log, via _audio.set_log) -- aqui só falta o aviso
            # visual não-bloqueante na bandeja.
            try:
                names = ", ".join(d["name"] for d in restored)
                tray.showMessage(
                    "AutoTrigger V10",
                    f"{len(restored)} dispositivo(s) de áudio foram desmutados "
                    f"ao fechar o app: {names}",
                    QSystemTrayIcon.Warning,
                    6000,
                )
            except Exception:
                pass
            # Dá um tempinho pro aviso da bandeja aparecer antes do processo
            # encerrar de vez (senão o Windows pode nem chegar a mostrar).
            QTimer.singleShot(2500, lambda: (tray.hide(), app.quit()))
            return

        tray.hide()
        app.quit()

    window._quit_fn = _quit
    tray = _build_tray(app, window, _quit)
    single_instance_server = _start_single_instance_server(
        lambda: (window.showNormal(), window.raise_(), window.activateWindow())
    )

    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
