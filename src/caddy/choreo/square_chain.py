"""Weitertanzen ueber die Figuren und Heads/Sides-Spiegeln (Square Flow Phase 2b, intern#247).

Qt-frei. Beides ist eine reine Umrechnung der Anzeige, die Engine rechnet nichts Neues:

- Weitertanzen: Eine gueltige Singing-Call-Figur endet in der Ausgangsstellung, nur steht
  jeder Mann mit einer anderen Frau da. Aus Anfangs- und Endbild der Animation ergibt sich,
  wer auf welchem Platz landet. Die naechste Figur beginnt mit diesen Leuten auf den Plaetzen;
  nach vier Figuren ist jeder wieder beim eigenen Partner.
- Spiegeln: "Sides ..." ist dasselbe Bild wie "Heads ...", um 90 Grad gedreht. Gedreht wird
  so, dass der Platz von Couple 1 auf den von Couple 2 kommt.

Plaetze = Startplaetze der Engine-Taenzer (Taenzer i beginnt auf Platz i). Eine Belegung
(ids) sagt je Platz, welcher Taenzer dort steht (Index in die Taenzerliste der Engine).
"""
import math

QT_FREE = True

# So nah muss ein Taenzer am Ende einem Startplatz sein, damit er als "zu Hause" gilt.
HOME_TOLERANCE = 0.6


def rotate_pose(pose):
    """Stellung um 90 Grad drehen (Heads -> Sides): (x, y) -> (-y, x), Blick +90 Grad."""
    return [[-y, x, (a + 90.0) % 360.0] for x, y, a in pose]


def _nearest(slots, x, y):
    best, dist = None, None
    for j, (sx, sy, _a) in enumerate(slots):
        d = math.hypot(sx - x, sy - y)
        if dist is None or d < dist:
            best, dist = j, d
    return best, dist


def slot_map(slots, pose):
    """Platz je Taenzer in pose (naechster Startplatz), None wenn nicht jeder eindeutig auf
    einem Platz steht."""
    out = []
    for x, y, _a in pose:
        j, d = _nearest(slots, x, y)
        if j is None or d > HOME_TOLERANCE:
            return None
        out.append(j)
    return out if len(set(out)) == len(slots) else None


def rotation_slots(slots):
    """Platz, auf den jeder Startplatz beim Spiegeln kommt."""
    return slot_map(slots, rotate_pose(slots))


def end_permutation(start_pose, end_pose):
    """Platz am Figurenende je Taenzer (Taenzer i beginnt auf Platz i), None wenn die Figur
    nicht in der Ausgangsstellung endet."""
    if not start_pose or len(start_pose) != len(end_pose):
        return None
    return slot_map(start_pose, end_pose)


def identity(n):
    return tuple(range(n))


def advance(ids, perm, rot=None):
    """Belegung nach einer Figur. perm = end_permutation der getanzten Figur (Engine-Plaetze),
    rot = rotation_slots, wenn die Figur gespiegelt getanzt wurde."""
    phys = rot or list(range(len(ids)))
    new = list(ids)
    for i, j in enumerate(perm):
        new[phys[j]] = ids[phys[i]]
    return tuple(new)


def shown_dancers(ids, rot=None):
    """Je Engine-Taenzer i: welcher Taenzer (Index) dort gezeichnet wird."""
    phys = rot or list(range(len(ids)))
    return [ids[phys[i]] for i in range(len(ids))]


class PartnerChain:
    """Belegung je Figuren-Teil, Teil fuer Teil fortgeschrieben.

    record(k, perm, rot) haelt fest, wie Teil k geendet hat (perm None = nicht zu Hause,
    Kette reisst: der naechste Teil beginnt wieder mit den eigenen Partnern)."""

    def __init__(self, n):
        self.n = n
        self._ends = {}

    def reset(self):
        self._ends.clear()

    def record(self, part, perm, rot=None):
        self._ends[part] = (perm, rot)

    def ids_for(self, part):
        """(Belegung zu Beginn von Teil part, Kette gerissen?)."""
        ids, broken = identity(self.n), False
        for k in range(max(0, part)):
            end = self._ends.get(k)
            if end is None or end[0] is None:
                ids, broken = identity(self.n), True
                continue
            ids = advance(ids, end[0], end[1])
            broken = False
        return ids, broken
