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
import copy
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

DEFAULT_TELEGRAM = {
    "enabled": False,
    "bot_token": "",
    # Vários contatos com o mesmo bot: [{"name": str, "chat_id": str, "enabled": bool}]
    "contacts": [],
    "events": {
        "start": True,
        "done": True,
        "error": True,
        "stream_reconnect": True,
    },
}

DEFAULT_MEDIALOG = {
    "enabled": False,
    # Pasta onde o V10 Player Network cria um XML temporário por áudio executado.
    "folder": r"C:\KL AV Systems\V10 Player Network\V10MediaLog",
}

DEFAULT_GLOBAL = {
    "start_minimized": False,   # abre direto na bandeja, sem mostrar a janela
    "txt_file_path": "",
    "default_input_device_id": "",
    "default_input_device_name": "",
    "default_output_device_id": "",
    "default_output_device_name": "",
    "email": copy.deepcopy(DEFAULT_EMAIL),
    "telegram": copy.deepcopy(DEFAULT_TELEGRAM),
    "medialog": copy.deepcopy(DEFAULT_MEDIALOG),
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
            "global": copy.deepcopy(DEFAULT_GLOBAL),
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
                g[key] = copy.deepcopy(default)
        medialog = g.setdefault("medialog", copy.deepcopy(DEFAULT_MEDIALOG))
        for key, default in DEFAULT_MEDIALOG.items():
            medialog.setdefault(key, default)
        # Migra o Telegram antigo (um único chat_id) para a lista de contatos.
        tg_old = g.get("telegram")
        if isinstance(tg_old, dict) and "chat_id" in tg_old:
            legacy = str(tg_old.pop("chat_id", "") or "").strip()
            if legacy and not tg_old.get("contacts"):
                tg_old["contacts"] = [
                    {"name": "Contato 1", "chat_id": legacy, "enabled": True}
                ]
        # Garante subchaves do email (ex.: 'events') em configs parciais.
        email = g.setdefault("email", dict(DEFAULT_EMAIL))
        for key, default in DEFAULT_EMAIL.items():
            if key not in email:
                email[key] = dict(default) if isinstance(default, dict) else default
        events = email.setdefault("events", dict(DEFAULT_EMAIL["events"]))
        for key, default in DEFAULT_EMAIL["events"].items():
            events.setdefault(key, default)
        # Garante subchaves do telegram (ex.: 'events') em configs parciais.
        telegram = g.setdefault("telegram", dict(DEFAULT_TELEGRAM))
        for key, default in DEFAULT_TELEGRAM.items():
            if key not in telegram:
                telegram[key] = copy.deepcopy(default)
        tg_events = telegram.setdefault("events", dict(DEFAULT_TELEGRAM["events"]))
        for key, default in DEFAULT_TELEGRAM["events"].items():
            tg_events.setdefault(key, default)

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

    def export_to(self, path: str, include_secrets: bool = False):
        """Grava uma cópia de TODA a configuração (global + sequências) em `path`.

        Sem `include_secrets`, a senha do e-mail e o token do bot do Telegram
        saem em branco -- o arquivo pode ser compartilhado sem vazar acesso.
        O formato é o mesmo do config.json (+ um bloco "_export" informativo).
        """
        from datetime import datetime
        try:
            from version import __version__ as app_version
        except Exception:
            app_version = ""
        data = copy.deepcopy(self._data)
        if not include_secrets:
            data.get("global", {}).get("email", {})["password"] = ""
            data.get("global", {}).get("telegram", {})["bot_token"] = ""
        data["_export"] = {
            "app_version": app_version,
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            "includes_secrets": include_secrets,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    # ── importação ───────────────────────────────────────────────────────────────

    @staticmethod
    def read_import(path: str) -> dict:
        """Lê e valida um arquivo de configuração (exportado pelo app ou um
        config.json). Retorna o dict normalizado (schema v2) SEM aplicar nada.
        Levanta ValueError com uma mensagem clara se o arquivo não servir."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except UnicodeDecodeError:
            raise ValueError("o arquivo não é um texto UTF-8 válido.")
        except json.JSONDecodeError as exc:
            raise ValueError(f"o arquivo não é um JSON válido ({exc.msg}, linha {exc.lineno}).")
        except OSError as exc:
            raise ValueError(f"não consegui abrir o arquivo ({exc.strerror or exc}).")
        if not isinstance(data, dict):
            raise ValueError("o arquivo não parece uma configuração do AutoTrigger.")
        try:
            version = int(data.get("version", 1) or 1)
        except (TypeError, ValueError):
            version = 1
        if version > 2:
            raise ValueError(f"o arquivo é de uma versão mais nova do app (schema {version}); "
                             f"atualize o AutoTrigger antes de importar.")
        if version < 2:
            data = _migrate_v1(data)
        if not isinstance(data.get("sequences"), list) or not isinstance(data.get("global", {}), dict):
            raise ValueError("o arquivo não parece uma configuração do AutoTrigger "
                             "(faltam as sequências).")
        seqs = []
        for i, sq in enumerate(data["sequences"], 1):
            if not isinstance(sq, dict):
                raise ValueError(f"a sequência nº {i} do arquivo está inválida.")
            sq = copy.deepcopy(sq)
            sq.setdefault("name", f"Sequência {i}")
            if not isinstance(sq.get("steps"), list):
                sq["steps"] = []
            if not sq.get("id"):
                sq["id"] = _new_id()
            seqs.append(sq)
        return {"global": copy.deepcopy(data.get("global", {}) or {}), "sequences": seqs,
                "includes_secrets": bool((data.get("_export") or {}).get("includes_secrets", True))}

    def import_from(self, path: str, mode: str = "replace") -> dict:
        """Aplica um arquivo de configuração e salva.

        mode="replace": troca as configurações globais e TODAS as sequências pelas
            do arquivo. Antes, grava uma cópia completa da configuração atual
            (config.antes-da-importacao-<data>.json) e mantém as 5 mais recentes.
            Senha do e-mail e token do Telegram em branco no arquivo NÃO apagam os
            atuais.
        mode="merge": só ACRESCENTA as sequências do arquivo (com ids novos), sem
            tocar nas configurações globais nem nas sequências existentes.

        Retorna {"mode", "sequences", "backup"}. Levanta ValueError se inválido.
        """
        if mode not in ("replace", "merge"):
            raise ValueError(f"modo de importação desconhecido: {mode}")
        incoming = self.read_import(path)
        backup = None
        if mode == "replace":
            backup = self._backup_before_import()
            cur_g = self._data.get("global", {})
            new_g = incoming["global"]
            for section, key in (("email", "password"), ("telegram", "bot_token")):
                sec = new_g.setdefault(section, {})
                if not isinstance(sec, dict):
                    sec = new_g[section] = {}
                if not sec.get(key):
                    sec[key] = (cur_g.get(section) or {}).get(key, "")
            self._data["global"] = new_g
            self._data["sequences"] = incoming["sequences"]
            self._ensure_global_defaults()
        else:
            existing_ids = {sq["id"] for sq in self._data.get("sequences", [])}
            existing_names = {sq.get("name", "") for sq in self._data.get("sequences", [])}
            for sq in incoming["sequences"]:
                sq["id"] = _new_id()
                while sq["id"] in existing_ids:
                    sq["id"] = _new_id()
                existing_ids.add(sq["id"])
                if sq.get("name", "") in existing_names:
                    sq["name"] = f"{sq['name']} (importada)"
                existing_names.add(sq["name"])
                self._data.setdefault("sequences", []).append(sq)
        self.save()
        return {"mode": mode, "sequences": len(incoming["sequences"]), "backup": backup}

    def _backup_before_import(self) -> str | None:
        """Cópia completa (com senhas) da configuração atual, ao lado do config."""
        from datetime import datetime
        import glob
        folder = os.path.dirname(CONFIG_FILE)
        path = os.path.join(folder, f"config.antes-da-importacao-{datetime.now():%Y%m%d-%H%M%S}.json")
        try:
            self.export_to(path, include_secrets=True)
        except OSError:
            return None
        for old in sorted(glob.glob(os.path.join(folder, "config.antes-da-importacao-*.json")))[:-5]:
            try:
                os.remove(old)
            except OSError:
                pass
        return path

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

    def reorder_sequences(self, ordered_ids: list):
        """Reordena as sequências para casar com `ordered_ids` (lista de ids).
        Ids desconhecidos são ignorados; sequências fora da lista mantêm a
        ordem relativa original, no final."""
        seqs = self._data.get("sequences", [])
        by_id = {s["id"]: s for s in seqs}
        new_order = [by_id[sid] for sid in ordered_ids if sid in by_id]
        seen = {s["id"] for s in new_order}
        new_order += [s for s in seqs if s["id"] not in seen]
        self._data["sequences"] = new_order

    def delete_sequence(self, seq_id: str):
        self._data["sequences"] = [
            s for s in self._data.get("sequences", []) if s["id"] != seq_id
        ]

    def new_sequence_template(self) -> dict:
        return {
            "id": _new_id(),
            "name": "Nova Sequência",
            "keyword_trigger": "",
            "trigger_source": "txt",  # "txt" | "medialog" | "both"
            # True: com gatilho do log do player, espera o áudio terminar e só
            # então conta o atraso fixo.
            "delay_from_audio_end": False,
            "enabled": True,
            "trigger_delay_seconds": 0,
            "schedule": {"mode": "always", "weekdays": [], "dates": []},
            "steps": [],
        }
