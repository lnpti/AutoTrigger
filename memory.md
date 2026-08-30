# AutoTrigger V10 — Memória do Projeto

> **Arquivo vivo.** Atualizado a cada sessão de desenvolvimento.  
> Contém todo o histórico de decisões, tecnologias, bugs resolvidos e planos futuros.  
> Última atualização: 2026-06-07 — **v2.3.0**

> ⚠️ **Nota histórica:** o projeto nasceu como *MaisNova Sport Trigger* (v1.0, fluxo
> fixo da Jornada Esportiva). Na **v2.0** virou **AutoTrigger V10**, um motor de
> sequências genérico. Seções abaixo já refletem a arquitetura v2+.

---

## 1. Visão Geral do Produto

**Nome:** AutoTrigger V10 (antigo MaisNova Sport Trigger)  
**Plataforma:** Windows (desktop, standalone .exe)  
**Propósito:** Automação genérica de blocos de áudio/comandos disparados por
palavras-chave lidas de um arquivo TXT (caso de uso original: bloco esportivo em
rádio ao vivo).

### O Problema que Resolve
O app monitora um arquivo TXT que o software de rádio atualiza com a mídia em
exibição. Quando uma **keyword** aparece no TXT, ele dispara uma **sequência** de
etapas configuráveis. Exemplo da Jornada Esportiva:
- Mutar o microfone (para não vazar áudio da rádio esportiva parceira)
- Parar a programação local (hotkey no software de rádio)
- Tocar uma vinheta de entrada
- Ligar o stream da rádio esportiva por tempo fixo
- Tocar uma vinheta de encerramento
- Retomar a programação local (hotkey PLAY)
- Aguardar a keyword de retorno no TXT
- Parar o stream e desmutar o microfone

Tudo isso vira uma lista de etapas editável na UI — **não é mais hardcoded**.

### Contexto de Uso
- **Rádio:** MaisNova / Terra FM (97,7 MHz – região amazônica)
- **Hardware de áudio:** RODECaster Pro Stereo
  - Input device: `Microfone (RODECaster Pro Stereo)` — ID: `{0.0.1.00000000}.{2a24c533-249e-4725-8743-197ba474ac03}`
  - Output device: `Alto-falantes (RODECaster Pro Stereo)` — ID: `{0.0.0.00000000}.{26e07ddf-8bb3-415e-835b-a63ee090dfba}`
- **Stream da jornada:** `https://8033.brasilstream.com.br/stream.m3u`
- **Hotkeys configuradas:** F11 (STOP) e F9 (PLAY)
- **Arquivo TXT monitorado:** `C:/Users/User/Downloads/MidiaAtual.txt`
- **Keywords:** `ESPORTE` (início) e `FIM_ESPORTE` (retorno)

---

## 2. Stack Tecnológica

| Biblioteca | Versão | Função |
|---|---|---|
| Python | 3.11 | Linguagem principal |
| **PySide6 (Qt 6)** | ≥ 6.6.0 | **UI (v2.2+)** — janela única, QSS, tray nativo |
| pycaw | ≥ 20230407 | Windows Core Audio API — mute/unmute |
| comtypes | ≥ 1.4.1 | COM initialization (necessário para pycaw) |
| python-vlc | ≥ 3.0.21203 | Reprodução de áudio (arquivos + streams M3U) |
| watchdog | ≥ 4.0.0 | Monitoramento em tempo real do arquivo TXT |
| keyboard | ≥ 0.13.5 | Envio e captura de hotkeys globais |
| pywin32 | ≥ 306 | Foco de janela alvo p/ hotkey (win32gui) |
| Pillow | ≥ 10.0.0 | Geração do ícone no build (create_icon.py) |
| PyInstaller | ≥ 6.0.0 | Empacotamento em .exe standalone |

> **v2.2:** UI migrada de **CustomTkinter → PySide6/Qt**. `customtkinter` e
> `pystray` foram **removidos** (tray agora é `QSystemTrayIcon`). Todo o backend
> Python permaneceu igual.

### Por que PySide6/Qt (v2.2)?
- CustomTkinter atingiu o teto visual (estilização/animação limitadas, modais
  empilhados). Qt dá QSS completo, janela única mestre-detalhe, tray nativo e é
  muito mais robusto — mantendo 100% do backend Python.
- **Ponte de threads:** `ui/qt_bridge.py` (QObject com signals) marshaliza os
  callbacks do engine (worker threads) para a GUI thread. Substitui o `after()`.

### Por que VLC (python-vlc) e não pygame/simpleaudio?
- VLC suporta nativamente M3U, HLS e streams HTTP
- Permite selecionar dispositivo de saída por ID (Windows MMDevice)
- Mais estável para streams de rádio ao vivo com buffering configurável

### Por que pycaw?
- Única biblioteca Python que acessa a API de áudio do Windows (WASAPI/MMDevice) para mutar dispositivos individuais
- Alternativas como sounddevice não permitem mute/unmute de dispositivos do sistema

---

## 3. Estrutura de Arquivos (v2.1)

```
Jornada_Maisnova/
├── main.py               # Entry point — wiring, tray, lifecycle, env do libVLC
├── version.py            # Fonte única da versão (__version__, GITHUB_REPO, ASSET)
├── config.py             # Config schema v2 (global + sequences); persistência robusta
├── config.json           # Configuração persistida (schema v2)
├── timeparse.py          # parse/format de tempo (h/m/s) + is_armed_today (agenda)
├── applog.py             # NOVO (v2.2) — logging em arquivo + UI sink + excepthooks
├── audio_manager.py      # Mute/unmute via pycaw + ledger _muted_by_app / restore_app_mutes
├── player.py             # AudioPlayer — reprodução VLC (arquivo + stream M3U)
├── file_monitor.py       # Watchdog — keyword_map dinâmico (register/unregister)
├── hotkey_sender.py      # send_hotkey + send_hotkey_to_window (pywin32) + list_window_titles
├── step_runner.py        # Executa UMA etapa (mute/hotkey/play_audio/stream/wait_*)
├── sequence_runner.py    # Executa UMA sequência em thread; aplica trigger_delay
├── sequence_engine.py    # Orquestra N sequências; arma triggers conforme agenda
├── updater.py            # Auto-update via GitHub Releases
├── requirements.txt      # Dependências pip (inclui pywin32)
├── version_info.txt      # Metadados do .exe (PyInstaller)
├── build.bat             # Compila AutoTriggerV10.exe (embute libVLC) + publica release
├── installer.iss         # Inno Setup (VLC embutido — não baixa mais)
├── memory.md             # Este arquivo
├── assets/               # icon.ico, banners do wizard
└── ui/  (PySide6/Qt — v2.2)
    ├── theme.py          # tokens de cor + folha QSS (estética broadcast console)
    ├── qt_bridge.py      # EngineBridge: signals que levam callbacks p/ a GUI thread
    ├── widgets.py        # TimeField, LogView, StatusDot, Chip, helpers
    ├── main_window.py    # QMainWindow: top bar, sidebar, stack (detalhe/global), log, tray
    ├── sequence_detail.py# Painel mestre-detalhe: edição inline + agenda + etapas + run/ensaio
    ├── step_editor.py    # Editor de UMA etapa, inline (sem pop-up)
    ├── global_settings.py# Configurações globais inline (TXT + dispositivos, com cache)
    └── update_dialog.py  # Dialog de atualização (Qt)
```
> Removidos na v2.2 (eram CustomTkinter): `journey_view.py`, `sequence_editor.py`,
> `settings_window.py`, `config_tab.py`, `log_tab.py`.

---

## 4. Arquitetura e Padrões de Design (v2)

### Motor de Sequências (substitui a máquina de estados fixa da v1)
- **`SequenceEngine`** registra, no `FileMonitor`, a `keyword_trigger` de cada
  sequência **habilitada e armada hoje** (`timeparse.is_armed_today`). Ao detectar
  a keyword, instancia um **`SequenceRunner`**.
- **`SequenceRunner`** roda a sequência em daemon thread `seq-<id>`. Antes do loop,
  aplica o **`trigger_delay_seconds`** (atraso pós-gatilho, cancelável). Para cada
  etapa chama o **`StepRunner`**.
- **`StepRunner.run_step`** executa o tipo da etapa. Tipos:
  `mute`/`unmute`/`open_channel`/`close_channel`, `hotkey`, `play_audio`,
  `stream`, `wait_time`, `wait_keyword`.
- `wait_keyword` usa um *keyword_waiter* temporário registrado no FileMonitor
  (`SequenceEngine._make_keyword_waiter`).

### Config schema v2 (`config.py`)
```
{ "version": 2,
  "global": { txt_file_path, default_input_device_*, default_output_device_* },
  "sequences": [ { id, name, keyword_trigger, enabled,
                   trigger_delay_seconds, schedule, steps:[...] } ] }
```
- Migração automática de v1 (`_migrate_v1`).
- `schedule = {"mode":"always"|"weekdays"|"dates","weekdays":[0..6],"dates":[...]}`.
- **Persistência (corrigida na v2.1):** `_resolve_config_file()` grava ao lado do
  `sys.executable` quando frozen (ou `%APPDATA%\AutoTriggerV10` como fallback), e
  ao lado do `.py` em dev.

### Áudio (`audio_manager.py`)
- `set_device_mute(id, mute)` mantém o ledger `_muted_by_app`.
- `restore_app_mutes()` (chamado no fechamento) desmuta **só** o que o app mutou.

### Hotkeys (`hotkey_sender.py`)
- `send_hotkey()` → janela em foco.
- `send_hotkey_to_window(hk, title)` → foca a janela alvo (pywin32), envia, devolve
  o foco. Usado quando a etapa tem `target_window`.

### VLC e Dispositivos de Saída
- Instância VLC com caching alto; arquivos → `MediaPlayer`, playlists/streams →
  `MediaListPlayer`. Saída via `audio_output_set("mmdevice")` + device id.
- **v2.1:** `libVLC` é embutido no .exe (`main._setup_bundled_vlc` aponta
  `PYTHON_VLC_LIB_PATH`/`PYTHON_VLC_MODULE_PATH`). `main_window._apply_output_device`
  aplica o dispositivo de saída padrão ao player no início e ao salvar config.

### UI (PySide6/Qt — v2.2)
- **Janela única mestre-detalhe**, sem modais. `MainWindow` (QMainWindow): top bar
  (logo, monitor, versão/update) · sidebar de sequências (cards com estado e
  "fora de agenda") · `QStackedWidget` (placeholder / `SequenceDetail` /
  `GlobalSettings`) · log no rodapé · `QSystemTrayIcon`.
- `SequenceDetail`: edita nome/keyword/atraso/agenda/etapas **inline**; a lista de
  etapas também é o fluxo visual (linha ativa/concluída/erro). Botões **Rodar
  agora**, **Ensaio** e **Cancelar**, e **▶ testar** por etapa. Editar uma etapa
  troca a página interna para o `StepEditor` (mesma janela).
- Tema "console de broadcast" (quase-preto + neon ciano/verde) em `ui/theme.py`.
- `MainWindow._daily_recheck` reavalia a agenda a cada 10 min.

### Estabilidade (v2.2)
- `applog.py`: `RotatingFileHandler` em `<data_dir>/logs/autotrigger.log`;
  `set_ui_sink()` liga o log à `LogView`; instala `sys.excepthook` e
  `threading.excepthook`. O engine/player logam via `applog.log`.
- `config.save()` é **atômico** (.tmp + `os.replace`) e mantém `config.json.bak`;
  `load()` cai no `.bak` se o principal corromper.

### Teste / Ensaio (v2.2)
- `engine.run_now(id)` dispara manual (sem TXT); `engine.rehearse(id)` roda em
  **dry-run** (mute/hotkey só logam "[ENSAIO]", áudio/stream limitados a ~8s);
  `engine.test_step(step)` executa uma etapa isolada. `dry_run`/`preview_cap`
  fluem por `SequenceRunner` → `StepRunner`.

### Distribuição & Auto-update (v2.2.4 — IMPORTANTE)
- **Instalação POR USUÁRIO**: `installer.iss` usa `PrivilegesRequired=lowest` e
  `DefaultDirName={localappdata}\Programs\AutoTrigger V10` (AppId novo
  `C5F9D4A3-...`, distinto do AppId admin antigo `B4E8C3F2-...`).
- **Motivo**: o auto-update substitui o próprio `.exe`. Em `C:\Program Files` o
  Windows exige admin → `Permission denied` (erro relatado pelo cliente). Pasta do
  usuário é gravável → update silencioso, sem UAC (padrão Chrome/VS Code/Discord).
- **updater.py**: baixa o `.exe` novo em `%TEMP%\AutoTriggerV10_update`, troca via
  batch. Se a pasta do app não for gravável (instalação antiga em Program Files),
  eleva via UAC (`ShellExecuteW runas`) e reinicia o app de-elevado por
  `explorer.exe`. `_is_writable()` decide.
- **Config/logs** em `%APPDATA%\AutoTriggerV10\` (config.json + .bak + logs/).
- ⚠️ **Updater quebrado em versões ≤ 2.2.2** (gravavam direto em Program Files).
  Por isso a migração para 2.2.4 exige **1 instalação manual** (desinstalar antigo
  + instalar `AutoTriggerV10_Setup_v2.2.4.exe`). Depois, tudo automático.
- Mantém entrada em "Adicionar/remover programas" (uninstall por usuário, HKCU).

---

## 5. Fases de Desenvolvimento

### Fase 1 — Concepção (Sessão inicial)
- Definição do problema e do fluxo completo
- Escolha de tecnologias
- Scaffolding inicial de todos os arquivos
- Instalação de dependências

### Fase 2 — Core Funcional
- `audio_manager.py` implementado e testado (3 dispositivos encontrados)
- `file_monitor.py` com watchdog funcionando
- `hotkey_sender.py` com send + capture
- `player.py` versão inicial (só arquivos locais)
- `sequence.py` versão inicial (fluxo básico)

### Fase 3 — Bug Fixes Críticos
**Bug 1 — pycaw API mismatch:**  
`CLSID_MMDeviceEnumerator` não exportado em pycaw ≥20230407.  
→ Fix: usar `AudioUtilities.GetDeviceEnumerator()` + `AudioUtilities.CreateDevice()`

**Bug 2 — device_id não salvo no config:**  
`_save()` salvava só o nome, não o ID.  
→ Fix: iterar `_input_devices`/`_output_devices` para buscar ID por nome

**Bug 3 — M3U stream reportando Ended imediatamente:**  
VLC parseava o container M3U rápido e disparava Ended antes do áudio.  
→ Fix: usar `MediaListPlayer` para extensões de playlist + sleep-based timer

**Bug 4 — Substring match incorreta:**  
`"ESPORTE"` era encontrado dentro de `"FIM_ESPORTE"`.  
→ Fix: checar `keyword_unmute` PRIMEIRO em `file_monitor.py`

**Bug 5 — Sem áudio no stream:**  
VLC não usava o dispositivo de saída configurado.  
→ Fix: `audio_output_set("mmdevice")` + `audio_output_device_set()` após inicialização VLC

### Fase 4 — Major Update (Fluxo Completo + UI)
- Renomeado `hotkey` → `hotkey_stop` + novo `hotkey_play`
- Sequência reescrita com 8 estados (MUTING antes da Vinheta 1)
- UI atualizada: dois campos de hotkey com botões "Capturar" independentes
- Painel visual `SequencePanel` com 7 etapas (azul=ativo, verde=concluído)
- `main_window.py` atualizado com novos estados no `_STATE_DISPLAY`
- `main.py` passa `player` para `MainWindow`, aplica `set_output_device()` na init
- Log do player conectado à UI via `set_log()`

### Fase 5 — Auto-Update + Build v1.0.0 (2026-06-02)
- `version.py` criado como fonte única da versão
- `updater.py`: consulta GitHub Releases API, baixa asset .exe, instala via batch sem bloquear app
- `ui/update_dialog.py`: dialog com notas de versão, barra de progresso de download
- `ui/main_window.py`: botão `v1.0.0` no header vira badge `🔔 vX.Y.Z disponível` quando há update
- `build.bat` reescrito: lê versão automaticamente, gera `.exe` versionado, publica release via `gh` CLI
- `version_info.txt`: metadados Windows (.exe mostra versão no Explorer)
- **v1.0.0 compilada (23,9 MB) e publicada em:** https://github.com/RobsonDV/maisnova-sport-trigger/releases/tag/v1.0.0

### Fase 6 — Documentação e Repositório (2026-06-02)
- `memory.md` criado
- `.gitignore` configurado
- Repositório GitHub criado e código publicado

### Fase 7 — Refino para Produção v2.1.0 (2026-06-03)
Sete pedidos do operador, todos implementados:
1. **Delay pós-gatilho:** campo `trigger_delay_seconds` por sequência —
   ao detectar a keyword, aguarda X (h/m/s) antes da 1ª etapa
   (`sequence_runner._run`, com contagem regressiva no timer da UI).
2. **Config não persistia (bug do onefile):** corrigido em
   `config._resolve_config_file()` — grava ao lado do `.exe`/`%APPDATA%`.
3. **Streaming sem VLC instalado:** libVLC **embutido** no .exe
   (`main._setup_bundled_vlc` + `build.bat --add-binary/--add-data`; installer
   não baixa mais VLC).
4. **Calendário de execução:** `schedule` por sequência (sempre / dias da semana
   / datas). Engine só arma a keyword nos dias válidos; recheck a cada 10 min;
   card mostra "fora de agenda".
5. **Unmute condicional ao fechar:** ledger `_muted_by_app` +
   `restore_app_mutes()` — só desmuta o que o app mutou.
6. **Hotkey sem o app em foco:** `send_hotkey_to_window` (pywin32) foca a janela
   alvo configurada (`target_window` na etapa hotkey), envia e devolve o foco.
7. **Tempo em h/m/s + aviso visual:** `timeparse.parse_secs/fmt_secs` aceitam
   horas; campos de tempo mostram o total interpretado ao vivo (`→ 1h 30m (5400s)`).

Bônus: `_apply_output_device` aplica o dispositivo de saída padrão ao player
(provável causa do "stream sem áudio"). `build.bat`/`installer` alinhados ao nome
`AutoTriggerV10.exe`.

### Fase 8 — Overhaul de UX/Visual v2.2.0 (2026-06-03)
Estudada a pasta `skills` (1.383 skills; relevantes: `frontend-design`,
`baseline-ui`, `electron-development`, `error-handling-patterns`,
`async-python-patterns`). Decisões e entregas:
1. **Migração de UI CustomTkinter → PySide6/Qt** (backend 100% preservado).
2. **Janela única mestre-detalhe** — fim do "janela atrás de janela" (3 modais
   empilhados viraram edição inline numa só janela).
3. **Estética "console de broadcast"** (dark + neon) via QSS em `ui/theme.py`.
4. **Estabilidade:** `applog.py` (log em arquivo + excepthooks), `config.save()`
   atômico + `.bak`.
5. **Ferramentas de teste:** ▶ testar etapa, **Ensaio** (dry-run) e **Rodar agora**.
6. Tray nativo `QSystemTrayIcon`; `requests`/updater mantidos; `pystray` e
   `customtkinter` removidos. Empacote com PySide6 (excludes de módulos Qt).

### Fase 9 — Watchdog de stream + Alertas por email v2.3.0 (2026-06-07)
Dois pedidos do operador (o stream "parava" e exigia play manual; faltava aviso):
1. **Watchdog de stream com auto-reconexão (`player.py`):** antes, no modo stream
   o monitor **só contava o tempo via `sleep` e ignorava o estado do VLC** — se a
   conexão caía no meio, o app seguia "achando" que tocava (silêncio no ar). Agora
   `_monitor_stream` checa `get_state()` a cada tick; se cai (`Error`/`Ended`/
   `Stopped`) antes do tempo acabar, **refaz o play sozinho** (helper extraído
   `_start_media`) com *backoff* (1s→5s), sem perder o tempo restante (duração é
   por tempo de parede). Novo callback `set_on_stream_event(kind, detail)`
   (`dropped`/`reconnecting`/`recovered`) alimenta o alerta. **VLC mantido** (mais
   robusto p/ M3U/HLS + device de saída por ID); o problema não era o VLC.
2. **Alertas por email (SMTP genérico):** novo módulo **`emailer.py`** (`smtplib`,
   sem dependência nova) — `send_email`/`notify_async` (envio em thread daemon, não
   bloqueia engine/UI, falha não interrompe sequência). Config: bloco `email` em
   `DEFAULT_GLOBAL` (host/porta/TLS/usuário/senha/remetente/destinos + flags de
   eventos), com merge de defaults na carga (`_ensure_global_defaults`) p/ configs
   antigas. UI: seção "ALERTAS POR EMAIL" em `ui/global_settings.py` + botão
   **"Enviar email de teste"**. Disparo central em `sequence_engine._on_state`
   (início/fim/erro) + handler `_on_stream_event` (queda/reconexão); **ensaio não
   envia** (via `SequenceRunner.is_dry_run`). SMTP_SSL p/ porta 465, senão
   STARTTLS quando `use_tls`.

---

## 6. Bugs Conhecidos / Pendências

| # | Descrição | Status |
|---|---|---|
| 1 | VLC requer instalação separada | ✅ Resolvido v2.1 (libVLC embutido) |
| 2 | Config não persistia no .exe onefile | ✅ Resolvido v2.1 |
| 3 | `build.bat` desatualizado (nome/`^` quebrados) | ✅ Resolvido v2.1 |
| 4 | Teste end-to-end completo com hardware real | Pendente |
| 5 | Stream sem áudio | Em acompanhamento (output device agora aplicado) |
| 11 | Stream caía e exigia play manual | ✅ Resolvido v2.3 (watchdog + auto-reconexão em player.py) |
| 6 | Build .exe v2.2 (PySide6) + release publicada | ✅ publicada |
| 7 | Tamanho do .exe (113MB) — enxugar excludes Qt/UPX | Aberto (otimização) |
| 8 | Teste em PC sem VLC instalado | Pendente |
| 9 | Auto-update falhava em Program Files (Permission denied) | ✅ Resolvido v2.2.4 (instalação por usuário) |
| 10 | Hotkey p/ software de rádio rodando COMO ADMIN | Em aberto (app por-usuário não envia a processo elevado) |

---

## 7. Planos Futuros (Ideias Discutidas)

### Alta Prioridade
- **Build PyInstaller (.exe):** Empacotar como executável único para distribuição sem precisar de Python instalado
- **Incluir VLC no bundle:** Investigar `vlc.dll` + libs dentro do .exe (ou instruir instalação separada com um `check_dependencies()` na inicialização)
- **Teste end-to-end:** Validar todo o fluxo com o RODECaster Pro e o software de rádio real

### Média Prioridade
- **Múltiplos perfis:** Salvar/carregar diferentes configurações (ex: perfil "Jornada Esportiva", perfil "Debate", etc.)
- **Histórico de jornadas:** Log persistido em arquivo com data/hora de cada execução
- **Notificação sonora de alerta:** Beep ou som curto se a keyword demorar demais
- **Timeout configurável para WAITING_NEXT:** Hoje não tem limite — se o TXT nunca tiver `FIM_ESPORTE`, fica esperando para sempre

### Futuro / Nice-to-have
- **Interface de teste de cada passo individualmente:** Botões "Testar Vinheta 1", "Testar Stream", "Testar Hotkey STOP" na aba de config
- **Integração com OBS/vMix:** Enviar cenas por WebSocket quando a jornada iniciar/encerrar
- **Suporte a múltiplas rádios esportivas:** Selecionar qual stream tocar por palavra-chave diferente
- **Modo "ensaio":** Simula toda a sequência sem realmente mutar/enviar hotkeys
- ~~**Watchdog de saúde do stream:** Reiniciar automaticamente se o stream cair durante a transmissão~~ ✅ feito v2.3 (player.py)
- **Auto-update:** Verificar GitHub por novas versões ao iniciar
- **Versão web (Electron/Tauri):** Tornar multiplataforma para Mac/Linux

---

## 8. Configuração de Referência (schema v2)

```json
{
  "version": 2,
  "global": {
    "txt_file_path": "C:/Users/User/Downloads/MidiaAtual.txt",
    "default_input_device_id": "{0.0.1.00000000}.{2a24c533-...}",
    "default_input_device_name": "Microfone (RODECaster Pro Stereo)",
    "default_output_device_id": "{0.0.0.00000000}.{26e07ddf-...}",
    "default_output_device_name": "Alto-falantes (RODECaster Pro Stereo)"
  },
  "sequences": [
    {
      "id": "162baf0a",
      "name": "Jornada Esportiva",
      "keyword_trigger": "ESPORTE",
      "enabled": true,
      "trigger_delay_seconds": 0,
      "schedule": { "mode": "always", "weekdays": [], "dates": [] },
      "steps": [
        { "type": "mute", "device_id": "...", "device_name": "Microfone ..." },
        { "type": "hotkey", "hotkey": "f11", "target_window": "" },
        { "type": "play_audio", "file": "...vinheta_entrada.mp3" },
        { "type": "stream", "url": "https://.../stream.m3u", "duration_seconds": 30 },
        { "type": "play_audio", "file": "...vinheta_saida.mp3" },
        { "type": "hotkey", "hotkey": "f9", "target_window": "" },
        { "type": "wait_keyword", "keyword": "FIM_ESPORTE" },
        { "type": "hotkey", "hotkey": "f11", "target_window": "" },
        { "type": "unmute", "device_id": "...", "device_name": "Microfone ..." }
      ]
    }
  ]
}
```
- `schedule.weekdays`: 0=Seg … 6=Dom. `schedule.dates`: lista `AAAA-MM-DD`.
- `trigger_delay_seconds`: atraso (segundos) após a keyword antes da 1ª etapa.
- `target_window` (etapa hotkey): vazio = janela em foco; preenchido = foca a
  janela cujo título contém esse texto, envia a hotkey e devolve o foco.

---

## 9. Comandos Úteis

```bash
# Rodar em desenvolvimento
python main.py

# Verificar sintaxe de todos os arquivos
python -c "import py_compile; [py_compile.compile(f, doraise=True) or print('OK', f) for f in ['main.py','config.py','timeparse.py','applog.py','audio_manager.py','player.py','file_monitor.py','hotkey_sender.py','step_runner.py','sequence_runner.py','sequence_engine.py','emailer.py','ui/theme.py','ui/qt_bridge.py','ui/widgets.py','ui/step_editor.py','ui/global_settings.py','ui/sequence_detail.py','ui/main_window.py','ui/update_dialog.py']]"

# Smoke test offscreen da UI Qt (sem abrir janela)
# QT_QPA_PLATFORM=offscreen python main.py

# Instalar dependências
pip install -r requirements.txt

# Gerar .exe (após PyInstaller configurado)
build.bat

# Listar dispositivos de áudio disponíveis
python -c "import audio_manager; print(audio_manager.list_input_devices()); print(audio_manager.list_output_devices())"
```

---

## 10. Histórico de Atualizações deste Arquivo

| Data | Descrição |
|---|---|
| 2026-06-02 | Criação inicial — documentação completa das fases 1-4 |
| 2026-06-02 | Auto-update + build v1.0.0 publicado no GitHub Releases |
| 2026-06-03 | Reescrita para arquitetura v2 (motor de sequências) + Fase 7 v2.1.0 |
| 2026-06-03 | Fase 8 v2.2.0 — migração para PySide6/Qt + UX mestre-detalhe + estabilidade |
| 2026-06-03 | Release v2.2.0 publicada no GitHub (.exe 113MB) + README.md criado |
| 2026-06-03 | v2.2.1 — marca do desenvolvedor RobsonDV (publisher, banner, app); release + instalador publicados |
| 2026-06-03 | v2.2.2 — CRUD de sequências na UI nova: excluir e duplicar sequência + ✕ de etapa destacado |
| 2026-06-03 | v2.2.3 — fix auto-update em Program Files (download no temp + troca elevada UAC); config sempre em %APPDATA% |
| 2026-06-03 | v2.2.4 — instalador POR USUÁRIO (%LocalAppData%, PrivilegesRequired=lowest, novo AppId) → auto-update sem UAC |
| 2026-06-07 | v2.3.0 — Fase 9: watchdog de stream c/ auto-reconexão (player.py) + alertas por email (emailer.py, SMTP genérico, seção na Config) |

