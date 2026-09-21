"""Tests fuer die Figuren-Mengen-Vorschlaege in sequence_mapper.py (BL-210.7).

Geprueft werden ausschliesslich zwei oeffentliche Schnittstellen:

  - suggest_figure_set(raw_text, exact_lookup, rest_lookup=None)
        -> (figure_set | None, pattern | None)
  - CallMatcher.exact_by_canonical(name) -> Optional[str]

``exact_lookup``/``rest_lookup`` sind handgeschriebene Dicts (KEINE
SongDatabase, kein Qt): Schluessel ist canon_key(Text) -- Kleinschreibung,
'&' -> 'and', Zahlwoerter 'eight'/'four' -> '8'/'4', Mehrfach-Leerzeichen
zusammengezogen (dieselbe Funktion, mit der auch CallMatcher.exact_by_-
canonical() seinen Schluessel bildet). ``exact_lookup`` enthaelt NUR rohe
kanonische Namen/Vorlagen/Konzepte, ``rest_lookup`` (optional) zusaetzlich
bereits bestehende Call-Text-Zuordnungen (z. B. aus call_text_mappings) --
siehe suggest_figure_set()-Docstring fuer die genaue Reihenfolge.
Die erwarteten Entity-IDs sind frei erfundene, aber realistische Namen -- sie
stammen unabhaengig von der Implementierung aus dieser Testdatei selbst.
"""
from sequence_mapper import CallMatcher, canon_key, suggest_figure_set


def test_volltreffer_unterdrueckt_vorschlag():
    # 'Right' und 'Left Thru' waeren je einzeln aufloesbar -- ohne Vorrang
    # des Volltreffers wuerde der Text am 'and' zerschnitten.
    exact_lookup = {
        "right and left thru": "call_right_and_left_thru",
        "right": "call_right",
        "left thru": "call_left_thru",
    }

    result = suggest_figure_set("Right and Left Thru", exact_lookup)

    assert result == (None, None)


def test_ziffer_wort_vereinheitlichung_trifft_namenstraeger_k1():
    # 'All 8 Circulate' trifft trotz Ziffer/Wort-Unterschied den Namenstraeger
    # 'All Eight Circulate' -- kein Vorschlag (K1, siehe BL-210.7 Nachtrag).
    # Konzept und 'Circulate' stehen mit drin: liefe die Volltreffer-Pruefung
    # ueber den normalisierten Lookup (normalize_call_text('All Eight
    # Circulate') == 'circulate'), kaeme hier K2 [Konzept, Circulate] heraus.
    exact_lookup = {
        "all 8 circulate": "call_all_eight_circulate",
        "all 8 concept": "concept_all_8",
        "circulate": "call_circulate",
    }

    assert suggest_figure_set("All 8 Circulate", exact_lookup) == (None, None)
    assert suggest_figure_set("All Eight Circulate", exact_lookup) == (None, None)


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
    assert suggest_figure_set("Swing and Mix", exact_lookup) == (None, None)


def test_wiederholungssuffixe_bleiben_k1():
    # Wiederholungsangaben duerfen den Volltreffer nicht verhindern -- sonst
    # bekommen diese Texte faelschlich einen Konzept-Vorschlag (K2). Je eine
    # Endung pro Alternative von _REPEAT_SUFFIX_RE (BL-210.11: faengt auch
    # eine Vorpruefung ab, die eine Endung vergisst). Der Rest samt Endung ist
    # bereits zugeordnet (rest_lookup), sonst liefe ein Fehler nur in K3 und
    # ergaebe ebenfalls (None, None).
    texts = ("All 8 Circulate Double", "All 8 Circulate 1 & 1/2",
             "All Eight Circulate Twice", "All 8 Circulate (again)",
             "All 8 Circulate 1/2", "All 8 Circulate 3",
             "All 8 Circulate Again", "All 8 Circulate, Go Double",
             "All 8 Circulate Two Times", "All 8 Circulate 2 Times",
             "All 8 Circulate Once And Half", "All 8 Circulate &",
             "All 8 Circulate And")
    exact_lookup = {
        "all 8 circulate": "call_all_eight_circulate",
        "all 8 concept": "concept_all_8",
    }
    rest_lookup = {canon_key(t.split(" ", 2)[2]): "call_circulate" for t in texts}

    for text in texts:
        assert suggest_figure_set(text, exact_lookup, rest_lookup) == (
            None, None), text


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


def test_anything_vorlage_mit_unbekanntem_rest_kein_vorschlag():
    # Vorlage erkannt, aber die Zielfigur ist unbekannt -> kein Vorschlag,
    # weder bei Suffix- ('(Anything) & Roll') noch bei Praefix-Vorlage
    # ('Explode & (Anything)').
    exact_lookup = {
        "(anything) and roll": "concept_anything_and_roll",
        "explode and (anything)": "concept_explode_and_anything",
        "circulate": "call_circulate",
    }

    assert suggest_figure_set("Frobnicate & Roll", exact_lookup) == (None, None)
    assert suggest_figure_set("Explode & Frobnicate", exact_lookup) == (None, None)


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

    # Eindeutig: jeder Teil ist fuer sich genau eine Figur -- fuer alle drei
    # Trenner (Komma, '&', 'and').
    for text in ("Circulate, Trade", "Circulate & Trade", "Circulate and Trade"):
        assert suggest_figure_set(text, exact_lookup) == (
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


def test_exact_by_canonical_ampersand_und_and_gleichwertig():
    # F2: exact_by_canonical() muss denselben Schluessel benutzen wie
    # canon_key() -- sonst findet ein per exact_by_canonical() gebautes
    # exact_lookup Vorlagen mit '&' nicht wieder, wenn suggest_figure_set()
    # sie ueber canon_key() (mit '&' -> 'and') nachschlaegt.
    canonicals = [
        ("concept_anything_and_roll", "(Anything) & Roll", 39.0012, "Plus"),
    ]
    matcher = CallMatcher(canonicals)

    assert matcher.exact_by_canonical("(Anything) & Roll") == "concept_anything_and_roll"
    assert matcher.exact_by_canonical("(Anything) and Roll") == "concept_anything_and_roll"


def test_exact_by_canonical_zahlwort_und_leerzeichen():
    # canon_key: 'Four'/'Eight' -> Ziffer, Mehrfach-Leerzeichen zusammengezogen.
    matcher = CallMatcher([
        ("concept_all_4_couples", "All 4 Couples Concept", 60.0035, "A2"),
        ("concept_all_8", "All 8 Concept", 60.0035, "A2"),
    ])

    assert matcher.exact_by_canonical("All  Four Couples Concept") == (
        "concept_all_4_couples")
    assert matcher.exact_by_canonical("all eight\tconcept") == "concept_all_8"


def test_rollenpraefix_volltreffer_kein_vorschlag():
    # F3: 'Heads Right & Left Thru' ist nach Abzug des Rollen-Praefixes ein
    # Volltreffer auf 'Right and Left Thru' -- kein Vorschlag, obwohl der
    # rohe Text ein '&' enthaelt und damit auch splittbar aussaehe.
    exact_lookup = {
        "right and left thru": "call_right_and_left_thru",
    }

    assert suggest_figure_set("Heads Right & Left Thru", exact_lookup) == (None, None)


def test_rollenpraefix_bei_anything_ziel():
    # F3: Die Zielfigur einer (Anything)-Vorlage kann selbst einen
    # gewoehnlichen Rollen-Praefix tragen ('Boys Trade & Roll' -> Ziel
    # 'Trade' unter dem Praefix 'Boys').
    exact_lookup = {
        "trade": "call_trade",
        "(anything) and roll": "concept_anything_and_roll",
    }

    assert suggest_figure_set("Boys Trade & Roll", exact_lookup) == (
        ["call_trade", "concept_anything_and_roll"], "anything")


def test_rest_lookup_loest_all8_rest_ueber_bestehende_zuordnung_auf():
    # F1: 'Touch 1/4' ist keine kanonische Figur (die heisst 'Touch A
    # Quarter'), aber laengst per call_text_mappings korrekt zugeordnet.
    # Mit rest_lookup wird daraus ein K2-Vorschlag.
    exact_lookup = {
        "all 4 couples concept": "concept_all_4_couples",
    }
    rest_lookup = {
        "touch 1/4": "call_touch_a_quarter",
    }

    assert suggest_figure_set(
        "All 4 Couples Touch 1/4", exact_lookup, rest_lookup) == (
        ["concept_all_4_couples", "call_touch_a_quarter"], "all8")


def test_ohne_rest_lookup_bleibt_konservatives_verhalten():
    # F1, Gegenprobe: derselbe Text ohne rest_lookup bleibt K3 (kein
    # Vorschlag) -- das heutige, konservative Verhalten aendert sich nicht.
    exact_lookup = {
        "all 4 couples concept": "concept_all_4_couples",
    }

    assert suggest_figure_set("All 4 Couples Touch 1/4", exact_lookup) == (
        None, None)


def test_rest_lookup_unterdrueckt_keinen_vorschlag():
    # Kern von F1: rest_lookup darf die Volltreffer-Pruefung des GESAMTEN
    # Textes nicht speisen. Sonst faellt jeder bereits zugeordnete Call-Text
    # in den Volltreffer und bekommt nie wieder einen Vorschlag -- also genau
    # die Alt-Zuordnungen, die BL-210.8 finden soll, waeren unsichtbar.
    exact_lookup = {
        "all 8 concept": "concept_all_8",
        "fan the top": "call_fan_the_top",
    }
    # Der ganze Text ist hier bereits zugeordnet (wie in call_text_mappings).
    rest_lookup = {
        "all 8 fan the top": "call_fan_the_top",
        "fan the top": "call_fan_the_top",
    }

    assert suggest_figure_set(
        "All 8 Fan The Top", exact_lookup, rest_lookup) == (
        ["concept_all_8", "call_fan_the_top"], "all8")


def test_split_ignoriert_rest_lookup():
    # Split loest ausschliesslich ueber rohe kanonische Namen auf (BL-210.7,
    # Baustein 4): mit bestehenden Zuordnungen wuerde sich die Split-Klasse
    # durch Bruchstuecke verdoppeln.
    exact_lookup = {
        "circulate": "call_circulate",
    }
    rest_lookup = {
        "frobnicate": "call_frobnicate",
    }

    assert suggest_figure_set(
        "Circulate, Frobnicate", exact_lookup, rest_lookup) == (None, None)


def test_split_ohne_duplikate_und_ohne_scheinmenge():
    # Das Ergebnis ist eine Menge, keine Aufzaehlung der Tanzschritte.
    exact_lookup = {
        "trade": "call_trade",
        "pass thru": "call_pass_thru",
        "trade by": "call_trade_by",
    }

    # Mehrfach dieselbe Figur -> nach dem Entdoppeln bleibt EINE Figur uebrig,
    # also kein Mehrfachfall und kein Mengenvorschlag.
    assert suggest_figure_set("Boys Trade, Girls Trade", exact_lookup) == (
        None, None)

    # Wiederholung innerhalb einer echten Mehrfachmenge: Duplikat faellt weg,
    # die Reihenfolge des ersten Auftretens bleibt.
    assert suggest_figure_set(
        "Pass Thru, Trade By, Pass Thru", exact_lookup) == (
        ["call_pass_thru", "call_trade_by"], "split")


def test_all8_rest_ist_volltreffer_kein_split():
    # 'Swing and Mix' ist eine eigene Figur. Der Rest hinter dem All-8-Praefix
    # muss sie als Ganzes treffen -- NICHT als [Swing, Mix] zerlegt werden.
    exact_lookup = {
        "all 8 concept": "concept_all_8",
        "swing and mix": "call_swing_and_mix",
        "swing": "call_swing",
        "mix": "call_mix",
    }

    assert suggest_figure_set("All 8 Swing & Mix", exact_lookup) == (
        ["concept_all_8", "call_swing_and_mix"], "all8")


def test_all8_k1_figur_mit_anything_vorlage():
    # 'All 8 Spin the Top' ist eine eigene Figur (K1). Mit '& Spread'
    # dahinter ist der Text die Vorlage mit der K1-Figur als Ziel -- NICHT
    # das All-8-Konzept (A2) plus 'Spin the Top'. Realer Fall aus der
    # Stichprobe (BL-210.11), dort kam der Rest ueber eine bestehende
    # Zuordnung ('Spin The Top & Spread' -> Spin the Top) zustande.
    exact_lookup = {
        "all 8 spin the top": "call_all_8_spin_the_top",
        "all 8 concept": "concept_all_8",
        "spin the top": "call_spin_the_top",
        "(anything) and spread": "concept_anything_and_spread",
    }
    rest_lookup = {"spin the top and spread": "call_spin_the_top"}
    expected = (["call_all_8_spin_the_top", "concept_anything_and_spread"],
                "anything")

    assert suggest_figure_set("All 8 Spin The Top & Spread", exact_lookup) == expected
    assert suggest_figure_set(
        "All 8 Spin The Top & Spread", exact_lookup, rest_lookup) == expected


def test_all4couples_rest_mit_and_im_figurennamen():
    # Gegenstueck zum vorigen Fall auf der All-4-Couples-Seite: das 'And' im
    # Figurennamen darf den Rest nicht am Split zerreissen.
    exact_lookup = {
        "all 4 couples concept": "concept_all_4_couples",
        "right and left thru": "call_right_and_left_thru",
        "right": "call_right",
        "left thru": "call_left_thru",
    }

    assert suggest_figure_set(
        "All 4 Couples Right And Left Thru", exact_lookup) == (
        ["concept_all_4_couples", "call_right_and_left_thru"], "all8")
