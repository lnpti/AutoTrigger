; ============================================================
;  AutoTrigger V10 — Inno Setup Script  (by RobsonDV)
;  Para compilar: build_installer.bat
;  Ou manualmente: ISCC.exe installer.iss
; ============================================================

#define AppName    "AutoTrigger V10"
#define AppVersion "2.3.7"
#define AppPublisher "RobsonDV"
#define AppURL     "https://github.com/lnpti/AutoTrigger"
#define AppExe     "AutoTriggerV10.exe"

[Setup]
; GUID da instalacao POR USUARIO (v2.2.4+). Diferente do AppId antigo (admin),
; para nao colidir com a versao anterior instalada em Program Files.
AppId={{C5F9D4A3-BE6F-4C8A-9D2B-4F3E5A7C9D11}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} v{#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases

; Instalacao POR USUARIO (sem admin) -> pasta gravavel -> auto-update sem UAC
DefaultDirName={localappdata}\Programs\AutoTrigger V10
DefaultGroupName=AutoTrigger V10
AllowNoIcons=yes
UsePreviousAppDir=yes

; Saída
OutputDir=dist
OutputBaseFilename=AutoTriggerV10_Setup_v{#AppVersion}

; Visual
SetupIconFile=assets\icon.ico
WizardStyle=modern
WizardSizePercent=120
WizardImageFile=assets\wizard_banner.bmp
WizardSmallImageFile=assets\wizard_icon.bmp

; Compressão máxima
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes

; SEM admin: instala por usuario, em area gravavel (essencial p/ auto-update)
PrivilegesRequired=lowest

; Ícone de desinstalação
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}

; Comentario: Automacao de disparos por gatilho em arquivo TXT

; Versão mínima do Windows
MinVersion=10.0

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar ícone na Área de Trabalho"; GroupDescription: "Atalhos:"; Flags: checkedonce
Name: "startuprun"; Description: "Iniciar automaticamente com o Windows"; GroupDescription: "Inicialização:"; Flags: unchecked

[Files]
; Executável principal
Source: "dist\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion

; Config padrão — NUNCA sobrescreve config existente do usuário
Source: "config.json"; DestDir: "{app}"; DestName: "config.json"; \
  Flags: onlyifdoesntexist uninsneveruninstall

; Ícone da aplicação (para atalhos)
Source: "assets\icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Menu Iniciar
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; \
  IconFilename: "{app}\icon.ico"; Comment: "Automação da Jornada Esportiva"
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"

; Área de Trabalho (opcional)
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; \
  IconFilename: "{app}\icon.ico"; Tasks: desktopicon

[Registry]
; Inicialização com o Windows (opcional)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
  ValueType: string; ValueName: "AutoTriggerV10"; \
  ValueData: """{app}\{#AppExe}"""; \
  Flags: uninsdeletevalue; Tasks: startuprun

[Run]
; Inicia o app ao final da instalação
Filename: "{app}\{#AppExe}"; \
  Description: "Iniciar {#AppName} agora"; \
  Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Remove arquivos gerados pelo app durante uso
Type: files; Name: "{app}\_update.bat"
Type: files; Name: "{app}\*.new"

; ============================================================
;  CÓDIGO PASCAL — Verificação e instalação do VLC
; ============================================================
[Code]

const
  VLC_REG_64  = 'SOFTWARE\VideoLAN\VLC';
  VLC_REG_32  = 'SOFTWARE\WOW6432Node\VideoLAN\VLC';
  VLC_URL_64  = 'https://download.videolan.org/pub/videolan/vlc/3.0.21/win64/vlc-3.0.21-win64.exe';
  VLC_URL_32  = 'https://download.videolan.org/pub/videolan/vlc/3.0.21/win32/vlc-3.0.21-win32.exe';

// Verifica se VLC está instalado (32 ou 64 bit)
function IsVLCInstalled: Boolean;
var
  sVal: String;
begin
  Result := RegQueryStringValue(HKLM, VLC_REG_64, '', sVal) or
            RegQueryStringValue(HKLM, VLC_REG_32, '', sVal) or
            RegQueryStringValue(HKCU, VLC_REG_64, '', sVal);
end;

// Baixa e instala o VLC silenciosamente
procedure DownloadVLC;
var
  sURL, sTmpFile, sPS: String;
  iResult: Integer;
begin
  if Is64BitInstallMode then
    sURL := VLC_URL_64
  else
    sURL := VLC_URL_32;

  sTmpFile := ExpandConstant('{tmp}\vlc_setup.exe');

  // Mostra progresso na tela do wizard
  WizardForm.StatusLabel.Caption :=
    'Baixando VLC Media Player... (pode levar alguns minutos dependendo da internet)';
  WizardForm.ProgressGauge.Style := npbstMarquee;

  // Download via PowerShell (nativo no Windows 10/11)
  sPS := '-ExecutionPolicy Bypass -NoProfile -Command "' +
         '[Net.ServicePointManager]::SecurityProtocol = ' +
           '[Net.SecurityProtocolType]::Tls12; ' +
         'Invoke-WebRequest -Uri ''' + sURL + ''' ' +
           '-OutFile ''' + sTmpFile + ''' -UseBasicParsing"';

  Exec('powershell.exe', sPS, '', SW_HIDE, ewWaitUntilTerminated, iResult);

  WizardForm.ProgressGauge.Style := npbstNormal;

  if (iResult = 0) and FileExists(sTmpFile) then
  begin
    WizardForm.StatusLabel.Caption := 'Instalando VLC Media Player...';
    Exec(sTmpFile, '/S', '', SW_HIDE, ewWaitUntilTerminated, iResult);

    if iResult = 0 then
      MsgBox('VLC Media Player instalado com sucesso!', mbInformation, MB_OK)
    else
      MsgBox('O VLC foi baixado mas houve um erro na instalação.' + #13#10 +
             'Instale manualmente em: https://www.videolan.org',
             mbError, MB_OK);
  end else
  begin
    MsgBox(
      'Não foi possível baixar o VLC automaticamente.' + #13#10 + #13#10 +
      'Para instalar manualmente:' + #13#10 +
      '1. Acesse: https://www.videolan.org/vlc/download-windows.html' + #13#10 +
      '2. Baixe a versão para Windows (64-bit)' + #13#10 +
      '3. Execute o instalador' + #13#10 + #13#10 +
      'O AutoTrigger V10 não funcionará sem o VLC instalado.',
      mbError, MB_OK
    );
  end;
end;

// Executado após a cópia dos arquivos
// A partir da v2.1 o libVLC vem EMBUTIDO no .exe — não é mais necessário
// instalar o VLC no sistema. As rotinas IsVLCInstalled/DownloadVLC acima ficam
// como fallback caso, no futuro, se opte por não embutir o VLC.
procedure CurStepChanged(CurStep: TSetupStep);
begin
  // Nada a fazer: o VLC já está embutido no executável.
end;

// Página de boas-vindas personalizada
function InitializeSetup: Boolean;
begin
  Result := True;
end;
