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
        extra_delay_seconds: float = 0.0,
        resume: Optional[dict] = None,
        progress_callback: Optional[Callable] = None,
        keyword_check: Optional[Callable] = None,
    ):
        # resume: entrada do diário (run_journal) de uma execução interrompida por
        # queda -- retoma na etapa em que parou. progress_callback(kind, idx, step,
        # end_epoch) alimenta o diário. keyword_check(kw) -> bool diz se a palavra
        # já está no TXT (para não esperar por algo que apareceu com o app fora).
        self._resume = resume
        self._progress = progress_callback
        self._keyword_check = keyword_check
        # Atraso somado ao `trigger_delay_seconds` da sequência (ex.: tempo que
        # falta pro áudio do player terminar -- ver SequenceEngine._on_trigger).
        self._extra_delay = max(0.0, float(extra_delay_seconds))
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

    def _report(self, kind: str, idx: int, step, end_epoch):
        if self._progress and not self._dry_run:
            try:
                self._progress(kind, idx, step, end_epoch)
            except Exception:
                pass

    def _adjust_resumed_step(self, step: dict, i: int, n: int):
        """Etapa em que o app caiu -> o que fazer ao retomar. None = pular."""
        t = step.get("type", "")
        label = step.get("label") or t
        end = (self._resume or {}).get("phase_end")
        rem = (float(end) - time.time()) if end else None
        if t == "stream":
            if rem is None or rem < 5:
                self._log(f"⏭ [{i + 1}/{n}] {label}: o stream já estaria terminando — seguindo.", "warn")
                return None
            self._log(f"🔁 [{i + 1}/{n}] {label}: retomando o stream por mais "
                      f"{fmt_secs(int(rem))}.", "warn")
            return {**step, "duration_seconds": int(rem), "label": f"{label} (retomado)"}
        if t == "wait_time":
            if rem is None or rem <= 0:
                self._log(f"⏭ [{i + 1}/{n}] {label}: a espera já teria acabado — seguindo.", "warn")
                return None
            self._log(f"🔁 [{i + 1}/{n}] {label}: retomando a espera por mais "
                      f"{fmt_secs(int(rem))}.", "warn")
            return {**step, "seconds": rem, "label": f"{label} (retomado)"}
        if t == "play_audio":
            self._log(f"⏭ [{i + 1}/{n}] {label}: o áudio interrompido não é repetido — seguindo.", "warn")
            return None
        if t == "wait_keyword":
            kw = step.get("keyword", "")
            if kw and self._keyword_check and self._keyword_check(kw):
                self._log(f"⏭ [{i + 1}/{n}] {label}: '{kw}' já está no TXT (apareceu com o "
                          f"app fora) — seguindo.", "warn")
                return None
            self._log(f"🔁 [{i + 1}/{n}] {label}: voltando a aguardar '{kw}'.", "warn")
            return step
        self._log(f"🔁 [{i + 1}/{n}] {label}: repetindo a etapa interrompida.", "warn")
        return step

    def _run(self):
        resume = self._resume
        resume_step = int(resume.get("step", 0)) if resume else 0
        in_delay = bool(resume) and resume.get("phase") == "delay"
        self._notify(RunnerState.RUNNING, -1 if (not resume or in_delay) else max(resume_step, 0))
        steps = self._seq.get("steps", [])
        n = len(steps)
        name = self._seq.get("name", self.seq_id)
        if self._dry_run:
            self._log(f"🧪 ENSAIO de '{name}' — nada será mutado/disparado de verdade.", "warn")

        # ── Atraso após o gatilho (delay) ──────────────────────────────────────
        delay = float(int(self._seq.get("trigger_delay_seconds", 0) or 0)) + self._extra_delay
        if resume:
            # Retomada: só o que faltava do atraso (se a queda foi nele); nada se
            # a queda foi depois dele.
            end_d = resume.get("phase_end")
            delay = max(0.0, float(end_d) - time.time()) if (in_delay and end_d) else 0.0
        if self._dry_run:
            delay = min(delay, 3.0)
        self._report("delay", -1, None, (time.time() + delay) if delay > 0 else None)
        if delay > 0:
            self._log(f"⏳ Aguardando {fmt_secs(int(round(delay)))} antes de iniciar…", "info")
            # Relógio monotônico + sono curto: termina no instante certo (o
            # antigo sleep(1.0) errava até 1 s -- crítico quando o atraso é
            # "até o áudio acabar"). O tick da UI continua a cada 1 s.
            t0 = time.monotonic()
            next_tick = 1.0
            while not self._stop_event.is_set():
                elapsed = time.monotonic() - t0
                if elapsed >= delay:
                    break
                if elapsed >= next_tick:
                    next_tick += 1.0
                    if self._on_tick:
                        try:
                            self._on_tick(-1, min(elapsed, delay), delay)
                        except Exception:
                            pass
                time.sleep(min(0.1, max(0.0, delay - elapsed)))
            if self._stop_event.is_set():
                self._log(f"⏹ Sequência '{name}' cancelada no atraso.", "warn")
                self._notify(RunnerState.CANCELLED, -1)
                return

        resume_pending = bool(resume) and not in_delay
        for i, step in enumerate(steps):
            if resume_pending and i < resume_step:
                continue
            if self._stop_event.is_set():
                self._notify(RunnerState.CANCELLED, i)
                return

            if resume_pending and i == resume_step:
                resume_pending = False
                step = self._adjust_resumed_step(step, i, n)
                if step is None:
                    continue

            self._notify(RunnerState.RUNNING, i)
            label = step.get("label") or step.get("type", "?")
            self._log(f"▶ [{i + 1}/{n}] {label}", "info")
            now = time.time()
            end_at = None
            if step.get("type") == "stream":
                end_at = now + int(step.get("duration_seconds", 300))
            elif step.get("type") == "wait_time":
                end_at = now + float(step.get("seconds", 0))
            self._report("step", i, step, end_at)

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
