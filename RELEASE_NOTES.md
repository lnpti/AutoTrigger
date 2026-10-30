## AutoTrigger V10 — v2.3.29

### Identificação do local nos alertas

- Novo campo **Local deste app** (Nome / descrição) em Configurações Globais, para
  quem roda o app em vários lugares saber de onde veio o alerta. Ex.: "Rádio Tua —
  Estúdio 2 (Marau)".
- **Telegram:** a primeira linha de cada alerta passa a ser `📍 <local>`.
  **E-mail:** o assunto ganha o prefixo `[<local>]` e o corpo começa com `Local: <local>`.
  Vale para início, fim, erro/cancelamento e queda/reconexão de stream, e também para
  os botões de teste (que usam o texto digitado, mesmo antes de salvar).
- Com o campo vazio, os alertas continuam exatamente como antes.

## AutoTrigger V10 — v2.3.28

### Atualização que não trava mais em silêncio

- Corrige a atualização que ficava parada em 100% depois de "Download concluído.
  Preparando instalação…". O script de instalação era gravado sempre com o mesmo
  nome na pasta temporária; se essa gravação falhasse (arquivo antigo bloqueado ou
  somente leitura, antivírus), a exceção só ia para o arquivo de log e a tela não
  mostrava nada.
- Agora o script tem **nome único a cada tentativa**, com a pasta de dados do app
  como alternativa; cada falha aparece no log da tela, e se nada puder ser gravado o
  log pede para instalar manualmente.
- O diálogo de atualização se recupera: se a instalação não encerrar o app, o botão
  volta como "Tentar de novo" com a explicação do problema.
- Qualquer erro inesperado em uma thread de fundo (não só na atualização) passa a
  aparecer também no log da tela, não apenas no arquivo.
- A correção vale para as atualizações **a partir desta versão**; quem está numa
  versão anterior e travar deve instalar o instalador desta versão uma vez.

## AutoTrigger V10 — v2.3.27

### Cadastro de streamings

- Nova seção **Streamings cadastrados** em Configurações Globais: cadastre cada
  streaming (nome + URL) **uma vez**.
- Na etapa de **Streaming** de qualquer sequência, escolha o streaming pelo nome na
  lista e defina só o **tempo** e o **ganho**. Dá para continuar digitando uma URL
  manual ("Outra URL").
- **Trocar a URL no cadastro vale para todas as sequências** que usam aquele streaming,
  na hora de rodar. Se você remover um cadastro, as etapas que o usavam continuam com
  a última URL que ele tinha (e o log avisa).
- As etapas que você já tem foram convertidas sozinhas na primeira abertura: URLs
  iguais viram **um** cadastro compartilhado (o nome vem do rótulo, ex.: "Streaming -
  Gaúcha" vira "Gaúcha"; renomeie à vontade). Nada precisa ser refeito.
- O cadastro vai junto na exportação/importação de configurações; ao importar "só
  adicionar as sequências", os streamings que faltam entram no cadastro.
- O resumo da etapa na lista mostra o nome do streaming, e o log mostra
  "[cadastro: nome]" quando a etapa usa um.

## AutoTrigger V10 — v2.3.26

### Duas sequências disparando juntas

- Corrige sequências que iniciavam ao mesmo tempo quando a keyword de uma é o
  começo da keyword de outra (ex.: `…3H` dentro de `…3H45`): o texto "…3H45"
  disparava a 3h **e** a 3h45. Agora, se um texto casa com várias keywords e uma
  está contida em outra, dispara só a **mais específica**. Vale para o arquivo TXT,
  para o log do player e para palavras de espera (`FIM_ESPORTE` x `ESPORTE`).
- O log avisa quando ignora uma keyword por isso ("ignorada: o texto também casa
  com '…' (mais específica)"). Keywords independentes continuam disparando juntas.

## AutoTrigger V10 — v2.3.25

### Correção da queda silenciosa do app (a causa real)

- Os `crash.log` do estúdio mostraram a causa das quedas sem aviso: uma falha
  nativa (`access violation`) quando o Python liberava objetos COM de áudio em
  uma thread diferente da que os criou. Reproduzido em teste e corrigido: esses
  objetos agora só são liberados quando o app fecha. Afetava o mute, a lista de
  placas e o vigia de áudio do stream.
- Se a proteção não puder ser aplicada, o log avisa na abertura.

### Retomada da sequência depois de uma queda

- Se o app cair no meio de uma sequência e voltar (pelo modo "sempre rodando"),
  ele **continua na etapa em que estava**: o stream segue só pelo tempo que
  faltava (com o mesmo ganho), esperas retomam o que faltava, uma espera por
  palavra-chave avança se a palavra já apareceu no TXT, e mute/hotkey repetem.
  Um áudio que estava tocando não é repetido.
- Só retoma se o app voltou em até **3 minutos** (campo novo em Configurações
  Globais; 0 = nunca retomar). Fora disso, ou se a sequência já foi retomada 2
  vezes, o log explica e o app **desmuta o que a sequência tinha mutado**.
- Sair pelo menu da bandeja nunca retoma nada.

### Vigia "sempre rodando" mais confiável

- Corrigido o vigia que reabria o app à toa (com o app vivo) e, depois de 5
  vezes, desistia para sempre. Agora só reabre se o app não der sinal de vida, e
  o contador de reaberturas zera a cada minuto de app estável.

## AutoTrigger V10 — v2.3.24

### Modo "manter sempre rodando"

- Nova opção em Configurações Globais: **Manter sempre rodando (reabrir sozinho
  se fechar)**. Com ela ligada, se o app sumir sem você pedir (queda, "Finalizar
  tarefa"...), um vigia escondido o reabre em alguns segundos. O vigia é
  separado do app e não atrapalha a atualização automática.
- Não reabre quando a saída foi pedida: **Sair** no menu da bandeja, atualização
  automática, desligar/fazer logoff do Windows ou desmarcar a opção.
- Se o app cair ao abrir 5 vezes seguidas sem ficar estável por 2 minutos, o
  vigia desiste (motivo no `keepalive.log`, na pasta de logs). O log do app
  registra "♻ Reaberto automaticamente" a cada reabertura.
- Não substitui **Iniciar com o Windows**: para o app também abrir quando o PC
  ligar, marque as duas opções.

## AutoTrigger V10 — v2.3.23

### Atualização automática sem o erro "Failed to load Python DLL"

- Corrige o erro `Failed to load Python DLL ... python313.dll` que aparecia ao
  reabrir o app depois de atualizar. Não era antivírus: o `.exe` novo herdava o
  ambiente do PyInstaller e reaproveitava a pasta temporária do app antigo, que é
  apagada quando ele fecha. O atualizador agora manda o app novo extrair a
  própria pasta.
- A troca do `.exe` também era tentada uma vez só: se o antigo ainda estivesse
  preso por um instante, a atualização era abandonada em silêncio. Agora tenta
  por até ~40 s.
- A correção vale para o app que faz a atualização: quem atualizar a partir da
  v2.3.22 ou anterior ainda pode ver o erro uma última vez (basta abrir o app de
  novo; o `.exe` novo já está instalado). As atualizações seguintes saem limpas.

### Vigia de stream mudo mais robusto

- Procura a sessão de áudio do app em todas as saídas, não só na selecionada, e
  não deixa uma sessão ilegível de outro programa interromper a busca.
- O log informa em qual placa o áudio está saindo. Se estiver saindo em outra
  que não a selecionada, avisa e tenta mover para a selecionada.
- Quando não consegue medir o áudio, o aviso agora traz o motivo.

## AutoTrigger V10 — v2.3.22

### Mute com a placa certa

- Corrige o mute/unmute que procurava uma placa diferente da selecionada. Se a
  placa gravada no passo não existir neste PC (por exemplo, configuração vinda
  de outro estúdio), o app usa a **placa padrão das Configurações Globais**
  (entrada para mute de entrada, saída para saída) e avisa no log qual usou.
  Quando a placa do passo existe, nada muda.
- O editor de etapa não mostra mais a primeira placa da lista como se fosse a
  escolhida: se a salva não existe neste PC, aparece "⚠ nome (não encontrado)",
  e salvar sem trocar mantém a placa gravada. Escolher outra e salvar corrige o
  passo de vez.

## AutoTrigger V10 — v2.3.21

### Placas de áudio achadas pelo nome

- Corrige o áudio que não saía na placa escolhida em Configurações Globais e o
  erro "Elemento não encontrado" ao mutar. O Windows troca o ID da placa ao
  reinstalar o driver, trocar a porta USB ou usar a configuração de outro PC;
  o app guardava só o ID. Agora **procura a placa pelo nome primeiro** e usa o
  ID salvo só se o nome não for achado. Vale para mute/unmute e para a saída
  do player. O log avisa quando o ID mudou ou quando a placa não está ativa.
- Configurações Globais não mostra mais a primeira placa da lista como se fosse
  a escolhida: se a salva não existe neste PC, aparece "⚠ nome (não encontrado)".

### Stream que fica mudo é reiniciado

- Se o stream ficar **10 segundos mudo**, o app faz stop + play e repete até o
  som voltar (a cada ~15 s). Também reinicia se o stream travar sem entrar em
  "Playing" por 25 s (a queda do VLC já era tratada).
- Alerta por e-mail/Telegram uma vez quando o problema começa (com o motivo) e
  outra quando o som volta. Se o app não conseguir medir o áudio numa reprodução,
  o vigia de mudo fica inativo e o log avisa.

## AutoTrigger V10 — v2.3.20

### Espelho de atualização no Cloudflare

- O app agora também consegue se atualizar pelo Cloudflare, além do GitHub —
  útil quando a rede do estúdio bloqueia o GitHub (era o caso relatado):
  se a checagem no GitHub falhar, o app tenta automaticamente um endereço
  Cloudflare alternativo, sem precisar mexer em nada na configuração.
- Continua tudo automático: se o GitHub responder normalmente, é ele que é
  usado (o Cloudflare é só reserva).

## AutoTrigger V10 — v2.3.19

### Importar configurações

- Novo botão **Importar configurações…** em Configurações Globais, ao lado de
  "Exportar configurações…". Carrega um `.json` exportado antes (ou um `config.json`)
  e pergunta como importar:
  - **Só adicionar as sequências** (padrão): acrescenta as do arquivo às atuais, sem
    mexer em mais nada; nomes repetidos ganham "(importada)".
  - **Substituir tudo:** troca as configurações globais e todas as sequências.
    Antes, salva uma cópia completa da configuração atual
    (`config.antes-da-importacao-<data>.json`, mantém as 5 mais recentes).
- Senha do e-mail e token do Telegram em branco no arquivo **não apagam** os atuais.
- Arquivo inválido (JSON quebrado, não é uma configuração, versão mais nova do app)
  mostra uma mensagem clara e não altera nada. Arquivos de versões antigas são
  convertidos automaticamente.
- Depois de importar, a lista de sequências e a tela são recarregadas e o monitor
  reinicia. Aviso na janela: dispositivos de áudio são do computador de origem e
  talvez precisem ser escolhidos de novo em outro PC.

## AutoTrigger V10 — v2.3.18

### Diagnóstico de quedas e travamentos (permanente)

- **`crash.log`** (na pasta de logs, junto do `autotrigger.log`): se o app cair de
  verdade, grava a pilha de todas as threads, mostrando em que linha do código ele
  estava. Gira sozinho ao passar de ~500 KB.
- **Aviso de sessão anterior:** se o app foi fechado sem terminar normalmente
  (queda, finalizado à força, falta de energia), a abertura seguinte registra um
  aviso no `autotrigger.log`. A atualização automática não gera esse aviso.
- **Vigia de travamento:** se a interface ficar mais de 8 s sem responder, a pilha
  das threads é gravada no `crash.log` e o `autotrigger.log` avisa quando ela volta.
- **Rastro fino no `autotrigger.log`** (linhas com `·`, só no arquivo): cada
  micro-passo do mute e do envio de hotkey (foco da janela, `keyboard.send`...).
  Se o app cair no meio, a última linha `·` mostra até onde chegou.

### Interface

- **Configurações Globais:** seções bem mais separadas (linha fina e mais espaço
  entre elas), e o arquivo TXT ganhou um título próprio ("Gatilho por arquivo TXT").

## AutoTrigger V10 — v2.3.17

- **Origem do gatilho: só "Arquivo TXT" ou "Log do player".** A opção "TXT ou log
  do player" saiu da lista. Sequências já salvas com ela continuam funcionando
  como antes; o item aparece como "(antigo — escolha um)" só enquanto a sequência
  o usa, até você escolher uma das duas.
- **Cards de sequência "suspensos":** sombra e 10 px de folga nas duas laterais,
  sem encostar nas bordas da coluna (a margem de 4 px da v2.3.16 foi desfeita).
  Nomes muito longos são cortados em vez de alargar o card.

## AutoTrigger V10 — v2.3.16

Esta versão **volta ao comportamento da v2.3.14** (gatilhos, log do player,
atraso, Telegram, volume em dB, inicialização) e acrescenta só o abaixo. As
novidades da v2.3.15 ("nome exato do arquivo", `;` no log do player e coluna de
sequências mais larga) foram **retiradas** até serem investigadas.

- **Exportar configurações:** novo botão em Configurações Globais que salva todas
  as configurações e sequências num arquivo `.json`. Pergunta se inclui a senha
  do e-mail e o token do Telegram (por padrão, não -- saem em branco).
- **Visual:** os cards da coluna de sequências ficam mais perto da lateral do app
  (margem de 10 px para 4 px).

## AutoTrigger V10 — v2.3.15

### Keyword "nome exato do arquivo"

- Nova caixa na sequência: **"Nome exato do arquivo (dispensa o ';' no fim)"**.
  Ligada, basta digitar o nome do arquivo (sem extensão e sem `;`) e a keyword
  só dispara quando for **igual ao nome inteiro** -- `ESPORTE 3h15mim` não
  dispara com `ESPORTE 3h` nem com `ESPORTE 4h`. Funciona no TXT (o nome é o
  que vem antes do `;` da linha) e no log do player.
- Desligada (padrão), tudo continua como antes: basta a keyword estar contida
  no texto, e o `;` no fim continua valendo.
- No log do player, terminar a keyword com `;` também casa só quando o nome
  termina ali (sem a extensão), igual ao TXT.
- A mesma palavra pode ter um gatilho "contém" e outro "nome exato" ao mesmo
  tempo, sem um sobrescrever o outro.

### Exportar configurações

- Novo botão **Exportar configurações…** em Configurações Globais: salva todas
  as configurações e sequências num arquivo `.json`. Pergunta se inclui a senha
  do e-mail e o token do Telegram (por padrão, não -- saem em branco).

### Interface

- A coluna de sequências abre 20 px mais larga (a janela também, para o painel
  de detalhe manter o tamanho).

## AutoTrigger V10 — v2.3.14

### Disparo pelo log do player (V10 Player Network)

- Nova origem de gatilho: o app lê os XMLs temporários que o player cria a cada
  áudio em execução e dispara as sequências pelo **nome do arquivo de áudio**.
  Configure em Configurações Globais → "Log do player" (pasta dos XMLs) e, em
  cada sequência, escolha a "Origem do gatilho": TXT, Log do player ou ambos.
- **Deixar o áudio terminar antes de contar o atraso:** a sequência dispara
  quando o áudio entra, espera ele acabar (tempo lido do XML) e só então conta
  o atraso e roda as etapas.
- O atraso das sequências agora usa relógio preciso (antes podia errar até 1 s).

### Ganho de volume no streaming

- A etapa de Streaming ganhou **Ganho de volume em dB** (-40 a +6 dB; 0 dB =
  normal; +6 dB é o máximo que o VLC amplifica).

### Telegram

- **Vários contatos**, cada um com nome, chat_id, botão de teste e opção de
  pausar. O log mostra quem recebeu ou falhou.
- **O chat_id funciona com ou sem o "-"**: se o Telegram recusar, o app tenta
  as outras formas (grupo `-ID`, supergrupo `-100ID`) e lembra a que funcionou.

### Inicialização

- Novas opções em Configurações Globais: **Iniciar com o Windows** e
  **Iniciar minimizado na bandeja**.

## AutoTrigger V10 — v2.3.13

### Alertas por Telegram para vários contatos

- Em Configurações Globais, o campo único de "Chat ID" virou uma **lista de
  contatos**: cada um com **nome** (ex.: "João — plantão"), chat_id, opção de
  pausar, botão de teste individual (📨) e remover (✕).
- O log identifica **quem recebeu ou falhou** ("Telegram enviado para João",
  "Falha ao enviar para Maria: …"). Se um contato falha, os outros continuam
  recebendo.
- Quem já tinha um chat_id configurado é migrado automaticamente para
  "Contato 1", sem perder nada.

### Ganho de volume no streaming

- A etapa de Streaming ganhou o campo **Ganho de volume (0–200%)**: 100% é o
  normal, acima disso amplifica. Aparece no resumo da etapa e no log.
- Vale só para o stream daquela etapa (áudios comuns seguem em 100%) e é
  reaplicado se o stream cair e reconectar. Etapas antigas assumem 100%.

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
