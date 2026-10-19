"""Regel-Bausteine rund um den aktuellen Song, ohne Qt (intern#218).

Die Bedingungen bekommen die Genre-Namen des Songs erst beim Auswerten
(main.py fragt die DB nur, wenn eine Regel sie wirklich braucht).
Dazu die Parameter-Auswertung der Aktion "Set Loop Active", die mit dem
Genre-Filter zusammen gedacht ist ("Genre Is ..." -> Loop aus).
"""
QT_FREE = True

LOOP_ON = "on"
LOOP_OFF = "off"


def genre_is(genres, params) -> bool:
    """Hat der Song das gewaehlte Genre? Gross/Klein egal; ohne Genre-Wahl nie.

    genres: Genre-Namen des Songs, None = kein Song geladen.
    """
    wanted = (params.get("genre_name") or "").strip().casefold()
    return bool(wanted) and wanted in {(g or "").strip().casefold()
                                       for g in genres or ()}


def genre_is_not(genres, params) -> bool:
    """Gegenstueck zu genre_is; wahr auch fuer Songs ohne Genre.

    Ohne geladenen Song (genres None, z. B. bei "App Started") falsch: dann
    gibt es keinen Song, ueber dessen Genre die Regel etwas sagen koennte.
    """
    if genres is None or not (params.get("genre_name") or "").strip():
        return False
    return not genre_is(genres, params)


def loop_active_wanted(params) -> bool:
    """"Set Loop Active": True fuer on, False fuer off."""
    return (params.get("state") or LOOP_ON).strip().lower() != LOOP_OFF
