"""
Monitora um arquivo TXT em tempo real usando watchdog.
v2: suporta keyword_map dinâmico — register/unregister em tempo de execução.
"""
import os
import threading

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class _TxtHandler(FileSystemEventHandler):
    def __init__(self, filepath: str, log_callback):
        super().__init__()
        self._filepath = os.path.abspath(filepath)
        self._log = log_callback or (lambda msg, _l="info": print(f"[Monitor] {msg}"))
        self._last_content = ""
        self._file_lock = threading.Lock()
        self._kw_lock = threading.Lock()
        self._keyword_map: dict = {}  # keyword.upper() -> callback

    def add_keyword(self, keyword: str, callback):
        with self._kw_lock:
            self._keyword_map[keyword.strip().upper()] = callback

    def remove_keyword(self, keyword: str):
        with self._kw_lock:
            self._keyword_map.pop(keyword.strip().upper(), None)

    def on_modified(self, event):
        if event.is_directory:
            return
        if os.path.abspath(event.src_path) != self._filepath:
            return
        self._check_file()

    def on_created(self, event):
        self.on_modified(event)

    def _check_file(self):
        with self._file_lock:
            try:
                with open(self._filepath, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read().strip().upper()
            except Exception as exc:
                self._log(f"Erro ao ler TXT: {exc}")
                return

            if content == self._last_content:
                return
            self._last_content = content
            self._log(f"TXT: '{content}'")

            with self._kw_lock:
                matched = [
                    (kw, cb) for kw, cb in self._keyword_map.items()
                    if kw and kw in content
                ]

            for kw, cb in matched:
                self._log(f"▶ Keyword: '{kw}'")
                threading.Thread(target=cb, daemon=True, name=f"kw-{kw[:8]}").start()


class FileMonitor:
    def __init__(self):
        self._observer: Observer | None = None
        self._handler: _TxtHandler | None = None

    def start(self, filepath: str, log_callback=None) -> bool:
        """Inicia monitoramento. Retorna True se iniciou corretamente."""
        self.stop()
        if not filepath:
            return False
        if not os.path.isfile(filepath):
            if log_callback:
                log_callback(f"Arquivo não encontrado: '{filepath}'", "error")
            return False

        folder = os.path.dirname(os.path.abspath(filepath))
        self._handler = _TxtHandler(filepath, log_callback)
        self._observer = Observer()
        self._observer.schedule(self._handler, folder, recursive=False)
        self._observer.start()
        return True

    def register_keyword(self, keyword: str, callback):
        if self._handler:
            self._handler.add_keyword(keyword, callback)

    def unregister_keyword(self, keyword: str):
        if self._handler:
            self._handler.remove_keyword(keyword)

    def stop(self):
        if self._observer and self._observer.is_alive():
            self._observer.stop()
            self._observer.join(timeout=3)
        self._observer = None
        self._handler = None

    def is_running(self) -> bool:
        return self._observer is not None and self._observer.is_alive()

