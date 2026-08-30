"""
Gerenciamento de configuração persistente em JSON — Schema v2.

Schema v2:
{
  "version": 2,
  "global": { "txt_file_path", "default_input_device_id", "default_input_device_name",
              "default_output_device_id", "default_output_device_name" },
  "sequences": [ { "id", "name", "keyword_trigger", "enabled", "steps": [...] } ]
}

Migração automática de v1 (keys planas) → v2 na primeira carga.
"""
import json
import os
import sys
import uuid


def _resolve_config_file() -> str:
    """
    Determina onde ler/gravar config.json de forma que persista.

    - Frozen (.exe onefile): grava ao lado do executável (pasta de instalação,
      onde o installer já coloca config.json e onde o app — rodando como admin —
      pode escrever). Se não for gravável, cai para %APPDATA%\\AutoTriggerV10.
    - Dev: ao lado deste arquivo.
    """
    if getattr(sys, "frozen", False):
        # Sempre em %APPDATA% (gravável sem admin, sem divergência entre execuções
        # normais e elevadas). Semeia a partir do config instalado/bundled na 1ª vez.
        exe_dir = os.path.dirname(sys.executable)
        appdata = os.environ.get("APPDATA") or exe_dir
        data_dir = os.path.join(appdata, "AutoTriggerV10")
        try:
            os.makedirs(data_dir, exist_ok=True)
        except OSError:
            return os.path.join(exe_dir, "config.json")
        target = os.path.join(data_dir, "config.json")
        if not os.path.exists(target):
            for src in (os.path.join(exe_dir, "config.json"),
                        os.path.join(getattr(sys, "_MEIPASS", exe_dir), "config.json")):
                if os.path.exists(src):
                    try:
                        import shutil
                        shutil.copy2(src, target)
                    except Exception:
                        pass
                    break
        return target

    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, "config.json")


def _is_dir_writable(path: str) -> bool:
    test = os.path.join(path, ".write_test.tmp")
    try:
        with open(test, "w") as f:
            f.write("")
        os.remove(test)
        return True
    except Exception:
        return False


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = _resolve_config_file()

DEFAULT_EMAIL = {
    "enabled": False,
    "smtp_host": "",
    "smtp_port": 587,
    "use_tls": True,
    "username": "",
    "password": "",
    "from_addr": "",
    "to_addrs": "",
    "events": {
        "start": True,
        "done": True,
        "error": True,
        "stream_reconnect": True,
    },
}

DEFAULT_GLOBAL = {
    "txt_file_path": "",
    "default_input_device_id": "",
    "default_input_device_name": "",
    "default_output_device_id": "",
    "default_output_device_name": "",
    "email": dict(DEFAULT_EMAIL),
}


def _new_id() -> str:
    return str(uuid.uuid4())[:8]


def _migrate_v1(old: dict) -> dict:
    """Converte config v1 (keys planas) → schema v2."""
    g = {
        "txt_file_path": old.get("txt_file_path", ""),
        "default_input_device_id": old.get("input_device_id", ""),
        "default_input_device_name": old.get("input_device_name", ""),
        "default_output_device_id": old.get("output_device_id", ""),
        "default_output_device_name": old.get("output_device_name", ""),
    }

    steps = []
    in_id = g["default_input_device_id"]
    in_name = g["default_input_device_name"]

    if in_id:
        steps.append({"type": "mute", "device_id": in_id,
                      "device_name": in_name, "label": "Mute Entrada"})
    if old.get("hotkey_stop"):
        steps.append({"type": "hotkey", "hotkey": old["hotkey_stop"], "label": "STOP"})
    if old.get("audio_file_1"):
        steps.append({"type": "play_audio", "file": old["audio_file_1"], "label": "Vinheta Entrada"})
    if old.get("stream_url"):
        steps.append({"type": "stream", "url": old["stream_url"],
                      "duration_seconds": old.get("stream_duration", 300), "label": "Streaming"})
    if old.get("audio_file_2"):
        steps.append({"type": "play_audio", "file": old["audio_file_2"], "label": "Vinheta Saída"})
    if old.get("hotkey_play"):
        steps.append({"type": "hotkey", "hotkey": old["hotkey_play"], "label": "PLAY"})
    if old.get("keyword_unmute"):
        steps.append({"type": "wait_keyword", "keyword": old["keyword_unmute"],
                      "label": f"Aguardar {old['keyword_unmute']}"})
    if old.get("hotkey_stop"):
        steps.append({"type": "hotkey", "hotkey": old["hotkey_stop"], "label": "STOP Retorno"})
    if in_id:
        steps.append({"type": "unmute", "device_id": in_id,
                      "device_name": in_name, "label": "Unmute Entrada"})

    return {
        "version": 2,
        "global": g,
        "sequences": [{
            "id": _new_id(),
            "name": "Jornada Esportiva",
            "keyword_trigger": old.get("keyword_start", "ESPORTE"),
            "enabled": True,
            "steps": steps,
        }],
    }


class Config:
    def __init__(self):
        self._data: dict = {
            "version": 2,
            "global": dict(DEFAULT_GLOBAL),
            "sequences": [],
        }
        self.load()

    def load(self):
        loaded = self._read_file(CONFIG_FILE)
        if loaded is None:
            # Tenta o backup se o principal corrompeu/sumiu
            loaded = self._read_file(CONFIG_FILE + ".bak")
            if loaded is not None:
                print("[Config] Recuperado do backup config.json.bak.")
        if loaded is None:
            return
        if loaded.get("version", 1) < 2:
            loaded = _migrate_v1(loaded)
            self._data = loaded
            self._ensure_global_defaults()
            print("[Config] Migrado de v1 → v2.")
            try:
                self.save()
            except Exception:
                pass
            return
        self._data = loaded
        self._ensure_global_defaults()

    def _ensure_global_defaults(self):
        """Preenche chaves de 'global' ausentes (ex.: bloco 'email' em configs
        gravadas antes desta versão), sem sobrescrever valores existentes."""
        g = self._data.setdefault("global", {})
        for key, default in DEFAULT_GLOBAL.items():
            if key not in g:
                g[key] = dict(default) if isinstance(default, dict) else default
        # Garante subchaves do email (ex.: 'events') em configs parciais.
        email = g.setdefault("email", dict(DEFAULT_EMAIL))
        for key, default in DEFAULT_EMAIL.items():
            if key not in email:
                email[key] = dict(default) if isinstance(default, dict) else default
        events = email.setdefault("events", dict(DEFAULT_EMAIL["events"]))
        for key, default in DEFAULT_EMAIL["events"].items():
            events.setdefault(key, default)

    def _read_file(self, path: str):
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            print(f"[Config] Erro ao ler '{path}': {exc}")
            return None

    def save(self):
        """Escrita atômica: grava .tmp, faz backup .bak e troca por os.replace."""
        tmp = CONFIG_FILE + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            if os.path.exists(CONFIG_FILE):
                try:
                    import shutil
                    shutil.copy2(CONFIG_FILE, CONFIG_FILE + ".bak")
                except Exception:
                    pass
            os.replace(tmp, CONFIG_FILE)
        except Exception as exc:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
            raise RuntimeError(f"Erro ao salvar configuração: {exc}") from exc

    # ── global ───────────────────────────────────────────────────────────────

    def get_global(self) -> dict:
        return self._data.get("global", {})

    def update_global(self, d: dict):
        self._data.setdefault("global", {}).update(d)

    # ── compat v1 API ────────────────────────────────────────────────────────

    def get(self, key: str, default=None):
        return self._data.get("global", {}).get(key, default)

    def set(self, key: str, value):
        self._data.setdefault("global", {})[key] = value

    def update(self, d: dict):
        self._data.setdefault("global", {}).update(d)

    # ── sequences ────────────────────────────────────────────────────────────

    def get_sequences(self) -> list:
        return self._data.get("sequences", [])

    def get_sequence_by_id(self, seq_id: str) -> dict | None:
        for s in self.get_sequences():
            if s["id"] == seq_id:
                return s
        return None

    def add_sequence(self, seq: dict) -> dict:
        if "id" not in seq:
            seq["id"] = _new_id()
        self._data.setdefault("sequences", []).append(seq)
        return seq

    def update_sequence(self, seq: dict):
        seqs = self._data.setdefault("sequences", [])
        for i, s in enumerate(seqs):
            if s["id"] == seq["id"]:
                seqs[i] = seq
                return
        seqs.append(seq)

    def delete_sequence(self, seq_id: str):
        self._data["sequences"] = [
            s for s in self._data.get("sequences", []) if s["id"] != seq_id
        ]

    def new_sequence_template(self) -> dict:
        return {
            "id": _new_id(),
            "name": "Nova Sequência",
            "keyword_trigger": "",
            "enabled": True,
            "trigger_delay_seconds": 0,
            "schedule": {"mode": "always", "weekdays": [], "dates": []},
            "steps": [],
        }
