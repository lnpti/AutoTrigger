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
import x32 as _x32
from config import resolve_stream
from player import db_to_percent, percent_to_db


def step_gain_db(step: dict) -> float:
    """Ganho (dB) de uma etapa de stream. Etapas da v2.3.13 guardavam
    `volume_percent`; converte se ainda não houver `gain_db`."""
    if "gain_db" in step:
        return float(step["gain_db"])
    if "volume_percent" in step:
        return round(percent_to_db(float(step["volume_percent"])), 1)
    return 0.0


class StepRunner:
    def __init__(self, player):
        self._player = player
        self._on_alert = None                # fn(kind, assunto, texto) -> alertas (ver set_on_alert)
        self._global_provider = lambda: {}   # -> config global (ver set_global_provider)
        self._log = lambda msg, level="info": print(f"[StepRunner][{level}] {msg}")

    def set_global_provider(self, fn):
        """fn() -> dict da config global; dá acesso às placas padrão."""
        self._global_provider = fn

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

        elif t == "x32_channel":
            return self._do_x32(step, dry_run=dry_run)

        elif t == "x32_watch":
            return self._do_x32_watch(step, stop_event, on_tick, dry_run=dry_run)

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
        dev_name = step.get("device_name", "")
        target_id, target_name = device_id, dev_name
        if _audio.resolve_active_device(device_id, dev_name) is None:
            fb = self._default_device_for(device_id)
            if fb:
                self._log(f"⚠ '{name}' não existe neste PC — usando a placa padrão das "
                          f"Configurações Globais: '{fb[1]}'.", "warn")
                target_id, name = fb
                target_name = fb[1]
        self._log(f"{action}: {name}")
        _audio.set_device_mute(target_id, mute, target_name)
        return True  # continua mesmo em falha de mute

    def _do_x32(self, step: dict, dry_run: bool = False) -> bool:
        """Liga/desliga (muta) um canal da mesa X32 por OSC. Falha não interrompe a
        sequência (como o mute de placa), mas aparece no log como erro."""
        cfg = (self._global_provider() or {}).get("x32", {}) or {}
        host = str(cfg.get("host", "") or "").strip()
        port = int(cfg.get("port", _x32.DEFAULT_PORT) or _x32.DEFAULT_PORT)
        kind = step.get("target", "ch")
        number = int(step.get("number", 1) or 1)
        on = step.get("action", "off") == "on"
        try:
            label = _x32.target_label(kind, number)
        except ValueError as exc:
            self._log(f"Mesa X32: etapa inválida ({exc}).", "error")
            return True
        verb = "LIGAR" if on else "DESLIGAR (mutar)"
        if dry_run:
            self._log(f"[ENSAIO] Mesa X32: {verb} {label} (sem efeito real)", "warn")
            return True
        if not host:
            self._log("Mesa X32: informe o IP da mesa em Configurações Globais.", "error")
            return True
        self._log(f"Mesa X32 ({host}): {verb} {label}")
        ok, detail = _x32.set_channel(host, port, kind, number, on)
        if ok:
            self._log(f"✓ Mesa X32: {label} {'ligado' if on else 'desligado'} ({detail}).", "success")
        else:
            self._log(f"✗ Mesa X32: não consegui {'ligar' if on else 'desligar'} {label}: {detail}.",
                      "error")
        return True  # continua mesmo em falha (o log mostra o erro)

    def _do_x32_watch(self, step: dict, stop_event: threading.Event, on_tick=None,
                      dry_run: bool = False) -> bool:
        """Vigia o áudio de um canal da X32 por `seconds`. Se o canal A ficar SEM áudio
        (abaixo de `threshold_db`) por `silence_seconds` seguidos, LIGA o canal B
        (`target`/`number`) -- e o B fica ligado. Se o A nunca falhar, só termina o tempo.
        Falha de rede/medidor não liga nada (evita disparo falso) e não trava a sequência."""
        cfg = (self._global_provider() or {}).get("x32", {}) or {}
        host = str(cfg.get("host", "") or "").strip()
        port = int(cfg.get("port", _x32.DEFAULT_PORT) or _x32.DEFAULT_PORT)
        seconds = float(step.get("seconds", 0) or 0)
        silence = max(0.5, float(step.get("silence_seconds", 3) or 3))
        thr = float(step.get("threshold_db", -50) or -50)
        watch_n = int(step.get("watch_number", 1) or 1)
        kind = step.get("target", "ch")
        number = int(step.get("number", 1) or 1)
        try:
            a_label = _x32.target_label("ch", watch_n)
            b_label = _x32.target_label(kind, number)
            _x32.meter_index("ch", watch_n)
        except ValueError as exc:
            self._log(f"Mesa X32: etapa de vigia inválida ({exc}).", "error")
            return True
        desc = (f"vigiar {a_label}; sem áudio (< {thr:g} dB) por {silence:g}s → ligar {b_label}"
                f" (por até {int(seconds)}s)")
        if dry_run:
            self._log(f"[ENSAIO] Mesa X32: {desc} (sem efeito real)", "warn")
            return True
        if not host:
            self._log("Mesa X32: informe o IP da mesa em Configurações Globais.", "error")
            return True
        self._log(f"Mesa X32 ({host}): {desc}")
        try:
            meter = _x32.MeterStream(host, port, "ch", watch_n)
        except (ValueError, _x32.X32Error) as exc:
            self._log(f"✗ Mesa X32: não consegui abrir o medidor: {exc}", "error")
            return True
        start = last_audio = last_data = time.time()
        warned_no_data = False
        peak_seen = None
        try:
            while not stop_event.is_set():
                now = time.time()
                elapsed = now - start
                if elapsed >= seconds:
                    self._log(f"Mesa X32: fim da vigia — {a_label} manteve o áudio; "
                              f"{b_label} não foi ligado.")
                    return True
                db = meter.level_db(0.25)
                now = time.time()
                if db is not None:
                    last_data = now
                    warned_no_data = False
                    peak_seen = db if peak_seen is None else max(peak_seen, db)
                    if db > thr:
                        last_audio = now
                elif now - last_data >= 10 and not warned_no_data:
                    warned_no_data = True
                    self._log(f"✗ Mesa X32: sem dados do medidor de {a_label} há 10 s "
                              f"(IP/rede/OSC?). Não ligo {b_label} sem medir.", "error")
                if on_tick:
                    on_tick(min(elapsed, seconds), seconds)
                if db is not None and now - last_audio >= silence:
                    self._log(f"⚠ Mesa X32: {a_label} sem áudio há {silence:g}s "
                              f"(nível {db:.0f} dB) — ligando {b_label}.", "warn")
                    ok, detail = _x32.set_channel(host, port, kind, number, True)
                    if ok:
                        self._log(f"✓ Mesa X32: {b_label} ligado ({detail}).", "success")
                    else:
                        self._log(f"✗ Mesa X32: não consegui ligar {b_label}: {detail}.", "error")
                    self._alert("x32_failover",
                                f"⚠ Canal sem áudio: {a_label}",
                                f"{a_label} ficou {silence:g}s sem áudio; "
                                + (f"{b_label} foi LIGADO." if ok else
                                   f"NÃO consegui ligar {b_label} ({detail})."))
                    return True
                time.sleep(0.02)
            return False
        finally:
            meter.close()

    def _alert(self, kind: str, subject: str, body: str):
        try:
            if self._on_alert:
                self._on_alert(kind, subject, body)
        except Exception as exc:      # alerta nunca derruba a sequência
            self._log(f"Falha ao enviar alerta: {exc}", "warn")

    def set_on_alert(self, fn):
        """fn(kind, assunto, texto): o engine envia por Telegram/e-mail."""
        self._on_alert = fn

    def _default_device_for(self, device_id: str):
        """(id, nome) da placa padrão (entrada ou saída, conforme o ID salvo no
        passo) das Configurações Globais, se ela existir neste PC; senão None."""
        prefix = {"capture": "input", "render": "output"}.get(_audio.kind_from_id(device_id or ""))
        if not prefix:
            return None
        g = self._global_provider() or {}
        dev = _audio.resolve_active_device(g.get(f"default_{prefix}_device_id", ""),
                                           g.get(f"default_{prefix}_device_name", ""))
        return (dev["id"], dev["name"]) if dev else None

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
        streams = (self._global_provider() or {}).get("streams", [])
        url, reg_name = resolve_stream(step, streams)
        if step.get("stream_id") and not reg_name:
            self._log("⚠ O streaming cadastrado desta etapa não existe mais — usando a "
                      "última URL salva nela.", "warn")
        duration = int(step.get("duration_seconds", 300))
        if preview_cap:
            duration = min(duration, preview_cap)
        label = step.get("label", "Stream")
        if not url:
            self._log("URL de stream não configurada.", "warn")
            return True
        gain_db = step_gain_db(step)
        volume = db_to_percent(gain_db)
        gain_txt = f", ganho {gain_db:+.1f} dB" if gain_db else ""
        reg_txt = f" [cadastro: {reg_name}]" if reg_name else ""
        self._log(f"Streaming: {label}{reg_txt} ({duration}s{gain_txt})")
        done_ev = threading.Event()
        self._player.set_on_finished(lambda: done_ev.set())
        if not self._player.play(url, duration_seconds=duration, volume=volume):
            self._log(f"Falha ao iniciar stream: {label}", "error")
            return True
        elapsed = 0.0
        while not done_ev.is_set() and not stop_event.is_set():
            time.sleep(1.0)
            elapsed += 1.0
            if on_tick:
                # Duração AO VIVO (não a capturada no início): reflete ajustes
                # de "tempo extra"/"retirar tempo" feitos durante a execução
                # (AudioPlayer.adjust_stream_time), sem alterar a etapa salva.
                on_tick(elapsed, self._player.get_stream_duration())
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
