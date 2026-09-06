## AutoTrigger V10 — v2.3.7

### Correção

- **Compilado com Python 3.13** (não 3.14): a v2.3.6 publicada antes foi
  compilada com Python 3.14, que exige uma versão do runtime C (UCRT) do
  Windows que máquinas sem atualizações recentes não têm — o app nem abria
  ("Failed to load Python DLL ... LoadLibrary: não foi possível encontrar o
  módulo especificado"). Corrigido republicando com Python 3.13, mais testado
  e compatível. Os scripts de build (`build.bat`/`build_installer.bat`)
  agora fixam a versão do Python usada, para não repetir esse problema.

### Novidade

- **O app agora impede o protetor de tela e a suspensão do Windows enquanto
  estiver aberto** (sempre ativo, sem precisar configurar nada). Isso resolve
  de raiz o problema de hotkeys de janela alvo não chegarem ao destino: em
  algumas máquinas, quando o protetor de tela ativa, o Windows troca para uma
  área de trabalho segura (a mesma da tela de bloqueio) — e nenhuma automação
  de mouse/teclado consegue atravessar isso sem a senha real do usuário.
  Evitando que o protetor ative, esse cenário nunca mais acontece.

### Correções anteriores (v2.3.6)

- Alertas por Telegram (nova seção em Configurações Globais).
- Instância única: abrir o app já rodando só mostra a janela existente.
- Diálogo de atualização podia travar em branco; botão de e-mail de teste
  quase invisível; ortografia "email" → "e-mail".
