## AutoTrigger V10 — v2.3.10

### Correções

- **Arrastar-e-soltar para reordenar sequências/etapas não funcionava.**
  A seleção nativa das listas estava desativada (para esconder o retângulo
  padrão de seleção do Qt), mas o mecanismo de arrastar do Qt depende dela
  internamente para saber o que está sendo arrastado. Corrigido mantendo a
  seleção ativa (escondendo só o visual via CSS) e deixando o clique no card
  da sequência propagar corretamente para a lista.
- **Erro "Failed to load Python DLL" às vezes ao atualizar**, mesmo com o
  app funcionando normal ao reabrir manualmente em seguida: era uma corrida
  entre o antivírus fazendo varredura em tempo real do `.exe` recém-baixado/
  substituído e o próprio instalador tentando reabrir o app rápido demais.
  Adicionada uma pequena pausa antes do reinício automático após a
  atualização, para dar tempo do arquivo "assentar".

### Novidades anteriores (v2.3.9)

- Reordenar sequências e etapas (agora funcionando de verdade — ver acima).
- Botão "A→Z" para ordenar sequências por nome.
- Aviso na bandeja do Windows quando um dispositivo é desmutado
  automaticamente ao fechar o app.
