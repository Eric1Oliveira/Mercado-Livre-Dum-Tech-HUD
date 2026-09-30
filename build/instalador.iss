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
function VoltarDepoisDeAtualizar: Boolean;
begin
  Result := ExpandConstant('{param:reabrir|0}') = '1';
end;
