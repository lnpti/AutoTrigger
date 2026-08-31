## AutoTrigger V10 — v2.3.4

Desenvolvido por **RobsonDV**.

### Correção

- **Hotkey de janela alvo podia falhar em silêncio após o protetor de tela:**
  quando o protetor de tela ativava durante uma sequência longa (ex.: stream
  de horas), o app conseguia encerrá-lo, mas a troca de foco para a janela
  alvo (para enviar a hotkey de PLAY, por exemplo) podia ser bloqueada pelo
  Windows sem gerar erro — a proteção "antirroubo de foco" do Windows deixa a
  `SetForegroundWindow` só piscar o ícone na barra de tarefas em vez de focar
  de verdade, e isso é mais provável logo depois de um input simulado (como o
  movimento de mouse usado para fechar o protetor). O log mostrava "sucesso",
  mas a hotkey ia para a janela errada. Corrigido usando `AttachThreadInput`
  (a técnica padrão do Windows para forçar a troca de foco de forma
  confiável) e confirmando se o foco realmente aconteceu antes de enviar a
  tecla — se não conseguir confirmar, agora aparece um aviso no log.
- Todas as mensagens de diagnóstico de hotkey (protetor de tela, janela não
  encontrada, foco não confirmado) agora vão para o log real do app (antes
  iam só para o console, que não existe no `.exe` empacotado — por isso
  falhas ficavam invisíveis).

### Correções anteriores (v2.3.2 / v2.3.3)

- Campos desconfigurados em telas com escala 125% (DPI `PassThrough` +
  rolagem na tela de Configurações Globais).
- Hotkey de janela alvo não funcionava com o protetor de tela ativo (fix
  inicial — v2.3.4 fecha uma lacuna que sobrava nesse mesmo cenário).
- Novo ícone e marca "AutoTrigger" na barra superior.
