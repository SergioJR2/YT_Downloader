; Instalador de YT Downloader (Inno Setup 6.3 o superior)
; Se genera con:  ISCC.exe instalador.iss   (lo hace compilar.bat automaticamente)

#define AppName    "YT Downloader"
#ifndef AppVersion
  ; compilar.bat lo reemplaza con APP_VERSION de models\config.py (ISCC /DAppVersion=...)
  ; Valor de respaldo: mantenerlo igual a APP_VERSION de models\config.py
  #define AppVersion "1.4.0"
#endif
#define AppExe     "YT_Downloader.exe"

[Setup]
AppId={{1451D9FC-3017-4A67-8DDC-EC6544EDEEAD}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
; Instalacion por usuario: no pide permisos de administrador
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=instalador
OutputBaseFilename=YT_Downloader_Setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Permite que la app actualice a la siguiente versión en silencio (cierra la app abierta)
CloseApplications=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el escritorio"; GroupDescription: "Accesos directos:"

[Files]
Source: "dist\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Abrir {#AppName}"; Flags: nowait postinstall
