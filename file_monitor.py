"""
Monitores de disparo (gatilhos) do AutoTrigger.

Duas origens, ambas casando o texto contra as keywords registradas
("keyword contida no texto", sem diferenciar maiúsculas):

  - "txt":      um arquivo TXT monitorado (conteúdo inteiro, só dispara quando
                o conteúdo MUDA).
  - "medialog": uma pasta onde o V10 Player Network cria, para cada áudio que
                entra em execução, um XML temporário (~2 s de vida). Cada XML
                é um evento: o texto casado é o NOME DO ARQUIVO de áudio.

v2: register/unregister de keywords em tempo de execução, por origem.
"""
import ntpath
import os
import re
import threading
import time
import xml.etree.ElementTree as ET

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

SOURCE_TXT = "txt"
SOURCE_MEDIALOG = "medialog"


class _Router:
    """Mapas keyword -> callback por origem + despacho do texto recebido."""

    def __init__(self, log):
        self._log = log
        self._lock = threading.Lock()
        self._maps = {SOURCE_TXT: {}, SOURCE_MEDIALOG: {}}

    def add(self, keyword: str, callback, source: str):
        with self._lock:
            self._maps[source][keyword.strip().upper()] = callback

    def remove(self, keyword: str, source: str | None = None):
        kw = keyword.strip().upper()
        with self._lock:
            for src, m in self._maps.items():
                if source is None or src == source:
                    m.pop(kw, None)

    def clear(self):
        with self._lock:
            for m in self._maps.values():
                m.clear()

    def dispatch(self, source: str, content_upper: str, ctx: dict | None = None):
        """Chama os callbacks casados. Na origem "medialog" o callback recebe
        `ctx` (dados do áudio: nome, remaining_s...); na "txt", nenhum argumento."""
        with self._lock:
            matched = [
                (kw, cb) for kw, cb in self._maps[source].items()
                if kw and kw in content_upper
            ]
        for kw, cb in matched:
            self._log(f"▶ Keyword: '{kw}'")
            args = (ctx or {},) if source == SOURCE_MEDIALOG else ()
            threading.Thread(target=cb, args=args, daemon=True, name=f"kw-{kw[:8]}").start()


# ── origem TXT ────────────────────────────────────────────────────────────────

class _TxtHandler(FileSystemEventHandler):
    def __init__(self, filepath: str, log, router: _Router):
        super().__init__()
        self._filepath = os.path.abspath(filepath)
        self._log = log
        self._router = router
        self._last_content = ""
        self._file_lock = threading.Lock()

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
            self._router.dispatch(SOURCE_TXT, content)


# ── origem log do player (XMLs temporários) ───────────────────────────────────

def _decode(data: bytes) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")  # nomes com acento


_XML_DECL = re.compile(r"^\s*<\?xml[^>]*\?>", re.I)


def _cdata_field(text: str, tag: str) -> str:
    m = re.search(
        rf"<{tag}>\s*(?:<!\[CDATA\[(.*?)\]\]>|([^<]*))\s*</{tag}>", text, re.S)
    return ((m.group(1) if m and m.group(1) is not None else (m.group(2) if m else "")) or "").strip()


def parse_medialog_xml(data: bytes) -> dict | None:
    """Extrai {kind, name, path, played_ms, total_ms} de um XML do player.

    Retorna None se o XML ainda está incompleto (arquivo sendo gravado).
    O nome vem do CAMINHO (txt_path_med): é o único campo confiável --
    txt_nome_med às vezes vem sem extensão ou com ponto sobrando ("SPOT-L21.").
    """
    text = _XML_DECL.sub("", _decode(data)).strip()
    if not text:
        return None
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return None  # incompleto -- quem chamou tenta de novo
    path = _cdata_field(text, "txt_path_med")
    name = ntpath.basename(path) or _cdata_field(text, "txt_nome_med")

    def _ms(tag):
        try:
            return int(float(_cdata_field(text, tag)))
        except ValueError:
            return 0

    return {"kind": root.tag, "name": name, "path": path,
            "played_ms": _ms("flt_tempo_exec_med"), "total_ms": _ms("flt_tempo_med")}


class MediaLogWatcher:
    """Vigia a pasta de XMLs do player e despacha o nome do áudio de cada um.

    Os arquivos vivem ~2 s, então: watchdog (instantâneo) + varredura a cada
    0.4 s como rede de segurança. Cada arquivo é processado UMA vez (por
    caminho), mesmo que chegue por created + modified + varredura. XMLs que já
    estavam na pasta ao iniciar são ignorados.
    """

    def __init__(self, folder: str, router: _Router, log, poll_interval: float = 0.4):
        self._folder = os.path.abspath(folder)
        self._router = router
        self._log = log
        self._poll = poll_interval
        self._seen: dict = {}
        self._seen_lock = threading.Lock()
        self._stop = threading.Event()
        self._observer: Observer | None = None
        self._poll_thread: threading.Thread | None = None

    def start(self):
        for e in self._scan():
            self._seen[e] = time.time()
        watcher = self

        class _H(FileSystemEventHandler):
            def on_created(self, event):
                if not event.is_directory:
                    watcher._consider(event.src_path)

            def on_modified(self, event):
                if not event.is_directory:
                    watcher._consider(event.src_path)

            def on_moved(self, event):
                if not event.is_directory:
                    watcher._consider(event.dest_path)

        self._observer = Observer()
        self._observer.schedule(_H(), self._folder, recursive=False)
        self._observer.start()
        self._poll_thread = threading.Thread(
            target=self._poll_loop, daemon=True, name="medialog-poll")
        self._poll_thread.start()

    def stop(self):
        self._stop.set()
        if self._observer and self._observer.is_alive():
            self._observer.stop()
            self._observer.join(timeout=3)
        self._observer = None

    def is_running(self) -> bool:
        return (self._observer is not None and self._observer.is_alive()
                and not self._stop.is_set())

    def _scan(self) -> list:
        try:
            return [e.path for e in os.scandir(self._folder)
                    if e.is_file() and e.name.lower().endswith(".xml")]
        except OSError:
            return []

    def _poll_loop(self):
        while not self._stop.wait(self._poll):
            for p in self._scan():
                self._consider(p)
            cutoff = time.time() - 120
            with self._seen_lock:
                for p in [p for p, t in self._seen.items() if t < cutoff]:
                    del self._seen[p]

    def _consider(self, path: str):
        if not path.lower().endswith(".xml"):
            return
        with self._seen_lock:
            if path in self._seen:
                return
            self._seen[path] = time.time()
        threading.Thread(target=self._process, args=(path, time.time()), daemon=True,
                         name="medialog-read").start()

    def _process(self, path: str, seen_at: float):
        info = None
        for _ in range(40):  # até ~2 s: o arquivo pode estar sendo gravado
            if self._stop.is_set():
                return
            try:
                with open(path, "rb") as f:
                    data = f.read()
            except FileNotFoundError:
                self._log(f"Log do player: {os.path.basename(path)} sumiu antes de "
                          f"ser lido.", "warn")
                return
            except OSError:
                data = b""
            info = parse_medialog_xml(data)
            if info:
                break
            time.sleep(0.05)
        if not info or not info["name"]:
            self._log(f"Log do player: não consegui ler o nome do áudio em "
                      f"{os.path.basename(path)}.", "warn")
            return
        played, total = info["played_ms"] / 1000, info["total_ms"] / 1000
        # Quanto falta pro áudio acabar: total - já tocado (no instante da
        # gravação do XML) - o tempo que levamos pra ler o arquivo.
        info["remaining_s"] = max(0.0, total - played - (time.time() - seen_at))
        self._log(f"🎵 Player: {info['name']} ({info['kind']}, "
                  f"{played:.1f}s de {total:.1f}s, faltam {info['remaining_s']:.1f}s)")
        self._router.dispatch(SOURCE_MEDIALOG, info["name"].upper(), info)


# ── fachada usada pelo engine ─────────────────────────────────────────────────

class FileMonitor:
    def __init__(self):
        self._observer: Observer | None = None
        self._medialog: MediaLogWatcher | None = None
        self._log = lambda msg, _l="info": print(f"[Monitor] {msg}")
        self._router = _Router(lambda m, l="info": self._log(m, l))

    def start(self, filepath: str = "", log_callback=None,
              medialog_folder: str | None = None) -> bool:
        """Inicia o monitoramento do TXT e/ou da pasta de log do player.

        Retorna True se PELO MENOS UMA origem iniciou.
        """
        self.stop()
        if log_callback:
            self._log = log_callback
        started = False

        if filepath:
            if os.path.isfile(filepath):
                folder = os.path.dirname(os.path.abspath(filepath))
                handler = _TxtHandler(filepath, self._log, self._router)
                self._observer = Observer()
                self._observer.schedule(handler, folder, recursive=False)
                self._observer.start()
                started = True
            else:
                self._log(f"Arquivo não encontrado: '{filepath}'", "error")

        if medialog_folder:
            if os.path.isdir(medialog_folder):
                self._medialog = MediaLogWatcher(medialog_folder, self._router, self._log)
                self._medialog.start()
                started = True
            else:
                self._log(f"Pasta do log do player não encontrada: '{medialog_folder}'",
                          "error")
        return started

    def register_keyword(self, keyword: str, callback, source: str = SOURCE_TXT):
        self._router.add(keyword, callback, source)

    def unregister_keyword(self, keyword: str, source: str | None = None):
        self._router.remove(keyword, source)

    def stop(self):
        if self._observer and self._observer.is_alive():
            self._observer.stop()
            self._observer.join(timeout=3)
        self._observer = None
        if self._medialog:
            self._medialog.stop()
        self._medialog = None
        self._router.clear()

    def is_running(self) -> bool:
        return ((self._observer is not None and self._observer.is_alive())
                or self.is_medialog_running())

    def is_medialog_running(self) -> bool:
        return self._medialog is not None and self._medialog.is_running()
