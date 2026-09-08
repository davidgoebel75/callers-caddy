"""Tests fuer singing_sections.figure_call_end_line (BL-200).

Die Funktion bestimmt fuer einen Figuren-INHALTSBEREICH die letzte Tanz-Call-
Zeile. Zeilen danach = angehaengter Gesangstext (waehrend der Heim-Promenade),
den Dynamic Lyrics nicht ersetzen soll. Rein textbasiert, GUI-frei.
"""
import singing_sections as ss


def _cut(block_lines, tail_cut=None):
    """Bequemlichkeit: block_lines ist der reine Inhaltsbereich (ohne Kopfzeile).
    Gibt den 0-basierten Index der Schnittzeile INNERHALB von block_lines zurueck
    (== letzte zu ersetzende Zeile). Kein Trim -> letzter Index."""
    return ss.figure_call_end_line(block_lines, 0, len(block_lines) - 1,
                                   tail_cut=tail_cut)


def test_achy_breaky_referenzfall():
    # Der namensgebende Fall: Eingangs-Promenade in Zeile 0, echte Heim-Promenade
    # spaeter; danach 2 Gesangszeilen, die erhalten bleiben muessen.
    block = [
        "Heads promenade, go half way around",
        "Walk right in and square thru go four",
        "Four hands around and then swing thru you know",
        "Boys run right and couples circulate",
        "Chain down the line and then square thru go three",
        "Swing the corner girl and promenade",   # Index 5 = Schnittkante
        "Don't tell my heart, my achy breaky heart",
        "I just don't think he'd understand",
    ]
    assert _cut(block) == 5


def test_letzte_promenade_gewinnt():
    # Mehrere Promenade-Nennungen -> die LETZTE ist die Schnittkante,
    # nicht die Eingangs-Promenade.
    block = [
        "Heads promenade half way",       # 0 (Eingang, NICHT der Schnitt)
        "Square thru four hands",          # 1
        "Swing and promenade",             # 2 = Schnittkante
        "song line one",                   # 3
        "song line two",                   # 4
    ]
    assert _cut(block) == 2


def test_block_endet_auf_promenade_kein_trim():
    # Kein angehaengter Gesangstext -> nichts zu schuetzen -> kein Trim.
    block = [
        "Square thru four hands",
        "Swing the corner girl and promenade",   # letzte Zeile
    ]
    assert _cut(block) == len(block) - 1  # == end_line, kein Trim


def test_promenade_nur_in_erster_zeile_kein_trim():
    # Waere die Eingangs-Promenade die einzige, wuerde der ganze Block als
    # "Gesangstext" gelten -> Schutz vor Ueber-Trim: kein Schnitt.
    block = [
        "Heads promenade go half way",   # 0 = erste Inhaltszeile
        "square thru and swing",
        "some song text",
    ]
    assert _cut(block) == len(block) - 1


def test_keine_promenade_kein_trim():
    block = [
        "Square thru four hands around",
        "Swing thru and boys run",
        "Ferris wheel and pass thru",
    ]
    assert _cut(block) == len(block) - 1


def test_home_als_songwort_kein_false_cut():
    # 'home' ist per Default KEIN Signal (steht fast nur im Songtext). Eine
    # Songzeile mit 'home' nach der echten Promenade darf den Schnitt NICHT
    # nach unten ziehen -> Schnitt bleibt auf der Promenade.
    block = [
        "Square thru four",
        "Swing the corner and promenade",   # 1 = korrekte Schnittkante
        "I want to be back home in Nashville",  # Songzeile mit 'home'
        "Nashville, Tennessee",
    ]
    assert _cut(block) == 1


def test_leerzeilen_im_tail():
    # Leerzeilen zwischen Promenade und Gesangstext zaehlen nicht als Tail-Signal,
    # aber es gibt echten Text danach -> Trim greift.
    block = [
        "Square thru four",
        "Swing and promenade",   # 1
        "",
        "song line",
    ]
    assert _cut(block) == 1


def test_leerer_tail_nur_whitespace_kein_trim():
    # Nach der Promenade nur Leerzeilen -> nichts Schuetzenswertes -> kein Trim.
    block = [
        "Square thru four",
        "Swing and promenade",
        "   ",
        "",
    ]
    assert _cut(block) == len(block) - 1


def test_user_delta_home_aktivierbar():
    # Wer 'HOME' bewusst als Signal will, kann es per tail_cut uebergeben
    # (analog User-Delta-JSON). Dann schneidet 'home' sehr wohl.
    block = [
        "Square thru four",
        "Promenade her home",   # 1 = Schnitt via HOME/PROMENADE
        "song tail",
    ]
    assert _cut(block, tail_cut=["PROMENADE", "HOME"]) == 1
    assert _cut(block, tail_cut=["HOME"]) == 1


def test_case_insensitive_und_wortgrenze():
    # Gross/Klein egal; 'promenade' als Teil eines groesseren Wortes zaehlt nicht.
    block = [
        "square thru",
        "SWING AND PROMENADE",   # 1 (Grossschreibung)
        "tail song",
    ]
    assert _cut(block) == 1
    # Wortgrenze: 'promenaden' o.ae. soll NICHT matchen
    block2 = [
        "walk the promenaden strip",   # kein echtes Signal (kein Wortende)
        "just song text here",
    ]
    assert _cut(block2) == len(block2) - 1


def test_indexbereich_mitten_in_groesserer_zeilenliste():
    # figure_call_end_line arbeitet auf einem Ausschnitt (start_line..end_line)
    # einer groesseren Zeilenliste und liefert absolute Indizes.
    lines = [
        "TITLE",                 # 0
        "OPENER",                # 1
        "circle left",           # 2
        "FIGURE",                # 3  (Kopfzeile)
        "square thru four",      # 4  (start_line)
        "swing and promenade",   # 5  = Schnittkante
        "song a",                # 6
        "song b",                # 7  (end_line)
    ]
    assert ss.figure_call_end_line(lines, 4, 7) == 5
