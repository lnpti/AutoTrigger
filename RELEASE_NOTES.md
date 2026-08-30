## AutoTrigger V10 — v2.3.3

Desenvolvido por **RobsonDV**.

### Correções

- **Campos desconfigurados em telas com escala 125%:** o Qt arredondava o fator
  de escala do Windows para 100% no cálculo do layout, mas desenhava o texto na
  escala real (125%), desalinhando labels e campos. Corrigido definindo a
  política de DPI como `PassThrough` (usa o fator real em telas com escala
  fracionária — 125%, 150%, 175%).
- **Configurações Globais ilegível em 125%:** a tela tinha altura fixa (sem
  rolagem); quando o conteúdo ficava mais alto que a janela nessa escala, o Qt
  comprimia/sobrepunha os campos para caber no espaço disponível — inclusive
  quebrando a renderização de checkboxes e ícones. Corrigido adicionando
  rolagem vertical à tela (os campos mantêm o tamanho normal; quando o
  conteúdo não cabe, aparece uma barra de rolagem em vez de espremer tudo).
- **Hotkey de janela alvo não funcionava com o protetor de tela ativo:** a
  janela do protetor ficava em primeiro plano e "roubava" a tecla enviada.
  Agora o app detecta o protetor de tela ativo e o encerra (simulando um
  pequeno movimento do mouse) antes de focar a janela alvo e enviar a hotkey.
  Não afeta telas de bloqueio com senha — essas continuam exigindo login manual
  por segurança do Windows.

### Distribuição

- A partir da v2.3.2, o app passa a publicar e verificar atualizações em
  **github.com/lnpti/AutoTrigger**.
