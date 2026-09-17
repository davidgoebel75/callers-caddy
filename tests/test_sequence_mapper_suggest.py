"""Tests fuer die Figuren-Mengen-Vorschlaege in sequence_mapper.py (BL-210.7).

Geprueft werden ausschliesslich zwei oeffentliche Schnittstellen:

  - suggest_figure_set(raw_text, exact_lookup) -> (figure_set | None, pattern | None)
  - CallMatcher.exact_by_canonical(name) -> Optional[str]

``exact_lookup`` ist ein handgeschriebenes Dict (KEINE SongDatabase, kein Qt):
Schluessel ist der kanonische Name, vereinheitlicht wie es suggest_figure_set
intern auch mit dem Eingabetext macht (Kleinschreibung, '&' -> 'and',
Zahlwoerter 'eight'/'four' -> '8'/'4', Mehrfach-Leerzeichen zusammengezogen).
Die erwarteten Entity-IDs sind frei erfundene, aber realistische Namen -- sie
stammen unabhaengig von der Implementierung aus dieser Testdatei selbst.
"""
from sequence_mapper import CallMatcher, suggest_figure_set


def test_volltreffer_unterdrueckt_vorschlag():
    exact_lookup = {
        "right and left thru": "call_right_and_left_thru",
    }

    result = suggest_figure_set("Right and Left Thru", exact_lookup)

    assert result == (None, None)


def test_ziffer_wort_vereinheitlichung_trifft_namenstraeger_k1():
    # 'All 8 Circulate' trifft trotz Ziffer/Wort-Unterschied den Namenstraeger
    # 'All Eight Circulate' -- kein Vorschlag (K1, siehe BL-210.7 Nachtrag).
    exact_lookup = {
        "all 8 circulate": "call_all_eight_circulate",
    }

    assert suggest_figure_set("All 8 Circulate", exact_lookup) == (None, None)


def test_all8_konzept_faellt_k2():
    # Gegenprobe zu K1: kein Namenstraeger fuer 'All 8 Swing Thru' -> K2,
    # Vorschlag ist Konzept-Figur + der (bereits vorhandene) Rest.
    exact_lookup = {
        "swing thru": "call_swing_thru",
        "all 8 concept": "concept_all_8",
    }

    assert suggest_figure_set("All 8 Swing Thru", exact_lookup) == (
        ["concept_all_8", "call_swing_thru"], "all8")


def test_kaufmanns_und_und_sind_gleichwertig_kein_split():
    # '&' vs 'and': Volltreffer auf 'Swing and Mix' unterdrueckt den Split,
    # obwohl 'Swing' und 'Mix' auch je einzeln aufloesbar waeren.
    exact_lookup = {
        "swing and mix": "call_swing_and_mix",
        "swing": "call_swing",
        "mix": "call_mix",
    }

    assert suggest_figure_set("Swing & Mix", exact_lookup) == (None, None)


def test_wiederholungssuffixe_bleiben_k1():
    # Wiederholungsangaben duerfen den Volltreffer nicht verhindern -- sonst
    # bekommen diese Texte faelschlich einen Konzept-Vorschlag (K2).
    exact_lookup = {
        "all 8 circulate": "call_all_eight_circulate",
    }

    assert suggest_figure_set("All 8 Circulate Double", exact_lookup) == (None, None)
    assert suggest_figure_set("All 8 Circulate 1 & 1/2", exact_lookup) == (None, None)
    assert suggest_figure_set("All Eight Circulate Twice", exact_lookup) == (None, None)


def test_all8_zweig_ist_terminal_kein_split():
    # Ohne Endungs-Bereinigung im Volltreffer wuerde 'All 8 Circulate 1 & 1/2'
    # den All-8-Zweig erreichen und dort am '&' zerschnitten werden koennen
    # (Split haette 'Circulate' und '1/2' -- falscher Vorschlag). Muss (None,
    # None) bleiben, nicht durch Split zerlegt werden.
    exact_lookup = {
        "all 8 circulate": "call_all_eight_circulate",
        "all 8 concept": "concept_all_8",
        "circulate": "call_circulate",
    }

    assert suggest_figure_set("All 8 Circulate 1 & 1/2", exact_lookup) == (None, None)


def test_all8_zweifelsfall_k3_kein_vorschlag():
    # 'Any Hand Remake' loest weder als Volltreffer noch als (Anything)-
    # Vorlage auf -- K3: kein Vorschlag, kein Rateversuch.
    exact_lookup = {
        "all 8 concept": "concept_all_8",
    }

    assert suggest_figure_set("All 8 Any Hand Remake", exact_lookup) == (None, None)


def test_anything_vorlagen_alle_sieben():
    # Alle 7 bestaetigten (Anything)-Vorlagen (siehe BL-210.7), je einmal mit
    # einer passenden Zielfigur durchgespielt. Reihenfolge im Ergebnis:
    # [Zielfigur, Vorlagen-Konzept] (siehe Nachtrag-Beispiel 'Alter The Wave').
    exact_lookup = {
        "chase right": "call_chase_right",
        "(anything) and roll": "concept_anything_and_roll",
        "(anything) and spread": "concept_anything_and_spread",
        "circulate": "call_circulate",
        "explode and (anything)": "concept_explode_and_anything",
        "clover and (anything)": "concept_clover_and_anything",
        "trade": "call_trade",
        "(anything) and cross": "call_anything_and_cross",
        "cross clover and (anything)": "call_cross_clover_and_anything",
        "transfer and (anything)": "concept_transfer_and_anything",
    }

    assert suggest_figure_set("Chase Right & Roll", exact_lookup) == (
        ["call_chase_right", "concept_anything_and_roll"], "anything")
    assert suggest_figure_set("Circulate & Spread", exact_lookup) == (
        ["call_circulate", "concept_anything_and_spread"], "anything")
    assert suggest_figure_set("Explode & Circulate", exact_lookup) == (
        ["call_circulate", "concept_explode_and_anything"], "anything")
    assert suggest_figure_set("Clover and Circulate", exact_lookup) == (
        ["call_circulate", "concept_clover_and_anything"], "anything")
    assert suggest_figure_set("Trade and Cross", exact_lookup) == (
        ["call_trade", "call_anything_and_cross"], "anything")
    assert suggest_figure_set("Cross Clover and Circulate", exact_lookup) == (
        ["call_circulate", "call_cross_clover_and_anything"], "anything")
    assert suggest_figure_set("Transfer and Circulate", exact_lookup) == (
        ["call_circulate", "concept_transfer_and_anything"], "anything")


def test_all4couples_konzept_plus_rest():
    exact_lookup = {
        "all 4 couples concept": "concept_all_4_couples",
        "rollaway": "call_rollaway",
    }

    assert suggest_figure_set("All 4 Couples Rollaway", exact_lookup) == (
        ["concept_all_4_couples", "call_rollaway"], "all8")


def test_rekursiver_rest_all8_plus_anything():
    # 'All 8 Alter The Wave & Roll' -> Konzept + Alter The Wave + der
    # (Anything)&Roll-Konzept (Nachtrag-Beispiel aus BL-210.7).
    exact_lookup = {
        "all 8 concept": "concept_all_8",
        "alter the wave": "call_alter_the_wave",
        "(anything) and roll": "concept_anything_and_roll",
    }

    assert suggest_figure_set("All 8 Alter The Wave & Roll", exact_lookup) == (
        ["concept_all_8", "call_alter_the_wave", "concept_anything_and_roll"],
        "all8")


def test_split_eindeutig_und_mehrdeutig():
    exact_lookup = {
        "circulate": "call_circulate",
        "trade": "call_trade",
    }

    # Eindeutig: jeder Teil ist fuer sich genau eine Figur.
    assert suggest_figure_set("Circulate, Trade", exact_lookup) == (
        ["call_circulate", "call_trade"], "split")

    # Mehrdeutig: 'Frobnicate' ist keine bekannte Figur -> kein Vorschlag.
    assert suggest_figure_set("Circulate, Frobnicate", exact_lookup) == (None, None)


def test_reihenfolge_anything_gewinnt_vor_split():
    # 'Explode & Circulate' passt sowohl auf die Anything-Vorlage
    # 'Explode & (Anything)' als auch -- waere 'Explode' selbst eine Figur --
    # auf einen Split ['Explode', 'Circulate']. Anything muss gewinnen.
    exact_lookup = {
        "explode": "call_explode",
        "circulate": "call_circulate",
        "explode and (anything)": "concept_explode_and_anything",
    }

    assert suggest_figure_set("Explode & Circulate", exact_lookup) == (
        ["call_circulate", "concept_explode_and_anything"], "anything")


def test_exact_by_canonical_deterministisch_bei_mehrfachnamen():
    # Realer Fall: 'Explode & (Anything)' existiert 3x in der Referenz (je
    # Programm). Bei Mehrdeutigkeit muss IMMER die niedrigste teaching_order
    # gewinnen -- unabhaengig von der Reihenfolge, in der die Zeilen
    # hereinkommen (sonst wandert die Vorlagen-entity_id zwischen Laeufen).
    canonicals_vorwaerts = [
        ("concept_explode_and_anything_plus", "Explode & (Anything)", 39.0018, "Plus"),
        ("concept_explode_and_anything_a1", "Explode & (Anything)", 49.0042, "A1"),
        ("concept_explode_and_anything_plus26", "Explode & (Anything)", 40.0039, "Plus (2026)"),
    ]
    canonicals_rueckwaerts = list(reversed(canonicals_vorwaerts))

    vorwaerts = CallMatcher(canonicals_vorwaerts)
    rueckwaerts = CallMatcher(canonicals_rueckwaerts)

    assert vorwaerts.exact_by_canonical("Explode & (Anything)") == (
        "concept_explode_and_anything_plus")
    assert rueckwaerts.exact_by_canonical("Explode & (Anything)") == (
        "concept_explode_and_anything_plus")
    # case-insensitiv
    assert vorwaerts.exact_by_canonical("explode & (anything)") == (
        "concept_explode_and_anything_plus")
