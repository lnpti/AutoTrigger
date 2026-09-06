## AutoTrigger V10 — v2.3.9

### Novidades

- **Reordenar sequências e etapas arrastando.** Tanto a lista de sequências
  (barra lateral) quanto a lista de etapas (dentro de uma sequência) agora
  aceitam arrastar-e-soltar para reordenar. Os botões ↑/↓ das etapas
  continuam funcionando também.
- **Botão "A→Z"** na barra lateral: ordena todas as sequências por nome de
  uma vez.
- **Aviso ao desmutar dispositivo automaticamente ao sair.** Se o app fechar
  enquanto um dispositivo que ele mesmo mutou (durante uma sequência) ainda
  está mutado, ele desmuta por segurança — e agora avisa isso com uma
  notificação na bandeja do Windows (não bloqueia o fechamento) e no log,
  citando o nome do dispositivo.

### Correções anteriores (v2.3.7 / v2.3.8)

- Ajuste de tempo ao vivo na etapa de streaming (+1m/+5m/-1m/-5m) e horário
  previsto de término.
- O app impede o protetor de tela e a suspensão do Windows enquanto estiver
  aberto.
- Republicado com Python 3.13 (compatibilidade mais ampla que 3.14).
