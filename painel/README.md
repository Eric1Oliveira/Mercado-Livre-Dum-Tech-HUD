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
    saude.js          as regras do uso: quem esfriou/sumiu, Hub aberto, versão, testes, celulares
    graficos.js       aberturas por dia (colunas) e a faixa de 30 dias de cada cliente
    telas/
      comercial.js    Resumo, Clientes (+ ficha) e Pedidos
      catalogo.js     Catálogo (módulos e combos) e Anúncios
      uso.js          Uso (analytics) e Segurança
      testes.js       Testes grátis
      celulares.js    Celulares (o "Ver no celular" de cada cliente)
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
| **Clientes** | todo mundo, com licença, situação, módulos, computadores e uso; busca por nome, e-mail ou chave | abrir a ficha, **cadastrar cliente** (sem venda), registrar venda |
| **Ficha** (gaveta) | dados, licença, módulos que tem, que não tem e que está **testando**, a faixa de uso dos últimos 30 dias e o último uso de cada módulo, testes grátis, celulares, o que faz sentido oferecer **e por quê**, computadores (versão do Hub e se está aberto agora), histórico de pedidos | editar, suspender/reativar/cancelar licença, liberar ou tirar módulo, **dar, estender e encerrar teste grátis**, **desconectar celular**, liberar vaga de computador, **excluir a licença**, **excluir o cliente**, abrir um pedido |
| **Pedidos** | os em aberto (site, Hub) e **todas** as vendas feitas, com busca por nome, e-mail ou nº do pedido e "carregar mais" | aprovar (libera os módulos e devolve a chave); clicar abre o pedido: **ver, editar e excluir** |
| **Catálogo** | módulos e combos, com preço, quantos clientes têm e quanto usam | criar/editar módulo, mudar preço, tirar de linha, **excluir** (só módulo que ninguém tem) |
| **Anúncios** | o pop-up que aparece no Início do Hub, uma vez por cliente | montar o anúncio vendo a **prévia do pop-up** como o cliente vai ver, mirar em quem *não* tem um módulo, agendar início e fim, e ver a situação real de cada um (no ar, programado, encerrado, parado) |
| **Uso** | aberturas por dia (e contra os 30 dias antes); cada cliente com licença: situação (usando, esfriando, sumiu, nunca abriu, não instalou), a faixa de 30 dias, cada computador com a versão do Hub e se está aberto agora, celulares; módulo **pago e não aberto**; uso por módulo; quem clicou em **Comprar no Hub** e se fez pedido | filtrar quem pede atenção, abrir a ficha, chamar no WhatsApp com o recado pronto |
| **Testes grátis** | quem está testando o quê, quanto do teste já passou, quanto usou **durante** o teste, quem comprou e a conversão | estender 7 dias (ou reabrir), encerrar, chamar no WhatsApp |
| **Celulares** | celulares conectados, quando cada um abriu, se o resumo dos dados está chegando, quem ainda não conectou e os desconectados | desconectar um celular, contar do celular pelo WhatsApp |
| **Segurança** | chaves recusadas, computadores insistindo (10+ tentativas em 24h), ativações com a versão do Hub | ver tentativa de pirataria |

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

## Uso, testes grátis e celulares

Com a migration `20261019120000_painel_uso_testes_celular.sql`:

- **Visões novas**: `painel_uso_dias` (uma linha por dia), `painel_uso_por_cliente` (a faixa
  de 30 dias numa linha por cliente: o PostgREST corta leitura acima de 1000 linhas),
  `painel_modulos_da_licenca`
  (cada módulo pago com o último uso) e `painel_testes` (cada teste, com o uso
  **durante** o teste e se virou compra).
- **Teste grátis**: o administrador dá (o começo é sempre agora), estende e encerra.
  Apagar, não: o teste feito é o que impede o mesmo cliente de testar de novo. A
  impressão digital da licença inclui os testes, então a mudança chega ao Hub em até
  2 minutos, como módulo liberado.
- **Celular**: o administrador desconecta, como o "Desconectar" do Hub.
- **Hub aberto agora**: o Hub pergunta a versão a cada 2 minutos e o banco anota de
  hora em hora; "aberto" é ter falado com o servidor na última hora e pouco.
- **O que o painel não vê**: o conteúdo do celular (vendas, clientes e valores da
  empresa do cliente) e o código de compra do "Comprar no Hub". O privilégio é por
  coluna: o painel lê só *quando* cada computador publicou o resumo, e quem clicou
  em Comprar e quando. Nem um painel adulterado consegue pedir mais.
- As regras (quem esfriou, quem sumiu, versão em dia, estado do teste e do celular)
  ficam em `js/saude.js`, testadas em `tests/saude.test.mjs`.
- **Sem a migration**, o painel publicado não quebra: a ficha abre sem os cartões
  novos, e Uso, Testes grátis e Celulares dizem que falta atualizar o banco.

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

## Excluir

Tudo o que o painel cadastra também se exclui. O banco deixa (as *policies* do
administrador valem para ler, gravar e apagar) e grava cada exclusão na
auditoria, com o valor de antes — a tela **Segurança** mostra.

| O quê | Como pede confirmação | O que vai junto |
|---|---|---|
| **Cliente** | digitar `EXCLUIR` | a licença e tudo dela (módulos, computadores, celulares, uso, Pix do Hub). Os pedidos ficam em Pedidos, sem ligação; os em aberto não podem mais ser aprovados |
| **Licença** | digitar `EXCLUIR` | módulos, computadores, celulares e uso. O cliente fica, como interessado |
| **Pedido em aberto, não pago** | um "ok" | nada: nenhuma licença muda |
| **Pedido pago ou atendido** | digitar `EXCLUIR` | o registro da venda e do pagamento; o valor sai de "Vendido". Os módulos entregues **continuam** na licença (para tirar, use a ficha) |
| **Módulo do catálogo** | um "ok" | só sai se ninguém tem; com cliente, kit, teste ou anúncio, o banco recusa e a tela diz onde ele está (ou oferece tirar de linha) |
| **Kit, cupom, anúncio** | um "ok" | vendido/usado também sai: quem comprou não perde nada, e os pedidos guardam o nome/código |

Cliente e licença mostram, antes do `EXCLUIR`, o caminho mais leve: cancelar a
licença para os módulos pararem e o histórico ficar. A exclusão confere que o
banco realmente apagou (`apagar(..., { conferir: true })`) — se uma *policy*
barrar, a tela diz, em vez de anunciar "excluído".

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
node --test "tests/**/*.test.mjs"
```

Testa o que é lógica pura (dinheiro, datas, "há 5 dias", telefone, CPF/CNPJ,
iniciais). O resto é DOM e rede, e se verifica abrindo o painel.
