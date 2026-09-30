# Roda TUDO que existe de teste no projeto, numa tacada.
#
#   powershell -ExecutionPolicy Bypass -File tools\verificar_tudo.ps1
#
# E o que substitui um servidor de integracao continua aqui: antes de gerar o
# instalador ou publicar o site, um comando so diz se esta tudo de pe.
#
#   Hub (Python)      tests\               unittest
#   Painel            painel\tests\        node --test
#   Loja              landingpage\tests\   node --test
#   Edge Functions    supabase\functions\tests\
#   Banco (SQL)       supabase\tests\      PGlite (precisa de: cd supabase; npm install)
param([switch]$Rapido)   # -Rapido pula o que depende de Node

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

$falhas = @()
$pulados = @()

function Etapa($nome, $bloco, [switch]$Opcional, $QuandoFaltar = "") {
  Write-Host "`n=== $nome" -ForegroundColor Cyan
  & $bloco
  if ($LASTEXITCODE -ne 0) {
    if ($Opcional) {
      $script:pulados += "$nome - $QuandoFaltar"
      Write-Host "   pulado: $QuandoFaltar" -ForegroundColor DarkYellow
    } else {
      $script:falhas += $nome
      Write-Host "   FALHOU" -ForegroundColor Red
    }
  }
}

$python = Join-Path $raiz ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "Falta o ambiente Python: .venv\Scripts\python.exe" }

Etapa "Hub (Python)" { & $python -m unittest discover }

if (-not $Rapido) {
  $node = Get-Command node -ErrorAction SilentlyContinue
  if ($node) {
    # Um curinga em vez da lista na mao: teste novo passa a rodar sozinho.
    # (Ficaram de fora por meses o de pagamento da loja e o de mensagens do
    # painel - e "Tudo passou" nao sabia da existencia deles.)
    Etapa "Painel" { node --test (Get-ChildItem painel\tests\*.test.mjs | ForEach-Object FullName) }
    Etapa "Loja"   { node --test (Get-ChildItem landingpage\tests\*.test.mjs | ForEach-Object FullName) }
    Etapa "Edge Functions" {
      Push-Location supabase\functions
      node --test (Get-ChildItem tests\*.test.mjs | ForEach-Object FullName)
      Pop-Location
    }
    if (Test-Path "supabase\node_modules\@electric-sql\pglite") {
      Etapa "Banco (SQL)" {
        Push-Location supabase
        node tests\rodar.mjs
        Pop-Location
      }
    } else {
      $pulados += "Banco (SQL) - rode: cd supabase; npm install"
      Write-Host "`n=== Banco (SQL)`n   pulado: falta o PGlite (cd supabase; npm install)" -ForegroundColor DarkYellow
    }
  } else {
    $pulados += "Painel, Loja, Edge Functions e Banco - Node.js nao encontrado"
    Write-Host "`nNode.js nao encontrado: so os testes do Hub rodaram." -ForegroundColor DarkYellow
  }
}

Write-Host "`n--------------------------------------------------"
foreach ($p in $pulados) { Write-Host "pulado:  $p" -ForegroundColor DarkYellow }
if ($falhas.Count) {
  Write-Host "FALHOU:  $($falhas -join ', ')" -ForegroundColor Red
  exit 1
}
Write-Host "Tudo passou." -ForegroundColor Green
exit 0
