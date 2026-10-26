# Versão 1.5.0 — agendamento online, telefone no cadastro e atualizar à vista

Quatro entregas na mesma versão, nesta ordem:

| # | Entrega | Tamanho |
|---|---|---|
| 1 | Telefone obrigatório no primeiro acesso | pequeno + 1 ajuste no servidor |
| 2 | Botão de atualizar mais evidente | pequeno |
| 3 | **Link de agendamento online** (a Agenda ganha uma página pública) | grande |
| 4 | Vídeos tutoriais regravados + 1 novo | no fim, com tudo pronto |

E uma regra que vale para o lançamento inteiro: **a atualização chega para
todos, o "o que mudou" só para quem tem o módulo.** Isso já funciona hoje
(`core/novidades.py` filtra por `app_id`; a janela antes de atualizar mostra
texto genérico, porque `notas` nem vai no manifesto assinado). A 1.5.0 entra em
`VERSOES` com uma novidade só, marcada `agenda`.

---

## 1. Telefone obrigatório no primeiro acesso

### O que muda

- Em `hub/views/boas_vindas_view.py`, o campo "Telefone (opcional)" vira
  **"Telefone (WhatsApp)"**, obrigatório. Máscara enquanto digita
  (`formatar_telefone`), e o Continuar recusa com "Digite o seu telefone com
  DDD." quando o número não for válido.
- Número válido: só dígitos; com `55` na frente e 12–13 dígitos, o `55` sai;
  sobram **10 ou 11 dígitos**, DDD de 11 a 99. A regra mora em
  `core/documentos.py` (`telefone_valido`), ao lado de `formatar_telefone`.
- O número vai para o servidor junto com nome e e-mail:
  `ContaService.registrar(nome, email, telefone)` e `reenviar(nome, telefone)`.
- **Só o primeiro acesso muda.** Quem já passou pelas boas-vindas não vê nada
  novo (decisão do dono).

### No servidor (migration `20261026120000_telefone_no_cadastro.sql`)

`dumtech_identificar_cliente(p_nome, p_email)` vira
`dumtech_identificar_cliente(p_nome, p_email, p_telefone text default '')`.

- A versão de 2 parâmetros é **removida** (`drop function`) e a nova criada no
  lugar. Com as duas existindo, o PostgREST não saberia qual chamar quando o Hub
  antigo manda só nome e e-mail. Com o `default ''`, o Hub antigo continua
  funcionando sem mudança.
- Cliente novo nasce com o telefone (só dígitos, até 20).
- Cliente que já existe continua intocado, **exceto** o telefone vazio, que é
  preenchido. Telefone já cadastrado nunca é trocado por algo digitado numa
  instalação qualquer.
- Mesmo limite de antes (30 por hora por IP) e as mesmas permissões
  (`anon`, `authenticated`).
- O painel já mostra o telefone do cliente (`painel/js/telas/comercial.js`):
  nada muda lá.

---

## 2. Botão de atualizar mais evidente

### Por que os clientes não atualizam

"Agora não", na faixa do Início e na janela de atualização, chama
`core/versao.dispensar`, que **cala aquela versão para sempre**. Sobra só um
botão comum no topo, igual aos outros.

### O que muda

- **Topo:** o botão vira uma pílula na cor de destaque — `● Atualizar · 1.5.0`.
  Quando a versão nova chega, o ponto pulsa devagar **3 vezes** e fica parado
  (nada de piscar sem parar). Dica: "Versão nova pronta: instala em menos de 1
  minuto". O widget mora em `ui/widgets/topbar.py`, ao lado de `SearchPill`; a
  animação usa o que já existe em `ui/motion.py`.
- **"Agora não" vira "Lembrar em 3 dias".** `core/versao.dispensar` passa a
  guardar a versão **e o dia**; `foi_dispensada` só vale por 3 dias
  (`DIAS_DE_ESPERA = 3`). Depois disso a faixa volta. A pílula do topo nunca
  some enquanto houver versão nova (já é assim: usa `disponivel`, não
  `para_avisar`).
- **Menu da empresa:** um item "Atualizar para 1.5.0" no topo do menu, visível
  só enquanto houver versão nova.
- Atualização obrigatória continua como hoje: sem botão de adiar.

---

## 3. Link de agendamento online

### O que o dono ganha

Um endereço como `https://dumtechsolution.com/agendar/beauty-e-cia`, para
mandar no WhatsApp ou pôr na bio do Instagram. O cliente dele abre no celular,
escolhe o serviço, o dia e o horário, informa nome e WhatsApp — e o
compromisso aparece na Agenda do Hub sozinho.

### Decisões tomadas com o dono

| Decisão | Escolha |
|---|---|
| Quantos clientes no mesmo horário | **vagas configuráveis** (1 a 10) |
| Cliente cancela sozinho | **sim, pelo próprio link**, até um prazo que o dono define |
| Reserva entra como | **Agendado**; o dono confirma pelo WhatsApp e ela vira Confirmado |
| Profissional por agendamento | fora desta versão (exigiria o conceito na Agenda inteira) |

### Como funciona

```
 HUB (computador)                 SUPABASE                     CELULAR DO CLIENTE
 Agenda > Online                  agenda_links                 /agendar/<slug>
   salva regras ───────────────►  config + ocupados  ◄──────── pagina, horarios
   publica ocupados (na mudança)  (sem nome de ninguém)
                                  agenda_reservas    ◄──────── reservar (com trava)
   a cada 1 min ◄──────────────── reservas novas               cancelar (código dele)
   grava na agenda.db
   confirma recebimento ───────►  apaga nome e telefone
```

1. O dono liga o link e define serviços, horário de atendimento e regras.
2. O Hub publica a configuração e os **horários ocupados** (início, duração e
   se é bloqueio — sem título, sem cliente).
3. A página pede os horários livres ao servidor, que os calcula.
4. A reserva é conferida de novo no servidor, com trava por link, e entra numa
   fila.
5. O Hub busca a fila a cada minuto, grava na Agenda e confirma o recebimento,
   mandando junto os ocupados novos. O servidor então **apaga nome, telefone e
   observação** da reserva.

**Funciona com o Hub fechado:** a página usa os últimos ocupados publicados +
as reservas ainda não entregues. Enquanto o Hub está fechado, ninguém marca
nada nele — então essa visão está certa. Com o Hub aberto e sem internet, uma
marcação feita no balcão pode não ter chegado ao servidor; se o link vender o
mesmo horário, a Agenda mostra o conflito como já faz hoje ("avisa, não trava").

### Regras de disponibilidade (uma fonte só: o SQL)

Um horário de início `s` para um serviço de `d` minutos está livre quando:

1. `[s, s+d)` cabe inteiro num intervalo aberto daquele dia da semana
   (`semana`), e `s` está no passo da grade a partir do começo do intervalo
   (09:00, 09:30, 10:00... com passo de 30);
2. `s ≥ agora_na_loja + antecedência`;
3. o dia está entre hoje e hoje + `dias` − 1;
4. nenhum **bloqueio** encosta em `[s, s+d)` — bloqueio (almoço, folga,
   feriado) fecha todas as vagas;
5. o **máximo de atendimentos simultâneos** dentro de `[s, s+d)` é menor que
   `vagas`. Contam: os ocupados publicados que não são bloqueio e as reservas
   ainda não entregues. Simultâneo de verdade, e não "quantos encostam": com
   2 vagas, 14:00–14:30 e 14:30–15:00 ocupados ainda deixam livre 14:00–15:00.

"Agora na loja" é `now()` em UTC + `fuso_min` que o Hub publica (o Brasil não
tem horário de verão desde 2019; o Hub republica o fuso a cada publicação).
Horários são guardados como hora de parede da loja (`timestamp` sem fuso), no
formato `YYYY-MM-DDTHH:MI` — o mesmo que a Agenda já usa.

A mesma função interna responde à página (`horarios`) e confere a reserva
(`reservar`). A página nunca decide disponibilidade sozinha.

### Banco de dados — Supabase

Migration nova `20261026130000_agendamento_online.sql`. **Nenhuma tabela
existente é alterada.** Tudo segue o desenho do "Hub no celular": RLS ligado, nenhuma
policy, `revoke all` de `anon` e `authenticated`; só funções `security
definer` com `search_path = ''`.

**`agenda_links`** — uma linha por computador (licença + máquina):

| coluna | tipo | |
|---|---|---|
| `id` | uuid pk | |
| `licenca_id` | uuid → `licencas` on delete cascade | |
| `maquina` | text | normalizada como nas outras funções |
| `slug` | text unique | `^[a-z0-9][a-z0-9-]{1,38}[a-z0-9]$` |
| `ativo` | boolean | desligado = página pausada |
| `config` | jsonb | o que a página mostra + as regras (abaixo) |
| `ocupados` | jsonb | `[["2026-10-28T14:00", 45, 0], ...]` — início, minutos, bloqueio 0/1 |
| `fuso_min` | smallint | ex.: −180 |
| `publicado_em`, `criado_em`, `atualizado_em` | timestamptz | |
| | unique (`licenca_id`, `maquina`) | |

`config` (montado pelo Hub, conferido pelo servidor):

```json
{
  "v": 1,
  "empresa": {"nome": "Beauty & Cia", "logo": "data:image/png;base64,...",
              "endereco": "Rua das Flores, 120 · Centro · Santo André/SP",
              "whatsapp": "5511987654321"},
  "mensagem": "Chegue 5 minutos antes",
  "cor": "violeta",
  "servicos": [{"id": "s1", "nome": "Corte feminino", "duracao": 45, "preco": 60.0}],
  "semana": [[[540, 720], [780, 1080]], [], [], [], [], [], []],
  "passo": 30, "vagas": 1, "antecedencia": 120, "dias": 30, "cancelar_ate": 180
}
```

- `semana`: 7 listas (segunda a domingo) de intervalos abertos em minutos desde
  a meia-noite. Almoço é o vão entre dois intervalos.
- Limites conferidos no servidor: config ≤ 64 KB; logo ≤ 48.000 caracteres e
  começando por `data:image/png;base64,` ou `data:image/jpeg;base64,`;
  1–20 serviços com duração 5–720; até 4 intervalos por dia, `0 ≤ início < fim
  ≤ 1440`; `passo` ∈ {10, 15, 20, 30, 45, 60}; `vagas` 1–10; `antecedencia`
  0–10080; `dias` 1–90; `cancelar_ate` 0–10080; textos com tamanho máximo
  (nome 80, endereço 160, mensagem 280); `cor` numa lista fechada de 8:
  `violeta` (padrão, a da DumTech), `rosa`, `vinho`, `terracota`, `verde`,
  `petroleo`, `azul`, `grafite`.
- `ocupados`: até 5.000 itens e 300 KB; o Hub manda só a janela de `dias`.

**`agenda_reservas`** — a fila:

| coluna | tipo | |
|---|---|---|
| `id` | uuid pk | |
| `link_id` | uuid → `agenda_links` on delete cascade | |
| `servico` | text | o nome no momento da reserva |
| `inicio` | timestamp | hora de parede da loja |
| `duracao` | smallint | 5–720 |
| `nome`, `telefone`, `observacao` | text | **apagados quando o Hub recebe** |
| `codigo_hash` | text unique | sha256 do código de cancelar do cliente |
| `situacao` | text | `nova` → `entregue` → (`cancelada`) |
| `criado_em`, `entregue_em`, `cancelada_em` | timestamptz | |

Índices: (`link_id`, `situacao`) e (`link_id`, `inicio`).

**Ciclo de uma reserva:**

| Evento | `nova` | `entregue` | `cancelada` |
|---|---|---|---|
| Hub recebe e confirma (com ocupados novos na mesma chamada) | → `entregue`, apaga dados pessoais | — | — |
| Cliente cancela no prazo | linha apagada (o Hub nunca soube) | → `cancelada` | já está |
| Hub aplica o cancelamento | — | — | linha apagada |
| Faxina (início há mais de 2 dias) | apagada | apagada | apagada |

A confirmação de recebimento **só vale junto com ocupados novos**: assim a
reserva nunca some da conta de ocupados entre sair da fila e entrar no
retrato que o Hub publica. A faxina roda de vez em quando dentro das próprias
funções (`random() < 0.05`), como as faxinas que já existem — sem agendador.

**Funções da página** (`anon`):

| Função | O que faz | Limite |
|---|---|---|
| `dumtech_agenda_pagina(p_slug)` | empresa, mensagem, cor, serviços, regras, hoje e agora na loja. Pausado: `indisponivel` + nome e WhatsApp da empresa | 600/h por IP |
| `dumtech_agenda_horarios(p_slug, p_servico)` | os dias da janela, cada um com os horários livres (dia vazio vem com lista vazia) | 600/h por IP (mesmo balde) |
| `dumtech_agenda_reservar(p_slug, p_servico, p_inicio, p_nome, p_telefone, p_observacao, p_armadilha)` | confere tudo com `for update` no link, grava e devolve o código de cancelar, o resumo e o prazo | 30/h por IP (operadora de celular põe muita gente no mesmo IP); 100/dia por link; 3 horários futuros por telefone no mesmo link |
| `dumtech_agenda_cancelar(p_codigo)` | cancela dentro do prazo | 30/h por IP |

Respostas de erro com `erro` + `mensagem` pronta: `ocupado` ("Esse horário
acabou de ser ocupado. Escolha outro."), `indisponivel`, `nao_encontrado`,
`dados`, `limite_telefone`, `prazo`, `muitas_tentativas`. `p_armadilha` é o
campo escondido do formulário: preenchido = robô, recusa.

**Funções do Hub** (`anon` + chave, máquina e computador — conferidos por
`dumtech_celular_licenca`, a mesma verificação do celular; a Agenda tem de
estar liberada: produto `AGENDA` na licença ou teste grátis valendo):

| Função | O que faz | Limite |
|---|---|---|
| `dumtech_agenda_salvar(p_chave, p_maquina, p_computador, p_ativo, p_config, p_sugestao, p_novo_endereco)` | cria ou atualiza o link desta máquina e devolve o `slug`. Slug: a sugestão do Hub (nome da empresa sem acento); se já for de outro link, ganha `-` + 4 caracteres aleatórios. `p_novo_endereco` força um slug novo (o antigo para de funcionar) | 60/h por licença |
| `dumtech_agenda_sincronizar(p_chave, p_maquina, p_computador, p_ocupados, p_fuso, p_recebidas, p_canceladas)` | guarda os ocupados (se vierem), marca as recebidas como entregues, apaga as canceladas aplicadas e devolve as reservas novas e os cancelamentos pendentes | 240/h por licença+máquina |

Licença vencida ou sem a Agenda: a página responde `indisponivel` e o Hub
para de sincronizar. Nada é apagado — renovou, voltou.

**Permissões:** as 6 funções entram na lista da API pública que os testes SQL
conferem (`licenciamento_test.sql`, `porta_entrada_test.sql` e os outros que
repetem a lista). As internas (`livres`, `liberada`, validação) ficam sem
permissão para `anon`.

### Banco de dados — o computador (`agenda.db`)

Migration 3 em `apps/agenda/database.py`, **só acréscimo**:

```sql
ALTER TABLE compromissos ADD COLUMN telefone TEXT NOT NULL DEFAULT '';
ALTER TABLE compromissos ADD COLUMN origem   TEXT NOT NULL DEFAULT '';
ALTER TABLE compromissos ADD COLUMN reserva  TEXT NOT NULL DEFAULT '';
CREATE UNIQUE INDEX IF NOT EXISTS idx_compromissos_reserva
    ON compromissos(reserva) WHERE reserva <> '';
CREATE TABLE IF NOT EXISTS ajustes (chave TEXT PRIMARY KEY, valor TEXT NOT NULL);
```

- `origem = 'link'` marca o que veio da página; `reserva` guarda o id da
  reserva e impede, pelo índice único, que a mesma reserva entre duas vezes
  (a confirmação de recebimento pode se perder na rede e a reserva voltar).
- `ajustes` guarda a configuração do link (JSON em `online`) e o estado (slug,
  ligado, última publicação). Fica no banco da Agenda: o link é deste
  computador e entra no backup junto com os compromissos.
- Hub antigo abrindo o banco novo: `user_version` 3 é maior que o que ele
  conhece, ele não migra nada e ignora as colunas a mais (`from_row` já filtra
  pelos campos). Nada quebra num rebaixamento.

### No Hub

**Contrato novo de módulo, no mesmo desenho de `avisos`, `indicadores` e
`celular`:** um `module.py` pode expor

```python
def online(paths) -> Sincronia | None
```

com `preparar()` (thread da tela: lê o banco e devolve `(funcao, params)` ou
`None` quando não há o que fazer) e `aplicar(resposta)` (thread da tela: grava
e devolve o que avisar). O Hub faz a chamada de rede no meio, em segundo plano
(`ui/tasks.executar`), igual ao celular: **banco só na thread da tela, rede só
fora dela.** O Hub continua sem saber o que é uma Agenda.

- `core/online.py` (novo): o contrato acima e `ServidorDaLicenca` — chama uma
  função do Supabase já com chave, máquina e computador, e traduz os erros
  para português (mesmo papel de `CelularService._chamar`).
- `AppContext.servidor` (novo, opcional): o `ServidorDaLicenca`, para a aba
  Online salvar o link. O launcher entrega sempre; a licença é conferida a
  cada chamada (ativou com a Agenda aberta, já vale), e sem licença ativa a
  chamada devolve a mensagem pronta em vez de ir à rede.
- `hub/main_window.py`: relógio de 15 s. A cada volta, `preparar()` de cada
  módulo liberado; a rede só é chamada se os ocupados mudaram (comparação local,
  como o celular faz) ou se já passou 1 minuto. Desligado, modo local ou sem
  licença: nada sai do computador.
- Depois de `aplicar`: `eventos.avisar("agenda")` (a Agenda aberta recarrega),
  o Início recalcula os avisos e aparece o **aviso flutuante** (novo,
  `ui/widgets/aviso_flutuante.py`): canto inferior direito, some em 8 s,
  "Novo agendamento pelo link · Maria · qui 30/10, 14:00 [Ver]". "Ver" abre a
  Agenda na semana do horário.

**Na Agenda (`apps/agenda/`):**

- `online.py` (novo, sem Qt de tela): `AjustesOnline` (valores padrão,
  validação, JSON), `slug_de(nome)`, `logo_em_data_uri(caminho)` (reaproveita a
  redução de `apps/estoque/imagem.py`: lado máximo 160 px), `montar_ocupados`,
  e a `Sincronia`.
- `models.py` / `repository.py`: `Compromisso` ganha `telefone`, `origem`,
  `reserva`; o repositório ganha `importar_reserva` (idempotente),
  `cancelar_reserva`, `ocupados(de, ate)`, `ajuste`/`definir_ajuste` e
  `do_link_para_confirmar()`.
- `ui/online_view.py` (novo): a aba **Online** — terceira aba da janela.
- `ui/grade.py`: bloco que veio do link ganha ícone de link (ícone novo
  `link` em `ui/icons.py`); a dica mostra o WhatsApp do cliente.
- `ui/compromisso_dialog.py`: campo **Telefone** (vale para qualquer
  compromisso); editar um compromisso do link preserva `origem` e `reserva`.
- `ui/compromissos_view.py`: o botão WhatsApp usa o telefone do compromisso
  e, sem ele, a agenda de clientes, como hoje (`mandar(..., telefone=...)`).
- `module.py`: o hook `online`; em `avisos`, "N agendamentos do link para
  confirmar" (do link, Agendado, ainda por vir); em `celular`, o mesmo como
  alerta.

**A aba Online:**

- **Primeira vez:** cartão "Seus clientes marcam sozinhos", três frases do que
  o link faz e o botão **Criar meu link**. Já vem preenchido: segunda a sexta
  9h–18h com almoço 12h–13h, sábado 9h–13h, um serviço "Atendimento" de 60
  min, passo 30, 1 vaga, antecedência 2 h, 30 dias, cancelar até 3 h antes,
  cor violeta.
- **Depois:** o cartão do link (interruptor Ligado/Desligado, endereço,
  Copiar, Enviar no WhatsApp, Abrir, QR com "Salvar imagem", "Publicado há 2
  min · N pelo link nesta semana", menu "…" com "Gerar endereço novo"), e
  três cartões de ajuste: **Serviços** (nome, duração, preço opcional),
  **Horário de atendimento** (por dia: aberto/fechado, das/às, almoço
  opcional) e **Regras** (vagas, passo, antecedência, dias, prazo de
  cancelamento, recado, cor).
- **Salvar e publicar** grava local e publica em segundo plano. Sem internet:
  "Salvo. Publica sozinho quando a internet voltar." (a próxima sincronia
  manda).
- Sem licença ativa (ou modo local): o cartão explica e não oferece criar.
- Os dados da empresa (nome, logo, endereço, WhatsApp) vêm de **Minha
  empresa**; a aba mostra de onde vêm e leva até lá.

### A página do cliente (`landingpage/agendar/`)

- `agendar/index.html`, `css/agendar.css`, `js/agendar.js` (funções puras,
  testadas em `landingpage/tests/agendar.test.mjs`) e `js/agendar-tela.js`
  (tela). Sem biblioteca externa; usa `js/config.js` para o endereço do
  servidor.
- **Endereço:** `/agendar/<slug>`. O `.htaccess` ganha
  `RewriteRule ^agendar/[a-z0-9-]+/?$ agendar/index.html [L]`; a página também
  aceita `?l=<slug>` (testes locais e servidores sem reescrita).
- **De cima para baixo:** logo (ou iniciais), nome, endereço, recado →
  **1 Serviço** (some se houver um só) → **2 Dia** (faixa rolável; dia sem
  horário apagado) → **3 Horário** (Manhã / Tarde / Noite) → **4 Seus dados**
  (nome, WhatsApp com máscara, observação opcional, resumo) → **Confirmar
  agendamento**. Abaixo: "Seu nome e WhatsApp vão só para <empresa>, para
  confirmar o horário."
- **Confirmado:** ✓ "Horário marcado", o resumo, **Adicionar ao calendário**
  (arquivo `.ics`, abre no iPhone e no Android), **Falar no WhatsApp** (da
  empresa) e **Cancelar** até o prazo. A reserva fica guardada no celular
  (`localStorage`, com `try/catch`); voltando ao link, "Você tem um horário
  marcado" aparece no topo. Horário que já passou some sozinho.
- **Erros com saída:** horário ocupado no meio do caminho → aviso e horários
  recarregados; link pausado → nome da empresa e botão do WhatsApp; sem
  internet → "Tentar de novo".
- **Visual:** mesma família da loja (Plus Jakarta Sans), uma cor de destaque
  das 8 que o dono escolhe (todas com contraste AA para texto branco), claro ou
  escuro conforme o aparelho, alvos de toque de 44 px, coluna única até 480 px
  e centrada no computador. Rodapé discreto "Agendamento online por DumTech".
- `noindex` (a página de cada empresa não entra em buscador) e tudo com
  `textContent` — nada que venha do servidor vira HTML.

### Testes

- **SQL (PGlite)** — `supabase/tests/agendamento_online_test.sql`: só com
  Agenda liberada; slug único e com sufixo; horários respeitam intervalo,
  almoço, passo, antecedência, janela, bloqueio e vagas (simultâneo de
  verdade); reserva concorrente não passa das vagas; limites; prazo de
  cancelar; ciclo nova → entregue (dados pessoais apagados) → cancelada →
  apagada; confirmação sem ocupados não vale; licença vencida; `anon` sem
  acesso às tabelas. E o teste do telefone em `porta_entrada_test.sql`.
- **Python** — `tests/test_agenda_online.py`: migration 3 num banco versão 2
  com dados (nada perdido); ocupados; importação idempotente; cancelamento;
  validação dos ajustes; `Sincronia` com servidor falso; a aba Online abre e
  salva. E os testes de telefone, de "Lembrar em 3 dias" e da pílula.
- **JavaScript** — `landingpage/tests/agendar.test.mjs`: slug da URL, máscara
  e validação do WhatsApp, agrupar horários por período, datas por extenso,
  `.ics`, guardar e ler reservas.
- **Ponta a ponta**, antes de pedir o lançamento: PGlite + página local
  (`?api=` local) + Hub de desenvolvimento — reservar na página, ver no Hub,
  cancelar no "celular", ver cancelado no Hub.
- `tools/verificar_tudo.ps1` inteiro passando.

---

## 4. Vídeos

- Os 23 vídeos do Passo a passo (`tools/videos/roteiros_passo.py`) regravados
  com o visual atual: `gravar.py --loja passo`, depois `publicar_passo.py`
  (copia para `landingpage/videos/`, refaz as capas e o `catalogo.js`).
- **1 vídeo novo**, `link-de-agendamento`: criar o link, copiar, enviar no
  WhatsApp e uma reserva chegando — aviso flutuante e bloco na grade. A
  reserva vem de um servidor de mentira, como o `CelularDeMentira` dos vídeos
  de hoje. Entra no `CATALOGO` com perguntas como "como o cliente marca
  sozinho".
- O vídeo do próprio catálogo (`usar-passo-a-passo`, gravado do site) fica
  como está.

---

## Lançamento

1. `__version__` → 1.5.0; `VERSOES["1.5.0"]` com a novidade da Agenda
   (`tests/test_novidades.py` confere).
2. README e `docs/arquitetura.md`: a Agenda passa a ter uma parte online
   opcional (a frase "Nenhum acesso à internet no funcionamento diário" ganha a
   exceção, ligada pelo dono).
3. **Paradas para o OK do dono, nesta ordem:**
   1. `npx supabase db push --linked` (as duas migrations), depois de
      `--dry-run` e do PGlite;
   2. `tools/lancar_versao.ps1`, que testa, gera o instalador, publica o site
      (com a página `agendar/` e os vídeos) e registra a 1.5.0.

O Hub 1.5.0 aguenta o servidor sem as migrations: a aba Online mostra "O
servidor ainda não está pronto" e nada mais quebra.

## Fora do escopo

- Escolher o profissional; agenda por profissional.
- Remarcar pela página (o cliente cancela e marca de novo).
- Cobrança antecipada ou sinal pelo Pix no agendamento.
- Avisar o cliente quando o **dono** cancela pelo Hub (ele avisa pelo
  WhatsApp, como hoje).
- Lembrete automático no dia (exigiria envio de mensagem pelo servidor).
