# Publicar uma versão nova

O caminho inteiro, do código no computador até o cliente ser avisado. Se você
seguir esta ordem, nada chega quebrado em quem paga.

## Atalho: tudo num comando (o jeito recomendado)

Mude a versão em `src/dumtech/__init__.py` e rode:

```
powershell -ExecutionPolicy Bypass -File tools\lancar_versao.ps1 -Notas "O que mudou"
```

Ele testa tudo, gera o instalador, publica o arquivo com **a versão no nome**
(`/baixar/DumTech-Hub-Setup-1.2.5.exe`), baixa de volta do ar para conferir o
SHA-256 e **só então** registra a versão. Não é preciso colar SHA nem tamanho no
painel, e a estrutura do banco não muda: a versão é só uma linha de dados.

- `-SemAvisar` publica o arquivo sem registrar; você libera pelo painel depois.
- `-Obrigatoria` marca como atualização importante.
- `-Silenciosa` é para ajuste pequeno: o Hub (1.5.1 ou mais novo) baixa sozinho
  e instala quando o cliente fecha o programa, sem botão e sem "O que mudou"
  (não escreva novidade para ela em `core/novidades.py`). Hub mais antigo mostra
  o botão como sempre, e quem nunca fecha o Hub vê o botão depois de 7 dias.
  Tela nova pode ganhar a etiqueta "Novo" em `TELAS_NOVAS`, no mesmo arquivo.
- No painel (Segurança › Versão do DumTech Hub) dá para desligar "Atualizar pelo
  Hub" a qualquer momento.

Por que o nome com versão: o Hub só instala se o arquivo baixado tiver o SHA
registrado. Com um endereço fixo, trocar o arquivo antes (ou depois) de mudar o
registro fazia o cliente ver "o arquivo baixado não é o oficial". Um endereço por
versão nunca muda de conteúdo.

As seções abaixo são o mesmo caminho, passo a passo.

## 1. Conferir tudo (um comando)

```
powershell -ExecutionPolicy Bypass -File tools\verificar_tudo.ps1
```

Roda, nesta ordem: Hub (Python), painel, loja, Edge Functions e as migrations
num Postgres local. Termina com **"Tudo passou"** ou com a lista do que falhou.

Os testes do banco precisam do PGlite, uma vez só:

```
cd supabase
npm install
```

## 2. Numerar a versão

Em `src/dumtech/__init__.py`, `__version__`. Use número e ponto (`1.2.0`): é
assim que o Hub compara o que está instalado com o que está publicado.

## 3. Gerar o instalador (e anotar a impressão digital)

```
powershell -ExecutionPolicy Bypass -File build\build.ps1
```

Ele **roda os testes antes** e se recusa a gerar o instalador se algo falhar
(`-PularTestes` pula, só use quando acabou de rodar a conferência).

Saída: `build\dist\DumTech-Hub-Setup.exe`, e no fim ele imprime o **SHA-256** e
o **tamanho** — os dois vão para o painel no passo 5 (também ficam gravados em
`build\dist\DumTech-Hub-Setup.sha256.txt`).

## 4. Publicar o site (loja, painel e instalador)

```
powershell -ExecutionPolicy Bypass -File tools\publicar_site.ps1
```

Ele monta `build\site` (já com os dois `.htaccess`) e envia por FTP para a
HostGator. Os dados de acesso saem de variáveis de ambiente — nunca do
repositório:

| Variável | Exemplo |
|---|---|
| `HOSTGATOR_FTP_HOST` | `ftp.dumtechsolution.com` |
| `HOSTGATOR_FTP_USER` | o usuário de FTP do cPanel |
| `HOSTGATOR_FTP_PASS` | a senha dele |
| `HOSTGATOR_FTP_DIR` | opcional; padrão `/public_html` |

Para gravar de uma vez (abre um PowerShell novo depois):

```
setx HOSTGATOR_FTP_HOST "ftp.dumtechsolution.com"
setx HOSTGATOR_FTP_USER "usuario"
setx HOSTGATOR_FTP_PASS "senha"
```

**Sem essas variáveis ele não envia**: gera `build\site.zip` e sai com erro, de
propósito. Assim o passo 5 nunca registra uma versão cujo instalador ainda não
está no ar. Nesse caso, suba o zip pelo cPanel › Gerenciador de Arquivos ›
`public_html` › *Upload* e depois *Extract* (marque **Mostrar arquivos
ocultos** para conferir que o `.htaccess` foi junto).

Outras opções: `-SemPublicar` só monta a pasta, `-Zip` monta e empacota sem
tentar FTP, `-SemSsl` desliga o FTPS (use só se a HostGator recusar TLS).

### Se der "Cannot find project ref"

A CLI do Supabase guarda o projeto ligado em `supabase/.temp/`. Essa pasta é
ignorada pelo git e parece descartável — mas apagá-la **desliga a CLI do
projeto**, e o passo 5 (registrar a versão) passa a falhar. Religue com:

```
npx supabase link --project-ref kpiyhhmtteojqxhhmcyr
```

Nada se perde: é só o ponteiro local, não o banco.

### Se o site subir mas algo parecer errado

| Sintoma | Causa quase certa |
|---|---|
| O `.exe` abre no navegador em vez de baixar | o `.htaccess` não subiu (arquivo oculto) |
| O app do celular não instala | faltou `AddType ... .webmanifest`, ou seja, o `.htaccess` de novo |
| O botão "Pagar" não responde | o segredo `DUMTECH_SITE_URL` não é exatamente `https://dumtechsolution.com` |
| Baixar dá 403 | mod_security da HostGator bloqueando `.exe`; peça liberação no suporte |

## 5. Publicar a versão (o passo que faz o cliente atualizar)

No painel, aba **Segurança**, cartão **Versão do DumTech Hub**:

| Campo | O que é |
|---|---|
| Versão publicada | o mesmo número do passo 2 |
| Endereço para baixar | `https://dumtechsolution.com/baixar/DumTech-Hub-Setup.exe` |
| Recado | o que mudou — aparece dentro do Hub, na janela de atualizar |
| **SHA-256 do instalador** | o `build.ps1` imprime no fim (e grava em `build\dist\DumTech-Hub-Setup.sha256.txt`) |
| Tamanho em bytes | também sai do build — só serve para a tela dizer "29,7 MB" |
| **Atualizar pelo Hub** | ligado: o cliente atualiza com um clique. Desligado: o Hub só avisa e manda para a página |
| Atualização importante | só para falha de segurança: o aviso não pode ser dispensado |

⚠️ **O SHA-256 tem que ser o do arquivo que está publicado.** É ele que o Hub
confere antes de instalar: errado, a atualização falha em vez de instalar coisa
errada. Publique o site (passo 4) **antes** de preencher aqui.

### O que o cliente vê

1. Um botão **Atualizar para 1.2.2** aparece na barra de cima do Hub (e uma
   faixa no Início).
2. Clicando, abre uma janela com as duas versões, o que mudou e o tamanho.
3. Em **Baixar e instalar**: barra de progresso, conferência da assinatura e da
   impressão digital, o Hub fecha, o instalador roda em silêncio e **o Hub abre
   de novo já atualizado**. Não pede administrador (a instalação é por usuário)
   e não toca em dados, licença nem backups.
4. **Agora não** cala até sair outra versão — a não ser que ela seja marcada
   como importante.

O mesmo cartão mostra quantos computadores já estão na versão nova e quantos
ficaram para trás (o Hub informa a versão dele de hora em hora).

---

# Ambiente de teste (antes de mexer no banco de produção)

Hoje migration e Edge Function vão direto para o projeto que atende os clientes.
Para um ensaio antes, crie um **segundo projeto Supabase** (o plano grátis
permite) e aponte tudo para ele — sem recompilar nada:

| Onde | Como apontar para o projeto de teste |
|---|---|
| Hub | variáveis `DUMTECH_SUPABASE_URL` e `DUMTECH_SUPABASE_KEY` (só valem fora do `.exe`, de propósito) |
| Painel | `painel/js/config.js` → `SUPABASE_URL` e `SUPABASE_ANON` |
| Loja | `landingpage/js/config.js` |
| Edge Functions | `supabase functions deploy <nome> --project-ref <ref-do-teste>` |

No projeto de teste, aplique as migrations na ordem (SQL Editor ou
`supabase db push`) e rode as baterias de `supabase/tests/`.

**Regra prática:** toda migration nova é ensaiada lá antes de ir para a
produção. As de hoje são escritas para poderem rodar duas vezes sem estrago
(`create table if not exists`, `create or replace`), mas ensaiar é mais barato
que descobrir no cliente.
