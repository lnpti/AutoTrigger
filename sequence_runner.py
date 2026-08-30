"""
Executa uma sequência de etapas em thread dedicada.

Estados:
  IDLE → RUNNING → DONE | ERROR | CANCELLED
"""
import threading
import time
from enum import Enum
from typing import Callable, Optional

from step_runner import StepRunner
from timeparse import fmt_secs


class RunnerState(Enum):
    IDLE = "idle"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"
    CANCELLED = "cancelled"


class SequenceRunner:
    def __init__(
        self,
        seq_dict: dict,
        step_runner: StepRunner,
        log_callback: Optional[Callable] = None,
        dry_run: bool = False,
    ):
        self._seq = seq_dict
        self._step_runner = step_runner
        self._log = log_callback or (lambda msg, level="info": print(f"[Runner] {msg}"))
        self._dry_run = dry_run
        self._state = RunnerState.IDLE
        self._current_step = -1
        self._stop_event = threading.Event()

        # Callbacks
        self._on_state_change: Optional[Callable] = None  # (RunnerState, step_idx: int)
        self._on_tick: Optional[Callable] = None           # (step_idx, elapsed, total)
        self._keyword_waiter: Optional[Callable] = None    # (keyword) -> threading.Event

    # ── properties ───────────────────────────────────────────────────────────

    @property
    def state(self) -> RunnerState:
        return self._state

    @property
    def seq_id(self) -> str:
        return self._seq["id"]

    @property
    def current_step(self) -> int:
        return self._current_step

    @property
    def is_dry_run(self) -> bool:
        return self._dry_run

    # ── configuration ─────────────────────────────────────────────────────────

    def set_callbacks(
        self,
        on_state_change: Optional[Callable] = None,
        on_tick: Optional[Callable] = None,
    ):
        self._on_state_change = on_state_change
        self._on_tick = on_tick

    def set_keyword_waiter(self, fn: Callable):
        self._keyword_waiter = fn

    # ── control ───────────────────────────────────────────────────────────────

    def start(self):
        if self._state == RunnerState.RUNNING:
            return
        self._stop_event.clear()
        self._state = RunnerState.IDLE
        threading.Thread(
            target=self._run,
            daemon=True,
            name=f"seq-{self.seq_id}",
        ).start()

    def cancel(self):
        self._stop_event.set()

    # ── internals ─────────────────────────────────────────────────────────────

    def _notify(self, state: RunnerState, step: int):
        self._state = state
        self._current_step = step
        if self._on_state_change:
            try:
                self._on_state_change(state, step)
            except Exception:
                pass

    def _run(self):
        self._notify(RunnerState.RUNNING, -1)
        steps = self._seq.get("steps", [])
        n = len(steps)
        name = self._seq.get("name", self.seq_id)
        if self._dry_run:
            self._log(f"🧪 ENSAIO de '{name}' — nada será mutado/disparado de verdade.", "warn")

        # ── Atraso após o gatilho (delay) ──────────────────────────────────────
        delay = int(self._seq.get("trigger_delay_seconds", 0) or 0)
        if self._dry_run:
            delay = min(delay, 3)
        if delay > 0:
            self._log(f"⏳ Aguardando {fmt_secs(delay)} antes de iniciar…", "info")
            elapsed = 0.0
            while elapsed < delay and not self._stop_event.is_set():
                time.sleep(1.0)
                elapsed += 1.0
                if self._on_tick:
                    try:
                        self._on_tick(-1, elapsed, float(delay))
                    except Exception:
                        pass
            if self._stop_event.is_set():
                self._log(f"⏹ Sequência '{name}' cancelada no atraso.", "warn")
                self._notify(RunnerState.CANCELLED, -1)
                return

        for i, step in enumerate(steps):
            if self._stop_event.is_set():
                self._notify(RunnerState.CANCELLED, i)
                return

            self._notify(RunnerState.RUNNING, i)
            label = step.get("label") or step.get("type", "?")
            self._log(f"▶ [{i + 1}/{n}] {label}", "info")

            def _tick(elapsed, total, _i=i):
                if self._on_tick:
                    self._on_tick(_i, elapsed, total)

            ok = self._step_runner.run_step(
                step,
                self._stop_event,
                on_tick=_tick,
                keyword_waiter=self._keyword_waiter,
                dry_run=self._dry_run,
                preview_cap=8 if self._dry_run else 0,
            )

            if not ok:
                if self._stop_event.is_set():
                    self._log(f"⏹ Sequência '{name}' cancelada.", "warn")
                    self._notify(RunnerState.CANCELLED, i)
                else:
                    self._log(f"✗ Etapa [{i + 1}] falhou: {label}", "error")
                    self._notify(RunnerState.ERROR, i)
                return

            self._log(f"✓ [{i + 1}/{n}] {label}", "success")

        self._notify(RunnerState.DONE, n)
        self._log(f"✅ Sequência '{name}' concluída.", "success")
