"""Sequenz-Filter: Ableitung der Abfrage-Parameter (intern#113).

Qt-frei. SequencesWidget liest seine Combos und ruft filter_query_args() auf,
tools/seq_invariants.py nutzt dieselbe Regel. Das Ergebnis geht per **args an
SongDatabase.get_filtered_count / get_filtered_sequences /
get_filtered_sequence_ids.
"""


def filter_query_args(*, contains=None, limit=None, only=False, seq_type=None,
                      difficulty=None, tags=None, bands=None,
                      show_hidden=False) -> dict:
    """Zentrale Ableitung ALLER Filter-Parameter fuer die Sequenz-Abfragen.

    contains   = entity_id des Enthaelt-Filters (oder None)
    limit      = Teaching-Order des Limits (oder None)
    only       = Nur-Filter angehakt
    bands      = Band-Menge der Tanzprogramm-Wahl (oder None/leer)
    show_hidden = "Auch ausgeblendete Sequenzen anzeigen" (intern#119) aktiv

    intern#156: Sequenzen ohne Einstufung (mind. ein Call-Text ohne tanzbare
    Zuordnung) haben unbekannten Inhalt und sind standardmaessig aus — auch ohne
    Tanzprogramm-Wahl. Nur show_hidden zeigt sie und setzt dazu die
    Tanzprogramm-Wahl aus.

    Mit Tanzprogramm-Wahl wirkt das Limit als FEINE Teaching-Order-Obergrenze
    (cover_max_to) INNERHALB der Baender — nicht als Band-Reduktion. So schliesst
    "Limit = Spin Chain Thru" die spaeter gelehrten Figuren desselben Bandes
    (Recycle) korrekt aus. Der Nur-Filter setzt dort die Baender UNTER dem
    obersten: angezeigt werden nur Sequenzen, die das oberste Band wirklich
    brauchen. Bei nur einem Band gibt es nichts darunter (None).

    Ohne Tanzprogramm-Wahl gilt der Alt-Pfad: Limit als max_to, Nur-Filter als
    Untergrenze min_to = Programm-Start des Limits (Ganzzahlteil der
    Teaching-Order, z.B. 50.0 bei einem A1-Limit). Ohne Limit kein Nur-Filter.
    """
    args = dict(
        entity_id_filter=contains,
        type_filter=seq_type,
        difficulty_filter=difficulty,
        tags_filter=tags,
        hide_unmapped=not show_hidden,
    )
    if show_hidden:
        bands = None
    if bands:
        below = set(bands) - {max(bands)} if only else None
        args.update(
            max_to_filter=None,
            min_to_filter=None,
            bands_filter=bands,
            bands_below_filter=below or None,
            cover_max_to=limit,
        )
    else:
        args.update(
            max_to_filter=limit,
            min_to_filter=float(int(limit)) if only and limit is not None else None,
            bands_filter=None,
            bands_below_filter=None,
            cover_max_to=None,
        )
    return args
