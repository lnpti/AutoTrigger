## AutoTrigger V10 — v2.3.11

### Correção (de verdade, desta vez)

- **"Failed to load Python DLL" ao reabrir sozinho após atualização.**
  A correção anterior (pausa de 3s) não fazia efeito nenhum: descobri, testando
  isoladamente, que o comando `timeout` do Windows **falha silenciosamente**
  quando roda sem um console interativo de verdade — que é exatamente como
  o script de atualização roda. Ou seja, a pausa nunca acontecia.
  Trocado por uma checagem de verdade: o script tenta renomear o `.exe`
  recém-substituído para o próprio nome, em loop — isso falha enquanto o
  antivírus estiver com o arquivo aberto para escanear, e funciona assim que
  for liberado. Testado isoladamente com um arquivo travado de propósito por
  3 segundos: o script esperou exatamente esse tempo e seguiu corretamente
  assim que destravou.

  **Observação:** como a correção está no próprio mecanismo de atualização,
  ela só entra em vigor a partir da *próxima* atualização depois desta — ou
  seja, é possível que a atualização desta versão específica (para quem
  estiver rodando a v2.3.10 ou anterior) ainda mostre o erro passageiro uma
  última vez, mas todas as atualizações futuras a partir daqui devem vir
  limpas.

### Correções anteriores (v2.3.10)

- Arrastar-e-soltar para reordenar sequências/etapas (corrigido).
- Botão "A→Z" para ordenar sequências por nome.
