"""Song-Katalog als zentrale Referenz fuer Titel/Label/Nummer (intern#126)."""
import csv

import pytest

import song_catalog as sc
import song_match

ROWS = [
    # Song Title, Label, Label Code, Number, Type, Caller, Genre, Original Artist, Released
    ("Aint She Sweet", "ESPrit", "ESP", "717", "Singing Call", "Caller A",
     "Oldies, Jazz", "Ben Bernie", "January 1, 2010"),
    ("Ring Of Fire", "Rawhide", "RWH", "1314", "Singing Call", "Caller B",
     "", "Johnny Cash", "September 29, 2025"),
    ("Ring Of Fire", "Cheyenne Gold", "CHYG", "725", "Singing Call", "Caller C",
     "", "Johnny Cash", "July 1, 2018"),
    ("Go Tell It On The Mountain", "Ego", "EGO", "112", "Singing Call", "X",
     "", "", "2019"),
    ("I Think Weâ€™re Alone Now", "Sting", "STING", "22209", "Singing Call", "Y",
     "", "Tommy James", ""),
    ("Red Feather", "Rhythm", "RR", "402", "Patter", "", "", "", ""),
]


@pytest.fixture
def catalog(tmp_path):
    path = tmp_path / sc.CATALOG_FILE
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(sc.COLUMNS)
        w.writerows(ROWS)
    return sc.SongCatalog.from_csv(str(path))


def test_laden_felder_und_mojibake(catalog):
    assert len(catalog) == len(ROWS)
    e = catalog.by_title("aint she sweet")[0]
    assert e.label_field == "ESP 717"
    assert e.release_year == "2010"
    assert e.genres == ["Oldies", "Jazz"]
    assert e.is_singing and not e.is_patter
    # doppelt kodiertes UTF-8 aus der Quelldatei wird repariert
    assert catalog.by_label_number("STING 22209")[0].title == "I Think We’re Alone Now"
    assert catalog.by_title("Red Feather")[0].is_patter


def test_label_nummer_braucht_beides(catalog):
    assert [e.title for e in catalog.by_label_number("ESP 717")] == ["Aint She Sweet"]
    assert catalog.by_label_number("RWH 717") == []      # Nummer passt, Label nicht
    assert catalog.by_label_number("ESP") == []          # ohne Nummer nichts


@pytest.mark.parametrize("title,label,want", [
    ("AintSheSweet", "ESP717", "Aint She Sweet"),                 # zusammengeschrieben
    ("Go Tell It On The Mountain (Vocal)", "EGO 112", "Go Tell It On The Mountain"),
    ("Ring Of Fire", "RWH 1314", "Ring Of Fire"),
    ("I Think Were Alone Now", "STING 22209", "I Think We’re Alone Now"),  # Apostroph
])
def test_identify_sicher_bei_titel_label_nummer(catalog, title, label, want):
    m = catalog.identify(title, label)
    assert m is not None and m.is_sure, m
    assert m.entry.title == want


def test_nur_titel_ist_nie_sicher(catalog):
    """Derselbe Titel gibt es bei mehreren Aufnahmen: ohne Label/Nummer nur
    Vorschlag, nie automatische Uebernahme."""
    m = catalog.identify("Aint She Sweet", "")
    assert m is not None and not m.is_sure


def test_falsche_nummer_ist_nicht_sicher(catalog):
    m = catalog.identify("Ring Of Fire", "RWH 999")
    assert m is None or not m.is_sure


def test_unique_label_nur_bei_einer_aufnahme(catalog):
    assert catalog.unique_label_for_title("Aint She Sweet") == "ESP 717"
    assert catalog.unique_label_for_title("Ring Of Fire") == ""      # zwei Aufnahmen
    assert catalog.unique_label_for_title("Unbekannt") == ""


def test_label_hint_eigenes_label_hat_vorrang(catalog, monkeypatch):
    monkeypatch.setattr(sc, "get_catalog", lambda app_dir="": catalog)
    assert sc.label_hint("Aint She Sweet", "XYZ 1") == "XYZ 1"
    assert sc.label_hint("Aint She Sweet", "") == "ESP 717"
    assert sc.label_hint("Ring Of Fire", "") == ""


def test_catalog_path_app_dir_vor_repo(tmp_path):
    d = tmp_path / sc.CATALOG_DIR
    d.mkdir()
    (d / sc.CATALOG_FILE).write_text(",".join(sc.COLUMNS) + "\n", encoding="utf-8")
    assert sc.catalog_path(str(tmp_path)) == str(d / sc.CATALOG_FILE)
    # ohne Kopie im App-Ordner: Repo-Ordner (Dev-Start aus 2_Test)
    repo = sc.catalog_path(str(tmp_path / "leer"))
    assert repo.endswith(sc.CATALOG_FILE) and sc.CATALOG_DIR in repo


def test_repo_katalog_passt_zum_format():
    """Die mitgelieferte CSV laedt und hat die erwarteten Spalten."""
    path = sc.catalog_path("")
    with open(path, newline="", encoding="utf-8") as f:
        assert next(csv.reader(f)) == sc.COLUMNS
    assert len(sc.SongCatalog.from_csv(path)) > 5000


# --- Verbesserungen in der gemeinsamen Match-Basis ------------------------

@pytest.mark.parametrize("a,b", [
    ("AintSheSweet", "Aint She Sweet"),
    ("RhythmOfTheRain", "Rhythm Of The Rain"),
    ("Hey Jude (Vocal)", "Hey Jude"),
    ("I Cant Fight This Feeling", "I Can’t Fight This Feeling"),
])
def test_title_similarity_gleich(a, b):
    assert song_match.title_similarity(a, b) == 1.0


def test_title_similarity_bleibt_unterscheidend():
    assert song_match.title_similarity("Hey Jude", "Hey Joe") < 0.85


def test_split_label_number_ignoriert_plus():
    assert song_match.split_label_number("DGR014+") == ("DGR", "014")
    assert song_match.split_label_number("Shakedown 302") == ("Shakedown", "302")


@pytest.mark.parametrize("parsed,entry,want", [
    ("Go Tell It On The Mountain (Vocal)", "Go Tell It On The Mountain",
     "Go Tell It On The Mountain (Vocal)"),
    ("AintSheSweet", "Aint She Sweet", "Aint She Sweet"),
    ("Dont Stop (Thinkin About Tomorrow)", "Don’t Stop (Thinkin’ About Tomorrow)",
     "Don’t Stop (Thinkin’ About Tomorrow)"),
])
def test_canonical_title_behaelt_klammer_zusatz(parsed, entry, want):
    assert sc.canonical_title(parsed, entry) == want
