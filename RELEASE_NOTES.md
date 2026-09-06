## AutoTrigger V10 — v2.3.8

### Novidade

- **Ajuste de tempo ao vivo na etapa de Streaming.** Enquanto uma etapa de
  streaming está rodando, aparecem botões **-5m / -1m / +1m / +5m** ao lado
  do cronômetro para adicionar ou retirar tempo dessa execução — vale só para
  a rodada atual (a duração configurada na etapa continua igual depois que a
  sequência termina, nada é salvo). Retirar tempo além do que já passou
  encerra o streaming em seguida.
- O cronômetro da etapa de streaming agora também mostra o **horário previsto
  de término** (ex.: "termina às 18:45"), atualizado automaticamente quando
  o tempo é ajustado.

### Correções anteriores (v2.3.7)

- O app impede o protetor de tela e a suspensão do Windows enquanto estiver
  aberto — resolve hotkeys de janela alvo não chegando ao destino quando a
  máquina entra em protetor de tela com área de trabalho segura.
- Republicado com Python 3.13 (compatibilidade mais ampla que 3.14).
