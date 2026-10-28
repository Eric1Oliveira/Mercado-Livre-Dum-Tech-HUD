# Lanca uma versao nova do DumTech Hub - do teste ao botao "Atualizar" no cliente.
#
#   powershell -ExecutionPolicy Bypass -File tools\lancar_versao.ps1 -Notas "O que mudou"
#
# Antes: mude a versao em src\dumtech\__init__.py (ex.: 1.2.5).
#
# O QUE FAZ, NESTA ORDEM
#   1. build\build.ps1          roda TODOS os testes e gera o instalador
#   2. guarda o instalador como build\versoes\DumTech-Hub-Setup-<versao>.exe
#   3. tools\publicar_site.ps1  sobe o site com esse arquivo
#   4. baixa o arquivo DO AR e confere o SHA-256 com o que saiu do build
#   5. so entao registra a versao no banco (a mesma linha que o painel edita)
#
# POR QUE NESSA ORDEM
#   O Hub so instala se o arquivo baixado tiver exatamente o SHA registrado. Se o
#   registro vier antes do arquivo (ou o arquivo trocar depois do registro), o
#   cliente ve "o arquivo baixado nao e o oficial". Com um endereco por versao e o
#   registro sempre por ultimo, isso nao acontece.
#
# CONTROLE CONTINUA SEU
#   -SemAvisar      sobe o arquivo mas NAO registra: voce libera pelo painel quando
#                   quiser (Seguranca > Versao do DumTech Hub - os dados ficam impressos)
#   -Obrigatoria    marca como atualizacao importante
#   -Silenciosa     mudanca pequena: o Hub (1.5.1+) baixa sozinho e instala quando
#                   o cliente fecha o programa - sem botao, sem "O que mudou".
#                   Hub mais antigo mostra o botao como sempre.
#   No painel da para desligar "Atualizar pelo Hub" a qualquer momento.
param(
  [Parameter(Mandatory = $true)][string]$Notas,
  [switch]$SemAvisar,
  [switch]$Obrigatoria,
  [switch]$Silenciosa,
  # Pula a bateria de testes. Use SO quando voce acabou de rodar
  # tools\verificar_tudo.ps1 e nao mexeu em codigo depois. Economiza ~4 min
  # dos ~6 do lancamento. O que sai daqui vai para computador de cliente: na
  # duvida, nao use.
  [switch]$Rapido
)
$ErrorActionPreference = "Stop"
if ($Silenciosa -and $Obrigatoria) {
  throw "Escolha uma: -Obrigatoria avisa o cliente, -Silenciosa nao avisa nada."
}
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

$python = Join-Path $raiz ".venv\Scripts\python.exe"
$versao = (& $python -c "import sys; sys.path.insert(0, 'src'); import dumtech; print(dumtech.__version__)").Trim()
Write-Host "Lancando a versao $versao" -ForegroundColor Cyan

# 0. a versao ja publicada: repetir numero nao chega em cliente nenhum
#    (core/versao.py so avisa quando a publicada e MAIOR que a instalada)
$jaPublicada = ""
try {
  # Duas armadilhas do PowerShell 5.1 aqui:
  #  - com $ErrorActionPreference = "Stop", o que o npx escreve no stderr vira
  #    erro TERMINANTE (mesmo com 2>$null) e o catch engolia a resposta calado;
  #  - o npx devolve um ARRAY de linhas, e com array o -match vira filtro em vez
  #    de preencher $Matches. Por isso o Out-String.
  $antes = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  $saidaCli = (npx supabase db query --linked "select versao from public.hub_versoes where id = 1" 2>&1 | Out-String)
  $ErrorActionPreference = $antes
  if ($saidaCli -match '"versao":\s*"([^"]+)"') { $jaPublicada = $Matches[1] }
} catch { $ErrorActionPreference = "Stop" }
if ($jaPublicada -and $jaPublicada -eq $versao) {
  throw ("A versao $versao JA esta publicada. Mude __version__ em " +
         "src\dumtech\__init__.py antes de lancar - repetir o numero publica o " +
         "arquivo mas nao acende o botao 'Atualizar' em nenhum cliente.")
}

# 1. testes + instalador (o build recusa gerar com teste falhando)
if ($Rapido) {
  Write-Host "MODO RAPIDO: pulando a bateria de testes." -ForegroundColor Yellow
  & powershell -ExecutionPolicy Bypass -File (Join-Path $raiz "build\build.ps1") -PularTestes
} else {
  & powershell -ExecutionPolicy Bypass -File (Join-Path $raiz "build\build.ps1")
}
if ($LASTEXITCODE -ne 0) { throw "O build falhou: nada foi publicado." }

$instalador = Join-Path $raiz "build\dist\DumTech-Hub-Setup.exe"
$sha = (Get-FileHash $instalador -Algorithm SHA256).Hash.ToLower()
$tamanho = (Get-Item $instalador).Length

# 2. endereco proprio desta versao (guarda as 3 ultimas: quem estiver no meio de
#    um download da anterior nao fica sem arquivo)
$pasta = Join-Path $raiz "build\versoes"
New-Item -ItemType Directory -Force $pasta | Out-Null
$nome = "DumTech-Hub-Setup-$versao.exe"
Copy-Item $instalador (Join-Path $pasta $nome) -Force
Get-ChildItem $pasta -Filter "DumTech-Hub-Setup-*.exe" | Sort-Object LastWriteTime -Descending |
  Select-Object -Skip 3 | Remove-Item -Force

# 3. site
& powershell -ExecutionPolicy Bypass -File (Join-Path $raiz "tools\publicar_site.ps1")
if ($LASTEXITCODE -ne 0) {
  # Sem as variaveis de FTP, o publicar_site monta build\site.zip e para de
  # proposito. Isso NAO e defeito: e o caminho manual (upload pelo cPanel).
  # O instalador com a versao no nome ja esta dentro do zip - o que falta e
  # subir e registrar, e os quatro campos do painel saem impressos aqui.
  $zipManual = Join-Path $raiz "build\site.zip"
  if (Test-Path $zipManual) {
    Write-Host ""
    Write-Host "O site NAO foi enviado (sem FTP configurado). Caminho manual:" -ForegroundColor Yellow
    Write-Host "  1. Suba pelo cPanel em /public_html e extraia:"
    Write-Host "     $zipManual"
    Write-Host "  2. Confira que este endereco BAIXA o arquivo:"
    Write-Host "     https://dumtechsolution.com/baixar/$nome"
    Write-Host "  3. So entao, no painel (Seguranca > Versao do DumTech Hub):"
    Write-Host "       Versao:  $versao"
    Write-Host "       URL:     https://dumtechsolution.com/baixar/$nome"
    Write-Host "       SHA-256: $sha"
    Write-Host "       Tamanho: $tamanho"
    Write-Host ""
    Write-Host "A versao NAO foi registrada. Registre so depois do passo 2 -" -ForegroundColor Yellow
    Write-Host "registrar antes faz o cliente ver 'o arquivo baixado nao e o oficial'." -ForegroundColor Yellow
    exit 2
  }
  throw "O site nao foi publicado: a versao NAO foi registrada."
}

# 4. confere o que ficou no ar - e nao o que achamos que subiu
$url = "https://dumtechsolution.com/baixar/$nome"
$baixado = Join-Path $env:TEMP "dumtech-conferencia-$versao.exe"
Invoke-WebRequest -Uri $url -OutFile $baixado -UseBasicParsing
$noAr = (Get-FileHash $baixado -Algorithm SHA256).Hash.ToLower()
Remove-Item $baixado -Force
if ($noAr -ne $sha) {
  throw "O arquivo no ar ($noAr) nao e o do build ($sha). A versao NAO foi registrada."
}
Write-Host "Arquivo no ar conferido." -ForegroundColor Green

if ($SemAvisar) {
  Write-Host ""
  Write-Host "Arquivo publicado, versao NAO registrada. Para liberar, no painel:" -ForegroundColor Yellow
  Write-Host "  Versao:  $versao"
  Write-Host "  URL:     $url"
  Write-Host "  SHA-256: $sha"
  Write-Host "  Tamanho: $tamanho"
  return
}

# 5. registra - por ultimo, depois de o arquivo estar comprovadamente no ar
$notasSql = $Notas.Replace("'", "''")
$obrig = if ($Obrigatoria) { "true" } else { "false" }
$quieta = if ($Silenciosa) { "true" } else { "false" }
$sql = "update public.hub_versoes set versao = '$versao', url = '$url', sha256 = '$sha', " +
       "tamanho = $tamanho, notas = '$notasSql', obrigatoria = $obrig, automatica = true, " +
       "silenciosa = $quieta, atualizado_em = now() where id = 1"
npx supabase db query --linked $sql | Out-Null
if ($LASTEXITCODE -ne 0) {
  throw "Nao consegui registrar (o CLI do Supabase esta na conta certa?). O arquivo ja esta no ar: registre pelo painel."
}

Write-Host ""
Write-Host "Versao $versao lancada." -ForegroundColor Green
if ($Silenciosa) {
  Write-Host "  Hubs 1.5.1 ou mais novos baixam sozinhos e instalam quando forem fechados."
  Write-Host "  Hubs mais antigos mostram o botao em ate 2 minutos."
} else {
  Write-Host "  Hubs 1.2.3 ou mais novos mostram o botao em ate 2 minutos."
  Write-Host "  Hub 1.2.2: quando o programa for aberto de novo."
}
