# Computadores da licença — a área do dono

## O buraco que isto fecha

Uma licença DumTech vale para N computadores (`licencas.max_computadores`).
Cada ativação vira uma linha em `ativacoes`, e o servidor recusa a de número
N+1 com `limite_maquinas`.

Para liberar uma vaga existe `dumtech_desativar_licenca(chave, maquina)` — e
hoje **quem chama é o botão "Remover licença deste computador"**, na tela
Licença do Hub. Repare na palavra: *deste*.

> O cliente só consegue liberar a vaga a partir do próprio computador que quer
> liberar.

Computador queimado, roubado, vendido ou formatado deixa a vaga presa para
sempre. O cliente não tem saída: ele liga para a DumTech, e alguém resolve na
mão, direto no banco. O painel mostra as ativações, mas só leitura — não há
botão para soltar vaga.

Esta área dá ao dono da licença o controle que hoje é da DumTech.

## O que ela faz, e o que ela não faz

| Faz | Por quê |
|---|---|
| Lista os computadores: apelido, ativado em, última vez visto, e qual é *este* | sem "última vez visto" ninguém distingue o computador que queimou do que está em uso |
| Renomeia um computador | vaga sem nome não se gerencia; "Balcão" e "Escritório" resolvem |
| Solta a vaga de **qualquer** computador, inclusive um que não liga mais | é o buraco descrito acima |
| Troca o PIN sabendo o PIN atual | troca de rotina não deveria depender do e-mail |

**Fora do escopo: mudar `max_computadores`.** Comprar vaga é compra, e passa
pela loja. Se o cliente pudesse aumentar o próprio limite aqui, estaria se
dando licença de graça.

## Onde mora

**Dentro do Hub**, não na web. A consequência a assumir: se o cliente tem UMA
licença de um computador só e esse computador morre, a área morre junto e o
suporte continua sendo a DumTech. Para licença de duas ou mais máquinas — que é
o caso que motiva a área — qualquer computador vivo resolve o morto.

## A autenticação

```
PRIMEIRA VEZ                DEPOIS                ESQUECEU O PIN
─────────────               ──────                ──────────────
código por e-mail           digita o PIN          código por e-mail
      ↓                           ↓                      ↓
   cria o PIN              sessão de 15 min        define um PIN novo
```

### Por que criar o PIN também exige e-mail

É a decisão que sustenta a segurança inteira. Se o PIN pudesse ser criado só
por estar na frente do computador, **o primeiro que sentasse no balcão** o
definiria — e passaria a mandar nas licenças do dono, podendo soltar a máquina
dele.

O e-mail é o que prova quem é o dono: ele vive no servidor, ligado à licença, e
não é o que o Hub diz ser. O PIN não substitui essa prova; ele só encurta o
caminho nas vezes seguintes.

Vale dizer com todas as letras, porque muda como se pensa o recurso:

> **O PIN nunca é mais forte que o e-mail que o redefine.** Ele é conveniência,
> não proteção adicional. Quem controla o e-mail da licença controla a área,
> com PIN ou sem.

### Contra força bruta

Seis dígitos são um milhão de combinações — pouco para um atacante com
tentativas infinitas, mesmo com hash lento. Então:

- **5 erros seguidos travam a licença por 15 minutos**, e a janela dobra a cada
  nova sequência de erros (15 → 30 → 60, teto de 60).
- A contagem é **do servidor, por licença**. No computador não serve: bastaria
  reinstalar o Hub para zerar.
- O `bloqueado_ate` vale para todos os computadores da licença. É um preço
  aceitável: quem está errando o PIN da própria loja tem o e-mail à mão.

### Hash

O PIN usa `crypt()` com `gen_salt('bf')` (bcrypt, pgcrypto — já instalado no
projeto). **Não** o `sha256` simples de `dumtech_pag_hash`: aquele protege um
código de seis dígitos que vive dez minutos e aceita cinco tentativas; este
protege um segredo que vive meses.

O código do e-mail e o segredo da sessão continuam com o padrão de hash já
usado em pagamentos — para eles, a vida curta é a proteção.

## Dados

Três tabelas novas:

```sql
licenca_pin
    licenca_id     uuid primary key references licencas(id) on delete cascade
    pin_hash       text not null            -- bcrypt
    erros          integer not null default 0
    bloqueado_ate  timestamptz
    criado_em      timestamptz not null default now()
    atualizado_em  timestamptz not null default now()

admin_codigos                                -- 6 dígitos, 10 min, 5 tentativas
    id           uuid primary key default gen_random_uuid()
    licenca_id   uuid not null references licencas(id) on delete cascade
    maquina      text not null
    codigo_hash  text not null
    criado_em    timestamptz not null default now()
    expira_em    timestamptz not null
    tentativas   integer not null default 0
    usado_em     timestamptz

admin_sessoes                                -- 15 min
    sessao_hash  text primary key
    licenca_id   uuid not null references licencas(id) on delete cascade
    maquina      text not null
    computador   text not null
    criado_em    timestamptz not null default now()
    expira_em    timestamptz not null
```

**O PIN é da licença, não do computador.** O dono usa o mesmo em qualquer
máquina da loja — é assim que ele resolve o computador morto a partir de outro.

### Por que tabelas separadas das de pagamento

`admin_codigos` e `admin_sessoes` têm quase o mesmo formato de
`pagamento_codigos` e `pagamento_sessoes`. Daria para generalizar com uma
coluna `uso`.

Não vamos: aquelas tabelas protegem **dinheiro** (a chave Pix do balcão), estão
em produção e são cobertas por bateria própria. Duplicar o formato custa umas
poucas linhas de SQL; compartilhar a tabela significa que todo erro futuro
numa área respinga na outra. Isolamento vale mais que a economia.

## Superfície da API

Uma Edge Function `computadores`, com rotas — mesmo desenho de `pagamentos`:
todas as funções SQL são de `service_role`, e a chave `anon` não enxerga
tabela nem função nenhuma daqui.

| Rota | Entrada | Faz |
|---|---|---|
| `codigo` | chave, máquina | gera o código e manda ao e-mail **da licença**; devolve o e-mail mascarado |
| `criar-pin` | chave, máquina, código, pin | confere o código e grava o PIN; abre sessão |
| `entrar` | chave, máquina, pin | confere o PIN; abre sessão |
| `trocar-pin` | sessão, pin atual, pin novo | troca sem depender do e-mail |
| `listar` | sessão | os computadores da licença |
| `renomear` | sessão, máquina, apelido | |
| `soltar` | sessão, máquina | apaga a ativação e libera a vaga |

O segredo da sessão volta **uma vez**, fica só na memória do Hub e nunca no
disco. O banco guarda o hash — igual a pagamentos.

### Limites de taxa

Reaproveitam `dumtech_dentro_do_limite`, com ações próprias:

| Ação | Teto | Escopo |
|---|---|---|
| `admin_codigo_ip` | 20/h | IP |
| `admin_codigo_licenca` | 5/h | licença |
| `admin_entrar_ip` | 30/h | IP |
| `admin_acao_ip` | 120/h | IP |

**Atenção ao contexto:** a correção de 2026-09-24 mostrou que um bloco
`EXCEPTION` em PL/pgSQL roda em subtransação, e o rollback desfaz a contagem
feita dentro dele. Toda função nova daqui que tiver `EXCEPTION` precisa contar
o limite **também no handler**, ou o limitador não conta as falhas — que são
exatamente o que se quer limitar.

## Telas no Hub

Espelham `PagamentosView`, que já resolveu este problema:

- `_pagina_trancada()` — pede o PIN; link "Esqueci o PIN"; e, quando ainda não
  há PIN, o caminho de criação por e-mail
- `_pagina_liberada()` — a lista, com contagem regressiva da sessão
- `hideEvent` tranca ao sair da tela; `trancar()` zera o segredo

**Sem internet a área não abre.** Não existe código de reserva no disco do
cliente — a mesma regra de Pagamentos, pelo mesmo motivo: um código guardado
localmente é um código que o atacante local também tem.

Soltar a vaga pede confirmação escrita com o nome do computador, porque é
destrutivo e não tem desfazer.

### Soltar o computador em que você está

É permitido — a tela Licença já oferece isso hoje, e seria estranho a área
nova proibir. Mas o efeito é diferente de soltar outro: **este Hub perde a
licença na hora**. Então o aviso de confirmação é outro ("os aplicativos vão
fechar neste computador"), e depois de soltar o Hub faz o mesmo que já faz ao
remover a licença — volta para a tela de ativação.

A sessão administrativa morre junto, porque ela é da licença que acabou de
sair deste computador.

## Testes

| Onde | O que cobre |
|---|---|
| `supabase/tests/admin_computadores_test.sql` | trava após 5 erros e a janela dobrando; código expirado; código de outra licença; sessão expirada; sessão de outra licença; soltar máquina inexistente; PIN criado sem código válido é recusado |
| `supabase/functions/tests/computadores.test.mjs` | rotas conhecidas e só elas; sessão ausente não vê nada; e-mail mascarado não entrega o endereço inteiro |
| `tests/test_computadores.py` | serviço: sessão expira sozinha, `trancar()` apaga o segredo, sem licença ativa não tenta rede |
| `tests/test_computadores_tela.py` | tela trancada não mostra a lista; contagem regressiva; sair da tela tranca |

## Ordem de implementação

1. Migration com as três tabelas e as funções SQL + bateria SQL
2. Edge Function `computadores` + testes
3. `core/computadores.py` (serviço) + testes
4. `hub/views/computadores_view.py` (tela) + testes
5. Ligar no trilho do Hub, junto de Licença

Cada passo fecha com a sua bateria verde antes do seguinte.

## O que fica de fora, de propósito

- **Comprar vaga** — é loja, não administração
- **Ver o que cada computador fez** — auditoria de uso é outro recurso
- **Bloquear um computador sem soltar a vaga** — dois estados onde um resolve
- **A área na web** — decisão registrada acima, com a consequência assumida
