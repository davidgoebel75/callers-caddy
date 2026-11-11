# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller Spec-File fuer Callers Caddy.

Erzeugt drei Executables in einem gemeinsamen Ordner:
  - callers_caddy.exe   (Hauptanwendung)
  - migration.exe       (Umzugshelfer)
  - class_designer.exe  (Class-Planungs-Tool)

Alle teilen sich _internal/ (Python-Runtime, Qt, etc.)
"""

import os
from pathlib import Path

block_cipher = None

PROJECT_ROOT = Path(SPECPATH).parent
SRC_DIR = PROJECT_ROOT / "src"
MIGRATION_DIR = SRC_DIR / "migration"
INSTALLER_DIR = PROJECT_ROOT / "installer"

# Icon-Pfad (muss vom User bereitgestellt werden)
ICON_FILE = str(INSTALLER_DIR / "icon.ico")
icon_param = ICON_FILE if os.path.exists(ICON_FILE) else None

# Version-Info (wird von build.py generiert)
VERSION_FILE = str(INSTALLER_DIR / "version_info.txt")
version_param = VERSION_FILE if os.path.exists(VERSION_FILE) else None

MIGRATION_VERSION_FILE = str(INSTALLER_DIR / "migration_version_info.txt")
migration_version_param = MIGRATION_VERSION_FILE if os.path.exists(MIGRATION_VERSION_FILE) else None

CD_VERSION_FILE = str(INSTALLER_DIR / "class_designer_version_info.txt")
cd_version_param = CD_VERSION_FILE if os.path.exists(CD_VERSION_FILE) else None

# Gemeinsame Exclude-Liste — Module die NICHT benoetigt werden
# Diese werden von PyInstaller faelschlich als Abhaengigkeit erkannt
# (z.B. ueber access_parser oder transitive numpy-Imports)
EXCLUDES = [
    # ML/AI — definitiv nicht benoetigt
    "torch",
    "torchvision",
    "transformers",
    "huggingface_hub",
    "hf_xet",
    "tokenizers",
    "safetensors",
    "sklearn",
    "scikit-learn",
    # Computer Vision
    "cv2",
    "opencv-python",
    # Bild/Plot
    "matplotlib",
    "PIL",
    "pillow",
    "Pillow",
    # GUI-Toolkits die wir nicht brauchen
    "tkinter",
    # Web/API
    "openai",
    "pydantic",
    "pydantic_core",
    # Sonstiges
    "jinja2",
    "markupsafe",
    "certifi",
    "rich",
    "click",
    "typer",
    "filelock",
    "tqdm",
    "packaging",
    "setuptools",
    "yaml",
    "pyyaml",
    "regex",
]

# ---------- Hauptanwendung ----------

app_analysis = Analysis(
    [str(SRC_DIR / "main.py")],
    pathex=[str(SRC_DIR)],
    binaries=[],
    datas=[
        # Skins (kompletter Ordner)
        (str(SRC_DIR / "skins"), "skins"),
        # Zentrale Bilder/Icons (Template-SVGs, fuer alle Themes gemeinsam)
        (str(SRC_DIR / "images"), "images"),
        # Uebersetzungen
        (str(SRC_DIR / "translations.json"), "."),
        # Saubere DB (wird von clean_db.py erzeugt)
        (str(INSTALLER_DIR / "callers_caddy_clean.db"), "."),
        # Default-INI
        (str(INSTALLER_DIR / "callers_caddy_default.ini"), "."),
        # System-Rules (wird nach rules/ kopiert)
        (str(SRC_DIR / "rules_system.json"), "."),
        # Gebuendelte Referenzdaten fuer MS50-Reseed (reference_calls.json).
        # Wird zur Laufzeit ueber os.path.dirname(__file__) neben song_db.py
        # gesucht -> im Bundle == _internal/, also Ziel ".".
        (str(SRC_DIR / "reference_calls.json"), "."),
        # Lizenzen (intern#248): build.py legt beides neben die EXE
        (str(PROJECT_ROOT / "LICENSE"), "."),
        (str(INSTALLER_DIR / "licenses"), "licenses"),
    ],
    hiddenimports=[
        "numpy",
        "scipy.signal",
        "soundfile",
        "sounddevice",
        "PySide6.QtWidgets",
        "PySide6.QtCore",
        "PySide6.QtGui",
        # pycaw: Windows WASAPI per-App-Volume (optional, graceful degradation ohne)
        "pycaw",
        "pycaw.pycaw",
        "comtypes",
        "comtypes.client",
        # pypdf: PDF-Lyrics-Anzeige (Lazy-Import, BL-146)
        "pypdf",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    cipher=block_cipher,
)

# ---------- Migrations-Tool ----------

migration_analysis = Analysis(
    [str(MIGRATION_DIR / "migrate.py")],
    pathex=[str(SRC_DIR)],
    binaries=[],
    datas=[
        # Keine eigenen Daten — nutzt translations.json aus der Hauptanwendung
    ],
    hiddenimports=[
        "access_parser",
        "PySide6.QtWidgets",
        "PySide6.QtCore",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    cipher=block_cipher,
)

# ---------- Class-Designer-Tool ----------

cd_analysis = Analysis(
    [str(SRC_DIR / "class_designer.py")],
    pathex=[str(SRC_DIR)],
    binaries=[],
    datas=[
        # Keine eigenen Daten — nutzt translations.json aus der Hauptanwendung
    ],
    hiddenimports=[
        "PySide6.QtWidgets",
        "PySide6.QtCore",
        "PySide6.QtGui",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    cipher=block_cipher,
)

# ---------- MERGE: Gemeinsame Bibliotheken ----------
# Dedupliziert alle gemeinsamen Abhaengigkeiten (Python, PySide6, Qt, etc.)
MERGE(
    (app_analysis, "callers_caddy", "callers_caddy"),
    (migration_analysis, "migration", "migration"),
    (cd_analysis, "class_designer", "class_designer"),
)

# ---------- EXE-Dateien ----------

app_pyz = PYZ(app_analysis.pure, cipher=block_cipher)

app_exe = EXE(
    app_pyz,
    app_analysis.scripts,
    [],
    exclude_binaries=True,
    name="callers_caddy",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,      # Windowed mode, kein Konsolenfenster
    icon=icon_param,
    version=version_param,  # Windows EXE-Detailinfos (Rechtsklick → Eigenschaften)
)

migration_pyz = PYZ(migration_analysis.pure, cipher=block_cipher)

migration_exe = EXE(
    migration_pyz,
    migration_analysis.scripts,
    [],
    exclude_binaries=True,
    name="migration",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,      # Windowed mode
    icon=icon_param,
    version=migration_version_param,
)

cd_pyz = PYZ(cd_analysis.pure, cipher=block_cipher)

cd_exe = EXE(
    cd_pyz,
    cd_analysis.scripts,
    [],
    exclude_binaries=True,
    name="class_designer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,      # Windowed mode
    icon=icon_param,
    version=cd_version_param,
)

# ---------- Gemeinsames COLLECT ----------
# Ein Ordner mit allen drei EXEs und geteiltem _internal/

combined_collect = COLLECT(
    app_exe,
    app_analysis.binaries,
    app_analysis.datas,
    migration_exe,
    migration_analysis.binaries,
    migration_analysis.datas,
    cd_exe,
    cd_analysis.binaries,
    cd_analysis.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="callers_caddy",
)
