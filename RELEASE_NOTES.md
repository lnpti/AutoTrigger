## AutoTrigger V10 — v2.3.12

### Arrastar-e-soltar refeito

- **Alça de arraste dedicada ("≡").** Reordenar sequências/etapas agora só
  acontece segurando essa alça — clicar em qualquer outro ponto do card só
  faz a ação normal (abrir a sequência, editar a etapa) sem risco de mudar
  a ordem sem querer.
- **O card se solta de verdade da lista e acompanha o cursor** durante o
  arraste, com um espaço abrindo ao vivo entre os outros conforme você
  passa por cima deles — em vez de só uma linha indicando onde vai cair.
- **Hover só destaca a borda.** Passar o mouse por cima de um card/etapa
  não preenche mais o fundo; o preenchimento cheio (com cor própria) fica
  reservado só para o card sendo efetivamente arrastado.
- Corrigido um card ficando esticado ocupando a lista inteira quando havia
  poucas sequências.
- **Reescrita a fundo por trás dos panos:** a primeira versão desse recurso
  usava o mecanismo nativo de arrastar-e-soltar do Qt, que se mostrou
  instável nesse cenário (chegou a travar o aplicativo). A lista de
  sequências/etapas agora é controlada na mão (mouse), sem depender desse
  mecanismo — mais previsível e testado antes de publicar.

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
