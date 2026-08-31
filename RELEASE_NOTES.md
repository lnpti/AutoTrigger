## AutoTrigger V10 — v2.3.6

### Novidade

- **Alertas por Telegram**, nova seção em Configurações Globais (ao lado dos
  alertas por e-mail): token do bot + chat ID, os mesmos eventos disparadores
  (início/fim/erro/queda de stream) e botão de teste. Basta falar com
  `@BotFather` no Telegram para criar um bot e pegar o token, e com
  `@userinfobot` para descobrir o chat ID.

### Correções

- **Abrir o app de novo enquanto já está rodando abria uma segunda instância**
  (em vez de só mostrar a janela já aberta na bandeja). Agora, se já houver
  uma instância rodando, a nova apenas avisa a existente para se mostrar
  (`showNormal` + foco) e se encerra sozinha.
- **Diálogo de "Atualização Disponível" podia travar em branco ("Não está
  respondendo")** ao ser aberto pela checagem manual: o resultado da checagem
  de atualização (que roda em thread de background) abria o diálogo direto
  dessa thread, o que é inválido no Qt — corrigido levando o resultado até a
  GUI thread via signal antes de abrir a janela.
- Corrigido o mesmo tipo de problema no botão **"Enviar e-mail de teste"**
  (usava o log da UI direto de uma thread de background).
- Botão "Enviar e-mail de teste" quase invisível (estilo fraco demais) —
  agora com contraste normal.
- Correção de ortografia: "email" → "e-mail" em toda a interface.

### Correções anteriores (v2.3.4 / v2.3.5)

- App podia fechar sozinho ao clicar em "Baixar e Instalar" (mesma causa-raiz
  de thread-safety do Qt, na barra de progresso do download).
- Hotkey de janela alvo podia falhar em silêncio após o protetor de tela
  (`AttachThreadInput` + confirmação de foco).
- Campos desconfigurados em telas com escala 125% (DPI `PassThrough` +
  rolagem em Configurações Globais).
- Novo ícone e marca "AutoTrigger" na barra superior.
