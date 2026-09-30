# Publica a loja, o painel, o instalador e o guia na HostGator.
#   powershell -ExecutionPolicy Bypass -File tools\publicar_site.ps1
#
# Monta build\site assim:
#   /                  landingpage/  (loja, baixar/, guia/, termos, privacidade)
#   /.htaccess         as regras do Apache (https, www -> raiz, tipos, cabecalhos)
#   /painel/           painel/ + o .htaccess dele
#   /baixar/DumTech-Hub-Setup.exe   o instalador de build\dist
#   /guia/Guia-DumTech-Hub.pdf      o guia em PDF (anexo da venda no Mercado Livre)
# e envia para https://dumtechsolution.com
#
# Antes: build\build.ps1 (gera o instalador). O PDF do guia e gerado aqui, com o Edge.
#
# COMO ELE ENVIA
#   Por FTP, com os dados vindos de variaveis de ambiente - nunca deste arquivo:
#     $env:HOSTGATOR_FTP_HOST   ex.: ftp.dumtechsolution.com
#     $env:HOSTGATOR_FTP_USER
#     $env:HOSTGATOR_FTP_PASS
#     $env:HOSTGATOR_FTP_DIR    opcional; vazio = a propria pasta da conta FTP
#                               (conta presa ao dominio). Rode -Conferir na duvida.
#   Para gravar de uma vez, no PowerShell:
#     setx HOSTGATOR_FTP_USER "usuario"
#
#   SEM essas variaveis ele NAO envia: monta tudo, gera build\site.zip para voce
#   subir pelo Gerenciador de Arquivos do cPanel (Upload > Extract) e SAI COM
#   ERRO de proposito. E o que impede tools\lancar_versao.ps1 de registrar uma
#   versao cujo instalador ainda nao esta no ar.
param(
  [switch]$SemPublicar,   # so monta build\site (nem zip, nem envio)
  [switch]$Zip,           # monta e gera o zip do cPanel, sem tentar FTP
  [switch]$SemSsl,        # FTP sem TLS (use so se a HostGator recusar FTPS)
  [switch]$Conferir       # so testa o FTP e mostra onde vai cair; nao monta nada
)
$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

# `setx` grava no registro, mas NAO alcanca janelas ja abertas: quem rodou o
# setx e continuou no mesmo PowerShell via "faltam as variaveis" e ficava sem
# publicar, achando que o script estava quebrado. Aqui a gente busca no
# registro quando o processo nao tem a variavel - assim funciona na janela
# velha tambem, sem ninguem precisar lembrar de reabrir o terminal.
function Ambiente($nome) {
  $valor = [Environment]::GetEnvironmentVariable($nome, "Process")
  if ($valor) { return $valor }
  foreach ($escopo in @("User", "Machine")) {
    $valor = [Environment]::GetEnvironmentVariable($nome, $escopo)
    if ($valor) { return $valor }
  }
  return ""
}

# --------------------------------------------- conferir o FTP (5 segundos) --
# Conta de FTP do cPanel criada com uma pasta fica PRESA a ela: ao entrar, voce
# ja esta dentro, e "/" e aquela pasta - nao a raiz da hospedagem. Por isso o
# padrao aqui e vazio, e nao "/public_html". `-Conferir` mostra o que existe do
# outro lado antes de mandar 54 MB para o lugar errado.
if ($Conferir) {
  $hostFtp = Ambiente "HOSTGATOR_FTP_HOST"
  $usuario = Ambiente "HOSTGATOR_FTP_USER"
  $senha   = Ambiente "HOSTGATOR_FTP_PASS"
  $destino = if (Ambiente "HOSTGATOR_FTP_DIR") { (Ambiente "HOSTGATOR_FTP_DIR").TrimEnd("/") } else { "" }
  if (-not ($hostFtp -and $usuario -and $senha)) {
    throw "Faltam HOSTGATOR_FTP_HOST / _USER / _PASS. Abriu um PowerShell NOVO depois do setx?"
  }
  Write-Host "Entrando em ftp://$hostFtp$destino/ como $usuario" -ForegroundColor Cyan
  $cred = New-Object System.Net.NetworkCredential($usuario, $senha)
  foreach ($comTls in @($true, $false)) {
    try {
      $p = [System.Net.FtpWebRequest]::Create("ftp://$hostFtp$destino/")
      $p.Credentials = $cred
      $p.Method = [System.Net.WebRequestMethods+Ftp]::ListDirectory
      $p.EnableSsl = $comTls; $p.UsePassive = $true; $p.KeepAlive = $false; $p.Timeout = 30000
      $resposta = $p.GetResponse()
      $leitor = New-Object System.IO.StreamReader($resposta.GetResponseStream())
      $itens = @(($leitor.ReadToEnd() -split "`r?`n") | Where-Object { $_ -and $_ -notin @(".", "..") })
      $leitor.Close(); $resposta.Close()

      Write-Host ""
      if ($comTls) { Write-Host "Conectou com FTPS (TLS)." -ForegroundColor Green }
      else { Write-Host "Conectou SEM TLS - publique com -SemSsl." -ForegroundColor Yellow }
      Write-Host "O que ja existe la dentro:"
      if ($itens.Count -eq 0) { Write-Host "  (pasta vazia)" } else { $itens | ForEach-Object { Write-Host "  $_" } }
      Write-Host ""
      if ($itens -contains "public_html") {
        Write-Host "ATENCAO: voce caiu na pasta DE CIMA (ha um public_html aqui)." -ForegroundColor Yellow
        Write-Host "Rode:  setx HOSTGATOR_FTP_DIR `"/public_html`"   (e abra um PowerShell novo)" -ForegroundColor Yellow
      } elseif ($itens.Count -eq 0 -or ($itens | Where-Object { $_ -in @("index.html", ".htaccess", "cgi-bin") })) {
        Write-Host "Esta parece a raiz do site: e aqui que o pacote deve cair." -ForegroundColor Green
      } else {
        Write-Host "Confira se esta e mesmo a pasta que o dominio serve." -ForegroundColor Yellow
      }
      exit 0
    } catch {
      if ($comTls) { Write-Host "FTPS recusado, tentando sem TLS..." -ForegroundColor DarkYellow; continue }
      throw "Nao consegui entrar: $($_.Exception.Message)"
    }
  }
}

$saida = Join-Path $raiz "build\site"
$instalador = Join-Path $raiz "build\dist\DumTech-Hub-Setup.exe"
if (-not (Test-Path $instalador)) { throw "Falta o instalador: rode build\build.ps1 antes." }

if (Test-Path $saida) { Remove-Item $saida -Recurse -Force }
New-Item -ItemType Directory -Force $saida | Out-Null

# o que e so de desenvolvimento nao vai para a internet.
# `_headers` e `netlify.toml` ficam de fora: na HostGator quem manda e o .htaccess.
$fora = @("tests", "servidor.mjs", "package.json", "README.md", "node_modules", "_headers", "netlify.toml")

Write-Host "1/5  Loja..." -ForegroundColor Cyan
Get-ChildItem landingpage -Force | Where-Object { $fora -notcontains $_.Name } |
  ForEach-Object { Copy-Item $_.FullName (Join-Path $saida $_.Name) -Recurse -Force }
if (-not (Test-Path (Join-Path $saida ".htaccess"))) {
  throw "O .htaccess da loja nao entrou no pacote - sem ele o site sobe sem https nem tipos certos."
}

# uma pagina por kit (/kit/comercio/...), com o preco e a imagem da previa do
# WhatsApp escritos no arquivo - o kit vem da tela Kits do painel, agora
Write-Host "     Paginas dos kits..." -ForegroundColor Cyan
node (Join-Path $raiz "tools\paginas_de_kit.mjs") $saida
if ($LASTEXITCODE -ne 0) { throw "Falha ao gerar as paginas dos kits." }

Write-Host "2/5  Painel..." -ForegroundColor Cyan
$painel = Join-Path $saida "painel"
New-Item -ItemType Directory -Force $painel | Out-Null
Get-ChildItem painel -Force | Where-Object { $fora -notcontains $_.Name } |
  ForEach-Object { Copy-Item $_.FullName (Join-Path $painel $_.Name) -Recurse -Force }
if (-not (Test-Path (Join-Path $painel ".htaccess"))) {
  throw "O .htaccess do painel nao entrou no pacote - o painel ficaria indexavel e sem https."
}

Write-Host "3/5  Instalador e guia em PDF..." -ForegroundColor Cyan
Copy-Item $instalador (Join-Path $saida "baixar\DumTech-Hub-Setup.exe") -Force
# Instaladores com a versao no nome (tools\lancar_versao.ps1 guarda em build\versoes).
# E para eles que o botao "Atualizar" do Hub aponta: um endereco por versao nunca
# troca de conteudo, entao o SHA cadastrado e o arquivo no ar nao se desencontram.
$versoes = Join-Path $raiz "build\versoes"
if (Test-Path $versoes) {
  Get-ChildItem $versoes -Filter "DumTech-Hub-Setup-*.exe" |
    ForEach-Object { Copy-Item $_.FullName (Join-Path $saida "baixar\$($_.Name)") -Force }
}
$edge = @("C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", "C:\Program Files\Microsoft\Edge\Application\msedge.exe") |
  Where-Object { Test-Path $_ } | Select-Object -First 1
$pdf = Join-Path $saida "guia\Guia-DumTech-Hub.pdf"
# guia\pdf.html e o documento feito para o PDF (A4, telas reais, sem contato fora do ML)
$pagina = "file:///" + ((Join-Path $saida "guia\pdf.html") -replace "\\", "/")
# Start-Process: o Edge escreve avisos inofensivos no stderr, que o
# ErrorActionPreference=Stop confundiria com erro
$lixo = Join-Path $env:TEMP "dumtech-edge-pdf.log"
Start-Process -FilePath $edge -Wait -NoNewWindow -RedirectStandardError $lixo -ArgumentList @(
  "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--virtual-time-budget=8000",
  "--print-to-pdf=`"$pdf`"", "`"$pagina`"")
$espera = 0
while (-not (Test-Path $pdf) -and $espera -lt 30) { Start-Sleep -Milliseconds 500; $espera++ }
if (-not (Test-Path $pdf)) { throw "O Edge nao gerou o PDF do guia." }
Copy-Item $pdf (Join-Path $raiz "build\dist\Guia-DumTech-Hub.pdf") -Force

$tamanho = "{0:N1} MB" -f ((Get-Item (Join-Path $saida "baixar\DumTech-Hub-Setup.exe")).Length / 1MB)
Write-Host "     instalador $tamanho, guia $("{0:N0} KB" -f ((Get-Item $pdf).Length / 1KB))"

if ($SemPublicar) { Write-Host "Montado em build\site (sem publicar)." -ForegroundColor Yellow; return }

# ----------------------------------------------------------- o pacote zip ---
function Gerar-Zip {
  $destinoZip = Join-Path $raiz "build\site.zip"
  if (Test-Path $destinoZip) { Remove-Item $destinoZip -Force }

  # Este zip e montado a mao por causa de DUAS armadilhas do Windows:
  #
  # 1. `Compress-Archive -Path pasta\*` ignora arquivos ocultos EM SILENCIO, e
  #    o .htaccess e oculto. O site subiria sem erro nenhum e o estrago so
  #    apareceria no cliente: sem https forcado, o instalador abrindo no
  #    navegador em vez de baixar, o app do celular recusando instalar.
  #
  # 2. `ZipFile::CreateFromDirectory` resolve o item 1, mas no .NET Framework
  #    (PowerShell 5.1) grava os caminhos com barra INVERTIDA. O padrao ZIP
  #    manda barra normal, e o extrator do cPanel e Linux: ele leria
  #    "painel\.htaccess" como NOME de arquivo, nao como pasta - e os 78
  #    arquivos cairiam soltos na raiz do public_html.
  #
  # Montando entrada por entrada com a barra certa, os dois somem.
  # os dois: ZipFile/ZipFileExtensions vem do FileSystem, ZipArchiveMode do outro
  Add-Type -AssemblyName System.IO.Compression
  Add-Type -AssemblyName System.IO.Compression.FileSystem
  $arquivos = Get-ChildItem $saida -Recurse -File -Force
  $pacote = [System.IO.Compression.ZipFile]::Open($destinoZip, [System.IO.Compression.ZipArchiveMode]::Create)
  try {
    foreach ($arquivo in $arquivos) {
      $nome = $arquivo.FullName.Substring($saida.Length).TrimStart("\").Replace("\", "/")
      [void][System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
        $pacote, $arquivo.FullName, $nome, [System.IO.Compression.CompressionLevel]::Optimal)
    }
  } finally { $pacote.Dispose() }

  # conferencia: o zip so serve se o .htaccess estiver dentro, e no lugar certo
  $conteudo = [System.IO.Compression.ZipFile]::OpenRead($destinoZip)
  try {
    $nomes = @($conteudo.Entries | ForEach-Object { $_.FullName })
  } finally { $conteudo.Dispose() }
  foreach ($exigido in @(".htaccess", "painel/.htaccess", "index.html")) {
    if ($nomes -notcontains $exigido) { throw "O zip saiu sem '$exigido' - nao suba este arquivo." }
  }
  if ($nomes | Where-Object { $_ -like "*\*" }) {
    throw "O zip saiu com barra invertida no caminho - o cPanel extrairia tudo solto na raiz."
  }
  return $destinoZip
}

Write-Host "4/5  Enviando para a HostGator..." -ForegroundColor Cyan

$hostFtp = Ambiente "HOSTGATOR_FTP_HOST"
$usuario = Ambiente "HOSTGATOR_FTP_USER"
$senha   = Ambiente "HOSTGATOR_FTP_PASS"
# vazio = a propria pasta da conta de FTP (o normal quando a conta foi criada
# presa ao dominio). Rode `-Conferir` para ver onde voce cai de verdade.
$destino = if (Ambiente "HOSTGATOR_FTP_DIR") { (Ambiente "HOSTGATOR_FTP_DIR").TrimEnd("/") } else { "" }

if ($Zip -or -not ($hostFtp -and $usuario -and $senha)) {
  $pacoteZip = Gerar-Zip
  Write-Host ""
  if ($Zip) {
    Write-Host "Pacote pronto (voce pediu -Zip):" -ForegroundColor Yellow
  } else {
    Write-Host "Faltam as variaveis de FTP - nada foi enviado." -ForegroundColor Yellow
    Write-Host "  HOSTGATOR_FTP_HOST / _USER / _PASS (e _DIR, opcional)" -ForegroundColor Yellow
  }
  Write-Host "  $pacoteZip"
  Write-Host ""
  $ondeCpanel = if ($destino) { $destino } else { "a pasta do dominio (public_html ou dumtechsolution.com)" }
  Write-Host "Suba pelo cPanel > Gerenciador de Arquivos > $ondeCpanel > Upload e depois Extract."
  Write-Host "Confira que o .htaccess foi junto (marque 'Mostrar arquivos ocultos')."
  exit 1   # de proposito: a versao NAO pode ser registrada sem o arquivo no ar
}

# ------------------------------------------------------------------ FTP -----
# FtpWebRequest e do .NET: nao precisa instalar nada. EnableSsl = FTPS explicito,
# que e o que a HostGator oferece; -SemSsl so para hospedagem que recusa.
$credencial = New-Object System.Net.NetworkCredential($usuario, $senha)
$criadas = New-Object System.Collections.Generic.HashSet[string]

# Descobre sozinho se da para usar FTPS. Hospedagem compartilhada costuma
# anunciar FTPS e recusar a negociacao do .NET; sem esta sondagem, o
# lancar_versao.ps1 morreria aqui e voce teria de lembrar do -SemSsl.
$usarTls = -not $SemSsl
if ($usarTls) {
  try {
    $sonda = [System.Net.FtpWebRequest]::Create("ftp://$hostFtp$destino/")
    $sonda.Credentials = $credencial
    $sonda.Method = [System.Net.WebRequestMethods+Ftp]::ListDirectory
    $sonda.EnableSsl = $true; $sonda.UsePassive = $true; $sonda.KeepAlive = $false
    $sonda.Timeout = 30000
    $sonda.GetResponse().Close()
    Write-Host "     conexao com FTPS (TLS)" -ForegroundColor DarkGray
  } catch {
    $usarTls = $false
    Write-Host "     o servidor recusou FTPS: enviando sem TLS" -ForegroundColor DarkYellow
  }
}

function Invoke-Ftp($uri, $metodo) {
  $pedido = [System.Net.FtpWebRequest]::Create($uri)
  $pedido.Credentials = $credencial
  $pedido.Method = $metodo
  $pedido.UseBinary = $true
  $pedido.UsePassive = $true
  $pedido.KeepAlive = $false
  $pedido.EnableSsl = $usarTls
  $pedido.Timeout = 120000
  return $pedido
}

function Criar-Pasta($caminhoRemoto) {
  if ($caminhoRemoto -eq "" -or $criadas.Contains($caminhoRemoto)) { return }
  # cria os pais primeiro
  $pai = $caminhoRemoto.Substring(0, [Math]::Max(0, $caminhoRemoto.LastIndexOf("/")))
  if ($pai -and $pai -ne $destino) { Criar-Pasta $pai }
  try {
    $pedido = Invoke-Ftp "ftp://$hostFtp$caminhoRemoto" ([System.Net.WebRequestMethods+Ftp]::MakeDirectory)
    $pedido.GetResponse().Close()
  } catch [System.Net.WebException] {
    # 550 = ja existe. Qualquer outra coisa e problema de verdade.
    $resposta = $_.Exception.Response
    $codigo = if ($resposta) { [int]$resposta.StatusCode } else { 0 }
    if ($codigo -ne 550 -and $_.Exception.Message -notmatch "550|exists") { throw }
  }
  [void]$criadas.Add($caminhoRemoto)
}

# Quanto pesa mandar um arquivo grande que ja esta la: cada instalador tem
# 27 MB, e uma publicacao carrega ate tres (o generico, o desta versao e o da
# anterior). Antes de subir os grandes, pergunta o tamanho do que esta no
# servidor; se bate, pula. Os pequenos (html/js/css, ~1 MB somados) vao sempre:
# perguntar por cada um custaria mais ida e volta do que simplesmente mandar.
function TamanhoRemoto($caminhoRemoto) {
  try {
    $pedido = Invoke-Ftp "ftp://$hostFtp$caminhoRemoto" ([System.Net.WebRequestMethods+Ftp]::GetFileSize)
    $pedido.Timeout = 30000
    $resposta = $pedido.GetResponse()
    $tam = $resposta.ContentLength
    $resposta.Close()
    return $tam
  } catch { return -1 }   # nao existe la, ou o servidor nao sabe dizer
}

$GRANDE = 1MB
$arquivos = Get-ChildItem $saida -Recurse -File -Force
$total = $arquivos.Count
$n = 0
$pulados = 0
$enviados = 0
foreach ($arquivo in $arquivos) {
  $n++
  $relativo = $arquivo.FullName.Substring($saida.Length).TrimStart("\").Replace("\", "/")
  $remoto = "$destino/$relativo"
  Criar-Pasta ($remoto.Substring(0, $remoto.LastIndexOf("/")))
  if ($arquivo.Length -ge $GRANDE -and (TamanhoRemoto $remoto) -eq $arquivo.Length) {
    $pulados++
    Write-Host ("     ja esta no ar, pulando: $relativo ({0:N1} MB)" -f ($arquivo.Length / 1MB)) -ForegroundColor DarkGray
    continue
  }
  $enviados++
  try {
    $pedido = Invoke-Ftp "ftp://$hostFtp$remoto" ([System.Net.WebRequestMethods+Ftp]::UploadFile)
    $pedido.ContentLength = $arquivo.Length
    $entrada = [System.IO.File]::OpenRead($arquivo.FullName)
    $fluxo = $pedido.GetRequestStream()
    $entrada.CopyTo($fluxo, 81920)
    $fluxo.Close(); $entrada.Close()
    $pedido.GetResponse().Close()
  } catch {
    throw "Falhou ao enviar $relativo : $($_.Exception.Message)`nNada foi registrado. Se for erro de TLS, tente -SemSsl; se for de login, confira HOSTGATOR_FTP_USER/PASS."
  }
  if ($n % 10 -eq 0 -or $n -eq $total) { Write-Host "     $n/$total arquivos" }
}
Write-Host "     $enviados enviados, $pulados ja estavam no ar" -ForegroundColor DarkGray

Write-Host "5/5  Conferindo o que ficou no ar..." -ForegroundColor Cyan
# uma batida so: se o .htaccess nao estiver valendo, isto aparece agora e nao
# depois, no cliente. (Ignora erro de rede: conferir e bonus, nao o publicar.)
try {
  $r = Invoke-WebRequest -Uri "https://dumtechsolution.com/" -UseBasicParsing -MaximumRedirection 3 -TimeoutSec 20
  if ($r.StatusCode -ne 200) { Write-Host "     a loja respondeu $($r.StatusCode)" -ForegroundColor Yellow }
} catch {
  Write-Host "     nao consegui abrir a loja agora: $($_.Exception.Message)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "No ar:" -ForegroundColor Green
Write-Host "  Loja:        https://dumtechsolution.com/"
Write-Host "  Baixar:      https://dumtechsolution.com/baixar/"
Write-Host "  Guia (PDF):  https://dumtechsolution.com/guia/Guia-DumTech-Hub.pdf"
Write-Host "  Painel:      https://dumtechsolution.com/painel/"
