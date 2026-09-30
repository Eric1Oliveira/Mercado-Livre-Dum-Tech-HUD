# DumTech Vendas — o QR Code do Pix no balcao

Data: 2026-09-09
Status: aprovado

## O problema

`Pix` ja aparece na lista de formas de pagamento do Vendas
(`apps/vendas/models.py`), mas e so um rotulo: escolher Pix nao produz nada. Na
pratica o balcao resolve por fora — o operador abre o aplicativo do banco no
proprio celular, gera o QR ali, vira o aparelho para o cliente e depois digita o
valor no sistema.

Isso custa o que sempre custa: tempo com a fila esperando, e o valor digitado
duas vezes em lugares diferentes, com a chance de sair diferente.

O que falta e o QR **da venda**, com o valor **da venda**, na tela onde a venda
esta sendo fechada.

## A decisao que define tudo: Pix estatico

O Pix tem dois caminhos, e eles nao sao dois tamanhos da mesma coisa — sao
produtos diferentes.

O **dinamico** fala com o banco (PSP) por API, devolve uma cobranca e avisa
quando o dinheiro cai. Confirmacao automatica. Em troca exige internet,
credencial e certificado por lojista, e um contrato que cada cliente teria que
assinar com o banco dele. Isso quebra a promessa que a plataforma faz na
primeira linha do README — funciona sem internet — e transforma "usar Pix" num
cadastro tecnico.

O **estatico** e montado aqui mesmo, a partir da chave Pix do lojista, com o
valor da venda dentro. Nao precisa de banco, de cadastro, de mensalidade nem de
internet. E o que este documento especifica.

O preco do estatico e uma limitacao real, e ela precisa estar escrita: **o
sistema nao sabe se o cliente pagou.** Quem confirma e o operador, olhando o
aplicativo do banco. O desenho inteiro tem que ser honesto sobre isso — e o
motivo da linha de aviso na seccao do dialogo.

## Onde aparece: so no balcao

So no dialogo de Receber (`apps/vendas/ui/pagamento_dialog.py`). E o unico ponto
do sistema com alguem esperando na fila, e o caso que foi pedido.

Comprovante impresso, Ordens de Servico e Orcamentos ficam **de fora**. O
`core/pix.py` nasce posicionado para atender esses depois — mas nao se constroi
agora o que ninguem pediu.

## As pecas

### `core/pix.py` — o payload, sem Qt

Segue o desenho do resto de `core/`: regra pura, sem interface, testavel sozinha.

```python
@dataclass(frozen=True)
class CobrancaPix:
    chave: str
    beneficiario: str
    cidade: str
    valor: float = 0.0
    documento: str = ""      # VEN-2026-0001 -> vira o txid

def payload(cobranca: CobrancaPix) -> str   # o "Pix copia e cola"
def tipo_chave(chave: str) -> str           # CPF, CNPJ, telefone, email, aleatoria
def normalizar(chave: str) -> str           # 11999998888 -> +5511999998888
```

O BR Code e uma cadeia de campos `ID(2) + tamanho(2) + valor`, fechada por um
CRC16. Os campos que importam para o Pix estatico:

| ID | Conteudo |
|----|----------|
| 00 | formato do payload (`01`) |
| 26 | conta do recebedor: GUI `br.gov.bcb.pix` + a chave |
| 52 | categoria do comerciante (`0000`) |
| 53 | moeda (`986`, real) |
| 54 | valor (`150.00`) — ausente quando o valor e zero |
| 58 | pais (`BR`) |
| 59 | nome do recebedor (max 25) |
| 60 | cidade do recebedor (max 15) |
| 62 | dados adicionais: o `txid` |
| 63 | CRC16 |

Quatro detalhes decidem se o aplicativo do banco le ou recusa, e cada um vira
teste:

- **nome e cidade sem acento e em maiusculas.** "Sao Joao del-Rei" precisa virar
  "SAO JOAO DEL-REI", e ser cortado em 15 caracteres sem quebrar o campo.
- **valor com ponto**, nunca virgula: `150.00`. Valor zero significa QR sem
  valor — o cliente digita quanto vai pagar, e isso e valido.
- **o `txid` so aceita letra e numero.** `VEN-2026-0001` vira `VEN20260001`.
- **o CRC entra sobre a cadeia ja incluindo `6304`**, nao antes.

Reaproveita `core/documentos.py` (`so_digitos`, validacao de CPF/CNPJ) em vez de
reimplementar o que ja existe.

### `ui/widgets/qr.py` — desenhar

O encoder e a biblioteca `qrcode` (BSD, Python puro; traz `colorama`, minusculo).
Ela devolve a matriz; quem pinta o `QPixmap` e o `QPainter`, no mesmo padrao de
`ui/icons.py`. Nao entra PIL: a matriz basta.

**O QR sai sempre preto no branco, com a margem branca — inclusive no tema
escuro.** E a unica coisa da plataforma que ignora o tema, e ignora de proposito:
QR invertido falha em muito leitor, e falhar aqui e o cliente parado no balcao
sem conseguir pagar.

### A chave fica em "Minha empresa"

Um campo `pix_chave` no dataclass `Empresa` (`core/empresa.py`). Persiste sozinho
— `carregar`/`salvar` percorrem `fields(cls)`, entao nao ha migracao. Fica no
Hub, e nao no Vendas, porque e a conta do lojista: vale para a plataforma toda.

`Empresa.validar()` passa a recusar chave que nao caiba em nenhum dos cinco
formatos: CPF (11 digitos), CNPJ (14), telefone (10 ou 11 digitos), e-mail (tem
`@` e ponto depois dele) e aleatoria (36 caracteres no formato UUID). Campo
vazio continua valido — quem nao usa Pix nao e obrigado a preencher.

Quando nome ou cidade estao vazios, o QR ainda e gerado: entra `LOJA` no nome e
`BRASIL` na cidade. Um QR que paga com a cidade generica e melhor que nenhum QR
— nem o nome nem a cidade influenciam para onde o dinheiro vai, eles so aparecem
na tela de confirmacao do celular.

### O painel no dialogo de Receber

Escolher `Pix` na forma abre um painel dentro do proprio dialogo:

- **o QR, ~190px**, refeito a cada mudanca do campo "Valor" — entao pagamento
  parcial em Pix funciona sem nada a mais;
- **o copia e cola com um botao Copiar** — nao e enfeite: e o que salva quando a
  camera nao foca, e muito cliente prefere colar;
- **a linha de aviso:** *"Confira o recebimento no seu aplicativo antes de
  lancar."*

Essa linha e a parte mais importante do desenho. O sistema nao pode insinuar que
confirmou um pagamento que ele nao tem como ver.

Sem chave cadastrada, o painel diz o que falta e aponta para Minha empresa. A
forma "Pix" continua funcionando como funciona hoje — ninguem fica impedido de
vender por causa de um campo em branco.

O dialogo cresce quando o Pix e escolhido e volta ao tamanho quando sai dele; as
outras formas nao mudam em nada.

## Testes

`core/pix.py` e logica pura, entao trava de verdade:

- **o CRC16 contra o vetor de conferencia do proprio algoritmo** —
  CRC-16/CCITT-FALSE de `"123456789"` e `0x29B1`. Este e o ancoradouro: e o valor
  publicado do algoritmo, verificavel sem depender de nenhum payload de exemplo.
- **round-trip estrutural** — remontar a cadeia campo a campo e conferir que cada
  ID carrega o tamanho e o conteudo esperados.
- **os casos que quebram na vida real** — acento no nome da loja, nome maior que
  25 caracteres, cidade maior que 15, valor zero, e uma chave de cada tipo.

O painel ganha teste de fumaca no padrao de `tests/test_vendas.py`: escolher Pix
mostra o QR, trocar o valor refaz o payload, e sem chave cadastrada o dialogo
avisa em vez de quebrar.

### A verificacao que nenhum teste meu substitui

Antes de considerar isto pronto, **um QR gerado pelo sistema precisa ser lido
por um aplicativo de banco de verdade**, conferindo que o valor e o recebedor
aparecem certos na tela do celular. Isto e dinheiro: teste automatizado prova que
a cadeia esta bem formada, nao que o banco aceita. Esta validacao e manual e e
obrigatoria.

## O que este documento nao faz

- Nao confirma pagamento, e nao tenta parecer que confirma.
- Nao toca no comprovante impresso, nas Ordens nem nos Orcamentos.
- Nao guarda o payload no banco: o QR e derivado da venda e da chave, e se
  refaz sempre. Nao ha estado novo para migrar.
