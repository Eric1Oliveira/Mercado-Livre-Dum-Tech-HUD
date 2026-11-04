# Contas e acessos: plano de implementação

> Execução inline, tarefa por tarefa (`superpowers:executing-plans`). Sem subagentes: o usuário não pediu.

**Objetivo:** dar à licença contas ADM e funcionário, com permissões por módulo e aviso, login offline, recuperação por e-mail, migração guiada e gestão por loja no painel, e lançar a 1.11.0 como pendente.

**Arquitetura:** o servidor é a fonte de verdade. A Edge Function `acesso` deriva e confere senhas (o Postgres só vê o hash) e assina um documento com as contas da licença, que o Hub guarda junto da licença. `core/acesso.py` concentra login online e offline, sessão do computador e sessão de gestão. O Hub passa a distinguir o que a licença libera (`available`) do que a pessoa vê (`visiveis`).

**Stack:** PL/pgSQL (PGlite nos testes), Deno/WebCrypto, Python 3.11 + PySide6, JS puro no painel.

**Spec:** `docs/superpowers/specs/2026-11-02-contas-e-acessos-design.md`

## Restrições globais

- Sem commit, sem `dumtech_atualizar_*` e sem `dumtech_recolher_versao`: quem manda a versão é o Eric. Commit só se ele pedir.
- Migration aditiva: Hub ≤ 1.10 e loja sem conta não podem sentir nada. Enquanto não houver conta, `dumtech_licenca_marca` tem de dar o mesmo md5 de hoje.
- Senha em claro não vai a parâmetro SQL nem a log. Sessão e código: só o hash no banco. Sessão de gestão só em memória no Hub.
- Rede em segundo plano com `tasks.executar`, gravação na thread da interface.
- Nada de dependência nova. `hashlib.pbkdf2_hmac` no Hub, WebCrypto no servidor e no painel.
- Sem modal na abertura do Hub: trava a suíte. Telas de entrada são páginas.
- Código comentado sem acento, como o resto do Python. Texto de tela em pt-BR com acento.
- Com a bateria completa rodando, não editar arquivo (gera falha falsa).

## Comandos

```
Python : $env:PYTHONPATH='src'; $env:QT_QPA_PLATFORM='offscreen'; .venv\Scripts\python.exe -m unittest tests.test_x
SQL    : cd supabase; node tests/rodar.mjs acesso_test.sql
Edge   : cd supabase/functions; node --test tests/acesso.test.mjs
Painel : cd painel; node --test tests/acessos.test.mjs
```

## Mapa de arquivos

| Arquivo | Responsabilidade |
|---|---|
| `supabase/migrations/20261102120000_contas_e_acessos.sql` | Tabelas, funções, marca, para_assinar, celular, painel |
| `supabase/tests/acesso_test.sql` | Bateria SQL |
| `supabase/functions/acesso/{nucleo,index}.ts` | Rotas, senha, e-mails, documentos assinados |
| `supabase/functions/licenca-assinada/*` | `contas` e `acesso_assinado` |
| `src/dumtech/core/acesso.py` | Serviço de contas do Hub |
| `src/dumtech/core/licensing.py`, `registry.py`, `paths.py`, `celular.py` | Pacote na licença, `visiveis`, `acesso_file`, sessão no celular |
| `src/dumtech/ui/widgets/campo_senha.py` | Campo com olho e medidor |
| `src/dumtech/hub/views/login_view.py` | Login, esqueci, troca obrigatória |
| `src/dumtech/hub/views/assistente_conta_view.py` | Migração e primeiro acesso |
| `src/dumtech/hub/views/usuarios_view.py`, `minha_conta_dialog.py` | Gestão e conta própria |
| `src/dumtech/hub/{main_window,launcher}.py`, `views/home_view.py`, `views/avisos_view.py`, `views/celular_dialog.py` | Portão e filtros |
| `painel/js/acessos.js`, `painel/js/telas/acessos.js` | Regras puras e tela nova |
| `painel/js/telas/comercial.js`, `painel/js/painel.js`, `painel/index.html` | Ficha, editar licença, navegação |

---

### Tarefa 1: Banco

**Arquivos:** criar a migration e `supabase/tests/acesso_test.sql`.

**Produz (service_role, recebem `p_chave, p_maquina, p_computador` primeiro):**

```
dumtech_acesso_licenca(chave, maquina, computador) -> uuid        ativacao existe; nao exige licenca ativa
dumtech_acesso_resumo(licenca uuid) -> jsonb                      {exigir_conta, usuarios:[{id,login,nome,papel,modulos,avisos,senha_versao,trocar_senha,ativo,tem_email,email_confirmado}]}
dumtech_acesso_criar_primeiro(..., nome, login, email, senha_hash, ip)
dumtech_acesso_buscar(..., login, ip)                             {ok, usuario_id, senha_hash} ou recusa com trava
dumtech_acesso_resultado(..., usuario_id, certo bool, ip)         conta erro/trava ou abre sessao; devolve {sessao, usuario, resumo}
dumtech_acesso_pedir_codigo(..., login, ip)                       {ok, email, nome, codigo, validade_minutos} | {ok, sem_email} | {ok}
dumtech_acesso_redefinir(..., login, codigo, senha_hash, ip)
dumtech_acesso_codigo_email(..., sessao)
dumtech_acesso_confirmar_email(..., sessao, codigo)
dumtech_acesso_buscar_sessao(..., sessao)                         {ok, usuario_id, senha_hash}
dumtech_acesso_gravar_senha(..., sessao, senha_hash)
dumtech_acesso_usuarios(..., sessao)
dumtech_acesso_salvar_usuario(..., sessao, id, dados jsonb, senha_hash)
dumtech_acesso_senha_usuario(..., sessao, id, senha_hash)
dumtech_acesso_apagar_usuario(..., sessao, id)
dumtech_acesso_computadores(..., sessao)
dumtech_acesso_renomear_computador(..., sessao, alvo, apelido)
dumtech_acesso_liberar_computador(..., sessao, alvo)
```

**Painel (authenticated, com `dumtech_e_admin()` por dentro):** `dumtech_painel_acessos()`, `dumtech_painel_usuarios(licenca)`, `dumtech_painel_salvar_usuario(licenca, id, dados, senha_hash)`, `dumtech_painel_senha_provisoria(id, senha_hash)`, `dumtech_painel_apagar_usuario(id)`, `dumtech_painel_exigir_conta(licencas uuid[], valor)`, `dumtech_ajustar_computadores(licenca, maximo, soltar text[])`.

**Reescreve:** `dumtech_licenca_marca` (termos novos viram NULL sem conta), `dumtech_licenca_para_assinar` (acrescenta `contas` e `acesso`), `dumtech_ativar_licenca` (mensagem do limite), `dumtech_celular_iniciar|aparelhos|revogar` (ganham `p_sessao text default ''`; mantêm o grant de anon).

- [ ] Ler os corpos atuais de `dumtech_licenca_para_assinar` (20260917170000), `dumtech_verificar_interno` e `dumtech_pagamentos_entrar`.
- [ ] Escrever `acesso_test.sql` cobrindo: anon não lê nada e não executa; `criar_primeiro` recusa com contas; 5 erros travam e a janela dobra até 60; código expirado, usado, de outra conta e com 5 tentativas; sessão vencida e de outra licença; funcionário recebe `so_adm` em todas as rotas de gestão; último ADM não cai; `senha_versao` sobe; `resumo` não tem hash; `ajustar_computadores` recusa sem soltar o suficiente e solta as vagas certas; celular sem sessão passa em licença sem contas e falha com contas; marca igual sem contas e diferente ao criar conta; limite conta no handler de `EXCEPTION`.
- [ ] Rodar e ver falhar.
- [ ] Escrever a migration.
- [ ] Rodar `node tests/rodar.mjs` completo: verde, inclusive `celular_test` e `licenciamento_test`.

### Tarefa 2: Edge Functions

**Arquivos:** criar `supabase/functions/acesso/{nucleo,index}.ts`, `supabase/functions/tests/acesso.test.mjs`; alterar `licenca-assinada/{nucleo,index}.ts` e o teste dela.

**Produz:** `tratar(ambiente, rota, corpo, ip) -> {status, corpo}`, `rotaDe(caminho)`, `derivarSenha(senha, {iteracoes?, sal?}) -> "pbkdf2$600000$<sal>$<derivado>"`, `conferirSenha(senha, guardado) -> boolean`, `senhaAceitavel(senha, login) -> mensagem | ""`, `conteudoAcesso(...)` com `uso:"acesso"`, `conteudoLembranca(...)` com `uso:"lembrar"`.

Respostas com sessão trazem `{ok, sessao, usuario, acesso_assinado, lembranca}`. `lembranca` só com `lembrar: true`. `licenca-assinada` remove `acesso` da resposta em claro e devolve `acesso_assinado`, e `conteudoDaLicenca` ganha `contas`.

- [ ] Escrever testes: rotas conhecidas; derivar e conferir, senha errada e formato inválido; `senha_hash` nunca aparece em nenhuma resposta; código nunca volta; e-mail mascarado; `falha_no_envio`; senha fraca recusada antes do RPC; pacote `acesso` e `lembrar` assinados e presos ao computador; pedido incompleto.
- [ ] Ver falhar, implementar, ver passar. Rodar toda a suíte de `supabase/functions`.

### Tarefa 3: Núcleo do Hub

**Arquivos:** criar `src/dumtech/core/acesso.py`, `tests/test_acesso.py`; alterar `licensing.py`, `registry.py`, `paths.py`, `tests/assinante.py`.

**Produz:**

```python
class AcessoError(Exception): codigo: str
@dataclass(frozen=True) class Usuario: id, login, nome, papel, modulos, avisos, senha_versao, trocar_senha, ativo, tem_email, email_confirmado
class AcessoService:
    def __init__(self, licenca: Callable, arquivo: Path | None = None, client=None, relogio=time.monotonic)
    ha_contas, exigir_conta, usuario, e_adm, pode_gerenciar, gestao_aberta, sessao   # propriedades
    def falta_documento(self) -> bool
    def precisa_login(self) -> bool
    def permite_modulo(self, app_id) -> bool
    def permite_aviso(self, tipo) -> bool
    def recentes(self) -> list[Usuario]
    def abrir_lembrado(self) -> Usuario | None
    def reconciliar(self) -> bool                 # True = a pessoa logada precisa sair
    def sair(self, esquecer: bool = True) -> None
    def trancar_gestao(self) -> None
    # rede (2o plano)
    def criar_primeiro(nome, login, email, senha) -> dict
    def entrar(login, senha, lembrar) -> dict     # cai no offline quando sem internet
    def pedir_codigo(login) -> dict
    def redefinir(login, codigo, senha, lembrar) -> dict
    def pedir_confirmacao() -> str
    def confirmar_email(codigo) -> None
    def trocar_senha(atual, nova) -> dict
    def reabrir_gestao(senha) -> dict
    def listar_usuarios() -> list[dict]
    def salvar_usuario(dados, senha="") -> dict
    def definir_senha(usuario_id, senha) -> dict
    def apagar_usuario(usuario_id) -> dict
    def computadores() -> dict
    def renomear_computador(maquina, apelido) -> dict
    def liberar_computador(maquina) -> dict
    # thread da tela
    def aplicar(self, resposta: dict) -> Usuario
MODELOS: dict[str, tuple[str, ...]]               # Vendedor, Estoque, Tecnico, Financeiro
def validar_login(login) -> str
def validar_senha(senha, login="") -> str
def forca_da_senha(senha) -> int                  # 0 a 3
```

`License` ganha `acesso: dict` e `tem_contas: bool` (o valor vem só do pacote assinado). `AppRegistry` ganha `usar_acesso(servico)` e `visiveis()`. `available()` e `locked()` não mudam. `DataPaths.acesso_file`.

Testes usam `SupabaseClient` falso e `tests/assinante.py` com `pacote_acesso()` e `pacote_lembranca()`.

- [ ] Escrever testes: sem contas `e_adm` e tudo visível; com contas sem login nada visível; pacote removido do arquivo com `contas:true` exige login; entrar online grava verificador; entrar offline confere; offline com senha errada recusa; `senha_versao` diferente descarta verificador; primeiro login offline dá `primeiro_acesso_online`; JSON editado para `lembrado=adm` sem lembrança válida não entra; lembrança de outro computador não vale; `sair` apaga a lembrança; funcionário não vê módulo não marcado; ADM vê tudo; `visiveis` versus `available`; gestão vence sozinha; `reconciliar` com conta bloqueada, apagada e senha trocada; `validar_senha`.
- [ ] Ver falhar, implementar, ver passar. Rodar `tests.test_licenciamento`, `tests.test_licenca_tempo_real` e `tests.test_pagamentos`.

### Tarefa 4: Campo de senha

**Arquivos:** criar `src/dumtech/ui/widgets/campo_senha.py`, `tests/test_campo_senha.py`; alterar `ui/icons` se faltar o olho.

**Produz:** `CampoSenha(QLineEdit)` com `alternar()`, `visivel`; `MedidorDeSenha(campo)` ligado a `forca_da_senha`.

- [ ] Testar que começa oculto, que o olho alterna e que o texto se mantém. Ver falhar, implementar, ver passar.

### Tarefa 5: Login, esqueci e troca obrigatória

**Arquivos:** criar `hub/views/login_view.py`, `tests/test_login_tela.py`.

**Produz:** `LoginView(acesso, parent)` com sinal `entrou`, métodos `preparar()`. Páginas: entrar, esqueci (login), código + senha nova, trocar senha.

- [ ] Usar `frontend-design` e `design-skill` para a direção visual, reaproveitando `theme`, `Card`, `Button`.
- [ ] Testar: recentes em um clique preenchem o login; senha errada mostra recado; sem internet mostra aviso; esqueci vai ao código e mostra e-mail mascarado; `sem_email` manda pedir ao ADM; `trocar_senha` obriga a nova senha antes de `entrou`; "Lembrar" começa ligado.
- [ ] Ver falhar, implementar, ver passar.

### Tarefa 6: Assistente de conta

**Arquivos:** criar `hub/views/assistente_conta_view.py`, `tests/test_assistente_conta.py`.

**Produz:** `AssistenteContaView(acesso, empresa, conta, parent)` com `abrir(obrigatorio: bool)`, sinais `concluido`, `adiado`. Passos: convite, conta, e-mail, equipe, pronto.

- [ ] Testar: convite com "Agora não" e sem ele quando obrigatório; e-mail já preenchido; senhas diferentes bloqueiam; confirmar e-mail é pulável; equipe é pulável; modelo marca os módulos; "Copiar acesso" põe login e senha na área de transferência; passo final diz quantos computadores vão pedir login; sem internet não trava.
- [ ] Ver falhar, implementar, ver passar.

### Tarefa 7: Usuários, computadores e Minha conta

**Arquivos:** criar `hub/views/usuarios_view.py`, `hub/views/minha_conta_dialog.py`, `tests/test_usuarios_tela.py`.

**Produz:** `UsuariosView(acesso, registry, parent)` com sinal `mudou`; `MinhaContaDialog(acesso, parent)`.

- [ ] Testar: sem gestão aberta pede senha; lista mostra papel e último acesso; criar funcionário com modelo; ADM não marca módulos; avisos seguem os módulos marcados; redefinir, bloquear e apagar confirmam; último ADM mostra a recusa do servidor; computadores com "2 de 3", renomear e liberar; liberar este computador avisa que a licença sai; sair da seção tranca.
- [ ] Ver falhar, implementar, ver passar.

### Tarefa 8: Ligar no Hub

**Arquivos:** alterar `hub/main_window.py`, `hub/launcher.py`, `hub/views/home_view.py`, `hub/views/avisos_view.py`, `hub/views/celular_dialog.py`, `core/celular.py`; criar `tests/test_hub_acesso.py`.

Trocar por `visiveis()`: `_atualizar_perfil`, `refresh_rail`, `buscar_nos_dados`, `build_commands`, `_contar_novidades`, `_preparar_proximo`, `home_view:163`, `avisos_view:109`. **Manter `available()`:** `publicar_no_celular` e `sincronizar_online`. `launcher.open` e `preparar` checam `permite_modulo`; `consultaveis` filtra também; pontes seguem por `license_service.allows`.

`CelularService.__init__` ganha `sessao: Callable[[], str] = lambda: ""` e manda `p_sessao`.

Novos: `PAGINA_LOGIN`, `PAGINA_ASSISTENTE`, `_pagina_de_abertura()`, `_usuario_entrou()`, `_trocar_usuario()`, `_sair()`, `_talvez_convidar()`, `_acesso_mudou()`, menu (Minha conta, Trocar de usuário, Sair; itens de dono escondidos para funcionário), comandos da paleta filtrados, ofertas fora para funcionário, topo escondido no login, `UsuariosView` em Configurações.

`_tarefas_de_rede`: `conferir_licenca` também quando `falta_documento()`, e `antes` inclui a assinatura do pacote.

- [ ] Testar: sem contas abre no Início como antes; com contas abre no login; lembrado abre direto; funcionário não tem abas nem comandos proibidos, nem Licença, Backup, Configurações e celular; `open_app` recusa módulo não marcado; resumo do celular continua completo com funcionário logado; sair com carrinho aberto pergunta; permissão nova com trabalho aberto espera; convite aparece sem contas e some com "Agora não"; `exigir_conta` tira o "Agora não"; offline não bloqueia; primeiro acesso leva ao assistente depois de ativar.
- [ ] Ver falhar, implementar, ver passar. Rodar `tests.test_celular` e as baterias do Hub existentes.

### Tarefa 9: Painel

**Arquivos:** criar `painel/js/acessos.js`, `painel/js/telas/acessos.js`, `painel/tests/acessos.test.mjs`; alterar `telas/comercial.js`, `painel.js`, `index.html`, `css/estilo.css`, `README.md`.

**Produz:** `derivarSenha(senha)`, `gerarProvisoria()`, `vagasASoltar(ativos, maximo)`, `resumoMigracao(linhas)`, `semLogin(ativacoes, versaoMinima="1.11.0")`, `emailDifere(linha)`.

- [ ] Testar: hash do navegador aceito por `conferirSenha` do servidor; provisória forte; regras de reduzir vagas; contagem de migração; versão sem login.
- [ ] Ver falhar, implementar regras, ver passar.
- [ ] Cartão "Contas e acessos" na ficha, interruptor "Exigir conta", "x de y vagas" e selo de versão sem login.
- [ ] Editar licença: reduzir abaixo do uso lista computadores e usa `dumtech_ajustar_computadores`.
- [ ] Tela "Acessos" com tiles, filtro e "Exigir de todas" com confirmação.
- [ ] Conferir as telas com o PostgREST de mentira em 127.0.0.1 (`?api=`), como em `lancamento-seguro`.

### Tarefa 10: Fechar e lançar como pendente

**Arquivos:** alterar `src/dumtech/__init__.py`, `core/novidades.py`, `docs/licenciamento.md`, `supabase/functions/README.md`.

- [ ] Versão 1.11.0 e novidades.
- [ ] Rodar todas as baterias: Python, SQL, Edge, painel e landing.
- [ ] Usar `code-review` no que mudou. O `security-review` não roda aqui (sem `origin/HEAD`): revisar auth e sessões à mão.
- [ ] `npx supabase db push --linked --yes`; rodar `acesso_test.sql` com rollback em produção se fizer sentido.
- [ ] `npx supabase functions deploy acesso --no-verify-jwt --use-api` e `licenca-assinada`.
- [ ] Confirmar que um Hub sem conta segue conferindo a licença em produção.
- [ ] `tools\lancar_versao.ps1 -Pendente -Notas "..."` em segundo plano e sozinho. Publicar o painel junto.
- [ ] Abrir `build\dist\DumTech Hub\DumTech Hub.exe` com `DUMTECH_DATA_DIR` temporária e ler o log.
- [ ] Conferir que nada chegou ao cliente: `versao` sem chave e SHA do instalador público iguais aos de antes.
- [ ] Atualizar as memórias `auditoria-2026-10-30` e `lancamento-seguro`.
