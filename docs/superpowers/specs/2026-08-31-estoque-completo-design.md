# DumTech Estoque — de CRUD a estoque de verdade

**Data:** 2026-08-31
**Escopo:** `src/dumtech/apps/estoque/`.
**Fora de escopo:** os outros seis aplicativos, o Hub e a casca compartilhada.

---

## 1. Problema

O Estoque de hoje cadastra produto e movimenta um item por vez. Falta o que uma
loja usa todo dia:

- **Dar baixa é lento.** Para movimentar um produto que está na sua frente na
  lista, o usuário precisa trocar de tela e procurar o item num `QComboBox` que
  lista o catálogo inteiro. Com 300 produtos isso é inviável.
- **Não existe código de barras.** O leitor USB é o periférico mais comum do
  balcão brasileiro e o módulo não tem onde receber a leitura.
- **Quantidade é inteira** (`quantidade INTEGER`). Loja de cabo, tecido ou
  material de construção não consegue usar.
- **Chegada de mercadoria é item a item.** Uma nota com 15 produtos são 15
  idas ao formulário.
- **O custo é digitado à mão e nunca mais muda**, então "valor em estoque" é um
  número que envelhece sozinho.
- **Sem importar/exportar.** Começar a usar com 200 itens exige digitação manual.
- **Excluir produto apaga o cadastro** e deixa o histórico órfão
  (`ON DELETE SET NULL`).
- **Sem contagem física.** Não há como conferir o estoque real contra o sistema.

## 2. O que este trabalho NÃO faz, e por quê

Decisões de corte, registradas para não voltarem por engano:

- **Sem lote e validade (FEFO).** Controle correto exige saldo por lote e saída
  consumindo o lote que vence primeiro — isso dobra a complexidade de toda
  saída. Quem precisa disso no Brasil (farmácia, alimento) tem obrigação legal
  de SNGPC/ANVISA e compra software especializado. Não é o comprador deste
  produto.
- **Sem cadastro de fornecedores.** Fornecedor é um campo de texto com
  autocompletar dos valores já usados, no mesmo padrão que `categoria` já segue.
  Cobre o uso real sem uma tabela, uma tela e um CRUD.
- **Sem módulo de compras.** Uma tabela de notas duplicaria o histórico. A
  entrada em lote grava várias `movimentacoes` numa transação, carregando
  fornecedor, documento e custo. Uma fonte da verdade.
- **Sem curva ABC nem "produtos sem giro".** Dono de loja pergunta duas coisas:
  o que preciso comprar e quanto tenho parado. Essas duas ficam, no painel.
  Não há tela de relatórios.

## 3. Modelo de dados (migração v2)

O banco do Estoque está na versão 1. A migração 2 reconstrói as duas tabelas
(SQLite não altera tipo de coluna) preservando os dados.

### produtos

| Coluna | Mudança | Por quê |
|---|---|---|
| `quantidade` | INTEGER → **REAL** | vender 1,5 kg / 2,75 m |
| `estoque_minimo` | INTEGER → **REAL** | idem |
| `estoque_maximo` | **nova** REAL, 0 | sem ela dá para dizer *que* comprar, não *quanto* |
| `unidade` | **nova** TEXT, `'UN'` | define as casas decimais exibidas |
| `codigo_barras` | **nova** TEXT, `''` | leitura do leitor USB; único quando preenchido |
| `fornecedor` | **nova** TEXT, `''` | de quem se compra normalmente |
| `localizacao` | **nova** TEXT, `''` | onde está na prateleira |
| `ativo` | **nova** INTEGER, 1 | inativar em vez de excluir |
| `preco_custo` | mesma coluna, **novo significado** | passa a ser o custo médio, recalculado a cada entrada com custo |

`codigo_barras` ganha índice único parcial
(`CREATE UNIQUE INDEX ... WHERE codigo_barras <> ''`): vários produtos podem
ficar sem código, mas dois não podem repetir o mesmo.

**Unidades:** `UN`, `CX`, `PC`, `KG`, `G`, `L`, `M`, `M2`, `M3`. Cada uma
declara suas casas decimais (0 para as contáveis, 3 para as de medida) numa
tabela `UNIDADES` em `models.py`. A formatação e os campos de entrada da
interface usam esse número — é o único lugar que decide isso.

**Custo médio:** numa entrada com `custo_unitario > 0`,
`novo_custo = (saldo * custo_atual + qtd * custo_unitario) / (saldo + qtd)`.
Continua editável à mão no cadastro; a entrada seguinte recalcula.

### movimentacoes

| Coluna | Mudança |
|---|---|
| `quantidade`, `saldo_anterior`, `saldo_atual` | INTEGER → **REAL** |
| `fornecedor` | **nova** TEXT, `''` |
| `documento` | **nova** TEXT, `''` — número da nota |
| `custo_unitario` | **nova** REAL, 0 |

`ON DELETE SET NULL` continua, mas passa a ser exceção: excluir só é oferecido
para produto que nunca se movimentou; o resto se inativa.

### contagem_itens (nova)

```sql
CREATE TABLE contagem_itens (
    produto_id    INTEGER PRIMARY KEY REFERENCES produtos(id) ON DELETE CASCADE,
    contado       REAL NOT NULL,
    atualizado_em TEXT NOT NULL
);
```

Uma folha de contagem ativa por vez — é assim que o balanço acontece na prática
(conta-se, confere-se, aplica-se). "Aplicar" gera um ajuste por divergência,
numa transação, e limpa a folha.

## 4. Regras (repository)

`repository.py` hoje tem 314 linhas e vai crescer. Divide-se em um pacote
`repository/` com quatro arquivos e uma fachada:

```
repository/
├── __init__.py     EstoqueRepository: junta as partes (o que as telas usam)
├── produtos.py     cadastro, busca, ativação, custo médio
├── movimentacoes.py  entrada, saída, ajuste, entrada em lote, histórico
├── contagem.py     folha de contagem e aplicação dos ajustes
└── planilha.py     importar e exportar CSV
```

A classe `EstoqueRepository` continua sendo o único nome que a interface
importa, com a mesma assinatura dos métodos que já existem — as telas atuais não
quebram.

**Regras novas:**

- `buscar(termo)` procura por código de barras, depois por código, depois por
  nome. É o que o campo de bipe chama: o leitor manda o EAN, mas o usuário
  também pode digitar "mou" e achar o mouse.
- `movimentar(...)` passa a aceitar `custo_unitario`, `fornecedor` e
  `documento`; entrada com custo recalcula o custo médio do produto.
- `entrada_em_lote(itens, fornecedor, documento)` grava tudo numa transação:
  ou a nota inteira entra, ou nada entra.
- `inativar(id)` / `reativar(id)`; `excluir(id)` só passa se o produto não tem
  movimentação, e explica quando recusa.
- `a_comprar()` devolve os produtos no mínimo ou abaixo com a sugestão de
  compra (`estoque_maximo - quantidade`, ou o mínimo quando não há máximo).
- `importar_csv(texto)` roda em dois tempos: `prever` devolve o que seria
  criado, atualizado e recusado; `aplicar` executa. O usuário vê antes.

**Erros:** tudo continua levantando `EstoqueError` com mensagem pronta para a
tela — sem `QMessageBox` no meio das regras.

## 5. Telas

Cinco, contra as três de hoje: **Painel · Produtos · Entradas · Movimentações ·
Contagem**.

### Produtos

Ganha, no topo, um **campo de bipe**: o leitor USB digita o código e dá Enter;
o produto é localizado e a baixa rápida abre já preenchida. Digitação manual
funciona igual.

Na tabela: unidade junto da quantidade, localização, margem calculada
(`(venda - custo) / venda`) e situação. Filtros de categoria, estoque baixo e
**inativos** (escondidos por padrão).

Teclado: `E` dá entrada e `S` dá saída no produto selecionado, abrindo um
diálogo pequeno já com o produto — sem trocar de tela. É a correção do problema
mais sentido.

Rodapé com **Importar** e **Exportar** CSV.

### Entradas

A chegada de mercadoria. Fornecedor e número da nota no topo; abaixo, linhas
com produto (por bipe ou busca), quantidade e custo unitário; total somando ao
vivo. "Confirmar entrada" grava tudo de uma vez e atualiza os custos médios.

### Movimentações

O histórico de hoje, com os filtros ampliados (tipo, período, fornecedor) e as
colunas novas (documento, custo). O formulário de movimentação avulsa continua.

### Contagem

Duas colunas: o que o sistema diz e o que você contou. Bipar ou buscar o
produto, digitar a quantidade encontrada, e a divergência aparece na hora.
"Aplicar ajustes" fecha a contagem gerando o histórico.

### Painel

Responde as duas perguntas do dono:

- **O que preciso comprar** — lista de reposição com a sugestão de quantidade.
- **Quanto tenho parado** — valor em estoque pelo custo médio, com os produtos
  de maior valor acumulado.

Mais os números de sempre (produtos, itens, estoque baixo) e as últimas
movimentações.

## 6. Camadas

Cada camada termina com o programa rodando e a suíte verde.

**Camada 1 — banco e regras.** Migração v2, `repository/` dividido, quantidade
decimal, unidades, custo médio, busca por código de barras, ativo/inativo.
Testes das regras novas. As três telas atuais continuam funcionando.

**Camada 2 — cadastro e lista.** `ProdutoDialog` com os campos novos;
`ProdutosView` com unidade, margem, localização e o filtro de inativos.

**Camada 3 — velocidade.** Campo de bipe, atalhos `E`/`S`, diálogo de baixa
rápida.

**Camada 4 — entradas e contagem.** As duas telas novas.

**Camada 5 — CSV e painel.** Importar com prévia, exportar, painel novo.

## 7. Testes

As regras são testáveis sem abrir janela e é onde a cobertura vai. Casos que
precisam existir:

- migração v1 → v2 preserva produtos e movimentações de um banco antigo;
- quantidade decimal sobrevive à ida e volta ao banco (1,5 kg continua 1,5);
- custo médio: duas entradas com custos diferentes dão a média ponderada;
- saída maior que o saldo continua recusada, com a mensagem certa;
- entrada em lote é atômica: se uma linha falha, nenhuma entra;
- `buscar` encontra por código de barras, por código e por nome, nessa ordem;
- excluir produto com movimentação é recusado; inativar funciona e some da lista;
- contagem aplica ajuste só onde há divergência;
- importar CSV: a prévia conta certo o que cria, atualiza e recusa;
- `a_comprar` sugere `maximo - quantidade`, e o mínimo quando não há máximo.

O teste de fumaça da interface continua abrindo o aplicativo dentro do Hub e
conferindo que as cinco telas montam.

## 8. Riscos

| Risco | Mitigação |
|---|---|
| A migração v2 reconstrói tabelas e pode perder dados do cliente | Teste dedicado que cria um banco v1 com dados, migra e confere linha a linha |
| `preco_custo` muda de significado | Continua editável; a mudança é só o recálculo automático na entrada. Documentado no README do módulo |
| Quantidade decimal quebra telas que assumem inteiro | Formatação central em `models.UNIDADES` + `fmt`; a suíte cobre os dois casos |
| Cinco abas deixam a barra de contexto cheia | Rótulos curtos; a barra já foi medida com sete e coube |
