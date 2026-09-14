; Callers Caddy — Inno Setup Script
; Installer mit integriertem Migrations-Wizard

#define MyAppName "Callers Caddy"
#define MyAppVersion "2.0.0"
#define MyAppPublisher "David"
#define MyAppExeName "callers_caddy.exe"
#define MyAppURL "https://callerscaddy.de"

[Setup]
AppId={{A3B7C9D1-E5F6-4A8B-9C0D-2E4F6A8B0C2D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName=C:\CallersCaddy
DefaultGroupName={#MyAppName}
; Kein Program Files — portabel
DisableProgramGroupPage=no
OutputDir=output
OutputBaseFilename=CallersCaddy_Setup_{#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
; Keine Admin-Rechte noetig (portabel)
PrivilegesRequired=lowest
; Erlaubt Aenderung des Installpfads
DisableDirPage=no
; Uninstaller
UninstallDisplayIcon={app}\{#MyAppExeName}
; Mindestens Windows 10
MinVersion=10.0

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
; Deutsch
german.MigrationPageTitle=Daten-Umzug
german.MigrationPageDescription=Moechten Sie Daten aus einem bestehenden System importieren?
german.MigrationYes=Ja, ich moechte Daten aus meinem alten System uebernehmen
german.MigrationNo=Nein, ich starte mit einer frischen Installation
german.MigrationInfo=Der Umzugshelfer wird nach der Installation gestartet und leitet Sie durch den Import Ihrer Songs, Playlists und Einstellungen.
german.MigrationRunning=Der Umzugshelfer wird jetzt gestartet...
german.DesktopIcon=Desktop-Verknuepfung erstellen

; English
english.MigrationPageTitle=Data Migration
english.MigrationPageDescription=Would you like to import data from an existing system?
english.MigrationYes=Yes, I want to import data from my old system
english.MigrationNo=No, I want to start with a fresh installation
english.MigrationInfo=The migration tool will start after installation and guide you through importing your songs, playlists and settings.
english.MigrationRunning=Starting the migration tool...
english.DesktopIcon=Create desktop shortcut

[Tasks]
Name: "desktopicon"; Description: "{cm:DesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; Hauptanwendung (PyInstaller Output)
Source: "dist\callers_caddy\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; Migrations-Tool
Source: "dist\migration\*"; DestDir: "{app}\migration"; Flags: ignoreversion recursesubdirs createallsubdirs

; Skins (neben der EXE, nicht in _internal)
Source: "dist\callers_caddy\_internal\skins\*"; DestDir: "{app}\skins"; Flags: ignoreversion recursesubdirs createallsubdirs

; Uebersetzungen (neben der EXE)
Source: "dist\callers_caddy\_internal\translations.json"; DestDir: "{app}"; Flags: ignoreversion

; Saubere DB (nur wenn noch keine vorhanden — Update-Sicherheit)
Source: "callers_caddy_clean.db"; DestDir: "{app}"; DestName: "callers_caddy.db"; Flags: onlyifdoesntexist

; Default-INI (nur wenn noch keine vorhanden)
Source: "callers_caddy_default.ini"; DestDir: "{app}"; DestName: "callers_caddy.ini"; Flags: onlyifdoesntexist

[Dirs]
; Leere Ordner fuer Benutzerdaten
Name: "{app}\music"
Name: "{app}\lyrics"
Name: "{app}\playlists"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; App nach Installation starten (optional)
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent unchecked

[Code]
var
  MigrationPage: TWizardPage;
  MigrationYesRadio: TNewRadioButton;
  MigrationNoRadio: TNewRadioButton;
  MigrationInfoLabel: TNewStaticText;

procedure InitializeWizard();
begin
  { Custom Page: Migration }
  MigrationPage := CreateCustomPage(
    wpSelectTasks,
    ExpandConstant('{cm:MigrationPageTitle}'),
    ExpandConstant('{cm:MigrationPageDescription}')
  );

  { Radio: Ja, migrieren }
  MigrationYesRadio := TNewRadioButton.Create(MigrationPage);
  MigrationYesRadio.Parent := MigrationPage.Surface;
  MigrationYesRadio.Caption := ExpandConstant('{cm:MigrationYes}');
  MigrationYesRadio.Top := 20;
  MigrationYesRadio.Left := 0;
  MigrationYesRadio.Width := MigrationPage.SurfaceWidth;
  MigrationYesRadio.Font.Style := [fsBold];

  { Radio: Nein, frisch starten }
  MigrationNoRadio := TNewRadioButton.Create(MigrationPage);
  MigrationNoRadio.Parent := MigrationPage.Surface;
  MigrationNoRadio.Caption := ExpandConstant('{cm:MigrationNo}');
  MigrationNoRadio.Top := 50;
  MigrationNoRadio.Left := 0;
  MigrationNoRadio.Width := MigrationPage.SurfaceWidth;
  MigrationNoRadio.Checked := True;  { Standard: frische Installation }

  { Info-Text }
  MigrationInfoLabel := TNewStaticText.Create(MigrationPage);
  MigrationInfoLabel.Parent := MigrationPage.Surface;
  MigrationInfoLabel.Caption := ExpandConstant('{cm:MigrationInfo}');
  MigrationInfoLabel.Top := 90;
  MigrationInfoLabel.Left := 0;
  MigrationInfoLabel.Width := MigrationPage.SurfaceWidth;
  MigrationInfoLabel.WordWrap := True;
  MigrationInfoLabel.AutoSize := True;
end;

function GetLangCode(): String;
begin
  if ActiveLanguage() = 'english' then
    Result := 'en'
  else
    Result := 'de';
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  MigrationExe: String;
begin
  if CurStep = ssPostInstall then
  begin
    if MigrationYesRadio.Checked then
    begin
      MigrationExe := ExpandConstant('{app}\migration\migration.exe');
      if FileExists(MigrationExe) then
      begin
        { Starte Migrations-Tool mit Installpfad und Sprache als Parameter }
        Exec(MigrationExe,
             '"' + ExpandConstant('{app}') + '" --lang ' + GetLangCode(),
             '', SW_SHOW, ewWaitUntilTerminated, ResultCode);
      end;
    end;
  end;
end;
