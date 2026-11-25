"""Call-Mapping-Tabelle: Caller-Schreibweise -> Taminations-Schreibweise (intern#163, #247).

Datei: `call_mapping.csv` neben diesem Modul (UTF-8 mit BOM, Trennzeichen ';',
in Excel bearbeitbar).

Spalten
  art            fest   = einzelne Zeile wird genau so ersetzt (Vergleich ohne Gross/Klein,
                          Mehrfach-Leerzeichen und Klammern)
                 muster = Regel-Familie, im Code umgesetzt (Spalte 'regel' = Name der Regel
                          in mapping.RULES); die Zeile dokumentiert sie mit Beispiel
  caller_variante  so steht es in den Sequenzen (bei 'muster' ein Beispiel)
  taminations      so versteht es Taminations; mehrere Calls mit ' | ' trennen
  regel          nur bei 'muster'
  status         geprueft | vorgeschlagen | abgelehnt
  quelle         manuell | vorschlag (Skript) | runde<N> | app_mapping
  pruefer, datum, notiz

Es gelten nur 'fest'-Eintraege mit Status 'geprueft'.
"""
import csv
import os
import re

QT_FREE = True

CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "call_mapping.csv")
FIELDS = ["art", "caller_variante", "taminations", "regel", "status", "quelle",
          "pruefer", "datum", "notiz"]


def norm(text):
    """Vergleichsform: ohne Klammern, Mehrfach-Leerzeichen und Gross/Klein."""
    t = re.sub(r"[()]", " ", text or "")
    return re.sub(r"\s+", " ", t).strip().lower()


def read_rows(path=CSV_PATH):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [{k: (r.get(k) or "").strip() for k in FIELDS}
                for r in csv.DictReader(f, delimiter=";")]


def write_rows(rows, path=CSV_PATH):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, delimiter=";", lineterminator="\r\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})


def _calls(r):
    return [p.strip() for p in r["taminations"].split("|") if p.strip()]


def load_fixed(rows, statuses=("geprueft",)):
    """{norm(variante): [call, ...]} fuer art=fest mit passendem Status."""
    return {norm(r["caller_variante"]): _calls(r) for r in rows
            if r["art"] == "fest" and r["status"] in statuses
            and r["caller_variante"] and r["taminations"]}


def load_app_fixed(rows):
    """Gepruefte Eintraege aus dem App-Mapping (quelle=app_mapping): Sie ersetzen die Zeile
    NICHT, sondern sind ihre letzte Lesart (siehe mapping._app_alt)."""
    return {norm(r["caller_variante"]): _calls(r) for r in rows
            if r["art"] == "fest" and r["quelle"] == "app_mapping"
            and r["status"] == "geprueft" and r["caller_variante"] and r["taminations"]}
