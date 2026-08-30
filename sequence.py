"""
Máquina de estados que orquestra o fluxo da Jornada Esportiva.

FLUXO COMPLETO:
  IDLE
    └─ keyword_start →
        MUTING      → muta input + envia hotkey_stop
        AUDIO1      → toca Vinheta 1 (aguarda terminar)
        STREAMING   → executa stream por stream_duration segundos
        AUDIO2      → toca Vinheta 2 (aguarda terminar)
        PLAY_CMD    → envia hotkey_play
        WAITING_NEXT → aguarda próxima keyword no TXT

    └─ keyword_unmute (em WAITING_NEXT) →
        STOP_RETURN → envia hotkey_stop + desmuta input
        IDLE
"""
import threading
import time
from enum import Enum


class State(Enum):
    IDLE         = "idle"
    MUTING       = "muting"
    AUDIO1       = "audio1"
    STREAMING    = "streaming"
    AUDIO2       = "audio2"
    PLAY_CMD     = "play_cmd"
    WAITING_NEXT = "waiting_next"
    STOP_RETURN  = "stop_return"


class Sequence:
    def __init__(self, config, audio_manager, player, hotkey_sender, log_callback=None):
        self._config = config
        self._audio_mgr = audio_manager
        self._player = player
        self._hotkey = hotkey_sender
        self._log = log_callback or (lambda msg, level="info": print(f"[Seq][{level}] {msg}"))

        self._state = State.IDLE
        self._state_lock = threading.Lock()
        self._cancel_event = threading.Event()
        self._step_done = threading.Event()
        self._on_state_change = None

    # ── public API ──────────────────────────────────────────────────────────

    def set_on_state_change(self, callback):
        self._on_state_change = callback

    @property
    def state(self) -> State:
        return self._state

    def trigger_start(self):
        """Chamado pelo FileMonitor ao detectar keyword_start."""
        with self._state_lock:
            if self._state != State.IDLE:
                self._log("Trigger de início ignorado — já em execução.", "warn")
                return

        self._cancel_event.clear()
        threading.Thread(
            target=self._run_sequence,
            daemon=True,
            name="sport-sequence",
        ).start()

    def trigger_unmute(self):
        """Chamado pelo FileMonitor ao detectar keyword_unmute."""
        with self._state_lock:
            current = self._state

        if current == State.WAITING_NEXT:
            threading.Thread(
                target=self._run_return,
                daemon=True,
                name="sport-return",
            ).start()
        else:
            self._log(f"Keyword de retorno recebida fora de hora (estado: {current.value}).", "warn")

    def cancel(self):
        """Cancela a sequência em andamento e retorna ao IDLE imediatamente."""
        self._cancel_event.set()
        self._player.stop()
        input_id = self._config.get("input_device_id", "")
        if input_id:
            self._audio_mgr.unmute_device(input_id)
        self._set_state(State.IDLE)
        self._log("Sequência cancelada.", "warn")

    # ── internal ────────────────────────────────────────────────────────────

    def _set_state(self, new_state: State):
        self._state = new_state
        self._log(f"[{new_state.value.upper()}]", "info")
        if self._on_state_change:
            self._on_state_change(new_state)

    def _wait_step(self, timeout: int = 300) -> bool:
        """
        Aguarda _step_done ou cancel_event dentro do timeout (segundos).
        Retorna True se o passo completou normalmente.
        """
        deadline = time.monotonic() + timeout
        while not self._step_done.is_set():
            if self._cancel_event.is_set():
                return False
            if time.monotonic() > deadline:
                self._log("Timeout aguardando passo — continuando.", "warn")
                return False
            time.sleep(0.1)
        return True

    def _play_and_wait(self, source: str, label: str,
                       duration: int = 0, timeout: int = 300) -> bool:
        """
        Inicia reprodução e aguarda terminar.
        Retorna False se cancelado ou erro fatal; True se OK.
        """
        if not source:
            self._log(f"{label} não configurado — pulando.", "warn")
            return not self._cancel_event.is_set()

        self._step_done.clear()
        self._player.set_on_finished(lambda: self._step_done.set())
        ok = self._player.play(source, duration_seconds=duration)
        if not ok:
            self._log(f"{label}: falha ao iniciar reprodução.", "error")
            return not self._cancel_event.is_set()

        self._wait_step(timeout=timeout)
        self._player.stop()
        return not self._cancel_event.is_set()

    def _run_sequence(self):
        """Executa o fluxo completo da Jornada Esportiva em thread de background."""
        import comtypes
        try:
            comtypes.CoInitialize()
        except OSError:
            pass

        try:
            # ── PASSO 1: Mutar entrada ────────────────────────────────────
            self._set_state(State.MUTING)
            input_id = self._config.get("input_device_id", "")
            if input_id:
                ok = self._audio_mgr.mute_device(input_id)
                self._log("Entrada de áudio mutada." if ok else "AVISO: falha ao mutar entrada.", "info" if ok else "warn")
            else:
                self._log("AVISO: Nenhum dispositivo de entrada configurado.", "warn")

            if self._cancel_event.is_set():
                return

            # ── PASSO 2: Envia hotkey STOP ────────────────────────────────
            hotkey_stop = self._config.get("hotkey_stop", "")
            if hotkey_stop:
                self._log(f"Enviando comando STOP: {hotkey_stop}", "info")
                self._hotkey.send_hotkey(hotkey_stop)
            else:
                self._log("Hotkey STOP não configurada — pulando.", "warn")

            if self._cancel_event.is_set():
                return

            # ── PASSO 3: Vinheta 1 ───────────────────────────────────────
            self._set_state(State.AUDIO1)
            audio1 = self._config.get("audio_file_1", "")
            self._log(f"Vinheta 1: {audio1 or '(não configurada)'}", "info")
            if not self._play_and_wait(audio1, "Vinheta 1", timeout=300):
                return

            # ── PASSO 4: Streaming ────────────────────────────────────────
            self._set_state(State.STREAMING)
            stream_url = self._config.get("stream_url", "")
            try:
                stream_duration = int(self._config.get("stream_duration", 300))
            except (ValueError, TypeError):
                stream_duration = 300

            self._log(f"Streaming: {stream_url or '(não configurado)'} | Duração: {stream_duration}s", "info")
            if not self._play_and_wait(stream_url, "Streaming",
                                        duration=stream_duration,
                                        timeout=stream_duration + 120):
                return

            # ── PASSO 5: Vinheta 2 ───────────────────────────────────────
            self._set_state(State.AUDIO2)
            audio2 = self._config.get("audio_file_2", "")
            self._log(f"Vinheta 2: {audio2 or '(não configurada)'}", "info")
            if not self._play_and_wait(audio2, "Vinheta 2", timeout=300):
                return

            # ── PASSO 6: Envia hotkey PLAY ────────────────────────────────
            self._set_state(State.PLAY_CMD)
            hotkey_play = self._config.get("hotkey_play", "")
            if hotkey_play:
                self._log(f"Enviando comando PLAY: {hotkey_play}", "info")
                self._hotkey.send_hotkey(hotkey_play)
            else:
                self._log("Hotkey PLAY não configurada — pulando.", "warn")

            if self._cancel_event.is_set():
                return

            # ── PASSO 7: Aguarda próxima keyword ──────────────────────────
            self._set_state(State.WAITING_NEXT)
            self._log(f"Aguardando keyword de retorno no TXT...", "info")

        except Exception as exc:
            self._log(f"Erro inesperado na sequência: {exc}", "error")
            self._set_state(State.IDLE)
        finally:
            try:
                comtypes.CoUninitialize()
            except Exception:
                pass

    def _run_return(self):
        """Executa o retorno à programação normal (após keyword_unmute)."""
        import comtypes
        try:
            comtypes.CoInitialize()
        except OSError:
            pass

        try:
            self._set_state(State.STOP_RETURN)

            # ── PASSO 8: Envia hotkey STOP (retorno) ──────────────────────
            hotkey_stop = self._config.get("hotkey_stop", "")
            if hotkey_stop:
                self._log(f"Enviando comando STOP (retorno): {hotkey_stop}", "info")
                self._hotkey.send_hotkey(hotkey_stop)
            else:
                self._log("Hotkey STOP não configurada — pulando.", "warn")

            # ── PASSO 9: Desmuta entrada ──────────────────────────────────
            input_id = self._config.get("input_device_id", "")
            if input_id:
                ok = self._audio_mgr.unmute_device(input_id)
                self._log("Entrada de áudio desmutada." if ok else "AVISO: falha ao desmutar entrada.", "info" if ok else "warn")
            else:
                self._log("AVISO: Nenhum dispositivo de entrada configurado.", "warn")

            self._set_state(State.IDLE)
            self._log("Jornada Esportiva encerrada. Retornando à programação normal.", "success")

        except Exception as exc:
            self._log(f"Erro no retorno: {exc}", "error")
            self._set_state(State.IDLE)
        finally:
            try:
                comtypes.CoUninitialize()
            except Exception:
                pass


