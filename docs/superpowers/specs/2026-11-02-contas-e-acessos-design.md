# Contas e acessos: login, papéis e a chave que manda nos computadores

## O que muda

Hoje a licença é do computador: quem abre o Hub vê tudo. Com esta versão, a
licença passa a ter **pessoas**. Cada chave tem contas ADM e funcionário, cada
funcionário vê só os módulos e avisos marcados, e o Eric enxerga e administra
tudo isso pelo painel, loja por loja.

A chave continua mandando nos computadores: permite N, a de número N+1 é
recusada. O que muda é que reduzir o limite passa a valer de verdade.

## Decisões já tomadas com o Eric

| Assunto | Decisão |
|---|---|
| Onde a conta fica | No servidor, ligada à licença. O Hub guarda cópia assinada |
| Quem já usa | O Hub convida a cada abertura, com "Agora não". Só vira obrigatório quando o Eric ligar no painel, por loja ou para todas |
| Cliente novo | Conta ADM faz parte do primeiro acesso, sem "Agora não" |
| Papéis | Dois: ADM e funcionário. Vários ADMs por chave |
| Login | Escolhido pelo gestor, não precisa ser e-mail. Único dentro da chave |
| Lançamento | 1.11.0 pendente. Nenhum cliente recebe sem o Eric mandar pelo painel |

Alternativas descartadas: conta só no computador (o painel não veria nada e não
haveria recuperação por e-mail) e login sempre online (quebraria a promessa de
funcionar offline).

## O que a conta protege, e o que não protege

A conta controla o que cada pessoa vê **dentro do programa**. A ameaça é o
funcionário curioso no balcão, não quem tem conhecimento técnico e acesso ao
Windows: os bancos `.db` continuam sem criptografia. Dizer isso aqui evita
vender uma garantia que o produto não dá.

Um computador em versão anterior à 1.11.0 continua abrindo sem login até
atualizar. O painel mostra esses computadores.

## Permissões

| | ADM | Funcionário |
|---|---|---|
| Módulos | Todos da licença | Só os marcados |
| Avisos do Início | Todos | Só os marcados, dentro dos módulos dele |
| Ver no celular | Sim | Não, recusado também no servidor |
| Licença, Minha empresa, Configurações, Backup | Sim | Não |
| Ofertas e compra de módulos | Sim | Não |
| Usuários e computadores | Tudo | Não |
| Própria senha | Troca | Troca |

- **Lista branca:** módulo comprado depois ou tipo de aviso novo não aparece para
  funcionário até o ADM marcar.
- **Modelos:** Vendedor (Vendas, Clientes, Agenda), Estoque (Estoque), Técnico
  (Ordens, Clientes, Agenda), Financeiro (Financeiro, Clientes). Só preenchem as
  caixas; o que vale é o que ficou marcado.
- **Pontes entre módulos não mudam.** Funcionário só com Vendas continua baixando
  estoque e lançando no Financeiro: a permissão é de tela, não de regra de
  negócio. O resumo do celular segue completo mesmo com funcionário logado,
  porque é da loja.
- O último ADM ativo não pode ser rebaixado, bloqueado nem apagado.
- Não há limite de contas por chave.

## Computadores e a chave

- **Aumentar:** direto no painel.
- **Diminuir abaixo do que está em uso:** o painel obriga a escolher quais
  computadores desconectar. O ajuste é atômico (limite + vagas soltas) e o
  computador solto perde a licença na próxima conferência, em até 2 minutos.
- **ADM da loja, no Hub:** vê, renomeia e libera computadores, mas não aumenta o
  limite. Comprar vaga é com a DumTech.
- A mensagem de `limite_maquinas` passa a dizer "x de x computadores" e aponta
  para o ADM ou para a DumTech.

Isso substitui o spec de 2026-09-24, que nunca foi construído: a sessão de ADM
faz o papel do PIN.

## Dados no servidor

Migration aditiva `20261102120000_contas_e_acessos.sql`.

```sql
alter table licencas add column exigir_conta boolean not null default false;

licenca_usuarios
    id uuid pk, licenca_id uuid → licencas on delete cascade
    login text        -- minúsculo, ^[a-z0-9._@+-]{3,60}$, unique (licenca_id, login)
    nome text, email text default '', email_confirmado boolean default false
    papel text        -- 'adm' | 'funcionario'
    modulos text[], avisos text[]        -- só para funcionário
    senha_hash text   -- pbkdf2$<iterações>$<sal>$<derivado>
    senha_versao int default 1           -- sobe a cada troca: invalida o cache
    trocar_senha boolean default false, ativo boolean default true
    erros int default 0, bloqueado_ate timestamptz
    ultimo_acesso timestamptz, ultimo_computador text default ''
    criado_em, atualizado_em

licenca_usuario_codigos    -- 6 dígitos, 10 min, 5 tentativas, um uso
    id, usuario_id, finalidade ('confirmar_email' | 'recuperar_senha'),
    codigo_hash, criado_em, expira_em, tentativas, usado_em

licenca_usuario_sessoes    -- 30 min, só o hash fica no banco
    sessao_hash pk, usuario_id, licenca_id, maquina, computador,
    criado_em, expira_em

licenca_usuario_eventos    -- quem fez o quê nas contas
    id, licenca_id, usuario_id, ator, acao, detalhe jsonb, criado_em
```

- RLS ligado. `anon` e `authenticated` não têm acesso direto. O painel lê por
  funções `dumtech_e_admin()`, e **`senha_hash` nunca sai** por elas.
- Todas as funções `dumtech_acesso_*` são de `service_role`, chamadas só pela
  Edge Function.
- Toda função com bloco `EXCEPTION` conta o limite também no handler (lição de
  20260924220000).

### A senha nunca chega ao banco

`pgcrypto` não existe nas migrations nem no PGlite dos testes. A Edge Function
deriva a senha com **PBKDF2-SHA256, 600 mil iterações e sal aleatório**, usando
WebCrypto. O banco recebe e guarda só a string derivada, e devolve o hash à
função para ela comparar. Assim a senha em claro não passa por parâmetro SQL nem
por log do Postgres.

Senha: de 8 a 72 caracteres, diferente do login, recusando as óbvias
(`12345678`, `senha123`). Sem regra de símbolo obrigatório.

**Contra força bruta:** 5 erros travam a conta por 15 minutos, dobrando até 60.
A contagem é do servidor, por conta, além de limite por IP com
`dumtech_dentro_do_limite`.

## Edge Function `acesso`

Mesmo desenho de `pagamentos`: `nucleo.ts` testável e `index.ts` só com HTTP.

| Rota | Quem | Faz |
|---|---|---|
| `criar-primeiro` | Chave + computador ativado | Cria o primeiro ADM, só se a licença não tem conta |
| `entrar` | Chave + computador | Confere a senha e abre sessão |
| `pedir-codigo` | Chave + computador | Manda o código ao e-mail da conta |
| `redefinir` | Chave + computador + código | Define senha nova |
| `confirmar-email` | Sessão | Marca o e-mail como confirmado |
| `trocar-senha` | Sessão + senha atual | Troca a própria senha |
| `usuarios`, `salvar-usuario`, `senha-usuario`, `apagar-usuario` | Sessão ADM | Gerencia as contas |
| `computadores`, `renomear-computador`, `liberar-computador` | Sessão ADM | Gerencia as vagas |

`pedir-codigo` responde igual para login que não existe. O código nunca volta ao
Hub. Conta sem e-mail recebe a resposta "peça ao administrador".

## O que vai assinado

`licenca-assinada` passa a devolver dois pacotes no mesmo envelope Ed25519:

- **`assinado`** (a licença de sempre) ganha `contas: true|false`. Sem isso,
  apagar o pacote de acessos do arquivo faria a loja parecer sem contas.
- **`acesso`** (novo, `uso: "acesso"`): `exigir_conta` e a lista de usuários, sem
  hash e sem e-mail completo, presa à chave, máquina e computador.

Hub antigo ignora os campos novos. `dumtech_licenca_marca` passa a incluir as
contas e `exigir_conta`, então mudança de permissão chega ao Hub em até 2 minutos
pelo mesmo caminho da licença.

`entrar` devolve também a **lembrança** (`uso: "lembrar"`): assinada, presa a
usuário, `senha_versao` e computador. É ela que abre o Hub direto sem senha, e por
ser assinada editar o JSON não transforma funcionário em ADM.

## No Hub

### Núcleo

`core/acesso.py` concentra tudo. Nome separado de `core/conta.py`, que continua
sendo "quem instalou o Hub".

```
config/acesso.json   fora do backup, apagado junto com a licença
    lembrado        id de quem abre direto
    locais          {usuario_id: {sal, verificador, senha_versao, lembranca}}
    recentes        últimos usuários deste computador
```

- **Login offline:** ao entrar com internet, o Hub grava um verificador PBKDF2
  local. Sem internet, confere com ele. Se a `senha_versao` assinada mudou, o
  verificador é descartado e a pessoa precisa de internet.
- **Primeiro login de cada pessoa em cada computador exige internet.**
- **Não trava loja sem internet:** obrigatoriedade sem internet vira só aviso, e
  pacote offline vencido mantém as últimas permissões conhecidas.
- **Duas sessões:** a *do computador* (quem está aqui, local) e a *de gestão* (30
  minutos, só em memória, zerada ao sair). Usuários, Computadores e Ver no celular
  exigem a de gestão. Sem ela, pede a senha de novo, como `PagamentosView` já faz.

`AppRegistry.available()` continua sendo o que a **licença** libera, porque
pontes, resumo do celular e sincronias dependem disso. Entra
`AppRegistry.visiveis()`, o que a **pessoa** vê, usado pelas abas, Início, paleta,
busca e abertura de módulo.

### Telas

| Tela | Conteúdo |
|---|---|
| `LoginView` (página, sem barra do topo) | Últimos usuários em um clique, ou login e senha; olho na senha; "Lembrar de mim neste computador" ligado; "Esqueci minha senha"; recado quando está sem internet |
| `AssistenteContaView` | Passo a passo de criar ADM, confirmar e-mail, montar equipe e concluir. Usado na migração e no primeiro acesso |
| `UsuariosView` (nova seção em Configurações) | Abas Usuários e Computadores: criar, editar, modelos, redefinir senha, bloquear, apagar, ver último acesso |
| `MinhaContaDialog` | Dados da pessoa, trocar senha, confirmar e-mail |
| `CampoSenha` (widget) | Campo com olho, reutilizado em tudo |

Menu do perfil: **Minha conta**, **Trocar de usuário** e **Sair**. Os dois tiram
`lembrado`: quem passou o computador não pode voltar sem senha ao reabrir o Hub.
"Sair" apaga também a lembrança. Os dois avisam quando há trabalho aberto, como o
carrinho do balcão.

Senha provisória não abre nada: nem módulos, nem gestão, nem celular. Ela só serve
para criar a senha da pessoa, no Hub e no servidor.

Computador que saiu da chave não fica preso no login: a tela mostra a saída para
ativar de novo, porque nenhuma senha resolve quando o servidor não reconhece a vaga.

### Migração de quem já usa

1. A licença chega sem contas: o Hub abre normalmente e mostra o convite.
2. O convite diz em três linhas o que muda, com "Criar minha conta" e "Agora não".
3. Criar: nome, login, senha e e-mail já preenchido (de `Conta` e `Empresa`).
4. Confirmar e-mail com código, com "Confirmar depois". Serve para pegar e-mail
   digitado errado antes do dia do "esqueci".
5. Equipe, opcional: nome, login, senha inicial e modelo. No fim, "Copiar acesso"
   de cada funcionário.
6. Fecha dizendo quantos computadores vão pedir login na próxima abertura.

Com `exigir_conta` ligado, o convite perde o "Agora não", se houver internet.

Os outros computadores da chave pedem login **na próxima abertura**. Hub aberto no
meio de uma venda não é derrubado.

### Cliente novo

Nome e contato, depois chave, conta ADM, confirmar e-mail, equipe (pulável) e "tudo
pronto". "Ainda não tenho chave" segue funcionando: o assistente aparece quando
ativar. Chave que já tem contas vai direto para o login.

### Mudança com a pessoa logada

Permissão alterada chega em até 2 minutos: abas somem, respeitando
`tem_trabalho_aberto`. Conta bloqueada ou senha redefinida volta ao login com o
mesmo cuidado.

## Esqueci minha senha

1. "Esqueci minha senha" no login, informando o login.
2. Código de 6 dígitos no e-mail da conta, mostrado mascarado.
3. Código e senha nova, com o olho.
4. Entra direto.

Sem e-mail na conta: pede ao ADM. ADM sem acesso ao e-mail: a DumTech redefine pelo
painel. Precisa de internet, e a tela diz isso.

Senha definida por outra pessoa (ADM ou Eric) liga `trocar_senha`: no primeiro
acesso a pessoa cria a própria senha.

## Ver no celular

`dumtech_celular_iniciar`, `dumtech_celular_aparelhos` e `dumtech_celular_revogar`
ganham `p_sessao text default ''`. Licença com contas exige sessão de ADM válida.
Licença sem contas segue igual, então Hub antigo sem conta não sente nada.
`dumtech_celular_publicar` não muda.

## Painel

**Ficha da loja, cartão "Contas e acessos":** nome, login, papel, e-mail (com selo
de confirmado), último acesso e situação. Ações: criar, editar permissões, redefinir
senha, bloquear e apagar. O interruptor "Exigir conta" fica aqui também.

**Redefinir pelo painel:** o navegador gera a senha provisória, deriva com o mesmo
PBKDF2 e manda só o hash para `dumtech_painel_senha_provisoria`. A senha aparece
uma vez para copiar.

**Cartão Computadores:** "2 de 3 vagas" e selo de versão sem login.

**Editar licença:** ao reduzir abaixo do uso, lista os computadores para marcar.
Sai o `atualizar("licencas")` do campo de computadores e entra
`dumtech_ajustar_computadores(licenca, maximo, soltar[])`.

**Tela nova "Acessos":** quantas lojas migraram, quantas faltam, quantas exigem
conta e quantos computadores estão em versão sem login. Lista por loja, com filtro
e "Exigir de todas" com confirmação. Selo quando o e-mail do ADM difere do e-mail
da licença, para o caso de um funcionário ter criado a conta antes do dono.

## Testes

| Onde | O que cobre |
|---|---|
| `supabase/tests/acesso_test.sql` | Sem acesso `anon`; `criar-primeiro` só sem contas; trava e janela dobrando; código expirado, usado e de outra conta; sessão vencida e de outra licença; funcionário não gerencia; último ADM; reduzir limite solta as vagas certas; celular exige ADM só quando há contas; marca muda com contas |
| `supabase/functions/tests/acesso.test.mjs` | Rotas conhecidas; derivar e conferir senha; hash nunca sai; código nunca volta; resposta igual para login inexistente; e-mail mascarado; pacotes assinados |
| `supabase/functions/tests/licenca-assinada.test.mjs` | `contas` no pacote; `acesso` sem hash |
| `tests/test_acesso.py` | Login online e offline; `senha_versao` invalida; JSON adulterado não sobe papel; pacote removido não libera; `visiveis` versus `available` |
| `tests/test_login_tela.py`, `test_assistente_conta.py`, `test_usuarios_tela.py` | Telas, olho da senha, sem internet, convite com e sem obrigatoriedade |
| `tests/test_hub_acesso.py` | Funcionário sem Licença, Backup e celular; troca de usuário fecha módulos; carrinho aberto não se perde |
| `painel/tests/acessos.test.mjs` | Derivação igual à do servidor; regras de reduzir vagas; contagem de migração |

## Lançamento

1. Migrations com `db push`, funções `acesso` e `licenca-assinada`: aditivas, sem
   efeito para quem não tem conta.
2. Painel publicado.
3. `lancar_versao.ps1 -Pendente` com a 1.11.0. O instalador público segue na versão
   publicada.
4. Confirmar que nada chegou ao cliente: `versao` sem chave e SHA do instalador
   público iguais aos de antes.

O Eric manda para a própria licença pelo painel. A 1.11.0 leva junto a 1.10.0, que
continua sem commit.

## Fora, de propósito

- **Registrar quem fez cada venda, OS ou lançamento:** a conta existe, mas gravar
  autoria mexe em todos os módulos.
- **Permissão por tela dentro de um módulo:** o pedido é por módulo e aviso.
- **Bloqueio por inatividade:** ninguém pediu e atrapalha o balcão.
- **Liberar vaga a partir de um computador novo:** o Eric resolve pelo painel.
- **Limite de contas por chave.**
- **Criptografia dos bancos locais.**
