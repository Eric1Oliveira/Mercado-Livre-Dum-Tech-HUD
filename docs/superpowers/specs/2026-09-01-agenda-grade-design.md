# DumTech Agenda — a grade do dia

Data: 2026-09-01
Status: aprovado

## O problema

Hoje a agenda e uma lista ordenada por data. Isso responde "o que tem marcado?"
— mas nao responde a pergunta que se faz olhando para uma agenda:

> **Tenho horario na quinta de manha?**

Uma lista nao mostra buraco. So a grade mostra. E, sem grade, tambem nao existe
o que vem junto com ela: marcar dois clientes no mesmo horario passa batido,
almoco e folga nao ocupam espaco nenhum, e o atendimento que se repete toda
semana e redigitado toda semana.

## O carater deste modulo

Todos os outros modulos tem a forma do seu trabalho: catalogo, maquina de
transacao, calendario de dinheiro, jornada de um objeto, funil comercial. A
Agenda tem a forma mais literal de todas — **o tempo desenhado**.

Por isso a tela principal e a **grade**: as horas na lateral, os dias em
colunas, e cada compromisso um bloco com a altura da sua duracao. O espaco
vazio na tela e o horario vago na vida real. Nenhuma outra tela da plataforma
funciona assim, e nenhuma outra deveria.

## Telas

1. **Agenda** — a grade, em dia ou semana, com a linha da hora atual.
2. **Compromissos** — a lista, para procurar e mexer em lote.

Duas telas. A grade ja e o painel deste modulo: um cartao dizendo "3 hoje" ao
lado de uma tela que mostra os tres seria repetir a mesma informacao.

## Dados (migracao v2)

`compromissos` so ganha colunas (`ALTER TABLE`):

- `tipo` — atendimento, visita, entrega, outro e **bloqueio**;
- `grupo`, `repeticao` — para o que se repete;
- `cor` nao existe: a cor vem do tipo, pela paleta do tema. Cor gravada no
  banco quebraria no tema claro.

**Bloqueio nao e tabela nova.** Almoco, folga e feriado sao compromissos de
tipo `bloqueio`: ocupam espaco na grade, entram na deteccao de conflito e
somem dos relatorios de atendimento. Uma tabela separada teria que repetir
tudo isso.

## Regras

**Conflito avisa, nao trava.** Salvar em cima de outro compromisso mostra qual
e o choque e pede confirmacao. Nao bloqueia: duas pessoas atendendo ao mesmo
tempo e situacao normal, e o programa nao sabe quantas maos a loja tem.

Compromisso **cancelado nao gera conflito** — o horario voltou a ficar livre.

**Repeticao gera compromissos de verdade**, N ocorrencias a frente, ligadas por
um grupo — mesma decisao do parcelamento no Financeiro. Cada ocorrencia pode
ser remarcada ou cancelada sozinha, que e o que acontece na pratica.

**Atrasado** e o que ja passou da hora e ninguem marcou como concluido. E o
numero que faz alguem revisar a agenda no fim do dia.

## A grade

`ui/grade.py`, widget pintado a mao:

- faixa de horas configuravel (padrao 7h as 20h), coluna por dia;
- bloco com altura proporcional a duracao e cor do tipo;
- coluna de hoje destacada e **linha da hora atual**;
- blocos que se sobrepoem dividem a largura da coluna, senao um esconde o
  outro;
- clique no vazio abre um compromisso novo ja naquele dia e hora — em agenda,
  o gesto natural e apontar para o buraco.

## Fora de escopo

Sincronizar com Google Agenda, convite por e-mail, arrastar bloco para
remarcar, visao de mes, multiplos profissionais com colunas proprias, lembrete
por notificacao.

## Ordem de implementacao

1. Modelos, migracao e repositorio (tipos, conflito, repeticao, grade) + testes
2. Interface: grade, tela Agenda, lista e dialogo
3. Revisao visual e suite completa
