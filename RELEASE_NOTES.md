## AutoTrigger V10 — v2.3.5

### Correções

- **App podia fechar sozinho ao clicar em "Baixar e Instalar" (atualização):**
  o progresso do download atualizava a tela a partir de uma thread em segundo
  plano de um jeito que não é seguro no Qt (mexia direto nos widgets em vez
  de usar o mecanismo de sinal/slot), o que podia derrubar o app no meio do
  download de arquivos grandes. Corrigido usando o padrão correto (thread-safe)
  já usado no resto do app.
- **Hotkey de janela alvo podia falhar em silêncio após o protetor de tela:**
  quando o protetor de tela ativava durante uma sequência longa (ex.: stream
  de horas), o app conseguia encerrá-lo, mas a troca de foco para a janela
  alvo (para enviar a hotkey de PLAY, por exemplo) podia ser bloqueada pelo
  Windows sem gerar erro — a proteção "antirroubo de foco" do Windows deixa a
  `SetForegroundWindow` só piscar o ícone na barra de tarefas em vez de focar
  de verdade. O log mostrava "sucesso", mas a hotkey ia para a janela errada.
  Corrigido usando `AttachThreadInput` (a técnica padrão do Windows para
  forçar a troca de foco de forma confiável) e confirmando se o foco
  realmente aconteceu antes de enviar a tecla — se não conseguir confirmar,
  agora aparece um aviso no log.
- Mensagens de diagnóstico de hotkey (protetor de tela, janela não
  encontrada, foco não confirmado) agora vão para o log real do app.

### Correções anteriores (v2.3.2 / v2.3.3)

- Campos desconfigurados em telas com escala 125% (DPI `PassThrough` +
  rolagem na tela de Configurações Globais).
- Novo ícone e marca "AutoTrigger" na barra superior.
