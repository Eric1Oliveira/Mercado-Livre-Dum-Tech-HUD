# Painel DumTech

O lugar de onde a DumTech enxerga o negócio: clientes, licenças, pedidos,
catálogo, anúncios e uso dos módulos. É HTML, CSS e JavaScript puro — sem build,
sem framework, sem dependência. Abre com um servidor estático e fala direto com
o Supabase.

```
painel/
  index.html          a casca: tela de entrada + topo + área da tela
  css/estilo.css      o visual (mesma identidade do Hub e da landing)
  js/
    config.js         URL e chave pública do projeto Supabase
    api.js            Supabase Auth + PostgREST (ler, inserir, atualizar, rpc)
    painel.js         entrar/sair, navegação, gaveta, recarregar
    ui.js             as peças: tabela, pílula, tile, cartão, recado
    formato.js        dinheiro, data, "há 5 dias", telefone, CPF/CNPJ
    modulos.js        cor e ícone de cada módulo (os mesmos do Hub)
    telas/
      comercial.js    Resumo, Clientes (+ ficha) e Pedidos
      catalogo.js     Catálogo (módulos e combos) e Anúncios
      uso.js          Uso (analytics) e Segurança
  tests/              testes do que é lógica pura (node --test)
  servidor.mjs        servidor de desenvolvimento
```

## Como abrir

```
node servidor.mjs          # http://localhost:4010
```

`file://` não serve: o navegador recusa módulos ES nessa origem e o Supabase Auth
precisa de uma origem de verdade.

## Como criar um administrador

Não existe cadastro no painel — de propósito. A conta nasce no Supabase e é
liberada à mão:

1. **Authentication → Users → Add user**: e-mail e senha, com *Auto Confirm User*
   marcado. Copie o **UID**.
2. No **SQL Editor**:

   ```sql
   insert into public.administradores (user_id, nome)
   values ('<UID copiado>', 'Eric');
   ```

Quem entra com uma conta que não está nessa tabela é recusado na porta — e, mesmo
que forçasse a entrada, não veria uma linha: as *policies* do banco perguntam
`dumtech_e_admin()` em toda leitura e toda escrita. O front não decide nada.

> A migration `20260912120000_painel_admin.sql` precisa estar aplicada no projeto.
> Sem ela não existem nem a tabela `administradores`, nem as visões do painel.

## O que cada tela faz

| Tela | O que mostra | O que dá para fazer |
|---|---|---|
| **Resumo** | clientes, licenças ativas e vencidas, módulos vendidos, faturado, pedidos esperando, uso em 30 dias, chaves recusadas em 24h | ir direto ao que precisa de você |
| **Clientes** | todo mundo, com licença, situação, módulos, computadores e uso; busca por nome, e-mail ou chave | abrir a ficha |
| **Ficha** (gaveta) | dados, licença, módulos que tem e que não tem, uso por módulo nos últimos 30 dias, o que faz sentido oferecer **e por quê**, computadores ativados, histórico de pedidos | suspender/reativar/cancelar licença, liberar ou tirar módulo, liberar vaga de computador |
| **Pedidos** | o que chegou do site e do Hub, com o kit e o total | aprovar (libera os módulos e devolve a chave) |
| **Catálogo** | módulos e combos, com preço, quantos clientes têm e quanto usam | criar/editar módulo e combo, mudar preço, tirar de linha |
| **Anúncios** | o pop-up que aparece no Início do Hub, uma vez por cliente | montar o anúncio vendo a **prévia do pop-up** como o cliente vai ver, mirar em quem *não* tem um módulo, agendar início e fim, e ver a situação real de cada um (no ar, programado, encerrado, parado) |
| **Uso** | aberturas por módulo, quem mais usa, e quem sumiu há mais de 14 dias | achar cliente prestes a desistir |
| **Segurança** | chaves recusadas, computadores insistindo (10+ tentativas em 24h) e ativações | ver tentativa de pirataria |

## De onde vêm os números

Tudo de visões `security_invoker` criadas na migration do painel — elas obedecem
as *policies*, não as contornam:

- `painel_resumo` — o retrato do negócio, numa linha.
- `painel_clientes` — cada cliente numa linha, com licença, módulos e uso.
- `painel_modulos` — cada módulo: clientes, aberturas, licenças ativas.
- `painel_recomendacoes` — o cruzamento de `integracoes` com o que o cliente já
  tem: "usa Vendas 168 vezes por mês e não tem Orçamentos".
- `pedidos_abertos` — a caixa de entrada comercial.

O uso vem de `uso_diario`, que o Hub envia agregado por dia: módulo, dia,
computador, quantas aberturas. Não há hora nem sequência — nem aqui, nem no banco.

## Entrar: senha + código do celular

Com a migration `20260912210000_assinatura_mfa_auditoria.sql`, o banco só entrega
dado a sessão **aal2** (senha + código TOTP). Na primeira entrada o painel mostra um
QR Code para o aplicativo autenticador; nas seguintes, pede o código de 6 números.
Pular a tela no navegador não adianta: toda policy pergunta `dumtech_e_admin()`, que
exige aal2. Sem a migration, o painel entra só com a senha, como antes.
Perdeu o celular: Authentication › Users › apague o fator MFA da conta.

## Vender fora da loja (Mercado Livre, WhatsApp, telefone)

**Clientes › Nova venda** (ou, na ficha, **Registrar venda**): canal, número do pedido
do ML, comprador, combo/módulos, tipo, computadores e valor recebido. O banco
(`dumtech_venda_manual`) cadastra quem precisar, entrega na licença que o cliente
**já tem** (inclusive suspensa ou vencida, que volta a valer) e registra a venda —
“Vendido” e “Comprou” contam tudo. Passo a passo em
[docs/mercado-livre.md](../docs/mercado-livre.md).

Na ficha: **Editar** (dados do cliente) e **Editar licença** (tipo, vencimento,
computadores — renovar é mudar a data). Nos pedidos, o painel avisa o que o cliente
**já tem** e se a licença dele está suspensa/cancelada/vencida, e a aprovação escolhe
o tipo (manter, vitalícia, assinatura até…).

## Enviar a chave ao cliente

Aprovar um pedido ou registrar uma venda abre a gaveta **Enviar a chave**, em dois
modos: **WhatsApp/e-mail** (com o link de download e o suporte) e **Mercado Livre**
(sem link, e-mail nem telefone — o painel confere antes de copiar — e com o guia PDF
para anexar). Se a Edge Function `enviar-chave`
estiver publicada e configurada, o e-mail sai sozinho e a gaveta confirma. A ficha
do cliente também tem o botão "Enviar chave".

## Quem mexeu em quê

A tela **Segurança** mostra as últimas alterações (tabela `auditoria`, gravada por
gatilho): quem, quando, o que mudou e o valor de antes e de depois. Ninguém apaga
pela API. O que o Hub e o site fazem pelas funções públicas não entra.

## Publicar

`.htaccess` (Apache/HostGator) e `_headers` (Netlify/Cloudflare Pages) já trazem
HTTPS obrigatório, proibição de iframe (clickjacking), `nosniff`, `noindex` e cache
revalidado. Publique a pasta inteira; `tests/`, `servidor.mjs` e `package.json`
ficam bloqueados no Apache.

## Velocidade e tempo real

- **Memória das leituras** (`js/api.js`): tela já vista abre na hora com o que se
  sabe, e a rede confere por trás. Gravar corrige a memória com o que o banco
  devolveu — o preço salvo aparece antes de a conferência terminar.
- **Tela desenhada fora da página** (`js/painel.js`): troca de uma vez, sem piscar
  "Carregando"; logo depois de entrar, as outras abas são preparadas em segundo plano.
- **Ao vivo**: o banco avisa pelo Supabase Realtime (canal privado `painel`, só
  administrador entra) e a tela aberta se atualiza sozinha — pedido novo acende o
  selo e mostra um recado. O selo "Ao vivo" no topo diz se a conexão está de pé.
  O aviso não carrega dado: o painel busca de novo pelas policies de sempre.
- `js/tempo-real.js` é **cópia idêntica** do da landing (os testes moram lá).

Medido no navegador contra um servidor com 120 ms de latência: trocar de aba
2–20 ms; preço salvo aparece no painel em ~190 ms e no site em ~450 ms, sem refresh.

> Precisa da migration `20260912180000_tempo_real_e_blindagem.sql` aplicada. Sem
> ela o painel funciona igual, só sem o "ao vivo" (confere ao voltar para a aba).

## Testes

```
node --test tests/formato.test.mjs
```

Testa o que é lógica pura (dinheiro, datas, "há 5 dias", telefone, CPF/CNPJ,
iniciais). O resto é DOM e rede, e se verifica abrindo o painel.
