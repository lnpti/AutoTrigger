"""
Player de áudio usando python-vlc.
Suporta arquivos locais (MP3, WAV, OGG...) e streams por URL, incluindo playlists M3U.
Requer VLC instalado no sistema.
"""
import threading
import time
from typing import Optional

try:
    import vlc
    VLC_AVAILABLE = True
except Exception:
    VLC_AVAILABLE = False

GAIN_DB_MIN = -40.0
GAIN_DB_MAX = 6.0   # o VLC amplifica no máximo 200% de amplitude = +6,02 dB


def db_to_percent(db: float) -> int:
    """Ganho em dB -> volume do VLC em % (0 dB = 100; +6 dB ~ 200)."""
    return max(0, min(200, round(100 * 10 ** (float(db) / 20))))


def percent_to_db(percent: float) -> float:
    """Inverso de db_to_percent (usado p/ migrar etapas salvas em %)."""
    import math
    return 20 * math.log10(percent / 100) if percent > 0 else GAIN_DB_MIN


# Stream tocando MUDO por tantos segundos seguidos -> o watchdog reinicia
# (stop + play) e repete até o som voltar. "Mudo" = pico abaixo de ~ -66 dBFS.
STREAM_SILENCE_SECONDS = 10.0
AUDIBLE_PEAK = 0.0005
# Logo após (re)iniciar, o VLC ainda enche o cache de rede: não conta como mudo.
STREAM_RESTART_GRACE_SECONDS = 4.0
# Travado fora de "Playing" (Opening/Buffering...) por tanto tempo -> reinicia.
# Maior que o cache de rede (8 s) + conexão, para não reiniciar uma abertura normal.
STREAM_STALL_SECONDS = 25.0

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
        self._stream_duration = 0.0   # duração AO VIVO do stream atual (ver adjust_stream_time)
        self._stream_started_at = 0.0
        self._is_streaming = False
        self._stream_lock = threading.Lock()
        self._output_device_id = ""   # ID MMDevice Windows do dispositivo de saída
        self._output_device_name = ""
        self._warned_output = None    # evita repetir o aviso de saída a cada play
        self._current_out_id = ""     # saída realmente pedida ao VLC no último play
        self._silence_limit = STREAM_SILENCE_SECONDS
        self._stall_limit = STREAM_STALL_SECONDS
        self._volume = 100            # % (0-200; acima de 100 = ganho/amplificação do VLC)
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

    def set_output_device(self, device_id: str, device_name: str = ""):
        """Define o dispositivo de saída Windows MMDevice para o VLC usar.
        O nome serve de reserva quando o ID não existe neste PC."""
        self._output_device_id = device_id
        self._output_device_name = device_name

    def _effective_output_id(self) -> str:
        """ID da saída a usar agora: primeiro pelo NOME (o ID do Windows muda
        com driver/porta USB/outro PC); se o nome não for achado, o ID salvo, se
        ativo; senão "" (saída padrão do Windows, avisando)."""
        if not (self._output_device_id or self._output_device_name):
            return ""
        try:
            import audio_manager as am
            alt = am.find_device_by_name(self._output_device_name, "render")
            if alt is None and any(d["id"] == self._output_device_id
                                   for d in am.list_output_devices()):
                return self._output_device_id
        except Exception:
            return self._output_device_id  # sem como checar: tenta o ID salvo
        label = self._output_device_name or self._output_device_id
        if alt:
            if alt["id"] != self._output_device_id and self._warned_output != ("id", alt["id"]):
                self._warned_output = ("id", alt["id"])
                self._log(f"O ID da saída '{label}' mudou neste PC; usando o ID "
                          f"atual (encontrado pelo nome).", "warn")
            return alt["id"]
        if self._warned_output != ("missing", label):
            self._warned_output = ("missing", label)
            self._log(f"Saída de áudio '{label}' não encontrada neste PC — "
                      f"tocando na saída padrão do Windows.", "warn")
        return ""

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

    def play(self, source: str, duration_seconds: int = 0, volume: int = 100) -> bool:
        """
        Reproduz um arquivo local ou URL de stream/playlist.
        duration_seconds > 0 → usa timer fixo (para streaming online).
        volume: ganho em % (0-200; 100 = normal, >100 amplifica). Vale só para
        esta reprodução -- toda chamada redefine (arquivos de áudio usam 100).
        Retorna True se iniciou sem erros.
        """
        if not self.is_vlc_available():
            self._log("VLC não disponível.", "error")
            return False

        self._volume = max(0, min(200, int(volume)))
        self.stop()
        self._generation += 1
        gen = self._generation

        # Detecta se é playlist pelo final da URL (ignora query string)
        source_lower = source.lower().split("?")[0]
        is_playlist = source_lower.endswith(_PLAYLIST_EXTS)

        if not self._start_media(source, is_playlist):
            return False

        with self._stream_lock:
            self._stream_duration = float(duration_seconds)
            self._is_streaming = duration_seconds > 0
            self._stream_started_at = time.time()

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
            out_id = self._effective_output_id()
            self._current_out_id = out_id
            if out_id:
                try:
                    self._player.audio_output_set("mmdevice")
                    self._player.audio_output_device_set("mmdevice", out_id)
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
            self._apply_volume()
            return True
        except Exception as exc:
            self._log(f"Erro ao reproduzir '{source}': {exc}", "error")
            return False

    def _apply_volume(self):
        """Aplica o ganho ao player atual. O VLC ignora (retorna -1) o volume
        enquanto a saída de áudio ainda não abriu -- por isso também é
        reaplicado quando o estado vira Playing (ver _await_playing)."""
        if self._player is None:
            return
        try:
            self._player.audio_set_volume(self._volume)
        except Exception as exc:
            self._log(f"Aviso ao ajustar volume: {exc}", "warn")

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

        if self._generation == generation:
            self._is_streaming = False

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
                self._apply_volume()
                return True
            time.sleep(0.3)
        return False

    def _monitor_stream(self, source: str, is_playlist: bool,
                        duration_seconds: int, generation: int):
        """Monitor de stream com watchdog/auto-reconexão (ver _monitor_playback).

        Reinicia o stream (stop + play) quando: o VLC cai (Error/Ended/Stopped),
        fica sem entrar em "Playing" (travado em buffering) ou toca MUDO por
        `_silence_limit` segundos seguidos.
        """
        DEAD = (vlc.State.Ended, vlc.State.Error, vlc.State.Stopped)
        limit = self._silence_limit
        stall_limit = self._stall_limit
        step = 0.5

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
        silent_for = stalled_for = unverified_for = 0.0
        grace_left = STREAM_RESTART_GRACE_SECONDS
        measured_ok = False       # o medidor já deu leitura real neste stream
        unverified_warned = False
        location_logged = None    # ID da saída onde o áudio foi visto (p/ logar 1x)
        redirects = 0             # tentativas de mover o áudio p/ a saída selecionada
        silence_restarts = 0
        meter = None
        try:
            from audio_meter import SessionPeakMeter
            meter = SessionPeakMeter(self._effective_output_id)
        except Exception as exc:
            self._log(f"Vigia de stream mudo indisponível: {exc}", "warn")

        try:
            while elapsed < self._stream_duration and not self._stop_monitor.is_set():
                time.sleep(step)
                elapsed += step
                if self._generation != generation:
                    return

                try:
                    st = self._player.get_state() if self._player else None
                except Exception:
                    st = None
                st_name = st.name if hasattr(st, "name") else str(st)

                reason = None   # (kind, texto) -> kind: "dead" | "silence" | "stalled"
                if st in DEAD:
                    reason = ("dead", f"VLC: {st_name}")
                elif st == vlc.State.Playing:
                    stalled_for = 0.0
                    level = meter.peak() if meter is not None else None
                    if level is not None:
                        measured_ok = True
                        loc = meter.location
                        if loc and loc[0] != location_logged:
                            location_logged = loc[0]
                            expected = self._current_out_id
                            if expected and loc[0] != expected:
                                shown = self._output_device_name or expected
                                if redirects < 2:
                                    redirects += 1
                                    self._log(f"⚠ O áudio do stream está saindo em '{loc[1]}', "
                                              f"não na saída selecionada '{shown}' — movendo "
                                              f"para a selecionada (tentativa {redirects}).", "warn")
                                    try:
                                        self._player.audio_output_device_set(None, expected)
                                    except Exception as exc:
                                        self._log(f"Não consegui mover a saída: {exc}", "warn")
                                    meter.reset()
                                    location_logged = None
                                else:
                                    self._log(f"⚠ O áudio continua saindo em '{loc[1]}', não em "
                                              f"'{shown}'. Confira a saída em Configurações Globais.",
                                              "warn")
                            elif expected and redirects:
                                self._log(f"✓ Áudio agora sai na saída selecionada ('{loc[1]}').",
                                          "success")
                            else:
                                self._log(f"Vigia de áudio ativo — saída em uso: '{loc[1]}'.", "info")
                        if level > AUDIBLE_PEAK:
                            silent_for = 0.0
                            if silence_restarts:
                                self._log("✓ O áudio do stream voltou.", "success")
                                self._emit_stream_event("recovered", "o áudio voltou")
                                silence_restarts = 0
                                reconnect_attempt = 0
                                backoff = 1.0
                        elif grace_left > 0:
                            grace_left -= step
                        else:
                            silent_for += step
                    elif measured_ok:
                        if grace_left > 0:
                            grace_left -= step
                        else:
                            silent_for += step   # mediu antes e a sessão sumiu
                    else:
                        # Nunca conseguiu medir (outra saída? erro de COM?): sem
                        # confirmar que o medidor funciona, não reinicia à toa.
                        unverified_for += step
                        if meter is not None and unverified_for >= 20.0 and not unverified_warned:
                            unverified_warned = True
                            why = (meter.last_problem if meter else "") or "sem detalhe"
                            self._log("Não consegui medir o nível do áudio — o vigia de "
                                      "stream mudo fica inativo nesta reprodução "
                                      "(queda e travamento continuam vigiados). "
                                      f"Motivo: {why}", "warn")
                    if silent_for >= limit:
                        reason = ("silence", f"mudo há {int(silent_for)}s")
                else:
                    silent_for = 0.0
                    stalled_for += step
                    if stalled_for >= stall_limit:
                        reason = ("stalled", f"sem tocar há {int(stalled_for)}s (VLC: {st_name})")

                if reason and elapsed < self._stream_duration and not self._stop_monitor.is_set():
                    kind, text = reason
                    reconnect_attempt += 1
                    remaining = int(self._stream_duration - elapsed)
                    m, s = divmod(remaining, 60)
                    what = {"dead": "Stream caiu", "silence": "Stream mudo",
                            "stalled": "Stream travado"}[kind]
                    self._log(f"⚠ {what} ({text}) — reiniciando (stop + play, "
                              f"tentativa {reconnect_attempt}), restam {m:02d}:{s:02d}.", "warn")
                    if reconnect_attempt == 1:
                        self._emit_stream_event("dropped", text)
                    self._emit_stream_event("reconnecting", f"tentativa {reconnect_attempt}")

                    if kind == "dead":
                        time.sleep(backoff)
                        backoff = min(backoff * 1.5, 5.0)
                    else:
                        time.sleep(1.0)   # mudo/travado: stop + play já, até o som voltar
                    if self._stop_monitor.is_set() or self._generation != generation:
                        return

                    silent_for = stalled_for = 0.0
                    grace_left = STREAM_RESTART_GRACE_SECONDS
                    if kind == "silence":
                        silence_restarts += 1
                    if meter is not None:
                        meter.reset()
                    if not self._start_media(source, is_playlist):
                        continue  # falhou ao recriar; tenta de novo no próximo ciclo
                    if self._await_playing(generation, 10.0) and kind != "silence":
                        # Após reinício por mudo, "recuperado" só quando o som voltar.
                        self._log("✓ Stream reconectado.", "success")
                        self._emit_stream_event("recovered", f"após {reconnect_attempt} tentativa(s)")
                        reconnect_attempt = 0
                        backoff = 1.0
                    continue

                if elapsed - last_log_at >= 10.0:
                    last_log_at = elapsed
                    remaining = int(self._stream_duration - elapsed)
                    m, s = divmod(remaining, 60)
                    self._log(f"Streaming... restam {m:02d}:{s:02d} | VLC: {st_name}", "info")
        finally:
            if meter is not None:
                meter.close()

    def stop(self):
        """Para a reprodução imediatamente."""
        self._stop_monitor.set()
        self._is_streaming = False
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

    def is_streaming(self) -> bool:
        """True enquanto uma etapa de streaming (duration_seconds > 0) está ativa."""
        return self._is_streaming

    def adjust_stream_time(self, delta_seconds: float) -> Optional[float]:
        """
        Soma (ou subtrai, se negativo) tempo à duração do stream ATUALMENTE em
        execução. Vale só para essa execução -- não altera a configuração
        salva da etapa (duration_seconds no config.json continua igual).

        Reduzir para menos que o tempo já decorrido encerra o stream no
        próximo ciclo do monitor (~0.5s), como um "encerrar antes".

        Retorna a nova duração total em segundos, ou None se não há stream
        em execução no momento.
        """
        with self._stream_lock:
            if not self._is_streaming:
                return None
            self._stream_duration = max(0.0, self._stream_duration + delta_seconds)
            return self._stream_duration

    def get_stream_duration(self) -> float:
        """Duração total AO VIVO do stream atual (pode já ter sido ajustada)."""
        return self._stream_duration

    def get_stream_end_time(self) -> Optional[float]:
        """Timestamp Unix (time.time()) previsto de término do stream atual,
        ou None se não há stream em execução."""
        if not self._is_streaming:
            return None
        return self._stream_started_at + self._stream_duration

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
