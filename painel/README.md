# Painel DumTech

O lugar de onde a DumTech toca o negócio: o que precisa de você hoje, os
clientes e as assinaturas, os planos, o site, o Hub e a segurança. É HTML, CSS
e JavaScript puro — sem build, sem framework, sem dependência. Abre com um
servidor estático e fala direto com o Supabase.

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
    gestao.js         as regras dos clientes: online, atualização, filtros, ordem, CSV, linha do tempo
    gestao-dados.js   o que Clientes e Atualizações leem do banco
    acessos.js        as regras das contas: senha provisória, vagas e migração
    atualizar.js      os botões Atualizar, Forçar, Recolher e Descartar
    graficos.js       aberturas por dia (colunas) e a faixa de 30 dias de cada cliente
    fila.js           a fila de Hoje: o que entra, em que ordem, o que conta no selo
    telas/
      hoje.js         Hoje: a fila com os botões que resolvem e os números do mês
      clientes.js     Clientes: todos numa lista, atalhos, filtros, etiquetas, CSV
      comercial.js    a ficha do cliente (uma só para todos) e os pedidos antigos da loja
      mensalidades.js o bloco Assinatura da ficha e as ações da mensalidade
      ficha-gestao.js os cartões de acompanhamento, atualização e linha do tempo
      planos.js       Planos > Planos e preços
      promocoes.js    Planos > Cupons e Site > Faixa de aviso
      textos-site.js  Site > Textos do site
      atualizacoes.js Hub > Atualizações: a versão pendente e o histórico
      uso.js          Hub > Uso e Segurança > Tentativas e auditoria
      catalogo.js     Hub > Anúncios
      acessos.js      Segurança > Contas de acesso, e o cartão de contas da ficha
      testes.js       o teste grátis de um módulo (ficha do vitalício)
      celulares.js    o celular de cada cliente (ficha)
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
> Clientes e Atualizações precisam de `20261101180000_gestao_e_atualizacoes.sql`.
> Sem ela não existem nem a tabela `administradores`, nem as visões do painel.

## O que cada tela faz

Seis lugares no menu (no celular, a barra de baixo). Planos, Site, Hub e
Segurança têm abas. Desde 04/11/2026 a loja vende **só mensalidade**: Resumo,
Pedidos, Nova venda, Catálogo de preços, Kits e os cupons antigos saíram, e
Assinantes, Testes grátis, Celulares, Uso e Acessos entraram na ficha ou viraram abas.

| Tela | O que mostra | O que dá para fazer |
|---|---|---|
| **Hoje** | a fila do que precisa de você (assinatura para confirmar, pagamento a confirmar ou só consulta, teste acabando ou que terminou, quem não instalou, assinante que parou de usar, quem cancelou, retorno combinado, pedido antigo da loja, versão do Hub para lançar, chaves recusadas demais) e os números do mês (receita, assinantes, testando, online agora); embaixo, o que aconteceu por último | resolver ali: **Confirmar assinatura**, **Descartar**, **Pagamento em dia**, **+7 dias**, WhatsApp com o recado pronto (sempre gentil); clicar abre a ficha. O selo vermelho conta o que não pode esperar |
| **Clientes** | todo mundo numa lista: plano e situação da mensalidade (vitalício aparece só como "Vitalícia"), os sete módulos, uso em 30 dias e conexão | busca; atalhos (Assinantes, Testando, Vitalícios, Sem licença, Pedem atenção, Online agora); **Filtros** finos (mensalidade, versão, módulo, licença, uso, validade, canal, etiqueta, retorno...); etiquetar vários; **exportar** CSV |
| **Ficha** (gaveta) | uma só para todos: no topo quem é e como está (situação, valor, contato, chave, computadores); depois **Assinatura** (assinante e teste) ou **Módulos** (vitalício), acompanhamento, uso, computadores, Hub e atualização, contas, celular, o que oferecer, linha do tempo com o histórico da assinatura e os pedidos antigos | assinatura: ativar, +7 dias, falhou, em dia, encerrar, reabrir, mudar plano/valor/computadores/datas (com "avisar por e-mail"); vitalício: liberar ou tirar módulo, teste grátis de módulo, computadores; para todos: WhatsApp, enviar chave, editar dados, liberar vaga, atualizar só ele, desconectar celular, suspender, cancelar, excluir |
| **Planos** | Planos e preços (a base, cada adicional, os planos prontos, o link de cada combinação, teste e carência) · Cupons | editar tudo o que o site cobra; criar cupom de parceiro |
| **Site** | Textos do site (rascunho e publicado) · Faixa de aviso | editar, ver como fica, publicar e voltar; faixa com datas |
| **Hub** | Atualizações (versão pronta, onde cada computador está, histórico) · Uso (aberturas, quem esfriou, módulo pago e não aberto) · Anúncios (o pop-up do Início) | **Atualizar todos**, **Forçar todos**, Descartar, Recolher; montar anúncio vendo a prévia |
| **Segurança** | Tentativas e auditoria (chaves recusadas, computadores insistindo, quem mexeu em quê) · Contas de acesso (quem já criou conta no Hub) | ver tentativa de pirataria; exigir conta |

**Pedidos antigos da loja** (o checkout do módulo avulso) ficou fora do menu: se
algum chegar, Hoje mostra e leva até lá para aprovar ou descartar.

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

## Lançar uma versão

```
tools\lancar_versao.ps1 -Pendente -Notas "O que mudou"
```

O script roda os testes, gera o instalador, sobe e confere o arquivo e registra a versão em
`hub_lancamentos`. **Nenhum cliente recebe.** A partir daí quem decide é o painel:

| Botão | Quem recebe | Como chega |
|---|---|---|
| **Atualizar** (cliente ou selecionados) | só eles | o botão Atualizar aparece; o cliente escolhe a hora. Serve para testar com um cliente antes |
| **Forçar** (cliente ou selecionados) | só eles | obrigatório, veja abaixo |
| **Atualizar todos** | todos | como Atualizar |
| **Forçar todos** | todos | obrigatório; pede para digitar a versão |
| **Recolher** | quem não instalou | volta a oferecer a versão anterior, e a nova volta a ser pendente. Quem já instalou fica nela |

**O que Forçar faz depende do Hub instalado.** Hub 1.10.0 ou mais novo baixa, avisa por cima de
tudo, conta 5 minutos, instala e abre de novo. Hub 1.5.1 a 1.9.0 baixa sozinho, mostra em até 5
minutos o aviso que não se dispensa e instala quando o programa é fechado; se o cliente clicar no
aviso, instala na hora. Hub mais antigo só mostra o aviso. O servidor manda os sinais assinados, e
cada Hub obedece ao que conhece.

O instalador do site (`/baixar/DumTech-Hub-Setup.exe`) continua sendo o da versão no ar, e as
páginas de download perguntam ao banco qual é a versão lançada: quem compra hoje não recebe uma
versão pendente.

## Quem está online

Cada Hub bate no servidor de 2 em 2 minutos, e `hub_presenca` anota. Online é ter batido nos
últimos 5 minutos (`ONLINE_MS` em `js/saude.js`), então fechar o Hub leva até 5 minutos para
aparecer. Vale para todo Hub 1.2.3 ou mais novo, sem atualizar nada. A batida não passa pelo tempo
real nem pela auditoria: a tela aberta confere a cada minuto.

## Entrar: senha + código do celular

Com a migration `20260912210000_assinatura_mfa_auditoria.sql`, o banco só entrega
dado a sessão **aal2** (senha + código TOTP). Na primeira entrada o painel mostra um
QR Code para o aplicativo autenticador; nas seguintes, pede o código de 6 números.
Pular a tela no navegador não adianta: toda policy pergunta `dumtech_e_admin()`, que
exige aal2. Sem a migration, o painel entra só com a senha, como antes.
Perdeu o celular: Authentication › Users › apague o fator MFA da conta.

## Venda avulsa (Mercado Livre, WhatsApp)

Saiu do painel em 04/11/2026: a loja vende só mensalidade, e quem fecha pelo
WhatsApp começa o teste no site e vira assinante com **Ativar assinatura**, na
ficha. O banco continua com `dumtech_venda_manual` e o passo a passo antigo está
em [docs/mercado-livre.md](../docs/mercado-livre.md), se um dia voltar.

## Enviar a chave ao cliente

O botão **Enviar chave**, no topo da ficha (e o aprovar de um pedido antigo), abre a gaveta, em dois
modos: **WhatsApp/e-mail** (com o link de download e o suporte) e **Mercado Livre**
(sem link, e-mail nem telefone — o painel confere antes de copiar — e com o guia PDF
para anexar). Se a Edge Function `enviar-chave`
estiver publicada e configurada, o e-mail sai sozinho e a gaveta confirma.

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
