; Instalador do DumTech Hub (Inno Setup 6).
;   Gerado por build\build.ps1 depois do PyInstaller:
;   ISCC.exe /DVersao=1.1.0 build\instalador.iss  ->  build\dist\DumTech-Hub-Setup.exe
;
; - instala por usuario (sem pedir administrador): %LOCALAPPDATA%\Programs\DumTech Hub
; - os DADOS do cliente ficam em %APPDATA%\DumTech Hub e NUNCA sao apagados aqui:
;   desinstalar ou atualizar nao mexe em clientes, vendas, licenca nem backups
; - o AppId abaixo e fixo: e ele que faz a versao nova instalar por cima da antiga

#ifndef Versao
  #define Versao "0.0.0"
#endif

[Setup]
AppId={{7A3C1E52-4D9B-4F0E-9C61-2B8F5D3A6E17}
AppName=DumTech Hub
AppVersion={#Versao}
AppVerName=DumTech Hub {#Versao}
AppPublisher=DumTech
AppPublisherURL=https://dumtechsolution.com
AppSupportURL=https://dumtechsolution.com/guia/
AppUpdatesURL=https://dumtechsolution.com/baixar/
DefaultDirName={autopf}\DumTech Hub
DefaultGroupName=DumTech Hub
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=dist
OutputBaseFilename=DumTech-Hub-Setup
SetupIconFile=..\assets\dumtech_hub.ico
UninstallDisplayIcon={app}\DumTech Hub.exe
UninstallDisplayName=DumTech Hub
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
CloseApplications=yes
RestartApplications=no
; log em %TEMP%\Setup Log *.txt: e por ele que o suporte ve o que houve
SetupLogging=yes
VersionInfoVersion={#Versao}
VersionInfoCompany=DumTech
VersionInfoDescription=Instalador do DumTech Hub

[Languages]
Name: "pt"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "atalho"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; atualizacao: tira as bibliotecas da versao anterior antes de copiar as novas
; (arquivo velho esquecido em _internal pode ser carregado no lugar do novo)
Type: filesandordirs; Name: "{app}\_internal"

[Dirs]
; as bibliotecas do programa ficam ocultas: apagar uma delas "para limpar"
; impedia o Hub de abrir. Oculta nao muda nada para o programa.
Name: "{app}\_internal"; Attribs: hidden

[Files]
Source: "dist\DumTech Hub\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\DumTech Hub"; Filename: "{app}\DumTech Hub.exe"
Name: "{autodesktop}\DumTech Hub"; Filename: "{app}\DumTech Hub.exe"; Tasks: atalho

[Run]
Filename: "{app}\DumTech Hub.exe"; Description: "{cm:LaunchProgram,DumTech Hub}"; Flags: nowait postinstall skipifsilent
; Atualizacao feita pelo proprio Hub: ele chama
;   DumTech-Hub-Setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /reabrir=1
; e fecha. Esta linha e o que traz o programa de volta, ja atualizado.
Filename: "{app}\DumTech Hub.exe"; Flags: nowait runasoriginaluser; Check: VoltarDepoisDeAtualizar

[Code]
{ ATUALIZACAO PELO HUB (instalador rodando em silencio)
  O Hub chama o instalador e fecha - mas o processo ainda leva uns segundos
  para soltar as bibliotecas. Se a troca comecasse nessa hora, metade de
  _internal sumia e o Hub nao abria mais ("Failed to load Python DLL").
  Por isso, antes de tocar em qualquer arquivo, o instalador espera o Hub
  soltar tudo. E mostra uma janela pequena enquanto trabalha: sem ela a
  pessoa achava que o Hub tinha sumido e clicava no icone no meio da troca. }

const
  ESPERA_MAXIMA = 45000;   { ms ate desistir de esperar o Hub fechar sozinho }

var
  Aviso: TSetupForm;
  AvisoBarra: TNewProgressBar;

function VoltarDepoisDeAtualizar: Boolean;
begin
  Result := ExpandConstant('{param:reabrir|0}') = '1';
end;

{ arquivo que nao abre para escrita = algum DumTech Hub desta pasta ainda o usa }
function EmUso(const Arquivo: String): Boolean;
var
  Teste: TFileStream;
begin
  Result := False;
  if not FileExists(Arquivo) then
    Exit;
  try
    Teste := TFileStream.Create(Arquivo, fmOpenReadWrite or fmShareExclusive);
    Teste.Free;
  except
    Result := True;
  end;
end;

function HubAberto: Boolean;
begin
  Result := EmUso(ExpandConstant('{app}\DumTech Hub.exe'))
    or EmUso(ExpandConstant('{app}\_internal\python311.dll'));
end;

procedure MostrarAviso;
var
  Titulo, Texto: TNewStaticText;
begin
  Aviso := CreateCustomForm(ScaleX(420), ScaleY(108), False, False);
  Aviso.Caption := 'DumTech Hub';
  Aviso.BorderIcons := [];
  Aviso.FormStyle := fsStayOnTop;
  Aviso.Position := poScreenCenter;

  Titulo := TNewStaticText.Create(Aviso);
  Titulo.Parent := Aviso;
  Titulo.Left := ScaleX(20);
  Titulo.Top := ScaleY(18);
  Titulo.Font.Style := [fsBold];
  Titulo.Font.Size := 10;
  Titulo.Caption := 'Atualizando o DumTech Hub...';

  Texto := TNewStaticText.Create(Aviso);
  Texto.Parent := Aviso;
  Texto.Left := ScaleX(20);
  Texto.Top := ScaleY(44);
  if VoltarDepoisDeAtualizar then
    Texto.Caption := 'Não abra o programa agora: ele abre sozinho quando terminar.'
  else
    Texto.Caption := 'Aguarde esta janela fechar para abrir o programa.';

  AvisoBarra := TNewProgressBar.Create(Aviso);
  AvisoBarra.Parent := Aviso;
  AvisoBarra.Left := ScaleX(20);
  AvisoBarra.Top := ScaleY(74);
  AvisoBarra.Width := Aviso.ClientWidth - ScaleX(40);
  AvisoBarra.Height := ScaleY(16);
  AvisoBarra.Style := npbstMarquee;

  Aviso.Show;
  Aviso.Refresh;
end;

procedure EsperarSoltar(const Limite: Integer);
var
  Esperado: Integer;
begin
  Esperado := 0;
  while HubAberto and (Esperado < Limite) do begin
    Sleep(200);
    Esperado := Esperado + 200;
    if Aviso <> nil then
      Aviso.Refresh;
  end;
  Log(Format('Espera pelo Hub: %d ms', [Esperado]));
end;

{ so o Hub DESTA pasta - outro DumTech Hub instalado em outro lugar segue aberto }
procedure EncerrarHub;
var
  Programa: String;
  Codigo: Integer;
begin
  Programa := ExpandConstant('{app}\DumTech Hub.exe');
  StringChangeEx(Programa, '''', '''''', True);
  Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    '-NoProfile -NonInteractive -Command "Get-Process -Name ''DumTech Hub'' -ErrorAction SilentlyContinue'
    + ' | Where-Object { $_.Path -eq ''' + Programa + ''' } | Stop-Process -Force"',
    '', SW_HIDE, ewWaitUntilTerminated, Codigo);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  { instalacao com tela: quem fecha o Hub e a pessoa, pela pergunta do Inno }
  if not WizardSilent then
    Exit;
  MostrarAviso;
  EsperarSoltar(ESPERA_MAXIMA);
  if HubAberto then begin
    { o Hub ja recebeu a ordem de fechar e travou no caminho: encerra }
    Log('O Hub nao fechou sozinho: encerrando o processo');
    EncerrarHub;
    EsperarSoltar(10000);
  end;
  { desistir AQUI nao estraga nada: nenhum arquivo foi tocado ainda }
  if HubAberto then
    Result := 'O DumTech Hub ainda está aberto. Feche o programa e tente atualizar de novo.';
end;

procedure CurInstallProgressChanged(CurProgress, MaxProgress: Integer);
begin
  if (AvisoBarra = nil) or (MaxProgress <= 0) then
    Exit;
  AvisoBarra.Style := npbstNormal;
  AvisoBarra.Max := MaxProgress;
  AvisoBarra.Position := CurProgress;
end;

procedure DeinitializeSetup;
begin
  if Aviso <> nil then
    Aviso.Free;
end;
