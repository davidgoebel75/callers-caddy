"""Erstellt eine saubere Auslieferungs-DB aus der Entwicklungs-DB.

Kopiert die DB und leert alle benutzerspezifischen Tabellen.
Referenzdaten (Sequenzen, Teaching Orders, Call-Mappings) bleiben erhalten.
"""

import os
import shutil
import sqlite3
import sys
from pathlib import Path

# Quell-DB (Testumgebung mit echten Daten). Per CC_TEST_DIR ueberschreibbar
# (siehe C:\Git\build-cc.bat), sonst Fallback = <Ordner ueber dem Repo>/2_Test.
_TEST_DIR = os.environ.get("CC_TEST_DIR")
SOURCE_DB = (Path(_TEST_DIR) if _TEST_DIR
             else Path(__file__).parent.parent.parent / "2_Test") / "callers_caddy.db"
# Ziel-DB (sauber fuer Auslieferung)
TARGET_DB = Path(__file__).parent / "callers_caddy_clean.db"

# Tabellen die geleert werden (Benutzerdaten)
TABLES_TO_CLEAR = [
    "songs",
    "locations",
    "play_history",
    "song_location_stats",
    "song_genres",
    "genres",
    # Ab 0.121: haengen alle an songs/locations und waren nach dem Leeren
    # verwaist trotzdem noch im Vollpaket-ZIP enthalten (DSGVO).
    "notes",              # Notizen des Callers, mit Zeitstempeln + location_id
    "song_properties",    # Sammlungs-Metadaten: Artist, Jahr, Songanfang, Sync-Punkte
    "photos",             # Fotos an Lokationen
    "potential_ignored",  # persoenliche "ignorieren"-Entscheidungen im Potential-Dashboard
    # MS50 (2026): Zuordnung Lokation->Tanzprogramme haengt an locations (Nutzerdaten).
    "location_programs",
    # intern#247: Square-Flow-Ergebnisse je Sequenz, reiner Rechen-Cache. Haengt an
    # sequence_id, und die Sequenzen werden unten neu gesetzt (neue IDs).
    "sequence_choreo",
]

# Tabellen die erhalten bleiben (Referenzdaten):
# sequences, sequence_calls, teaching_order_calls, call_text_mappings,
# dance_programs
# MS50 (2026): calls (Call-Identitaet), call_programs (Programm-Zugehoerigkeit),
# app_meta (Referenzdaten-Version fuer den Reseed) — ebenfalls Referenzdaten.

# Keine dieser Tabellen darf Zeilen behalten, die auf einen Song oder eine
# Lokation zeigen — songs/locations sind leer, alles andere waere verwaister
# Privatbestand im Auslieferungspaket.
USER_TABLES_MUST_BE_EMPTY = TABLES_TO_CLEAR


def clean_db():
    """Kopiert die DB und leert Benutzerdaten-Tabellen."""
    if not SOURCE_DB.exists():
        print(f"FEHLER: Quell-DB nicht gefunden: {SOURCE_DB}")
        sys.exit(1)

    # Kopieren
    print(f"Kopiere {SOURCE_DB.name} ...")
    shutil.copy2(SOURCE_DB, TARGET_DB)

    # Saeuberung
    conn = sqlite3.connect(TARGET_DB)
    for table in TABLES_TO_CLEAR:
        count_before = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        conn.execute(f"DELETE FROM {table}")
        print(f"  {table}: {count_before} Zeilen geloescht")

    # Auto-Increment-Zaehler zuruecksetzen
    conn.execute("DELETE FROM sqlite_sequence WHERE name IN ({})".format(
        ",".join(f"'{t}'" for t in TABLES_TO_CLEAR)
    ))

    # MS50-Perf: persistenter Band-Cover-Cache (nur Sequenz-IDs, keine
    # Nutzerdaten) — leeren. Er ist mit dem Trigger-Versionszaehler gestempelt,
    # den die Saeuberung oben ohnehin hochzaehlt; alte Eintraege waeren also
    # sowieso ungueltig. Baut sich beim ersten Start des Nutzers neu auf.
    try:
        conn.execute("DELETE FROM _band_cover")
    except sqlite3.OperationalError:
        pass   # Tabelle in aelterer Quell-DB evtl. noch nicht vorhanden

    conn.commit()
    conn.execute("VACUUM")
    conn.close()

    # --- Referenz-Sequenzen deterministisch setzen -------------------------
    # Statt die (evtl. unsauberen) Sequenzen aus der Entwicklungs-DB zu
    # uebernehmen, wird der komplette Referenz-Satz aus reference_sequences.json
    # frisch gesetzt und mit source='ceder' markiert. So ist das Vollpaket
    # reproduzierbar und der Referenz-Satz spaeter sauber ersetzbar.
    ref_json = Path(__file__).parent / "reference_sequences.json"
    if ref_json.exists():
        sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
        from song_db import SongDatabase  # oeffnet DB, migriert Schema
        import json as _json
        db = SongDatabase(str(TARGET_DB))
        db._conn.execute("DELETE FROM sequence_calls")
        db._conn.execute("DELETE FROM sequences")
        db._conn.commit()
        seqs = _json.load(open(ref_json, encoding="utf-8"))
        ins, _skp = db.bulk_import_sequences(
            seqs, source="ceder", dedup_against_existing=False)
        over15 = db._conn.execute(
            "SELECT COUNT(*) FROM sequences WHERE json_array_length(calls_json)>15"
        ).fetchone()[0]
        db._conn.execute("VACUUM"); db._conn.commit()
        db._conn.close()
        print(f"  Referenz-Sequenzen gesetzt: {ins} (source='ceder', "
              f"davon {over15} mit >15 Calls)")
    else:
        print(f"  WARNUNG: {ref_json.name} nicht gefunden — Sequenzen aus Dev-DB "
              f"uebernommen (nicht als 'ceder' markiert).")

    # Ergebnis
    size_mb = TARGET_DB.stat().st_size / (1024 * 1024)
    print(f"\nSaubere DB erstellt: {TARGET_DB}")
    print(f"Groesse: {size_mb:.1f} MB")

    # Verifikation
    conn = sqlite3.connect(TARGET_DB)
    print("\nVerbleibende Referenzdaten:")
    for table in ["sequences", "sequence_calls", "teaching_order_calls",
                  "call_text_mappings", "dance_programs",
                  "calls", "call_programs", "app_meta"]:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {count} Zeilen")

    # Sperre: lieber kein Release als eines mit Privatdaten. Bis 0.120 sind
    # notes + song_properties unbemerkt mitgelaufen, weil hier nur gedruckt
    # und nichts geprueft wurde.
    print("\nDSGVO-Kontrolle (Benutzerdaten muessen leer sein):")
    leftovers = []
    for table in USER_TABLES_MUST_BE_EMPTY:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {count}")
        if count:
            leftovers.append(f"{table} ({count} Zeilen)")

    # Neue Tabellen fallen sonst still durchs Raster: alles, was weder geleert
    # noch bewusst als Referenzdaten freigegeben ist, muss auffallen.
    known = set(TABLES_TO_CLEAR) | {
        "sequences", "sequence_calls", "teaching_order_calls",
        "call_text_mappings", "dance_programs", "sqlite_sequence",
        # MS50 (2026): neue Referenz-Tabellen
        "calls", "call_programs", "app_meta",
        # MS50-Perf: interner Band-Cache-Versionszaehler (Laufzeit, kein Inhalt);
        # wird von den _bcv_*-Triggern gepflegt und beim Start neu angelegt.
        "_band_cache_ver",
        # MS50-Perf: persistenter Band-Cover-Cache (nur Sequenz-IDs, kein
        # Nutzerinhalt); oben geleert, baut sich beim Start neu auf.
        "_band_cover",
        # BL-210: weitere Figuren je Call-Text (Figuren-Mengen). Referenzdaten
        # wie call_text_mappings, bleibt erhalten.
        "call_text_figures_extra",
    }
    unknown = [t for (t,) in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'") if t not in known]
    conn.close()

    if unknown:
        print(f"\nFEHLER: unbekannte Tabelle(n): {', '.join(sorted(unknown))}")
        print("Bitte in clean_db.py entscheiden: leeren (Benutzerdaten) oder"
              " als Referenzdaten freigeben.")
        sys.exit(1)
    if leftovers:
        print(f"\nFEHLER: Benutzerdaten in der Auslieferungs-DB: "
              f"{', '.join(leftovers)}")
        sys.exit(1)
    print("  -> in Ordnung, keine Benutzerdaten in der Auslieferungs-DB.")


if __name__ == "__main__":
    clean_db()
