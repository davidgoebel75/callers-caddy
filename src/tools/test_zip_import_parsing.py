"""Standalone-Tests fuer die ZIP-Import-Namenserkennung (zip_import.py).

Ausfuehren:  python tools/test_zip_import_parsing.py   (aus 1_Source/src/)

Die Faelle stammen aus realen Label-ZIPs plus den Praxis-Beispielen aus dem
SquareDesk-Quellcode (breakFilenameIntoParts-Kaskade). Kein Framework noetig:
einfache Asserts mit Abschlussbericht.
"""

import os
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import zip_import  # noqa: E402
from zip_import import (  # noqa: E402
    ImportLists, analyze, classify_audio, cleanup, split_title_label,
    _smart_titlecase,
)

FAILS = []


def check(desc, got, expected):
    if got == expected:
        print(f"  OK   {desc}")
    else:
        print(f"  FAIL {desc}\n       erwartet: {expected!r}\n       erhalten: {got!r}")
        FAILS.append(desc)


def main():
    lists = ImportLists.defaults()
    labelmap = lists.labels.effective()
    modmap = lists.modifiers.effective()
    rolemap = lists.roles.effective()

    print("split_title_label — Bestandsfaelle (Regression):")
    cases = [
        ("Play It Cool - BS 2534a",       ("Play It Cool", "BS 2534a")),
        ("Strings Galore - Chaparral 117b", ("Strings Galore", "Chaparral 117b")),
        ("A Summer Song - CHIC3002",      ("A Summer Song", "CHIC3002")),
        ("STING 22209 - My Title",        ("My Title", "STING 22209")),
        ("Born to Hand Jive - WM 002v",   ("Born to Hand Jive", "WM 002v")),
        ("RR 409h1 - Some Song",          ("Some Song", "RR 409h1")),
        ("Just Instrumental Music",       ("Just Instrumental Music", "")),
    ]
    for name, exp in cases:
        check(name, split_title_label(name, labelmap), exp)

    print("split_title_label — neue Faelle (SquareDesk-Erkenntnisse):")
    cases = [
        # Labels mit Bindestrich (via Label-Liste maskiert)
        ("4-Bar-B 123 - Chicken Plucker", ("Chicken Plucker", "4-Bar-B 123")),
        ("Chicken Plucker - 4-bar-b 123", ("Chicken Plucker", "4-bar-b 123")),
        ("Jay-Bar-Kay 501 - Foo",         ("Foo", "Jay-Bar-Kay 501")),
        # Mehrwort-Labels (bekannt via Liste bzw. generisch ab 3-stelliger Nummer)
        ("Streets of London - New Beat 203a", ("Streets of London", "New Beat 203a")),
        ("Some Song - Big Deal 4051",     ("Some Song", "Big Deal 4051")),
        # Label-Kuerzel mit Ziffer im Namensteil
        ("OGRMP3 04 - Addam's Family",    ("Addam's Family", "OGRMP3 04")),
        # Nummer-only-Label links, Punkt-Trenner
        ("123 - Chicken Plucker",         ("Chicken Plucker", "123")),
        ("123.Chicken Plucker",           ("Chicken Plucker", "123")),
        ("123. Chicken Plucker",          ("Chicken Plucker", "123")),
        # Label-Nummer mit Bindestrich statt Space
        ("Paper Doll - Windsor-4936B",    ("Paper Doll", "Windsor 4936B")),
        ("Windsor-4936 - Paper Doll",     ("Paper Doll", "Windsor 4936")),
        # Download-Slugs (Underscore/%20)
        ("ego_112_-_go_tell_aunt_rhody",  ("go tell aunt rhody", "ego 112")),
        ("My%20Song%20-%20GP%20509",      ("My Song", "GP 509")),
        # Kompakte SqView-Namen (Dateiname = Label)
        ("A1005m",                        ("A1005m", "A1005m")),
        ("sd318v",                        ("sd318v", "sd318v")),
        # Negativfaelle: hier darf KEIN Label erkannt werden
        ("Bryan Adams - Summer of 69",    ("Bryan Adams - Summer of 69", "")),
        ("10-20Hoedown",                  ("10-20Hoedown", "")),
        ("Track  3",                      ("Track 3", "")),
        ("Free_m",                        ("Free m", "")),
    ]
    for name, exp in cases:
        check(name, split_title_label(name, labelmap), exp)

    print("classify_audio:")
    cases = [
        ("Born to Hand Jive - WM 002",    ("", "Instrumental", True)),
        ("Born to Hand Jive - WM 002v",   ("v", "Vocal", False)),
        ("My Song (V) - STING 22209",     ("V", "Vocal", False)),
        ("My Song (Vocal) - STING 22209", ("Vocal", "Vocal", False)),
        ("Foo Bar Vocal - RR 123",        ("Vocal", "Vocal", False)),
        ("original Born to Hand Jive",    ("", "Original", False)),
        ("hoedown_sample_wm_002",         ("", "Sample", False)),
        # Kompaktes Paar: A1005 = Haupt-MP3, A1005v = Vocal-Variante
        ("A1005",                         ("", "Instrumental", True)),
        ("A1005v",                        ("v", "Vocal", False)),
    ]
    for stem, (mod, text, is_main) in cases:
        info = classify_audio(stem, modmap, labelmap, rolemap)
        check(stem, (info["modifier"], info["label_text"], info["is_main"]),
              (mod, text, is_main))

    print("_smart_titlecase:")
    check("slug klein", _smart_titlecase("go tell aunt rhody"), "Go Tell Aunt Rhody")
    check("alles gross", _smart_titlecase("GO TELL AUNT RHODY"), "Go Tell Aunt Rhody")
    check("gemischt bleibt", _smart_titlecase("McGregor Special"), "McGregor Special")

    print("analyze — End-to-End mit synthetischem ZIP:")
    tmp = tempfile.mkdtemp(prefix="cc_ziptest_")
    zip_path = os.path.join(tmp, "ego_112_-_go_tell_aunt_rhody.zip")
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("ego_112_-_go_tell_aunt_rhody.mp3", b"main")
        zf.writestr("ego_112_-_go_tell_aunt_rhody_(vocal).mp3", b"vocal-track")
        zf.writestr("ego 112 - go tell aunt rhody.html", b"<html>lyrics</html>")
        zf.writestr("cover.jpg", b"jpg")
    result = analyze([zip_path], lists=lists)
    try:
        check("1 Bundle", len(result.bundles), 1)
        b = result.bundles[0]
        check("Titel (Slug normalisiert + Title-Case)", b.title, "Go Tell Aunt Rhody")
        check("Label aus Slug", b.label, "ego 112")
        check("2 Audios", len(b.audio), 2)
        check("Primaer = Datei ohne Modifier",
              b.audio[0].filename, "ego_112_-_go_tell_aunt_rhody.mp3")
        check("Variante als Vocal erkannt", b.audio[1].label_text, "Vocal")
        check("1 Lyrics", len(b.lyrics), 1)
        check("Cover ignoriert mit Grund",
              result.ignored_reasons.get("cover.jpg"), "Bild/Cover")
        check("Vollstaendigkeitscheck", result.is_complete, True)
    finally:
        cleanup(result)

    print()
    if FAILS:
        print(f"{len(FAILS)} FEHLER:")
        for f in FAILS:
            print(f"  - {f}")
        sys.exit(1)
    print("Alle Tests bestanden.")


if __name__ == "__main__":
    main()
