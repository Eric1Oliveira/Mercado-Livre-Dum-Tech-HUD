# Edge Functions da DumTech

| Função | Quem chama | Para quê |
|---|---|---|
| `licenca-assinada` | o **Hub** (chave anon) | confere a licença e devolve ela **assinada** (Ed25519). O Hub guarda e confere a assinatura toda vez que abre: editar ou copiar o `license.json` não libera nada |
| `enviar-chave` | o **painel** (token do administrador) | manda por e-mail a chave de uma licença, com os dados buscados no banco pelo próprio token de quem pediu |
| `pagamentos` | o **Hub** (chave anon) | a área **Configurações › Pagamentos**: manda o código de 6 dígitos para o e-mail **da licença**, abre uma sessão de 15 min, **assina a chave Pix** para cada computador e avisa o dono por e-mail a cada troca |
| `checkout` | a **loja** e a **InfinitePay** | cria o link de pagamento do pedido, recebe o aviso de pago, confere com a InfinitePay (`payment_check`) e entrega a licença; a página `/pedido/` pergunta por ela |

`licenca-assinada` e `enviar-chave` são opcionais: sem a primeira o Hub usa a
verificação antiga; sem a segunda o painel oferece WhatsApp, e-mail e copiar.
**`checkout` é obrigatória para a loja vender**: sem ela, o botão "Ir para o
pagamento" mostra o erro e oferece o WhatsApp.

## Checkout (InfinitePay)

1. **Banco:** no SQL Editor, cole e rode, nesta ordem,
   `migrations/20260913090000_vendas_e_identidade.sql` (se ainda não rodou) e
   `migrations/20260913150000_checkout_infinitepay.sql`.
   Para conferir: cole `tests/checkout_test.sql` (desfaz tudo no fim).
2. **Função:** `supabase functions deploy checkout --no-verify-jwt --project-ref kpiyhhmtteojqxhhmcyr`
   (ou pelo painel, *Via Editor*, com `index.ts` e `nucleo.ts`, **Verify JWT desligado**:
   a InfinitePay não manda token).
3. **Loja:** `tools\publicar_site.ps1`.

Segredos opcionais: `INFINITEPAY_HANDLE` (padrão `dumtechsolutions`) e
`DUMTECH_SITE_URL` (padrão `https://dumtechsolution.com`). O webhook é o
endereço da própria função (`.../functions/v1/checkout/webhook`), mandado em cada
link: não há nada para cadastrar no app da InfinitePay.

**Por que é seguro:** o aviso da InfinitePay não é assinado, então nenhuma licença
sai dele. A função pergunta de novo à InfinitePay, com a InfiniteTag da DumTech, e
o banco só entrega quando o valor confirmado cobre o pedido e a transação nunca foi
usada. A chave só aparece para quem tem o segredo do pedido (fica no navegador de
quem comprou), e só quando a licença nasceu nesta compra: quem digitar o e-mail de
um cliente antigo paga, os módulos entram na chave dele, e a chave não aparece.

## Pagamentos protegidos (código por e-mail)

A chave Pix do balcão só vale **assinada pelo servidor**: editar o `hub.json`
(funcionário ou vírus) não muda para onde o dinheiro vai. Para trocar a chave, o
Hub pede um código de 6 dígitos que chega no e-mail cadastrado **na licença**
(não um e-mail digitado no computador). Todo o controle mora no banco.

1. **E-mail grátis (escolha um):**
   - **Brevo** (recomendado, sem domínio): crie a conta em brevo.com, confirme o
     e-mail remetente em *Senders* (pode ser um Gmail) e gere a chave em
     *SMTP & API › API Keys*. 300 e-mails/dia grátis.
   - **Resend**: 3.000/mês grátis, mas exige domínio próprio verificado.
2. **Banco:** no SQL Editor, rode `migrations/20260916120000_pagamentos_protegidos.sql`.
   Para conferir: cole `tests/pagamentos_test.sql` (desfaz tudo no fim).
3. **Função:** *Deploy a new function › Via Editor*, nome `pagamentos`, com
   `index.ts` e `nucleo.ts` desta pasta, **Verify JWT desligado** (o Hub chama com a
   chave anon). Pelo CLI: `supabase functions deploy pagamentos --no-verify-jwt`.
4. **Segredos:** `BREVO_API_KEY` (ou `RESEND_API_KEY`) e `DUMTECH_EMAIL_REMETENTE`
   (ex.: `DumTech <seuemail@gmail.com>`). A chave de assinatura é a mesma da licença
   (`DUMTECH_LICENCA_CHAVE_PRIVADA` e `DUMTECH_LICENCA_KID`) — já cadastrada.
5. **Recompilar e distribuir o Hub.**

**Atenção:** o cliente precisa ter e-mail no cadastro (quem comprou pelo Mercado
Livre ganha o e-mail quando digita no primeiro acesso do Hub). Sem e-mail, o Hub
diz para falar com a DumTech. Depois da atualização, a chave Pix que estava em
"Minha empresa" **deixa de valer**: o QR Code volta quando o cliente cadastra a
chave em Configurações › Pagamentos (uma vez, com o código).

**Sem internet:** a área **não abre** e a tela diz isso ("conecte o computador para
mexer em Pagamentos"). Não existe código de reserva guardado na máquina do cliente —
seria mais uma chave para alguém achar. **O balcão continua vendendo normalmente**,
com a chave Pix já confirmada e o QR Code funcionando.

**Cliente perdeu o acesso ao e-mail:** troque o e-mail dele no painel (cadastro do
cliente). O próximo código já chega no endereço novo.

## Ordem para ligar tudo (sem travar ninguém)

1. **Publicar o painel novo** (tela do código de 2 fatores). Ele funciona com o banco antigo.
2. **Ligar o TOTP no Supabase:** Authentication › Multi-Factor › TOTP ativado.
3. **Aplicar as migrations** no SQL Editor, nesta ordem:
   `20260912180000_tempo_real_e_blindagem.sql` e depois
   `20260912210000_assinatura_mfa_auditoria.sql`.
   No próximo login o painel mostra o QR Code; leia com o celular.
4. **Publicar `licenca-assinada`** com os segredos (abaixo).
5. **Recompilar e distribuir o Hub** (`build\build.ps1`). Na primeira conferência com
   internet (até 1 h), cada Hub recebe a licença assinada.
6. **Depois que os clientes tiverem atualizado**, mude
   `ASSINATURA_OBRIGATORIA = True` em `src/dumtech/core/licensing.py` e recompile.
   A partir daí, `license.json` sem assinatura não abre módulo.
7. Quando tiver conta no Resend e domínio verificado: **publicar `enviar-chave`**.

## Publicar

O CLI desta máquina responde 403 para este projeto (a conta não tem o papel
necessário). Dois caminhos:

**Pelo painel do Supabase** — Edge Functions › *Deploy a new function* › *Via Editor*:
crie um arquivo por vez com o mesmo nome e conteúdo (`index.ts` e `nucleo.ts`).
Em `licenca-assinada`, **desligue "Verify JWT"** (o Hub chama com a chave anon).
Em `enviar-chave`, deixe ligado.

**Pelo CLI** (numa conta com permissão):

```
supabase functions deploy licenca-assinada --no-verify-jwt
supabase functions deploy enviar-chave
```

## Segredos (Edge Functions › Secrets)

| Segredo | Função | Valor |
|---|---|---|
| `DUMTECH_LICENCA_CHAVE_PRIVADA` | licenca-assinada | conteúdo de `%USERPROFILE%\DumTech-segredos\licenca-k1-privada.txt` |
| `DUMTECH_LICENCA_KID` | licenca-assinada | `k1` |
| `DUMTECH_LICENCA_DIAS_OFFLINE` | licenca-assinada | opcional, padrão `30` (1 a 90): quantos dias o Hub abre sem conferir |
| `RESEND_API_KEY` | enviar-chave | chave da conta no resend.com |
| `DUMTECH_EMAIL_REMETENTE` | enviar-chave | `DumTech <licencas@seudominio.com.br>` (domínio verificado no Resend) |
| `DUMTECH_EMAIL_RESPONDER` | enviar-chave | opcional: para onde vai a resposta do cliente |
| `DUMTECH_PAINEL_ORIGEM` | enviar-chave | opcional: `https://painel.seudominio.com.br` (restringe o CORS) |

**A chave privada** emite licença de qualquer módulo para qualquer pessoa. Ela só
existe no arquivo acima (guarde num cofre de senhas e apague do disco depois) e no
segredo da função. O arquivo está no `.gitignore` da pasta pessoal.

Para trocar de chave: `node tools/gerar_chave_licenca.mjs "%USERPROFILE%\DumTech-segredos" k2`,
**acrescente** a pública nova em `CHAVES_PUBLICAS` (sem tirar a `k1`), recompile e
distribua o Hub, e só então troque os segredos para `k2`.

## Perdeu o celular do 2 fatores?

Supabase › Authentication › Users › (a conta) › apague o fator MFA. No próximo login
o painel pede para cadastrar de novo.

## Testes

```
node --test tests/licenca-assinada.test.mjs tests/enviar-chave.test.mjs tests/checkout.test.mjs tests/pagamentos.test.mjs
```

O teste da assinatura gera um pacote com WebCrypto (a mesma do Deno), e
`tests/test_assinatura.py`, no Hub, confere um pacote assinado assim em Python —
as duas pontas provadas uma contra a outra.
