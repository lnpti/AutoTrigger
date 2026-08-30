"""
Executa etapas individuais de uma sequência.

Tipos suportados:
  mute / unmute / open_channel / close_channel — audio_manager.set_device_mute()
  hotkey      — hotkey_sender.send_hotkey()
  play_audio  — AudioPlayer.play(file)
  stream      — AudioPlayer.play(url, duration_seconds)
  wait_time   — sleep com tick callback
  wait_keyword — espera threading.Event (fornecido por keyword_waiter)
"""
import threading
import time
import os

import audio_manager as _audio
import hotkey_sender as _hotkey


class StepRunner:
    def __init__(self, player):
        self._player = player
        self._log = lambda msg, level="info": print(f"[StepRunner][{level}] {msg}")

    def set_log(self, fn):
        self._log = fn

    def run_step(
        self,
        step: dict,
        stop_event: threading.Event,
        on_tick=None,           # Callable(elapsed_s, total_s)
        keyword_waiter=None,    # Callable(keyword: str) -> threading.Event
        dry_run: bool = False,  # modo ensaio: não muta/dispara de verdade
        preview_cap: int = 0,   # >0 limita áudio/stream a N segundos (teste/ensaio)
    ) -> bool:
        """
        Executa uma etapa. Retorna True se concluída, False se falhou/cancelada.
        """
        t = step.get("type", "")

        if t in ("mute", "open_channel"):
            return self._do_mute(step, mute=True, dry_run=dry_run)

        elif t in ("unmute", "close_channel"):
            return self._do_mute(step, mute=False, dry_run=dry_run)

        elif t == "hotkey":
            return self._do_hotkey(step, dry_run=dry_run)

        elif t == "play_audio":
            return self._do_play_audio(step, stop_event, preview_cap=preview_cap)

        elif t == "stream":
            return self._do_stream(step, stop_event, on_tick, preview_cap=preview_cap)

        elif t == "wait_time":
            return self._do_wait_time(step, stop_event, on_tick, dry_run=dry_run)

        elif t == "wait_keyword":
            if dry_run:
                self._log("[ENSAIO] Aguardar keyword — pulado no ensaio.", "warn")
                return True
            return self._do_wait_keyword(step, stop_event, keyword_waiter)

        else:
            self._log(f"Tipo de etapa desconhecido: '{t}' — pulando.", "warn")
            return True

    # ── step handlers ─────────────────────────────────────────────────────────

    def _do_mute(self, step: dict, mute: bool, dry_run: bool = False) -> bool:
        device_id = step.get("device_id", "")
        name = step.get("device_name", device_id) or device_id
        action = "Mutando" if mute else "Desmutando"
        if dry_run:
            self._log(f"[ENSAIO] {action}: {name} (sem efeito real)", "warn")
            return True
        self._log(f"{action}: {name}")
        _audio.set_device_mute(device_id, mute)
        return True  # continua mesmo em falha de mute

    def _do_hotkey(self, step: dict, dry_run: bool = False) -> bool:
        hk = step.get("hotkey", "")
        label = step.get("label", hk)
        target = step.get("target_window", "").strip()
        if dry_run:
            tw = f" → janela '{target}'" if target else ""
            self._log(f"[ENSAIO] Hotkey: {label} ({hk}){tw} (sem efeito real)", "warn")
            return True
        if target:
            self._log(f"Hotkey: {label} ({hk}) → janela '{target}'")
            _hotkey.send_hotkey_to_window(hk, target)
        else:
            self._log(f"Hotkey: {label} ({hk})")
            _hotkey.send_hotkey(hk)
        return True

    def _do_play_audio(self, step: dict, stop_event: threading.Event,
                       preview_cap: int = 0) -> bool:
        path = step.get("file", "")
        label = step.get("label", os.path.basename(path) if path else "áudio")
        if not path:
            self._log("Caminho de áudio não configurado.", "warn")
            return True
        cap_txt = f" (prévia {preview_cap}s)" if preview_cap else ""
        self._log(f"Tocando: {label}{cap_txt}")
        done_ev = threading.Event()
        self._player.set_on_finished(lambda: done_ev.set())
        if not self._player.play(path, duration_seconds=0):
            self._log(f"Falha ao reproduzir: {label}", "error")
            return True  # continua mesmo em falha de áudio
        elapsed = 0.0
        while not done_ev.is_set() and not stop_event.is_set():
            time.sleep(0.2)
            elapsed += 0.2
            if preview_cap and elapsed >= preview_cap:
                self._player.stop()
                break
        if stop_event.is_set():
            self._player.stop()
            return False
        return True

    def _do_stream(
        self, step: dict, stop_event: threading.Event, on_tick=None,
        preview_cap: int = 0,
    ) -> bool:
        url = step.get("url", "")
        duration = int(step.get("duration_seconds", 300))
        if preview_cap:
            duration = min(duration, preview_cap)
        label = step.get("label", "Stream")
        if not url:
            self._log("URL de stream não configurada.", "warn")
            return True
        self._log(f"Streaming: {label} ({duration}s)")
        done_ev = threading.Event()
        self._player.set_on_finished(lambda: done_ev.set())
        if not self._player.play(url, duration_seconds=duration):
            self._log(f"Falha ao iniciar stream: {label}", "error")
            return True
        elapsed = 0.0
        while not done_ev.is_set() and not stop_event.is_set():
            time.sleep(1.0)
            elapsed += 1.0
            if on_tick:
                on_tick(elapsed, float(duration))
        if stop_event.is_set():
            self._player.stop()
            return False
        return True

    def _do_wait_time(
        self, step: dict, stop_event: threading.Event, on_tick=None,
        dry_run: bool = False,
    ) -> bool:
        seconds = float(step.get("seconds", 0))
        label = step.get("label", f"Aguardar {seconds}s")
        if dry_run:
            seconds = min(seconds, 3.0)
            self._log(f"[ENSAIO] Aguardando: {label} (reduzido p/ {int(seconds)}s)", "warn")
        else:
            self._log(f"Aguardando: {label}")
        elapsed = 0.0
        while elapsed < seconds and not stop_event.is_set():
            time.sleep(1.0)
            elapsed += 1.0
            if on_tick:
                on_tick(elapsed, seconds)
        return not stop_event.is_set()

    def _do_wait_keyword(
        self, step: dict, stop_event: threading.Event, keyword_waiter=None
    ) -> bool:
        keyword = step.get("keyword", "")
        label = step.get("label", f"Aguardar '{keyword}'")
        if not keyword:
            self._log("Keyword de espera não configurada.", "warn")
            return True
        if not keyword_waiter:
            self._log("keyword_waiter não configurado.", "warn")
            return True
        self._log(f"Aguardando keyword: '{keyword}'")
        ev = keyword_waiter(keyword)
        while not ev.is_set() and not stop_event.is_set():
            time.sleep(0.1)
        return not stop_event.is_set()
