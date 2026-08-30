"""
Motor de sequências — gerencia múltiplas sequências em paralelo.

- Registra triggers de keyword no FileMonitor para cada sequência habilitada
- Instancia SequenceRunner quando keyword é detectada
- Expõe callbacks de estado/tick para a UI
"""
import threading
from datetime import datetime
from typing import Callable, Dict, Optional

import emailer
from step_runner import StepRunner
from sequence_runner import SequenceRunner, RunnerState
from file_monitor import FileMonitor
from timeparse import is_armed_today


class SequenceEngine:
    def __init__(self, config, player, file_monitor: FileMonitor):
        self._config = config
        self._file_monitor = file_monitor
        self._step_runner = StepRunner(player)
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

    # ── monitor control ───────────────────────────────────────────────────────

    def start_monitor(self) -> bool:
        txt = self._config.get_global().get("txt_file_path", "")
        if not txt:
            self._log_fn("Caminho do arquivo TXT não configurado.", "error")
            return False
        ok = self._file_monitor.start(txt, log_callback=self._log_fn)
        if ok:
            self._register_all_triggers()
        return ok

    def stop_monitor(self):
        self._file_monitor.stop()

    def is_monitor_running(self) -> bool:
        return self._file_monitor.is_running()

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

    def _register_trigger(self, seq: dict):
        kw = seq["keyword_trigger"].strip()
        sid = seq["id"]
        self._file_monitor.register_keyword(
            kw, lambda _sid=sid: self._on_trigger(_sid)
        )

    # ── execution ─────────────────────────────────────────────────────────────

    def _on_trigger(self, seq_id: str):
        self.run_sequence(seq_id)

    def run_sequence(self, seq_id: str, dry_run: bool = False, manual: bool = False):
        """Inicia uma sequência. manual=True ignora o gatilho do TXT (botão Rodar)."""
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

        runner = SequenceRunner(seq, self._step_runner, self._log_fn, dry_run=dry_run)
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
                self._file_monitor.unregister_keyword(kw)

            self._file_monitor.register_keyword(kw, _fire)
            return ev

        return _waiter

    def _on_state(self, seq_id: str, state: RunnerState, step_idx: int):
        self._maybe_email_state(seq_id, state, step_idx)
        if self._on_runner_update:
            self._on_runner_update(seq_id, state.value, step_idx)

    # ── alertas por email ──────────────────────────────────────────────────────

    def _email_cfg(self) -> dict:
        return self._config.get_global().get("email", {}) or {}

    def _seq_name(self, seq_id: str) -> str:
        seq = self._config.get_sequence_by_id(seq_id)
        return seq.get("name", seq_id) if seq else seq_id

    def _maybe_email_state(self, seq_id: str, state: RunnerState, step_idx: int):
        """Dispara emails de início/fim/erro conforme a config. Ignora ensaios."""
        runner = self._runners.get(seq_id)
        if runner is not None and runner.is_dry_run:
            return

        # Rastreia a sequência atualmente em execução p/ contextualizar o stream.
        if state == RunnerState.RUNNING and step_idx == -1:
            self._streaming_seq_id = seq_id
        elif state in (RunnerState.DONE, RunnerState.ERROR, RunnerState.CANCELLED):
            if self._streaming_seq_id == seq_id:
                self._streaming_seq_id = None

        cfg = self._email_cfg()
        if not (cfg.get("enabled") and emailer.is_configured(cfg)):
            return
        events = cfg.get("events", {})

        name = self._seq_name(seq_id)
        ts = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

        if state == RunnerState.RUNNING and step_idx == -1 and events.get("start"):
            self._send_email(cfg, f"▶ Disparo iniciado: {name}",
                             f"A sequência '{name}' iniciou em {ts}.")
        elif state == RunnerState.DONE and events.get("done"):
            self._send_email(cfg, f"✅ Disparo concluído: {name}",
                             f"A sequência '{name}' foi concluída em {ts}.")
        elif state in (RunnerState.ERROR, RunnerState.CANCELLED) and events.get("error"):
            motivo = "falhou" if state == RunnerState.ERROR else "foi cancelada"
            self._send_email(cfg, f"⚠ Disparo {motivo}: {name}",
                             f"A sequência '{name}' {motivo} em {ts} "
                             f"(etapa {step_idx + 1}).")

    def _on_stream_event(self, kind: str, detail: str):
        """Handler do watchdog do player (queda/reconexão de stream)."""
        name = self._seq_name(self._streaming_seq_id) if self._streaming_seq_id else "Stream"
        ts = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        cfg = self._email_cfg()
        if not (cfg.get("enabled") and emailer.is_configured(cfg)):
            return
        if not cfg.get("events", {}).get("stream_reconnect"):
            return
        if kind == "dropped":
            self._send_email(cfg, f"⚠ Stream caiu: {name}",
                             f"O stream da sequência '{name}' caiu em {ts} ({detail}). "
                             f"O app está tentando reconectar automaticamente.")
        elif kind == "recovered":
            self._send_email(cfg, f"✓ Stream reconectado: {name}",
                             f"O stream da sequência '{name}' foi reconectado em {ts} ({detail}).")

    def _send_email(self, cfg: dict, subject: str, body: str):
        emailer.notify_async(cfg, subject, body, log=self._log_fn)

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

    def get_runner(self, seq_id: str) -> Optional[SequenceRunner]:
        return self._runners.get(seq_id)

    def is_seq_armed_today(self, seq: dict) -> bool:
        """True se a sequência (habilitada, com keyword) está armada hoje."""
        if not (seq.get("enabled", True) and seq.get("keyword_trigger", "").strip()):
            return False
        return is_armed_today(seq)
