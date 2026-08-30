"""
Player de áudio usando python-vlc.
Suporta arquivos locais (MP3, WAV, OGG...) e streams por URL, incluindo playlists M3U.
Requer VLC instalado no sistema.
"""
import threading
import time

try:
    import vlc
    VLC_AVAILABLE = True
except Exception:
    VLC_AVAILABLE = False

# Extensões de playlist que precisam de MediaListPlayer
_PLAYLIST_EXTS = (".m3u", ".m3u8", ".pls", ".xspf", ".asx")


class AudioPlayer:
    def __init__(self):
        self._instance = None
        self._player = None           # vlc.MediaPlayer
        self._list_player = None      # vlc.MediaListPlayer (para M3U/playlists)
        self._monitor_thread: threading.Thread | None = None
        self._stop_monitor = threading.Event()
        self._on_finished = None
        self._on_stream_event = None  # cb(kind, detail) p/ watchdog (dropped/reconnecting/recovered)
        self._generation = 0          # evita callbacks de threads antigas
        self._output_device_id = ""   # ID MMDevice Windows do dispositivo de saída
        self._log = lambda msg, level="info": print(f"[Player][{level}] {msg}")

        if VLC_AVAILABLE:
            try:
                self._instance = vlc.Instance(
                    "--quiet",
                    "--no-video",
                    "--network-caching=8000",
                    "--live-caching=8000",
                    "--sout-mux-caching=8000",
                )
            except Exception as exc:
                print(f"[Player] Erro ao iniciar instância VLC: {exc}")

    # ── public API ────────────────────────────────────────────────────────────

    def is_vlc_available(self) -> bool:
        return VLC_AVAILABLE and self._instance is not None

    def set_output_device(self, device_id: str):
        """Define o dispositivo de saída Windows MMDevice para o VLC usar."""
        self._output_device_id = device_id

    def set_on_finished(self, callback):
        """Define callback chamado ao fim natural da mídia (não em stop() manual)."""
        self._on_finished = callback

    def set_on_stream_event(self, callback):
        """Callback do watchdog de stream: callback(kind, detail).

        kind ∈ {"dropped", "reconnecting", "recovered"}. Usado para alimentar
        alertas (ex.: email). Disparado de forma defensiva.
        """
        self._on_stream_event = callback

    def _emit_stream_event(self, kind: str, detail: str = ""):
        cb = self._on_stream_event
        if cb:
            try:
                cb(kind, detail)
            except Exception:
                pass

    def set_log(self, callback):
        self._log = callback

    def play(self, source: str, duration_seconds: int = 0) -> bool:
        """
        Reproduz um arquivo local ou URL de stream/playlist.
        duration_seconds > 0 → usa timer fixo (para streaming online).
        Retorna True se iniciou sem erros.
        """
        if not self.is_vlc_available():
            self._log("VLC não disponível.", "error")
            return False

        self.stop()
        self._generation += 1
        gen = self._generation

        # Detecta se é playlist pelo final da URL (ignora query string)
        source_lower = source.lower().split("?")[0]
        is_playlist = source_lower.endswith(_PLAYLIST_EXTS)

        if not self._start_media(source, is_playlist):
            return False

        self._stop_monitor.clear()
        self._monitor_thread = threading.Thread(
            target=self._monitor_playback,
            args=(source, is_playlist, duration_seconds, gen),
            daemon=True,
            name="player-monitor",
        )
        self._monitor_thread.start()
        return True

    # ── internal ──────────────────────────────────────────────────────────────

    def _start_media(self, source: str, is_playlist: bool) -> bool:
        """Cria os players VLC, aplica o device de saída e inicia a reprodução.

        Usado tanto pelo play() inicial quanto pela reconexão do watchdog.
        Libera qualquer player anterior antes de recriar.
        """
        # Libera players antigos (reconexão)
        if self._list_player is not None:
            try:
                self._list_player.stop()
                self._list_player.release()
            except Exception:
                pass
            self._list_player = None
        if self._player is not None:
            try:
                self._player.stop()
                self._player.release()
            except Exception:
                pass
            self._player = None

        try:
            self._player = self._instance.media_player_new()

            # Configura dispositivo de saída ANTES de iniciar (síncrono)
            # Isso evita que o VLC abra o device padrão e depois mude,
            # o que causaria áudio duplicado na transição.
            if self._output_device_id:
                try:
                    self._player.audio_output_set("mmdevice")
                    self._player.audio_output_device_set(
                        "mmdevice", self._output_device_id
                    )
                except Exception as exc:
                    self._log(f"Aviso ao configurar saída de áudio: {exc}", "warn")

            if is_playlist:
                self._log(f"Modo playlist (M3U/PLS): {source}", "info")
                media_list = self._instance.media_list_new([source])
                self._list_player = self._instance.media_list_player_new()
                self._list_player.set_media_player(self._player)
                self._list_player.set_media_list(media_list)
                self._list_player.play()
            else:
                media = self._instance.media_new(source)
                self._player.set_media(media)
                self._player.play()
            return True
        except Exception as exc:
            self._log(f"Erro ao reproduzir '{source}': {exc}", "error")
            return False

    def _monitor_playback(self, source: str, is_playlist: bool,
                          duration_seconds: int, generation: int):
        """
        Modo STREAM (duration_seconds > 0):
          Aguarda VLC iniciar (máx 15s) → conta o tempo de parede.
          Watchdog: se o VLC cair (Error/Ended/Stopped) antes do tempo acabar,
          reconecta sozinho (refaz o "play") com backoff, sem perder o tempo
          restante. Loga status a cada 10s para diagnóstico.

        Modo ARQUIVO (duration_seconds == 0):
          Aguarda estado Ended/Error/Stopped do VLC → chama on_finished.
        """
        if duration_seconds > 0:
            self._monitor_stream(source, is_playlist, duration_seconds, generation)
        else:
            # Arquivo local: aguarda fim natural
            time.sleep(0.5)
            while not self._stop_monitor.is_set():
                if self._player is None:
                    break
                try:
                    state = self._player.get_state()
                except Exception:
                    break
                if state in (vlc.State.Ended, vlc.State.Error, vlc.State.Stopped):
                    break
                time.sleep(0.2)

        # Só chama on_finished se não houve stop() manual e geração é válida
        if not self._stop_monitor.is_set() and self._generation == generation:
            self.stop()
            cb = self._on_finished
            if cb:
                cb()

    def _await_playing(self, generation: int, timeout: float) -> bool:
        """Aguarda o VLC entrar em Playing (até timeout). False se cair/timeout."""
        deadline = time.time() + timeout
        while time.time() < deadline and not self._stop_monitor.is_set():
            if self._generation != generation:
                return False
            try:
                st = self._player.get_state() if self._player else None
            except Exception:
                return False
            if st == vlc.State.Playing:
                return True
            time.sleep(0.3)
        return False

    def _monitor_stream(self, source: str, is_playlist: bool,
                        duration_seconds: int, generation: int):
        """Monitor de stream com watchdog/auto-reconexão (ver _monitor_playback)."""
        # Estados que indicam que o stream caiu / parou.
        DEAD = (vlc.State.Ended, vlc.State.Error, vlc.State.Stopped)

        self._log("Conectando ao stream...", "info")
        started = self._await_playing(generation, 15.0)
        if not started and not self._stop_monitor.is_set():
            self._log("Stream não iniciou no timeout — tentando reconectar.", "warn")
        elif started:
            self._log(f"Stream ativo. Tocando por {duration_seconds}s.", "success")

        elapsed = 0.0
        last_log_at = 0.0
        reconnect_attempt = 0
        backoff = 1.0

        while elapsed < duration_seconds and not self._stop_monitor.is_set():
            time.sleep(0.5)
            elapsed += 0.5
            if self._generation != generation:
                return

            try:
                st = self._player.get_state() if self._player else None
            except Exception:
                st = None

            # Watchdog: stream caiu antes da hora → reconecta (simula o "play").
            if st in DEAD and elapsed < duration_seconds and not self._stop_monitor.is_set():
                reconnect_attempt += 1
                st_name = st.name if hasattr(st, "name") else str(st)
                remaining = int(duration_seconds - elapsed)
                m, s = divmod(remaining, 60)
                self._log(
                    f"⚠ Stream caiu (VLC: {st_name}) — reconectando "
                    f"(tentativa {reconnect_attempt}), restam {m:02d}:{s:02d}.",
                    "warn",
                )
                if reconnect_attempt == 1:
                    self._emit_stream_event("dropped", f"VLC: {st_name}")
                self._emit_stream_event("reconnecting", f"tentativa {reconnect_attempt}")

                time.sleep(backoff)
                backoff = min(backoff * 1.5, 5.0)
                if self._stop_monitor.is_set() or self._generation != generation:
                    return

                if not self._start_media(source, is_playlist):
                    continue  # falhou ao recriar; tenta de novo no próximo ciclo
                if self._await_playing(generation, 10.0):
                    self._log("✓ Stream reconectado.", "success")
                    self._emit_stream_event("recovered", f"após {reconnect_attempt} tentativa(s)")
                    reconnect_attempt = 0
                    backoff = 1.0
                continue

            if elapsed - last_log_at >= 10.0:
                last_log_at = elapsed
                remaining = int(duration_seconds - elapsed)
                m, s = divmod(remaining, 60)
                st_name = st.name if hasattr(st, "name") else str(st)
                self._log(f"Streaming... restam {m:02d}:{s:02d} | VLC: {st_name}", "info")

    def stop(self):
        """Para a reprodução imediatamente."""
        self._stop_monitor.set()
        if self._list_player is not None:
            try:
                self._list_player.stop()
                self._list_player.release()
            except Exception:
                pass
            self._list_player = None
        if self._player is not None:
            try:
                self._player.stop()
                self._player.release()
            except Exception:
                pass
            self._player = None

    def is_playing(self) -> bool:
        if self._player is None:
            return False
        try:
            return self._player.get_state() == vlc.State.Playing
        except Exception:
            return False

    def release(self):
        """Libera todos os recursos VLC."""
        self.stop()
        if self._instance is not None:
            try:
                self._instance.release()
            except Exception:
                pass
            self._instance = None
