# Gera o executavel do DumTech Hub para Windows - e o instalador.
#   powershell -ExecutionPolicy Bypass -File build\build.ps1
#
#   build\dist\DumTech Hub\DumTech Hub.exe   o programa (pasta)
#   build\dist\DumTech-Hub-Setup.exe         o instalador que o cliente baixa
#   -PularTestes pula a conferencia (so quando voce acabou de roda-la)
#
# Os testes rodam ANTES: instalador quebrado vai para o computador de cliente
# pagante e nao volta atras. Para pular (raro), use -PularTestes.
param([switch]$PularTestes)
$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

$python = Join-Path $raiz ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }

if (-not $PularTestes) {
  Write-Host "0/4  Conferindo os testes..." -ForegroundColor Cyan
  & powershell -ExecutionPolicy Bypass -File tools\verificar_tudo.ps1
  if ($LASTEXITCODE -ne 0) { throw "Tem teste falhando - o instalador nao foi gerado." }
}

Write-Host "1/4  Instalando dependencias..." -ForegroundColor Cyan
& $python -m pip install -r requirements.txt --quiet

Write-Host "2/4  Gerando icones..." -ForegroundColor Cyan
& $python tools\gerar_icones.py

Write-Host "3/4  Empacotando com PyInstaller..." -ForegroundColor Cyan
& $python -m PyInstaller build\dumtech_hub.spec --noconfirm --distpath build\dist --workpath build\work
if ($LASTEXITCODE -ne 0) { throw "PyInstaller falhou." }

Write-Host "4/4  Gerando o instalador (Inno Setup)..." -ForegroundColor Cyan
$versao = (& $python -c "import sys; sys.path.insert(0, 'src'); import dumtech; print(dumtech.__version__)").Trim()
$iscc = @(
  "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
  "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
  "C:\Program Files\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($iscc) {
  & $iscc "/DVersao=$versao" "/Qp" "build\instalador.iss"
  if ($LASTEXITCODE -ne 0) { throw "Inno Setup falhou." }
  Write-Host ""
  Write-Host "Pronto! Versao $versao" -ForegroundColor Green
  Write-Host "  Programa:   build\dist\DumTech Hub\DumTech Hub.exe"
  Write-Host "  Instalador: build\dist\DumTech-Hub-Setup.exe"
  # a impressao digital vai para o painel: e ela que libera o botao
  # "Baixar e instalar" dentro do Hub (o Hub confere byte a byte)
  $arquivo = Join-Path $raiz "build\dist\DumTech-Hub-Setup.exe"
  $hash = (Get-FileHash $arquivo -Algorithm SHA256).Hash.ToLower()
  $bytes = (Get-Item $arquivo).Length
  Set-Content -Path (Join-Path $raiz "build\dist\DumTech-Hub-Setup.sha256.txt") -Value "$hash  $bytes" -Encoding utf8
  Write-Host ""
  Write-Host "  Para o painel (Seguranca > Versao do DumTech Hub):" -ForegroundColor Cyan
  Write-Host "    SHA-256: $hash"
  Write-Host "    Tamanho: $bytes"
} else {
  Write-Host "Inno Setup nao encontrado (winget install JRSoftware.InnoSetup): so o programa foi gerado." -ForegroundColor Yellow
  Write-Host "  Programa: build\dist\DumTech Hub\DumTech Hub.exe"
}
