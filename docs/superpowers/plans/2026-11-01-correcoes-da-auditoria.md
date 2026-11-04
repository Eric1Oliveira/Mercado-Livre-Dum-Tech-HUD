# Correções da auditoria (itens 1-23, 32, 34-39)

**Objetivo:** resolver os erros, as integrações internas e as melhorias escolhidas pelo Eric em 2026-11-01.
**Fora do escopo, por decisão dele:** 24-31 (integrações externas), 33 (usuários) e 40-45 (segurança e proteção do negócio, inclusive push e assinatura).
**Regras:** sem commit, sem push, sem publicar e sem lançar versão até ele pedir. Toda mudança de banco é migração nova. Cada fase termina com os testes da área; o conjunto inteiro roda no fim.
**Testes:** `QT_QPA_PLATFORM=offscreen PYTHONPATH=src .venv/Scripts/python.exe -m unittest tests.<modulo>` (todos: ~10 min).

## Decisões

- **Migração atômica:** cada `Migration` roda em `BEGIN IMMEDIATE ... COMMIT`, com `foreign_keys` desligado fora da transação (dentro é ignorado) e `foreign_key_check` antes do commit. Antes de migrar banco com dados, cópia `<banco>.antes-v<N>.bak`.
- **`Database.transaction` reentrante:** o bloco interno não dá commit. É o que torna `importar`, `salvar` e `movimentar` tudo-ou-nada.
- **Sem limite em soma:** `limite=-1` (LIMIT -1 no SQLite) em todo resumo. Listas que cortam escolhem os registros mais perto de hoje e avisam "mostrando só N".
- **Troco:** `vendas_dinheiro` soma o `recebido` (o que entrou); `esperado` continua tirando `trocos`.
- **Devolução:** coluna `devolucoes.em_dinheiro`. Só sai da gaveta o que foi pago em dinheiro; histórico fica com o valor antigo.
- **Baixa de estoque por linha:** `venda_itens.baixado` e `os_itens.baixado`. Cancelar devolve só o que saiu de verdade.
- **Editar venda paga:** só Cliente e Observações. Itens e valores travados, com recado (corrige por Devolução ou cancelando). Pendente pode mudar itens: ajusta estoque e conta (`Contas.ajustar`).
- **Financeiro → Vendas:** `Origem.conta_recebida/conta_reaberta` em `core/contas.py`, chamada pelo repositório do Financeiro por `ao_quitar`/`ao_reabrir`. A ponte `ContasFinanceiro` não tem esses ganchos, então não há laço. Dados antigos: `financeiro.conciliar` fecha sem mexer na gaveta.
- **Gaveta:** contrato `core/caixa.py` (`Gaveta.entrada`). Tipo novo `recebimento` em `caixa_movimentos`. Só OS e baixa manual do Financeiro usam; baixa de conta de venda entra pela própria venda.
- **Caixa → Financeiro:** sangria pergunta "Pagou despesa" ou "Guardou/depositou". Despesa vira lançamento pago; guardar vira transferência (caixa→banco) se existirem as duas contas, senão lançamento em categoria fora do resultado. Suprimento é o inverso. Sobra e quebra viram lançamento no fechamento.
- **Vencimento:** coluna `vendas.vencimento`, padrão 30 dias (`PRAZO_PADRAO_DIAS`), vale para prazo, pendente e primeira parcela. Pendente exige cliente.
- **Desconto por linha:** unitário arredonda para cima e a diferença entra no desconto do documento; o total fecha no centavo.
- **Proposta:** coluna `orcamentos.gerado`. Gerar de novo pede confirmação. Sem destino na licença, aprovar lança conta com o número da proposta; reabrir cancela.
- **Cliente:** continua por nome, sem `cliente_id`. Renomear propaga a todos os módulos pela `Consulta`. Duas pessoas de mesmo nome seguem juntas (limite conhecido).
- **Consulta:** contrato único `core/consulta.py`, um `apps/<x>/consulta.py` por módulo: `buscar` (item 39), `do_cliente` (20), `renomear_cliente` (20), `vendido_por_cliente` (21).
- **Variações:** cada tamanho/cor é um produto de verdade ligado por `grupo`. Reaproveita venda, código de barras e saldo.
- **Lote:** tabela `lotes`, saída consome primeiro o que vence antes (FEFO).
- **Aviso de agendamento (23):** e-mail pela Edge Function `avisar-reserva` e reservas lidas pelo app do celular. Sem Web Push, que exigiria chaves novas e não dá para provar sem publicar.
- **Sinal online (38):** depende de pagamento por empresa, que é integração externa fora do escopo. Sinal fica manual e vai ao Financeiro.
- **Modo consulta (35):** `PRAGMA query_only` nos bancos dos módulos. Só libera ver e exportar; nunca libera escrever.

## Fases

### A. Base
- [x] 5 Migração atômica, cópia antes de migrar, transação reentrante
- [x] 5 Restaurar: confere tudo antes, troca atômica, devolve `hub.json`, para se a cópia de segurança falhar
- [x] 5 Trava de instância única
- [x] 4 Backup automático vai para fora, roda com o Hub aberto e avisa quando falha

### B. Vendas
- [x] 1 Troco no Caixa
- [x] 12 Venda lançada entra na gaveta; devolução de Pix não sai dela
- [x] 3 Resumo do Vendas sem limite; aviso de lista cortada no `CrudView`
- [x] 6 Estoque por linha
- [x] 7 Edição de venda paga e de pendente
- [x] 11 Vencimento e cliente obrigatório
- [x] 15 Centavos do desconto
- [x] 8 Receber no Financeiro fecha a venda

### C. Financeiro
- [x] 2 Lista não esconde a conta de hoje
- [x] 13 Quitar sem conta soma no saldo
- [x] 22 Compra parcelada
- [x] 16 Caixa → Financeiro
- [x] 17 Recebimentos → Gaveta

### D. OS, Orçamentos, Agenda, Estoque
- [x] 9 Cancelar e excluir OS
- [x] 14 Proposta gerada e duplicada
- [x] 18 Proposta → Financeiro
- [x] 3 Agenda, Orçamentos e Ordens sem corte
- [x] 10 Planilha

### E. Integrações
- [x] 19 Agenda → Vendas e OS
- [x] 20 Cliente completo
- [x] 21 Parceiros e comissão
- [x] 23 Aviso de agendamento online

### F. Melhorias
- [x] 32 Lucro, margem, vendedor e comissão
- [x] 34 DRE e exportação
- [x] 35 Licença vencida em modo consulta
- [x] 36 Estoque avançado
- [x] 37 OS completa
- [x] 38 Agenda completa
- [x] 39 Busca geral

### G. Fechamento
- [x] Testes completos e telas novas conferidas
- [ ] Relatório do que ficou pronto, do que não foi possível e do que falta para lançar
