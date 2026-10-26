# Como a plataforma DumTech funciona

## A ideia em uma frase

O **Hub** e uma casca: ele descobre quais aplicativos estao instalados, pergunta a
licenca quais podem ser abertos e mostra um card para cada um. Ele nao sabe nada
sobre o que existe dentro de um aplicativo.

```
                      +------------------+
                      |   DumTech Hub    |
                      +------------------+
                               |
             +-----------------+-----------------+
             |                 |                 |
        registry.py       licensing.py       launcher.py
     "quais apps        "quais apps o        "abre a janela
      existem?"          cliente pagou?"      do aplicativo"
             |
   +---------+----------+-----------------+-----------------+
   |                    |                 |                 |
apps/estoque      apps/financeiro     apps/vendas      apps/agenda
 (module.py)        (module.py)        (module.py)      (module.py)
      ...            apps/clientes    apps/orcamentos   apps/ordens
```

Hoje a plataforma traz sete aplicativos (Estoque, Clientes, Financeiro,
Orcamentos, Vendas, Ordem de Servico e Agenda) e todos foram escritos seguindo
exatamente o mesmo desenho descrito abaixo.

## O contrato de um aplicativo

Cada aplicativo mora em `src/dumtech/apps/<id>/` e expoe **apenas duas coisas** no
arquivo `module.py`:

```python
MANIFEST = AppManifest(
    app_id="estoque",              # identificador tecnico
    name="DumTech Estoque",        # nome comercial
    short_name="Estoque",          # nome no card
    description="...",             # frase do card
    icon="box",                    # icone (ver ui/icons.py)
    accent="#8A7BF8",              # cor do aplicativo
)

def create_window(context: AppContext):
    from .ui.window import EstoqueWindow
    return EstoqueWindow(context)
```

O `AppContext` entregue pelo Hub traz:

- `context.manifest` - a identidade do aplicativo;
- `context.db_path` - **o banco de dados exclusivo daquele aplicativo**
  (`%APPDATA%\DumTech Hub\data\apps\<id>.db`);
- `context.paths` - as pastas da plataforma.

Ou seja: um aplicativo nunca mexe nos dados de outro, e cada um evolui seu proprio
esquema de banco sem afetar os demais.

## Como adicionar um novo aplicativo (ex.: Financeiro)

1. **Criar a pasta** `src/dumtech/apps/financeiro/` copiando a estrutura do
   estoque:

   ```
   financeiro/
   ├── module.py       MANIFEST + create_window
   ├── database.py     tabelas do financeiro.db
   ├── models.py       estruturas de dados
   ├── repository.py   regras (sem interface)
   └── ui/window.py    janela do aplicativo
   ```

2. **Registrar o modulo** em `src/dumtech/apps/__init__.py`:

   ```python
   INSTALLED_APPS = (
       "dumtech.apps.estoque.module",
       "dumtech.apps.financeiro.module",   # <- nova linha
   )
   ```

3. **Liberar na licenca**: no desenvolvimento basta incluir o id em
   `DEFAULT_ENTITLEMENTS` (`core/licensing.py`). Para vender, o modulo precisa
   virar um registro em `produtos` no Supabase (bloco 4 de
   `docs/supabase/operacoes_admin.sql`) - o codigo e o id em maiuscula. Dai ele
   chega ao Hub no campo `entitlements`, vindo da licenca.

4. **Empacotar**: acrescentar o modulo em `hiddenimports` no
   `build/dumtech_hub.spec` (o Hub importa por nome, entao o PyInstaller precisa
   ser avisado).

Nada no Hub precisa ser alterado: o card novo aparece sozinho.

## O que os aplicativos ganham de graca

A classe `AppWindow` (`ui/app_shell.py`) e a casca de todo aplicativo. Herdando
dela, o aplicativo ja nasce com:

- menu lateral com a marca DumTech e a cor do proprio aplicativo;
- troca de telas ligada ao menu (`self.add_view("Painel", "dashboard", widget)`);
- **seletor de tema por aplicativo** (Seguir o Hub / Sempre claro / Sempre escuro),
  gravado nas preferencias e reaplicado nas proximas aberturas;
- botao "Voltar ao Hub" e o encerramento correto do banco (`teardown()`).

Alem disso, `ui/widgets/` oferece pecas prontas que ja seguem o tema:

| Peca | Para que serve |
|---|---|
| `CrudView` | tela de listagem completa (pesquisa, filtros, tabela, Novo/Editar/Excluir) |
| `FormDialog` + `form.*` | formularios com campos de texto, dinheiro, data, escolha e sugestao |
| `ItemsEditor` | lista de itens de orcamentos e vendas |
| `StatCard` / `ListPanel` | os cartoes e listas dos paineis |
| `DataTable` | tabela padrao, com celulas coloridas por token do tema |

## Temas

`ui/theme.py` define duas paletas (`DARK` e `LIGHT`) e monta a folha de estilo a
partir delas. Regras importantes:

- **nenhuma cor escrita solta no codigo**: use tokens (`"accent"`, `"danger"`...)
  ou papeis de estilo (`label(texto, "muted")`, `Pill(texto, "success")`);
- o Hub tem um `ThemeManager` que aplica o tema na aplicacao inteira e avisa quem
  estiver escutando (`changed`);
- cada janela pode ter o proprio tema com `apply_window_theme(janela, paleta)` -
  e o que permite um aplicativo ficar claro enquanto o resto esta escuro;
- widgets que desenham cor propria (icones, badges) implementam
  `apply_theme(palette)`; a plataforma percorre a janela chamando esse metodo.

## Regras de convivencia

- **A interface nunca fala com o banco direto.** Telas usam o `repository` do seu
  aplicativo; as regras (ex.: "saida nao pode deixar saldo negativo") ficam la e
  podem ser testadas sem abrir janela.
- **Cores e estilos so em `ui/theme.py`.** Isso mantem todos os aplicativos com a
  mesma cara e permite mudar o visual da plataforma inteira em um lugar so.
  Evite `setStyleSheet` em widgets que tem filhos: a folha local ganha prioridade
  e "apaga" o estilo dos filhos.
- **Um banco por aplicativo**, com migracoes numeradas em `database.py`. A unica
  excecao e a agenda de clientes (`core/contacts.py`), que e da plataforma: o
  Clientes administra e os outros aplicativos apenas leem os nomes para sugerir.
  Nenhum aplicativo depende de outro para funcionar. A versao
  aplicada fica gravada no proprio arquivo (`PRAGMA user_version`), entao
  atualizacoes futuras nao perdem dados do cliente.
- **Nenhum acesso a internet e obrigatorio** no funcionamento diario. A rede so
  entra no que o dono liga: licenca, celular e o link de agendamento da Agenda.
  Um modulo com parte online expoe `online(paths, empresa)` no `module.py`
  (contrato em `core/online.py`): ele le o proprio banco na thread da tela, o
  Hub conversa com o servidor em segundo plano e devolve a resposta para o
  modulo gravar. O Hub continua sem saber o que existe dentro do modulo.
- **Um aplicativo com defeito nao derruba o Hub**: falhas ao carregar ou abrir um
  aplicativo sao registradas no log e viram aviso na tela.
