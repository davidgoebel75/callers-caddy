"""Build-Script fuer Callers Caddy — ZIP-Distribution.

Orchestriert den gesamten Build-Prozess:
1. Saubere DB erstellen (clean_db.py)
2. PyInstaller ausfuehren (callers_caddy.spec)
3. Ressourcen von _internal/ ins Root verschieben
4. Leere Benutzerordner anlegen
5. ZIP-Archive erstellen (Vollpaket, Update, Source)

Beide EXEs (callers_caddy.exe + migration.exe) teilen sich
einen gemeinsamen _internal/ Ordner dank MERGE im Spec-File.

Version wird aus src/main.py gelesen (__version__).

Ordnerstruktur:
  <Repo-Klon>/      Code + Build-Skripte
  2_Test/           Testumgebung mit echten Daten (ohne Code)
  3_Build/          PyInstaller-Workspace (CC_BUILD_DIR, sonst neben dem Klon)
  4_Release/        Fertige ZIPs (CC_RELEASE_DIR, sonst neben dem Klon)

Voraussetzungen:
  - pip install pyinstaller
"""

import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

INSTALLER_DIR = Path(__file__).parent          # <Repo>/installer/
SOURCE_DIR = INSTALLER_DIR.parent              # <Repo>/
SRC_DIR = SOURCE_DIR / "src"                   # <Repo>/src/
REPO_ROOT = SOURCE_DIR.parent                  # Ordner ueber dem Repo (nur Fallback)
TEST_DIR = REPO_ROOT / "2_Test"                # 2_Test/ (historisch, ungenutzt)
# Build-Ausgabe: per Umgebungsvariable ueberschreibbar (siehe C:\Git\build-cc.bat).
# So stehen persoenliche Pfade NICHT im Repo und Thomas kann eigene setzen.
# Fallback = <Ordner ueber dem Repo>/3_Build bzw. /4_Release.
BUILD_DIR = Path(os.environ["CC_BUILD_DIR"]) if os.environ.get("CC_BUILD_DIR") else (REPO_ROOT / "3_Build")
RELEASES_DIR = Path(os.environ["CC_RELEASE_DIR"]) if os.environ.get("CC_RELEASE_DIR") else (REPO_ROOT / "4_Release")

# Dateien/Ordner die im Update-ZIP NICHT enthalten sein duerfen (User-Daten)
UPDATE_EXCLUDE = {
    "callers_caddy.db",
    "callers_caddy.ini",
    "music",
    "lyrics",
    "playlists",
    "notes",
}


def get_version() -> str:
    """Liest __version__ aus src/main.py."""
    main_py = SRC_DIR / "main.py"
    if not main_py.exists():
        print(f"FEHLER: {main_py} nicht gefunden!")
        sys.exit(1)
    content = main_py.read_text(encoding="utf-8")
    m = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)
    if not m:
        print("FEHLER: __version__ nicht in src/main.py gefunden!")
        sys.exit(1)
    return m.group(1)


def step(msg):
    """Druckt einen Schritt-Header."""
    print(f"\n{'='*60}")
    print(f"  {msg}")
    print(f"{'='*60}\n")


def run(cmd, cwd=None):
    """Fuehrt einen Befehl aus und bricht bei Fehler ab."""
    print(f"  > {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    result = subprocess.run(cmd, cwd=cwd, shell=isinstance(cmd, str))
    if result.returncode != 0:
        print(f"\nFEHLER: Befehl fehlgeschlagen (Exit Code {result.returncode})")
        sys.exit(1)


def move_to_root(internal_dir: Path, root_dir: Path):
    """Verschiebt Ressourcen von _internal/ ins App-Root.

    - skins/ (kompletter Ordner)
    - translations.json
    - callers_caddy_clean.db -> callers_caddy.db
    - callers_caddy_default.ini -> callers_caddy.ini
    """
    moves = [
        # (Quelle in _internal, Ziel im Root, ist Ordner?)
        ("skins", "skins", True),
        ("images", "images", True),
        ("translations.json", "translations.json", False),
        ("callers_caddy_clean.db", "callers_caddy.db", False),
        ("callers_caddy_default.ini", "callers_caddy.ini", False),
    ]
    for src_name, dst_name, is_dir in moves:
        src = internal_dir / src_name
        dst = root_dir / dst_name
        if src.exists():
            if dst.exists():
                if is_dir:
                    shutil.rmtree(dst)
                else:
                    dst.unlink()
            shutil.move(str(src), str(dst))
            print(f"  {src_name} -> {dst_name}")
        else:
            print(f"  WARNUNG: {src_name} nicht in _internal/ gefunden")


def _write_version_info(path: Path, version: str, description: str,
                        internal_name: str, original_filename: str):
    """Erzeugt eine version_info.txt fuer PyInstaller (Windows EXE-Details)."""
    parts = version.split(".")
    major = int(parts[0]) if len(parts) > 0 else 2
    minor = int(parts[1]) if len(parts) > 1 else 0
    patch = int(parts[2]) if len(parts) > 2 else 0

    path.write_text(f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({major}, {minor}, {patch}, 0),
    prodvers=({major}, {minor}, {patch}, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          u'040904B0',
          [
            StringStruct(u'CompanyName', u'Callers Caddy'),
            StringStruct(u'FileDescription', u'{description}'),
            StringStruct(u'FileVersion', u'{version}'),
            StringStruct(u'InternalName', u'{internal_name}'),
            StringStruct(u'OriginalFilename', u'{original_filename}'),
            StringStruct(u'ProductName', u'Callers Caddy'),
            StringStruct(u'ProductVersion', u'{version}'),
          ]
        )
      ]
    ),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
""", encoding="utf-8")


def create_version_info(version: str):
    """Erzeugt Version-Info-Dateien fuer alle drei EXEs."""
    _write_version_info(
        INSTALLER_DIR / "version_info.txt", version,
        description="Callers Caddy - Musik-Player fuer Square Dance Caller",
        internal_name="callers_caddy",
        original_filename="callers_caddy.exe",
    )
    _write_version_info(
        INSTALLER_DIR / "migration_version_info.txt", version,
        description="Callers Caddy - Umzugshelfer / Migration Tool",
        internal_name="migration",
        original_filename="migration.exe",
    )
    _write_version_info(
        INSTALLER_DIR / "class_designer_version_info.txt", version,
        description="Callers Caddy - Class Designer",
        internal_name="class_designer",
        original_filename="class_designer.exe",
    )
    print(f"  Version-Info erstellt: v{version} (callers_caddy.exe + migration.exe + class_designer.exe)")


def create_zip(app_dir: Path, version: str) -> Path:
    """Erstellt ein Vollpaket-ZIP (Neuinstallation) in 4_Release/<version>/."""
    version_dir = RELEASES_DIR / version
    version_dir.mkdir(parents=True, exist_ok=True)
    zip_name = f"Callers_Caddy_{version}.zip"
    zip_path = version_dir / zip_name

    if zip_path.exists():
        zip_path.unlink()
        print(f"  Altes ZIP entfernt: {zip_name}")

    print(f"  Erstelle {zip_name} ...")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(app_dir.rglob("*")):
            if file_path.is_file():
                arcname = f"Callers_Caddy/{file_path.relative_to(app_dir)}"
                zf.write(file_path, arcname)

    size_mb = zip_path.stat().st_size / 1024 / 1024
    print(f"  Vollpaket-ZIP erstellt: {zip_path}")
    print(f"  ZIP-Groesse: {size_mb:.0f} MB")
    return zip_path


def create_update_zip(app_dir: Path, version: str) -> Path:
    """Erstellt ein Update-ZIP (ohne User-Daten) in 4_Release/<version>/.

    Enthaelt EXEs, _internal/, skins/, translations.json.
    NICHT enthalten: DB, INI, leere User-Ordner (music, lyrics, etc.).
    """
    version_dir = RELEASES_DIR / version
    version_dir.mkdir(parents=True, exist_ok=True)
    zip_name = f"Callers_Caddy_Update_{version}.zip"
    zip_path = version_dir / zip_name

    if zip_path.exists():
        zip_path.unlink()
        print(f"  Altes ZIP entfernt: {zip_name}")

    print(f"  Erstelle {zip_name} ...")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(app_dir.rglob("*")):
            if file_path.is_file():
                rel = file_path.relative_to(app_dir)
                # Pruefen ob Datei/Ordner ausgeschlossen ist
                parts = rel.parts
                if parts[0] in UPDATE_EXCLUDE or rel.name in UPDATE_EXCLUDE:
                    continue
                arcname = f"Callers_Caddy/{rel}"
                zf.write(file_path, arcname)

    size_mb = zip_path.stat().st_size / 1024 / 1024
    print(f"  Update-ZIP erstellt: {zip_path}")
    print(f"  ZIP-Groesse: {size_mb:.0f} MB")
    return zip_path


BRIDGE_VERSION = "2.0"
# Die Bruecke ist fest die Update-ZIP von 2.0.0 und wird danach nie mehr ersetzt.
BRIDGE_SOURCE = "2.0.0"


def create_bridge_zip(update_zip: Path, version: str) -> Path | None:
    """Kopiert die Update-ZIP von 2.0.0 als Bruecke fuer Clients bis 0.162.

    Deren Update-Pruefung erkennt nur zweistellige Nummern ("0.162") und
    uebersieht Ordner wie "2.0.16". Den Ordner "2.0" mit
    Callers_Caddy_Update_2.0.zip finden sie dagegen und bieten ihn an.
    Ab 2.0.0 ueberspringt die Update-Pruefung den Ordner (update_check._is_bridge),
    nach dem Bruecken-Update meldet sie also die jeweils neueste 2.x.
    Die ZIP enthaelt keinen Versionsordner, eine umbenannte Kopie reicht.
    Nur der Build von genau 2.0.0 legt 4_Release/2.0/ an. Spaetere Builds
    lassen den Ordner unberuehrt, damit ein Probe- oder Nachbau ihn nie ersetzt.
    """
    if version != BRIDGE_SOURCE:
        return None
    bridge_dir = RELEASES_DIR / BRIDGE_VERSION
    bridge_dir.mkdir(parents=True, exist_ok=True)
    bridge_path = bridge_dir / f"Callers_Caddy_Update_{BRIDGE_VERSION}.zip"
    shutil.copy2(update_zip, bridge_path)
    (bridge_dir / "INHALT.txt").write_text(
        f"Bruecke fuer Installationen bis 0.162: Update-ZIP von {version}.\n",
        encoding="utf-8",
    )
    print(f"  Bruecken-ZIP erstellt: {bridge_path} (= Update {version})")
    return bridge_path


def create_source_zip(version: str) -> Path:
    """Erstellt ein ZIP-Archiv des Source-Codes in 4_Release/<version>/.

    Enthaelt nur den Repo-Klon (Code, Installer-Skripte).

    WICHTIG (DSGVO): Der Ordner docs/ wird NICHT mitgepackt.
    Lokal liegen dort perf_logs/ mit Rechnernamen, IPs und Vornamen aus
    Testumgebungen — solche personenbezogenen Daten duerfen nicht in
    veroeffentlichten Releases landen.
    """
    version_dir = RELEASES_DIR / version
    version_dir.mkdir(parents=True, exist_ok=True)
    zip_name = f"Callers_Caddy_Code_{version}.zip"
    zip_path = version_dir / zip_name

    if zip_path.exists():
        zip_path.unlink()
        print(f"  Altes ZIP entfernt: {zip_name}")

    # Nur der Repo-Klon wird eingepackt (der eigentliche Code)
    # "docs" steht hier explizit wegen DSGVO — siehe Docstring oben.
    # "docs" steht hier wegen DSGVO — ebenso "logs"/"crash"/"crashes":
    # Crash-Reports enthalten volle Dateipfade und damit den Windows-
    # Benutzernamen, Perf-Logs zusaetzlich Rechnernamen. Beides hat in einem
    # weitergegebenen Archiv nichts zu suchen.
    EXCLUDE_DIRS = {".git", "__pycache__", "build", "dist", "output", ".venv",
                    "_fallback", "tools", "docs",
                    "logs", "crash", "crashes", "perf_logs"}
    EXCLUDE_EXTS = {".pyc", ".pyo", ".exe", ".dll", ".so", ".pyd", ".bak",
                    ".mp3", ".wav", ".flac", ".ogg", ".aif", ".aiff",
                    ".au", ".caf", ".w64"}
    EXCLUDE_FILES = {"callers_caddy.db", "callers_caddy.ini",
                     "callers_caddy_clean.db"}

    print(f"  Erstelle {zip_name} ...")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(SOURCE_DIR.rglob("*")):
            if file_path.is_file():
                parts = file_path.relative_to(SOURCE_DIR).parts
                if any(p in EXCLUDE_DIRS for p in parts):
                    continue
                if file_path.suffix.lower() in EXCLUDE_EXTS:
                    continue
                # Backups jeder Art raus — auch datierte wie ".bak_pre_ms50_..."
                # oder ".bak_v2_...", deren Suffix eben NICHT exakt ".bak" ist und
                # die sonst durchrutschen (z.B. ein 11-MB-DB-Backup, das das
                # Code-ZIP verdreifacht hat).
                if ".bak" in file_path.name.lower():
                    continue
                if file_path.name in EXCLUDE_FILES:
                    continue
                arcname = f"Callers_Caddy_Code/{file_path.relative_to(SOURCE_DIR)}"
                zf.write(file_path, arcname)

    size_mb = zip_path.stat().st_size / 1024 / 1024
    print(f"  Source-ZIP erstellt: {zip_path}")
    print(f"  Source-ZIP-Groesse: {size_mb:.1f} MB")
    return zip_path


def main():
    os.chdir(INSTALLER_DIR)

    version = get_version()
    print(f"\n  Callers Caddy v{version}")

    # --- Schritt 1: Saubere DB ---
    step("Schritt 1/5: Saubere Datenbank erstellen")
    run([sys.executable, "clean_db.py"])

    # Version-Info fuer Windows EXE-Eigenschaften generieren
    create_version_info(version)

    # --- Schritt 2: PyInstaller ---
    step("Schritt 2/5: PyInstaller -- EXE-Dateien erzeugen")

    dist_dir = BUILD_DIR / "dist"
    build_work_dir = BUILD_DIR / "build"

    # Alten Build aufraeumen
    if dist_dir.exists():
        print("  Raeume alten Build auf...")
        shutil.rmtree(dist_dir)
    if build_work_dir.exists():
        shutil.rmtree(build_work_dir)
    BUILD_DIR.mkdir(exist_ok=True)

    run([
        sys.executable, "-m", "PyInstaller",
        "--clean",
        "--distpath", str(dist_dir),
        "--workpath", str(build_work_dir),
        str(INSTALLER_DIR / "callers_caddy.spec"),
    ])

    # Pruefen ob Output existiert (alle drei EXEs im selben Ordner)
    app_dir = dist_dir / "callers_caddy"
    app_exe = app_dir / "callers_caddy.exe"
    migration_exe = app_dir / "migration.exe"
    cd_exe = app_dir / "class_designer.exe"

    if not app_exe.exists():
        print(f"FEHLER: {app_exe} wurde nicht erzeugt!")
        sys.exit(1)
    print(f"  callers_caddy.exe: OK ({app_exe.stat().st_size / 1024 / 1024:.1f} MB)")

    if not migration_exe.exists():
        print("  WARNUNG: migration.exe wurde nicht erzeugt!")
    else:
        print(f"  migration.exe: OK ({migration_exe.stat().st_size / 1024 / 1024:.1f} MB)")

    if not cd_exe.exists():
        print("  WARNUNG: class_designer.exe wurde nicht erzeugt!")
    else:
        print(f"  class_designer.exe: OK ({cd_exe.stat().st_size / 1024 / 1024:.1f} MB)")

    # --- Schritt 3: Ressourcen verschieben ---
    step("Schritt 3/5: Ressourcen von _internal/ ins Root verschieben")
    internal_dir = app_dir / "_internal"
    move_to_root(internal_dir, app_dir)

    # App-Icon ins Root kopieren (wird zur Laufzeit fuer Taskleiste/Titelleiste geladen)
    logo_src = SOURCE_DIR / "cc-logo.png"
    if logo_src.exists():
        shutil.copy2(str(logo_src), str(app_dir / "cc-logo.png"))
        print("  cc-logo.png -> cc-logo.png")
    else:
        print(f"  WARNUNG: cc-logo.png nicht gefunden ({logo_src})")

    # Leere Ordner fuer Benutzerdaten anlegen
    for folder in ["music", "lyrics", "playlists", "notes", "loop_presets", "class_designer"]:
        d = app_dir / folder
        d.mkdir(exist_ok=True)
        print(f"  {folder}/ angelegt")

    # Music-Extended-Data: Song-Katalog (song_catalog.py, intern#126). Wird per
    # tools/update_song_catalog.py aus dem Scraper-Projekt aktualisiert.
    med_src = SOURCE_DIR / "music-extended-data"
    med_dst = app_dir / "music-extended-data"
    if med_src.exists():
        if med_dst.exists():
            shutil.rmtree(med_dst)
        shutil.copytree(str(med_src), str(med_dst))
        files = list(med_dst.iterdir())
        print(f"  music-extended-data/ kopiert ({len(files)} Datei(en))")
    else:
        print(f"  WARNUNG: music-extended-data/ nicht im Repo gefunden ({med_src})")

    # Beispieldateien (first-steps/) kopieren
    first_steps_src = SOURCE_DIR / "first-steps"
    first_steps_dst = app_dir / "first-steps"
    if first_steps_src.exists():
        if first_steps_dst.exists():
            shutil.rmtree(first_steps_dst)
        shutil.copytree(str(first_steps_src), str(first_steps_dst))
        files = list(first_steps_dst.iterdir())
        print(f"  first-steps/ kopiert ({len(files)} Dateien)")
    else:
        print("  WARNUNG: first-steps/ nicht im Repo gefunden")

    # HINWEIS (ab 0.148): Referenz-/Import-Sequenzen werden bewusst NICHT mehr
    # in die Setup-ZIPs gepackt. Solche Import-Dateien sollen zentral abgelegt
    # und separat bezogen werden, damit sie das Voll- und Update-ZIP nicht
    # unnoetig aufblaehen. Die frueher hier kopierte reference_sequences.json
    # (Ordner "Sequence-Import/") entfaellt daher im Build.

    # Groesse ermitteln
    total_size = sum(
        f.stat().st_size for f in app_dir.rglob("*") if f.is_file()
    )
    total_mb = total_size / 1024 / 1024

    # --- Schritt 4: ZIP-Archive erstellen ---
    step("Schritt 4/5: ZIP-Archive erstellen")
    zip_path = create_zip(app_dir, version)
    update_zip_path = create_update_zip(app_dir, version)
    source_zip_path = create_source_zip(version)
    bridge_zip_path = create_bridge_zip(update_zip_path, version)

    # --- Schritt 5: Zusammenfassung ---
    step("Build abgeschlossen!")
    print(f"  Version:       {version}")
    print(f"  Ergebnis:      {app_dir}")
    print(f"  Gesamtgroesse: {total_mb:.0f} MB")
    print(f"  Vollpaket-ZIP: {zip_path}")
    print(f"  Update-ZIP:    {update_zip_path}")
    print(f"  Source-ZIP:    {source_zip_path}")
    if bridge_zip_path:
        print(f"  Bruecke 0.x:   {bridge_zip_path}")
        print("              -> einmalig als Ordner '2.0' in den Download-Bereich (fuer Clients bis 0.162)")
    print(f"\n  Release-Ordner: {RELEASES_DIR / version}")
    print("  Vollpaket = Neuinstallation (alles enthalten)")
    print("  Update    = Ueber bestehende Installation drueberextrahieren")
    print("              (DB + INI + Musikordner bleiben erhalten)")


if __name__ == "__main__":
    main()
