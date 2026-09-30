# Redesign da Hub DumTech — visual e estrutura

**Data:** 2026-08-31
**Escopo:** a plataforma (Hub + casca compartilhada + sistema visual).
**Fora de escopo:** as regras e telas internas dos 7 aplicativos (`src/dumtech/apps/`).

---

## 1. Problema

A Hub de hoje é um lançador de atalhos com aparência de produto genérico. Três
causas concretas, todas verificadas no código:

**1.1 — A Hub e os 7 aplicativos desenham a mesma casca.**
`hub/main_window.py::_build_sidebar` e `ui/app_shell.py::_build_sidebar` produzem
o mesmo desenho: marca no topo, separador, lista de `NavButton`, `addStretch`,
botão de tema, versão no rodapé. O usuário abre um aplicativo e cai numa tela
que é visualmente indistinguível de onde ele estava. Cada aplicativo é uma
`QMainWindow` independente, então sete aplicativos abertos são sete janelas
soltas na barra de tarefas do Windows, sem relação visível entre si.

**1.2 — A tela inicial não tem hierarquia.**
`hub/views/apps_view.py` renderiza um `FlowLayout` de `AppCard` de tamanho fixo
(252×288), todos idênticos, todos com a mesma pill "Disponivel", ordenados
alfabeticamente. Não há agrupamento, não há noção de uso, não há foco. O
`hub.db` já grava `last_opened` e `open_count` (`core/hub_store.py`), mas
`open_count` nunca é lido e `last_opened` vira uma linha de texto cinza no rodapé
do card.

**1.3 — Existe paleta, não existe sistema visual.**
`ui/theme.py` acerta nos tokens de cor (dataclass `Palette`, tema claro e escuro
completos, nada hard-coded). Mas `Metrics` tem exatamente quatro números
(`radius`, `radius_lg`, `gap`, `padding`) e a tipografia é definida solta dentro
do QSS em pontos (`20pt`, `11pt`, `9pt`) sem escala, sem pesos coerentes, sem
tracking. Não há elevação, não há estado de foco desenhado, não há densidade
pensada. O resultado é o visual "label + card + 16px" que se repete em toda tela.

## 2. Objetivo

A Hub deve parecer **uma plataforma**, não um menu: uma janela só, com identidade
própria, onde entrar num aplicativo é uma transição clara de contexto e cada
aplicativo tem cor e presença próprias dentro de um sistema coerente.

Critérios de sucesso:

- Abrir um aplicativo **não** cria janela nova no Windows.
- Nenhuma sidebar duplicada: existe uma navegação global e uma navegação de
  telas do aplicativo atual, visualmente distintas.
- Nenhum arquivo dentro de `src/dumtech/apps/` é alterado.
- A suíte `unittest` continua verde (com os ajustes descritos na secao 6).
- A Hub roda de fato e é inspecionada visualmente nos dois temas antes de
  qualquer declaração de conclusão.

## 3. Arquitetura

### 3.1 Camadas

```
ui/theme.py            SISTEMA VISUAL   tokens, escalas, QSS  (base de tudo)
ui/widgets/            PEÇAS            card, nav, pill, paleta de comandos
ui/app_shell.py        CASCA            AppSurface: o app monta suas telas aqui
hub/workspace.py       HOSPEDEIRO       monta AppSurface dentro da Hub
hub/main_window.py     JANELA ÚNICA     trilho global + barra de contexto
apps/*                 INTOCADO         só consome setup_data/build_views/add_view
```

### 3.2 A mudança estrutural central: `AppWindow` -> `AppSurface`

Hoje `AppWindow(QMainWindow)` faz três coisas de uma vez: é janela, é casca
visual e é hospedeira das telas. Vamos separar:

- **`AppSurface(QWidget)`** — o que o aplicativo constrói. Mantém *exatamente*
  os mesmos ganchos públicos que os aplicativos já usam:
  `setup_data()`, `build_views()`, `add_view(title, icon, widget)`,
  `refresh_all()`, `teardown()`, `context`, `manifest`, `prefs`, `stack`.
  Deixa de desenhar sidebar, marca, botão de tema e botão "Voltar ao Hub".
  Passa a **expor** o que construiu: `views` -> tupla de `(title, icon_name, widget)`,
  para quem o hospeda desenhar a navegação como quiser.

- **`AppWindow(QMainWindow)`** — mantida como invólucro fino sobre `AppSurface`,
  para o modo avulso (testes e execução de um aplicativo sozinho). Preserva
  `windowTitle`, `stack`, `theme_mode`, `resolved_palette()`, `_apply_theme_mode()`.

Os `module.py` dos aplicativos continuam expondo `create_window(context)`; o que
muda é o que ele retorna internamente. Para não quebrar o contrato público
descrito em `core/app_module.py`, `create_window` passa a retornar um
`AppSurface` — que **é** um `QWidget`, exatamente o que o contrato já promete
("`create_window(context) -> QWidget`"). Nenhum `module.py` precisa mudar porque
todos apenas repassam a classe da janela, e a classe da janela apenas herda a
casca.

### 3.3 Fluxo de abertura

```
HomeView   --open_app(app_id)-->  HubWindow
HubWindow  -->  AppLauncher.open(app_id)
AppLauncher -->  registry.get() -> licença permite? -> entry.create_window(ctx)
AppLauncher -->  devolve AppSurface, guarda em _open[app_id]
HubWindow  -->  Workspace.mount(surface, manifest)   (empilha no QStackedWidget)
HubWindow  -->  trilho global marca o app como aberto/ativo
HubWindow  -->  hub_store.register_open(app_id)
```

Fechar um aplicativo (X no item do trilho ou Ctrl+W) chama `surface.teardown()`,
remove do stack e do `_open`, e volta para o Início.

### 3.4 Tema por aplicativo — mudança de comportamento declarada

Hoje cada aplicativo pode fixar tema próprio (`Seguir o Hub` / `claro` / `escuro`),
documentado no README. Numa janela única, um painel claro dentro de uma Hub
escura fica visualmente quebrado. Decisão:

- **No workspace**, o aplicativo segue o tema da Hub. Sempre.
- **No modo avulso** (`AppWindow`), a preferência continua sendo lida, gravada e
  respeitada — o código e o teste permanecem.
- O menu "Tema" some da casca do aplicativo (ele não tem mais sidebar); o
  controle de tema passa a ser um só, no trilho global.
- README atualizado para descrever o comportamento real.

Isto é uma redução deliberada de funcionalidade em nome da coerência visual, e
está registrada aqui para ser uma escolha, não um acidente.

## 4. O sistema visual (Camada 0)

`ui/theme.py` deixa de ser "paleta + QSS" e passa a ser design system. Os tokens
de cor atuais ficam como estão — estão certos. Acrescenta-se:

**Escala tipográfica** — uma função `font(role)` e papéis QSS derivados dela,
não pontos soltos espalhados. Papéis: `display`, `title`, `section`, `body`,
`bodyStrong`, `caption`, `overline` (maiúsculas, tracking positivo, usado nos
rótulos de grupo do trilho), `metric`, `mono` (números tabulares em tabelas e
valores). Pesos: 400 / 500 / 600 apenas. Tracking negativo nos tamanhos grandes,
positivo no `overline` — é o detalhe que separa tipografia intencional de padrão.

**Escala de espaçamento** — base 4: `Space.xs=4, sm=8, md=12, lg=16, xl=24, xxl=32`.
`Metrics.gap/padding` viram apelidos para não quebrar chamadas existentes.

**Raio** — `Radius.sm=8, md=10, lg=14, xl=18, pill=999`, coerente com o que já existe.

**Elevação** — três níveis (`flat`, `raised`, `overlay`) expressos como par
borda+fundo por paleta, já que QSS não tem sombra. `overlay` ganha
`QGraphicsDropShadowEffect` aplicado em código (paleta de comandos e diálogos).

**Estados** — foco visível e consistente (anel `accent` de 2px) em botões,
campos, itens de nav e linhas de tabela. Hoje o QSS começa com `* { outline: 0 }`
e nada substitui isso: navegar por teclado é invisível. Isso é acessibilidade
básica e é o tipo de detalhe que faz software parecer profissional.

**Densidade** — revisão das alturas mínimas e paddings. Hoje `Button` tem
`minimumHeight=36` e `NavButton` `42`, com `padding: 8px 16px` — folgado demais
para uma ferramenta de trabalho. Alvo: 32 (compacto) / 36 (padrão) / 40 (ação
primária), com o padding reduzido proporcionalmente.

## 5. As telas

### 5.1 Trilho global (esquerda, largura fixa, sempre visível)

```
DumTech HUB                (marca, compacta)
------------------
Buscar...        Ctrl+K    (abre a paleta de comandos)
Início
------------------
ABERTOS                    (overline; só aparece se houver algum)
* Vendas               X   (ponto na cor do app; X no hover)
* Estoque              X
------------------
APLICATIVOS                (overline)
  Clientes                 (todos os liberados, ordenados por uso)
  Financeiro
  ...
------------------
Tema                       (rodapé)
Licença
Sobre
v1.0.0
```

Os itens de aplicativo mostram o ícone na cor do próprio app quando ativos e em
`text_muted` quando não. Aplicativo aberto ganha indicador; aplicativo ativo
ganha barra de 3px na cor do app na borda esquerda do item.

### 5.2 Barra de contexto (topo da área de conteúdo)

Aparece **apenas** quando um aplicativo está montado. Contém: ícone e nome do
aplicativo à esquerda (fundo tingido com `manifest.accent` em baixa opacidade),
a faixa horizontal de telas do aplicativo (`views` do `AppSurface`) e as ações
do aplicativo à direita. É a transição de contexto que hoje não existe.

### 5.3 Início (`hub/views/home_view.py`, substitui `apps_view.py`)

1. **Cabeçalho** — saudação e uma linha de estado real da plataforma
   (aplicativos liberados, situação da licença), não um título decorativo.
2. **Continuar** — até 3 aplicativos mais usados (`open_count`) com o último
   acesso, em cartões largos e horizontais. Dá à tela um ponto de entrada óbvio
   e finalmente usa os dados que o `hub.db` já coleta.
3. **Aplicativos por categoria** — `manifest.category` já existe e nunca foi
   usado ("Gestao", "Vendas", ...). Vira o agrupamento, com `overline` por grupo.
4. **Cartão de aplicativo redesenhado** — mais baixo e mais largo que o atual
   (252×288 é quase quadrado e desperdiça altura), com a faixa de cor do app,
   ícone, nome curto como título, descrição em duas linhas, e metadados
   (versão, último acesso) em `caption` discreto. Sem a pill "Disponivel"
   redundante — na tela Início *tudo* está disponível; o que está bloqueado vive
   na tela Licença.
5. **Estado vazio** (sem licença) permanece, com o visual novo.

### 5.4 Paleta de comandos (`ui/widgets/command_palette.py`)

`Ctrl+K` em qualquer lugar. Overlay centralizado sobre a janela, com sombra.
Digitar filtra por prefixo e por subsequência. Comandos:

- abrir aplicativo (`Vendas`)
- abrir tela específica de aplicativo aberto (`Vendas > Painel`)
- ir para Início / Licença / Sobre
- alternar tema
- fechar aplicativo atual

Setas navegam, Enter executa, Esc fecha. Sem dependência nova: `QLineEdit` +
`QListView` com um modelo simples.

### 5.5 Licença e Sobre

Não são reescritas — recebem o sistema visual novo e a mesma estrutura de
cabeçalho da tela Início, para deixarem de parecer telas de outro produto.

## 6. Execução em camadas

Cada camada termina com o programa rodando e a suíte verde. Nenhuma camada
depende de uma camada posterior.

**Camada 0 — sistema visual.** `ui/theme.py`. Escalas, elevação, foco, densidade,
QSS reorganizado. Sem mudança estrutural. Ganho visível imediato na Hub e nos 7
aplicativos, já que todos herdam a mesma folha.

**Camada 1 — casca hospedável.** `ui/app_shell.py` dividido em `AppSurface` +
`AppWindow`. Comportamento idêntico ao de hoje (ainda em janelas separadas),
apenas com a casca separada da janela. Testes ajustados.

**Camada 2 — workspace.** `hub/workspace.py` novo, `hub/main_window.py` e
`hub/launcher.py` reescritos: trilho global, barra de contexto, montagem do
aplicativo dentro da Hub, fechamento, `Ctrl+W`. Aqui as janelas separadas somem.

**Camada 3 — Início.** `hub/views/home_view.py` e `ui/widgets/app_card.py`.
`apps_view.py` é removido.

**Camada 4 — paleta de comandos.** `ui/widgets/command_palette.py` e o atalho
global.

**Camada 5 — acabamento.** Licença e Sobre no sistema novo, README atualizado
(janela única, tema, capturas), varredura final nos dois temas.

### Testes ao longo das camadas

`tests/test_interface.py` referencia `launcher._windows[app_id]`,
`janela.windowTitle()` e `janela.stack.count()`. Com o workspace, o launcher
passa a guardar `AppSurface` em `_open[app_id]`. O teste é atualizado para a
estrutura nova preservando o que ele de fato verifica: todo aplicativo liberado
abre, reabrir reaproveita a instância, aplicativo inexistente não abre, e os
dados chegam na tela. Os testes de tema por aplicativo passam a exercitar o modo
avulso (`AppWindow`), que é onde a funcionalidade continua existindo.

Testes novos: montar e desmontar aplicativo no workspace não vaza (`teardown`
chamado, `_open` esvaziado); `AppSurface.views` devolve as telas na ordem em que
foram adicionadas; a paleta de comandos encontra um aplicativo por nome parcial.

## 7. Riscos

| Risco | Mitigação |
|---|---|
| Refatorar a casca quebra os 7 aplicativos | A API pública (`setup_data`/`build_views`/`add_view`/`refresh_all`) não muda; `test_interface` abre todos os aplicativos e é a rede de segurança |
| `teardown()` deixa banco aberto ao trocar de app no workspace | O workspace mantém o `AppSurface` montado enquanto o app estiver "aberto"; `teardown` só ao fechar de fato. Teste específico |
| Janela única fica apertada em telas pequenas | Mínimo da Hub sobe para 1100×700 (os apps já pediam 980×640 dentro de suas janelas); trilho recolhível se necessário |
| Perda do tema por aplicativo | Decisão declarada em 3.4, preservada no modo avulso, README corrigido |
