# Gestão de clientes e atualizações no painel

**Pedido (2026-11-01):** a versão com as correções da auditoria sobe para o painel como
**pendente**, e o Eric escolhe quando lançar. No painel: sinal de online por cliente, botão de
forçar por cliente, filtros combináveis (versão, cliente, módulo...), "Atualizar todos" (não
obrigatório) e "Forçar" (obrigatório), gestão e informações dos clientes bem mais ricas.

## Decisões

- **Pendente:** `hub_lancamentos` guarda cada versão que subiu. Pendente = sem `liberada_em`.
  O Hub só enxerga `hub_versoes` (geral) ou `hub_liberacoes` (por cliente). Nenhum cliente recebe
  uma versão pendente sem clique no painel.
- **Instalador público:** com `-Pendente`, `/baixar/DumTech-Hub-Setup.exe` continua sendo a versão
  liberada. As páginas de download passam a seguir a versão liberada no banco; o arquivo genérico é
  a reserva.
- **Online:** `hub_presenca`, tabela própria, sem auditoria e sem tempo real (batida de 2 em 2
  minutos). Online = bateu nos últimos 5 minutos. Funciona em todo Hub 1.2.3 ou mais novo, sem
  atualizar nada no cliente. O painel confere a cada minuto.
- **Por cliente:** vale para todos os computadores da licença.
- **Atualizar (cliente ou todos):** o aviso aparece e o cliente escolhe a hora.
- **Forçar:** manifesto com `forcada`, `obrigatoria` e `silenciosa`.
  - Hub 1.10.0 ou mais novo: baixa, avisa por cima de tudo, conta 5 minutos para a pessoa terminar
    o que está fazendo, instala e reabre.
  - Hub 1.5.1 a 1.9.0: manifesto silencioso nos primeiros 3 minutos (da ordem ou da abertura do
    Hub), para baixar; depois só obrigatório, para o aviso aparecer. O que já baixou instala ao
    fechar, porque essa versão não confere `silenciosa` de novo.
  - Hub anterior a 1.5.1: aviso que não se dispensa.
- **Segurança do clique:** "Forçar todos" pede digitar a versão. "Recolher" devolve a versão
  anterior e a nova volta a ser pendente.
- **Filtros:** E entre grupos, OU dentro do grupo. Guardados no navegador.
- **Gestão:** etiquetas, próximo contato, anotações, linha do tempo, seleção em massa, exportar CSV.
- **Privacidade:** a política passa a citar a versão e o sinal de programa aberto.

## Fases

- [x] Banco: migration + testes SQL
- [x] Servidor: `versao` assina `forcada`
- [x] Hub: forçada de verdade, 1.10.0, novidades
- [x] Painel: regras (`gestao.js`) + testes
- [x] Painel: Clientes, Atualizações, ficha
- [x] Site: download segue a versão liberada; privacidade
- [x] Ferramentas: `lancar_versao.ps1 -Pendente`, `publicar_site.ps1 -Generico`
- [x] Testes completos e telas conferidas
- [x] Produção: migrations, funções, site, instalador, conferência
