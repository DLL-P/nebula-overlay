; Instalador do Nebula Overlay (Inno Setup 6). Gerado por empacotar/construir.py:
;   ISCC /DVersao=2026.10.17.1 empacotar\NebulaOverlay.iss
; Instala por usuário (sem pedir administrador) em %LOCALAPPDATA%\Programs\Nebula Overlay.
; As configurações e capturas ficam em Documentos\Nebula Overlay e não são apagadas ao desinstalar.
; Também é usado pela atualização automática: o app roda este instalador com /SILENT e ele reabre o app.

#ifndef Versao
  #define Versao "0.0.0"
#endif

[Setup]
AppId={{6F0C2A5E-6C1B-4B8E-9C2E-4E5A0B7D9A31}
AppName=Nebula Overlay
AppVersion={#Versao}
AppVerName=Nebula Overlay {#Versao}
AppPublisher=DLL-P
AppPublisherURL=https://github.com/DLL-P/nebula-overlay
AppSupportURL=https://github.com/DLL-P/nebula-overlay/issues
DefaultDirName={localappdata}\Programs\Nebula Overlay
DefaultGroupName=Nebula Overlay
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=NebulaOverlay-Setup
SetupIconFile=..\dados\icone.ico
UninstallDisplayIcon={app}\NebulaOverlay.exe
UninstallDisplayName=Nebula Overlay
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
ShowLanguageDialog=auto

[Languages]
Name: "pt"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[CustomMessages]
pt.SemNpcap=O Nebula Overlay precisa do Npcap para ler a conexão do jogo, e ele ainda não está instalado.%n%nQuer abrir a página de download do Npcap agora? Na instalação, se você usa ExitLag (ou outro acelerador), marque "Support loopback traffic".
en.SemNpcap=Nebula Overlay needs Npcap to read the game connection, and it is not installed yet.%n%nOpen the Npcap download page now? During setup, if you use ExitLag (or another booster), check "Support loopback traffic".
es.SemNpcap=Nebula Overlay necesita Npcap para leer la conexión del juego, y aún no está instalado.%n%n¿Abrir ahora la página de descarga de Npcap? Durante la instalación, si usas ExitLag (u otro acelerador), marca "Support loopback traffic".

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; a cada atualização, troca a pasta interna inteira (nada de arquivo velho sobrando)
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\NebulaOverlay\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Nebula Overlay"; Filename: "{app}\NebulaOverlay.exe"
Name: "{autodesktop}\Nebula Overlay"; Filename: "{app}\NebulaOverlay.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\NebulaOverlay.exe"; Description: "{cm:LaunchProgram,Nebula Overlay}"; Flags: nowait postinstall skipifsilent
; atualização automática (modo silencioso): reabre o app sozinho
Filename: "{app}\NebulaOverlay.exe"; Flags: nowait; Check: WizardSilent

[Code]
function NpcapInstalado: Boolean;
begin
  Result := FileExists(ExpandConstant('{sysnative}\Npcap\wpcap.dll')) or RegKeyExists(HKLM64, 'SOFTWARE\Npcap')
            or RegKeyExists(HKLM32, 'SOFTWARE\Npcap');
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Codigo: Integer;
begin
  if (CurStep = ssPostInstall) and (not WizardSilent) and (not NpcapInstalado) then
    if MsgBox(CustomMessage('SemNpcap'), mbInformation, MB_YESNO) = IDYES then
      ShellExec('open', 'https://npcap.com/#download', '', '', SW_SHOWNORMAL, ewNoWait, Codigo);
end;
