# Vídeos de demonstração do DumTech Hub

Os vídeos são **o Hub de verdade rodando**: um roteiro abre o programa, move o
cursor, digita, clica, cadastra um item — e cada quadro vira MP4 com legenda.
Quando a interface mudar, é só gravar de novo.

```powershell
pip install imageio-ffmpeg            # uma vez (ou tenha o ffmpeg no PATH)
.venv\Scripts\python tools\videos\gravar.py              # os 8 vídeos
.venv\Scripts\python tools\videos\gravar.py vendas hub   # só estes
```

Saída: `build\videos\<nome>.mp4` — Full HD (1920×1080), H.264, sem áudio.
O Hub é gravado numa janela de notebook (1280×720) para tudo aparecer grande.

| Arquivo | O que mostra |
|---|---|
| `hub.mp4` | Visão geral: Início, as abas dos 7 módulos, Ctrl+K, tema escuro, celular |
| `vendas.mp4` | Balcão: bipar, sugestão do estoque, cliente, receber com troco, painel e caixa |
| `estoque.mp4` | Cadastrar produto, busca, entradas, painel |
| `financeiro.mp4` | Fluxo, painel, novo lançamento, receber uma conta, contas |
| `ordens.mp4` | Bancada, nova ordem com peça e serviço, avançar etapa, painel |
| `orcamentos.mp4` | Funil, nova proposta com itens, enviar, aprovar |
| `clientes.mp4` | Painel, novo cliente com CEP que preenche o endereço, ficha |
| `agenda.mp4` | Semana hora a hora, novo compromisso, lista |

## Peças

- `semente.py` — a empresa de demonstração (assistência técnica com loja).
  Nada é gravado no seu Hub: cada vídeo usa uma pasta de dados temporária.
- `roteiros.py` — o passo a passo de cada vídeo (legenda + gestos).
- `gravador.py` — o motor: fotografa a janela, cola diálogos e menus por
  cima, desenha cursor/clique/legenda e manda para o ffmpeg.
- `gravar.py` — prepara um Hub limpo por vídeo e roda o roteiro.

## Quando um roteiro quebra

A mensagem de erro lista o que está visível na tela (botões, rótulos e
campos) — normalmente um botão mudou de nome. Para ver em que linha parou:
`$env:VIDEO_PASSOS=1` antes de gravar.

Armadilhas já resolvidas: o `QTest` derruba o processo com letra acentuada
(por isso `_tecla_de_texto`); Esc dentro de formulário fecha o formulário;
diálogo mais alto que 720 px é encolhido no vídeo, e o cursor acompanha.

O vídeo não fala com o servidor da DumTech (licença local, celular de mentira).
