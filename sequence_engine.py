"""
Motor de sequências — gerencia múltiplas sequências em paralelo.

- Registra triggers de keyword no FileMonitor para cada sequência habilitada
- Instancia SequenceRunner quando keyword é detectada
- Expõe callbacks de estado/tick para a UI
"""
import threading
import time
from datetime import datetime
from typing import Callable, Dict, Optional

import audio_manager as _audio
import emailer
import run_journal
import telegram_notifier
from step_runner import StepRunner
from sequence_runner import SequenceRunner, RunnerState
from file_monitor import FileMonitor, SOURCE_TXT, SOURCE_MEDIALOG
from timeparse import is_armed_today, fmt_secs


class SequenceEngine:
    def __init__(self, config, player, file_monitor: FileMonitor):
        self._config = config
        self._file_monitor = file_monitor
        self._step_runner = StepRunner(player)
        self._step_runner.set_global_provider(lambda: self._config.get_global())
        self._player = player

        self._runners: Dict[str, SequenceRunner] = {}
        self._temp_kw_lock = threading.Lock()
        self._temp_kw_events: Dict[str, list] = {}

        self._log_fn: Callable = lambda msg, level="info": print(f"[Engine][{level}] {msg}")
        self._on_runner_update: Optional[Callable] = None  # (seq_id, state_name, step_idx)
        self._on_tick: Optional[Callable] = None           # (seq_id, step_idx, elapsed, total)

        # Watchdog de stream → alerta por email
        self._streaming_seq_id: Optional[str] = None
        self._player.set_on_stream_event(self._on_stream_event)

        # Retomada após queda: lê ANTES de qualquer execução nova sobrescrever o
        # diário, e carrega o que a sessão anterior deixou mutado (ver resume_interrupted).
        self._prior_runs: dict = run_journal.load()
        self._stale_mutes: dict = _audio.load_ledger()
        threading.Thread(target=self._journal_loop, daemon=True, name="run-journal").start()

    # ── configuration ─────────────────────────────────────────────────────────

    def set_log(self, fn: Callable):
        self._log_fn = fn
        self._step_runner.set_log(fn)

    def set_on_runner_update(self, fn: Callable):
        """Callback: (seq_id: str, state_name: str, step_idx: int)"""
        self._on_runner_update = fn

    def set_on_tick(self, fn: Callable):
        """Callback: (seq_id: str, step_idx: int, elapsed: float, total: float)"""
        self._on_tick = fn

    def is_vlc_available(self) -> bool:
        return self._player.is_vlc_available()

    # ── ajuste de tempo do streaming em execução ─────────────────────────────────
    # Vale só para a execução atual da etapa (a duração salva na sequência não
    # muda) -- pedido do usuário: "tempo extra"/"retirar tempo" ao vivo.

    def is_streaming(self) -> bool:
        return self._player.is_streaming()

    def adjust_stream_time(self, delta_seconds: float) -> Optional[float]:
        """Soma/subtrai tempo ao stream em execução. None se não há stream ativo."""
        return self._player.adjust_stream_time(delta_seconds)

    def get_stream_end_time(self) -> Optional[float]:
        """Timestamp Unix previsto de término do stream atual, ou None."""
        return self._player.get_stream_end_time()

    # ── monitor control ───────────────────────────────────────────────────────

    def start_monitor(self) -> bool:
        g = self._config.get_global()
        txt = (g.get("txt_file_path", "") or "").strip()
        ml = g.get("medialog", {}) or {}
        folder = (ml.get("folder", "") or "").strip() if ml.get("enabled") else ""
        if not txt and not folder:
            self._log_fn("Configure o arquivo TXT e/ou a pasta do log do player "
                         "(Configurações Globais).", "error")
            return False
        ok = self._file_monitor.start(txt, log_callback=self._log_fn,
                                      medialog_folder=folder or None)
        if ok:
            self._register_all_triggers()
        return ok

    def stop_monitor(self):
        self._file_monitor.stop()

    def is_monitor_running(self) -> bool:
        return self._file_monitor.is_running()

    def is_medialog_running(self) -> bool:
        return self._file_monitor.is_medialog_running()

    def reload_sequences(self):
        """Recarrega triggers após mudança na config. Chama após salvar configurações."""
        for seq in self._config.get_sequences():
            kw = seq.get("keyword_trigger", "").strip()
            if kw:
                self._file_monitor.unregister_keyword(kw)
        if self._file_monitor.is_running():
            self._register_all_triggers()

    # ── triggers ──────────────────────────────────────────────────────────────

    def _register_all_triggers(self):
        for seq in self._config.get_sequences():
            if not (seq.get("enabled", True) and seq.get("keyword_trigger", "").strip()):
                continue
            if not is_armed_today(seq):
                self._log_fn(
                    f"'{seq.get('name', seq['id'])}' fora de agenda hoje — gatilho desativado.",
                    "warn",
                )
                continue
            self._register_trigger(seq)

    @staticmethod
    def _trigger_sources(seq: dict) -> list:
        """Origens que disparam a sequência: 'txt' (padrão), 'medialog' ou ambas."""
        src = seq.get("trigger_source", SOURCE_TXT)
        if src == "both":
            return [SOURCE_TXT, SOURCE_MEDIALOG]
        return [SOURCE_MEDIALOG] if src == SOURCE_MEDIALOG else [SOURCE_TXT]

    def _register_trigger(self, seq: dict):
        kw = seq["keyword_trigger"].strip()
        sid = seq["id"]
        for source in self._trigger_sources(seq):
            if source == SOURCE_MEDIALOG and not self._file_monitor.is_medialog_running():
                self._log_fn(
                    f"'{seq.get('name', sid)}' usa o log do player, mas ele não está "
                    f"ativo (habilite e aponte a pasta em Configurações Globais).",
                    "warn",
                )
            if source == SOURCE_MEDIALOG:
                cb = lambda ctx, _sid=sid: self._on_trigger(_sid, ctx)
            else:
                cb = lambda _sid=sid: self._on_trigger(_sid)
            self._file_monitor.register_keyword(kw, cb, source)

    # ── execution ─────────────────────────────────────────────────────────────

    def _on_trigger(self, seq_id: str, ctx: dict | None = None):
        """Gatilho detectado. `ctx` (só do log do player) traz os dados do áudio."""
        seq = self._config.get_sequence_by_id(seq_id)
        extra = 0.0
        if ctx and seq and seq.get("delay_from_audio_end"):
            extra = float(ctx.get("remaining_s", 0.0))
            self._log_fn(
                f"🎵 '{ctx.get('name', '')}' termina em {fmt_secs(int(round(extra)))} — "
                f"o atraso só começa a contar depois disso.", "info")
        self.run_sequence(seq_id, extra_delay=extra)

    def run_sequence(self, seq_id: str, dry_run: bool = False, manual: bool = False,
                     extra_delay: float = 0.0, resume: dict | None = None):
        """Inicia uma sequência. manual=True ignora o gatilho do TXT (botão Rodar).
        `resume` (entrada do diário) retoma uma execução interrompida por queda."""
        runner = self._runners.get(seq_id)
        if runner and runner.state == RunnerState.RUNNING:
            seq = self._config.get_sequence_by_id(seq_id)
            name = seq.get("name", seq_id) if seq else seq_id
            self._log_fn(f"'{name}' já em execução — ignorado.", "warn")
            return

        seq = self._config.get_sequence_by_id(seq_id)
        if not seq:
            return

        name = seq.get("name", seq_id)
        if dry_run:
            self._log_fn(f"🧪 Ensaio: '{name}'", "warn")
        else:
            origin = "manual" if manual else "gatilho"
            self._log_fn(f"🚀 Iniciando ({origin}): '{name}'", "success")

        if not dry_run:
            run_journal.begin(seq_id, name,
                              resumes=(int(resume.get("resumes", 0)) + 1) if resume else 0)
        runner = SequenceRunner(
            seq, self._step_runner, self._log_fn, dry_run=dry_run,
            extra_delay_seconds=extra_delay, resume=resume,
            progress_callback=lambda kind, i, step, end, _id=seq_id: self._on_progress(
                _id, kind, i, step, end),
            keyword_check=self._txt_contains)
        runner.set_keyword_waiter(self._make_keyword_waiter())
        runner.set_callbacks(
            on_state_change=lambda s, i, _id=seq_id: self._on_state(_id, s, i),
            on_tick=lambda i, e, t, _id=seq_id: self._on_runner_tick(_id, i, e, t),
        )
        self._runners[seq_id] = runner
        runner.start()

    def run_now(self, seq_id: str):
        """Dispara manualmente a sequência (sem esperar a keyword)."""
        self.run_sequence(seq_id, dry_run=False, manual=True)

    def rehearse(self, seq_id: str):
        """Ensaio: percorre a sequência sem mutar/disparar de verdade."""
        self.run_sequence(seq_id, dry_run=True, manual=True)

    def test_step(self, step: dict):
        """Executa uma ÚNICA etapa em worker thread (stream/áudio limitados)."""
        label = step.get("label") or step.get("type", "etapa")
        self._log_fn(f"🧪 Testando etapa: {label}", "warn")

        def _run():
            ev = threading.Event()
            try:
                self._step_runner.run_step(step, ev, preview_cap=8)
                self._log_fn(f"✓ Teste da etapa concluído: {label}", "success")
            except Exception as exc:
                self._log_fn(f"✗ Erro ao testar etapa: {exc}", "error")

        threading.Thread(target=_run, daemon=True, name="test-step").start()

    def _make_keyword_waiter(self) -> Callable:
        """Retorna função que registra keyword temporária e retorna threading.Event."""
        def _waiter(keyword: str) -> threading.Event:
            kw = keyword.strip().upper()
            ev = threading.Event()
            with self._temp_kw_lock:
                if kw not in self._temp_kw_events:
                    self._temp_kw_events[kw] = []
                self._temp_kw_events[kw].append(ev)

            def _fire():
                with self._temp_kw_lock:
                    for e in self._temp_kw_events.pop(kw, []):
                        e.set()
                self._file_monitor.unregister_keyword(kw, SOURCE_TXT)

            self._file_monitor.register_keyword(kw, _fire, SOURCE_TXT)
            return ev

        return _waiter

    def _on_state(self, seq_id: str, state: RunnerState, step_idx: int):
        # Rastreia a sequência atualmente em execução p/ contextualizar o stream.
        if state == RunnerState.RUNNING and step_idx == -1:
            self._streaming_seq_id = seq_id
        elif state in (RunnerState.DONE, RunnerState.ERROR, RunnerState.CANCELLED):
            if self._streaming_seq_id == seq_id:
                self._streaming_seq_id = None

        runner = self._runners.get(seq_id)
        if (state in (RunnerState.DONE, RunnerState.ERROR, RunnerState.CANCELLED)
                and (runner is None or not runner.is_dry_run)):
            run_journal.end(seq_id)   # terminou (ou foi cancelada): nada a retomar
        if runner is None or not runner.is_dry_run:  # ignora ensaios
            self._maybe_email_state(seq_id, state, step_idx)
            self._maybe_telegram_state(seq_id, state, step_idx)
        if self._on_runner_update:
            self._on_runner_update(seq_id, state.value, step_idx)

    # ── alertas por email / telegram ─────────────────────────────────────────────

    def _location(self) -> str:
        """Nome/descrição do local deste app (Configurações Globais): identifica de
        onde veio o alerta quando o app roda em vários lugares."""
        return str(self._config.get_global().get("location", "") or "").strip()

    def _email_cfg(self) -> dict:
        return self._config.get_global().get("email", {}) or {}

    def _telegram_cfg(self) -> dict:
        return self._config.get_global().get("telegram", {}) or {}

    def _seq_name(self, seq_id: str) -> str:
        seq = self._config.get_sequence_by_id(seq_id)
        return seq.get("name", seq_id) if seq else seq_id

    def _state_message(self, seq_id: str, state: RunnerState, step_idx: int):
        """Retorna (event_key, título, texto) para o estado, ou None se não notifica."""
        name = self._seq_name(seq_id)
        ts = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

        if state == RunnerState.RUNNING and step_idx == -1:
            return "start", f"▶ Disparo iniciado: {name}", f"A sequência '{name}' iniciou em {ts}."
        elif state == RunnerState.DONE:
            return "done", f"✅ Disparo concluído: {name}", f"A sequência '{name}' foi concluída em {ts}."
        elif state in (RunnerState.ERROR, RunnerState.CANCELLED):
            motivo = "falhou" if state == RunnerState.ERROR else "foi cancelada"
            return ("error", f"⚠ Disparo {motivo}: {name}",
                    f"A sequência '{name}' {motivo} em {ts} (etapa {step_idx + 1}).")
        return None

    def _maybe_email_state(self, seq_id: str, state: RunnerState, step_idx: int):
        """Dispara emails de início/fim/erro conforme a config."""
        cfg = self._email_cfg()
        if not (cfg.get("enabled") and emailer.is_configured(cfg)):
            return
        msg = self._state_message(seq_id, state, step_idx)
        if msg and cfg.get("events", {}).get(msg[0]):
            _, subject, body = msg
            subject, body = emailer.with_location(subject, body, self._location())
            emailer.notify_async(cfg, subject, body, log=self._log_fn)

    def _maybe_telegram_state(self, seq_id: str, state: RunnerState, step_idx: int):
        """Dispara mensagens Telegram de início/fim/erro conforme a config."""
        cfg = self._telegram_cfg()
        if not (cfg.get("enabled") and telegram_notifier.is_configured(cfg)):
            return
        msg = self._state_message(seq_id, state, step_idx)
        if msg and cfg.get("events", {}).get(msg[0]):
            _, subject, body = msg
            telegram_notifier.notify_async(
                cfg, telegram_notifier.with_location(f"{subject}\n{body}", self._location()),
                log=self._log_fn)

    def _on_stream_event(self, kind: str, detail: str):
        """Handler do watchdog do player (queda/reconexão de stream)."""
        name = self._seq_name(self._streaming_seq_id) if self._streaming_seq_id else "Stream"
        ts = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

        if kind == "dropped":
            subject = f"⚠ Problema no stream: {name}"
            body = (f"O stream da sequência '{name}' parou de funcionar em {ts} ({detail}). "
                    f"O app está reiniciando automaticamente (stop + play).")
        elif kind == "recovered":
            subject = f"✓ Stream reconectado: {name}"
            body = f"O stream da sequência '{name}' foi reconectado em {ts} ({detail})."
        else:
            return

        email_cfg = self._email_cfg()
        if (email_cfg.get("enabled") and emailer.is_configured(email_cfg)
                and email_cfg.get("events", {}).get("stream_reconnect")):
            mail_subject, mail_body = emailer.with_location(subject, body, self._location())
            emailer.notify_async(email_cfg, mail_subject, mail_body, log=self._log_fn)

        tg_cfg = self._telegram_cfg()
        if (tg_cfg.get("enabled") and telegram_notifier.is_configured(tg_cfg)
                and tg_cfg.get("events", {}).get("stream_reconnect")):
            telegram_notifier.notify_async(
                tg_cfg, telegram_notifier.with_location(f"{subject}\n{body}", self._location()),
                log=self._log_fn)

    def _on_runner_tick(self, seq_id: str, step_idx: int, elapsed: float, total: float):
        if self._on_tick:
            self._on_tick(seq_id, step_idx, elapsed, total)

    # ── control ───────────────────────────────────────────────────────────────

    def cancel(self, seq_id: str):
        runner = self._runners.get(seq_id)
        if runner:
            runner.cancel()

    def cancel_all(self):
        for runner in self._runners.values():
            runner.cancel()
        run_journal.clear()   # saída pedida (Sair): não retomar nada na próxima abertura

    # ── retomada após queda ───────────────────────────────────────────────────

    def _on_progress(self, seq_id: str, kind: str, idx: int, step, end_epoch):
        if kind == "delay":
            run_journal.update(seq_id, "delay", -1, "", end_epoch)
        else:
            run_journal.update(seq_id, "step", idx, (step or {}).get("type", ""), end_epoch)

    def _live_end(self, entry: dict):
        """Término AO VIVO do stream (o usuário pode ter dado/tirado tempo)."""
        if entry.get("step_type") == "stream" and self._player.is_streaming():
            return self._player.get_stream_end_time()
        return None

    def _journal_loop(self):
        while True:
            time.sleep(5.0)
            try:
                run_journal.touch(self._live_end)
            except Exception:
                pass

    def _txt_contains(self, keyword: str) -> bool:
        """A palavra já está no TXT monitorado agora? (retomada: ela pode ter
        aparecido enquanto o app estava fora)."""
        path = (self._config.get_global().get("txt_file_path", "") or "").strip()
        if not path or not keyword.strip():
            return False
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return keyword.strip().upper() in f.read().strip().upper()
        except OSError:
            return False

    def resume_interrupted(self) -> int:
        """Depois de uma queda: retoma, na etapa em que estavam, as sequências que
        rodavam -- se o app voltou dentro do limite (Configurações Globais,
        `resume_window_seconds`). O que não for retomado e tiver deixado a entrada
        mutada é desmutado. Retorna quantas foram retomadas."""
        runs, self._prior_runs = self._prior_runs, {}
        window = int(self._config.get_global().get("resume_window_seconds", 180) or 0)
        now = time.time()
        resumed = 0
        for seq_id, entry in runs.items():
            seq = self._config.get_sequence_by_id(seq_id)
            name = entry.get("name", seq_id)
            down = max(0.0, now - float(entry.get("last_seen", 0)))
            step_no = int(entry.get("step", -1)) + 1
            where = f"etapa {step_no}" if step_no > 0 else "atraso inicial"
            why = None
            if seq is None or not seq.get("enabled", True):
                why = "a sequência não existe mais ou está desativada"
            elif window <= 0:
                why = "a retomada está desligada em Configurações Globais"
            elif down > window:
                why = (f"o app ficou fora por {fmt_secs(int(down))}, mais que o limite de "
                       f"{fmt_secs(window)}")
            elif int(entry.get("resumes", 0)) >= 2:
                why = "ela já foi retomada 2 vezes e o app caiu de novo"
            if why:
                self._log_fn(f"⚠ '{name}' estava em execução ({where}) quando o app caiu, "
                             f"mas NÃO foi retomada: {why}.", "warn")
                continue
            self._log_fn(f"♻ Retomando '{name}' ({where}): o app ficou fora por "
                         f"{fmt_secs(int(down))}.", "warn")
            self._streaming_seq_id = seq_id
            self.run_sequence(seq_id, resume=entry)
            resumed += 1
        if not resumed:
            restored = _audio.restore_stale_mutes()
            if restored:
                self._log_fn("🔊 Desmutado(s) o(s) dispositivo(s) que ficaram mutados quando "
                             "o app caiu: " + ", ".join(d["name"] for d in restored), "warn")
        return resumed

    def get_runner(self, seq_id: str) -> Optional[SequenceRunner]:
        return self._runners.get(seq_id)

    def is_seq_armed_today(self, seq: dict) -> bool:
        """True se a sequência (habilitada, com keyword) está armada hoje."""
        if not (seq.get("enabled", True) and seq.get("keyword_trigger", "").strip()):
            return False
        return is_armed_today(seq)
