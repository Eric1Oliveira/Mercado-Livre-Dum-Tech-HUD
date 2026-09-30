-- ============================================================================
-- Dominio proprio: dumtech-hub.netlify.app -> dumtechsolution.com
--
-- O endereco de download fica numa LINHA DE DADOS (hub_versoes.url), nao no
-- esquema. Por isso a troca vem numa migration e nao numa edicao da migration
-- antiga: mexer no arquivo de 20260917 nao mudaria nada no banco que ja rodou.
--
-- Por que isto importa: `core/versao.py` so aceita um endereco de atualizacao
-- cujo host seja o mesmo compilado dentro do .exe. Com o Hub novo apontando
-- para dumtechsolution.com e o banco ainda respondendo netlify.app, o Hub
-- descartaria a atualizacao EM SILENCIO - nao ha erro nenhum nessa recusa.
--
-- Roda duas vezes sem estrago: so troca o que ainda estiver no endereco velho.
-- ============================================================================

update public.hub_versoes
   set url           = replace(url, 'dumtech-hub.netlify.app', 'dumtechsolution.com'),
       atualizado_em = now()
 where url like '%dumtech-hub.netlify.app%';

-- Os comunicados (as "ofertas" do Inicio do Hub) tambem guardam endereco. O
-- botao leva o cliente para la, e `core/loja.py:e_da_loja` so acrescenta o
-- codigo que identifica quem chegou quando o link e da NOSSA loja. Link no
-- dominio velho deixaria de ser reconhecido: a oferta abriria sem identificar
-- o cliente, que teria de digitar nome e e-mail de novo.
update public.comunicados
   set link          = replace(link, 'dumtech-hub.netlify.app', 'dumtechsolution.com'),
       atualizado_em = now()
 where link like '%dumtech-hub.netlify.app%';
