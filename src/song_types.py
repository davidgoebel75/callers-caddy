"""Song-Typen an einer Stelle (intern#170).

Ein Song traegt zwei Schalter, is_pattern und is_singing. Daraus ergeben sich
drei Typen: Patter, Singing Call und Other. "Other" ist kein dritter Schalter,
sondern der Zustand "weder Patter noch Singing" — ein Sammelbecken fuer alles,
wozu nicht getanzt wird (Friendship Ring, Happy Birthday). Ein Song kann
Patter und Singing Call zugleich sein, aber nicht Other und etwas anderes.

Ohne Qt und ohne DB, damit Oberflaeche, Regeln und Abfragen dieselbe
Definition benutzen.
"""

# Schluessel wie in Statistik und Regeln. "pattern" ist der historische
# interne Name fuer Patter (siehe GLOSSARY.md).
PATTER = "pattern"
SINGING = "singing"
OTHER = "other"

# WHERE-Bedingung je Typ fuer Abfragen auf songs (Alias s).
SQL_FILTER = {
    PATTER: "s.is_pattern = 1",
    SINGING: "s.is_singing = 1",
    OTHER: "s.is_pattern = 0 AND s.is_singing = 0",
}


def is_other(is_pattern, is_singing) -> bool:
    return not is_pattern and not is_singing


def matches(is_pattern, is_singing, type_key) -> bool:
    """True, wenn ein Song mit diesen Schaltern zum Typ gehoert. Ein Song mit
    beiden Schaltern gehoert zu Patter und zu Singing."""
    if type_key == PATTER:
        return bool(is_pattern)
    if type_key == SINGING:
        return bool(is_singing)
    if type_key == OTHER:
        return is_other(is_pattern, is_singing)
    raise ValueError(f"unbekannter Song-Typ: {type_key!r}")


def type_tag(is_pattern, is_singing) -> str:
    """Kuerzel fuer Listen: P = Patter, S = Singing, PS = beides, O = Other."""
    if is_pattern and is_singing:
        return "PS"
    if is_pattern:
        return "P"
    if is_singing:
        return "S"
    return "O"
