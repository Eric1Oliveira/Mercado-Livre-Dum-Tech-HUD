# Telas do DumTech Hub

Uma pasta por parte do produto, na ordem em que o cliente encontra cada
coisa. Geradas por `tools/capturar_telas.py` com a loja de demonstracao
(`tools/dados_demo.py`) - nenhuma imagem aqui e montagem.

Sao 56 imagens, no **tema claro**; o
escuro aparece uma vez, como opcao.

| Pasta | O que tem |
|---|---|
| `00_hub` | inicio com avisos, licenca, config minha empresa, config avisos, config mensagens, config backup, sobre, paleta de comandos, inicio no outro tema |
| `01_estoque` | painel, produtos, entradas, movimentacoes, contagem, cadastro de produto, entrada de mercadoria |
| `02_clientes` | painel, lista de clientes, ficha de cadastro, ficha com anotacoes |
| `03_financeiro` | fluxo de caixa, painel, lancamentos, contas, novo lancamento, receber ou pagar, parcelamento, transferencia |
| `04_orcamentos` | funil, lista de propostas, montagem da proposta, motivo da recusa |
| `05_vendas` | balcao pdv, painel, lista de vendas, caixa do dia, pagamento, devolucao, fechamento do caixa |
| `06_ordens` | bancada, painel, lista de ordens, ficha da ordem, aprovacao do orcamento, entrega e garantia |
| `07_agenda` | grade da semana, lista de compromissos, novo compromisso |
| `08_documentos` | proposta comercial a4, comprovante de entrega a4, janela do documento, comprovante de venda bobina, entrada de os bobina, mensagem de whatsapp |
| `09_licenca` | inicio 7 modulos, inicio 1 modulo |

Para regerar:

    .venv\Scripts\python.exe tools/capturar_telas.py
    .venv\Scripts\python.exe tools/capturar_telas.py --escuro
