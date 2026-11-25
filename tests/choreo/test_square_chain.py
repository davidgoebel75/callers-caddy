"""Weitertanzen und Spiegeln (Square Flow Phase 2b, intern#247)."""
from caddy.choreo import square_chain as sc


def _square():
    """Static Square wie die Engine: Taenzer 2c = Mann von Couple c+1, 2c+1 = seine Frau.
    Couple 1 unten bei x = -3, die anderen entstehen durch Drehen um je 90 Grad."""
    couple = [[-3.0, 1.0, 0.0], [-3.0, -1.0, 0.0]]
    out = []
    for _c in range(4):
        out += couple
        couple = sc.rotate_pose(couple)
    return out


def _progressed(square):
    """Ende einer Singing-Call-Figur: Maenner zu Hause, Frau von Couple c steht beim Mann
    von Couple c+1 (Corner wird Partnerin)."""
    return [square[2 * ((i // 2 + 1) % 4) + 1] if i % 2 else square[i]
            for i in range(8)]


def test_drehen_bringt_couple1_auf_couple2():
    rot = sc.rotation_slots(_square())
    assert rot[0] == 2 and rot[1] == 3 and rot[6] == 0


def test_endplaetze_und_nicht_zu_hause():
    sq = _square()
    perm = sc.end_permutation(sq, _progressed(sq))
    assert perm == [0, 3, 2, 5, 4, 7, 6, 1]
    off = [list(p) for p in sq]
    off[0] = [0.0, 0.0, 0.0]
    assert sc.end_permutation(sq, off) is None


def test_nach_vier_figuren_wieder_beim_partner():
    sq = _square()
    perm = sc.end_permutation(sq, _progressed(sq))
    chain = sc.PartnerChain(8)
    for k in range(4):
        chain.record(k, perm)
    ids1, broken = chain.ids_for(1)
    assert not broken
    assert ids1[0] == 0 and ids1[3] == 1          # Frau 1 jetzt beim Mann von Couple 2
    assert chain.ids_for(4) == (sc.identity(8), False)


def test_gespiegelte_figur_fuehrt_die_kette_gleich_fort():
    """Die Progression ist drehsymmetrisch: gespiegelt getanzt endet sie genauso."""
    sq = _square()
    perm = sc.end_permutation(sq, _progressed(sq))
    rot = sc.rotation_slots(sq)
    assert sc.advance(sc.identity(8), perm, rot) == sc.advance(sc.identity(8), perm)


def test_gespiegelt_zeigt_die_leute_vom_gedrehten_platz():
    rot = sc.rotation_slots(_square())
    shown = sc.shown_dancers(sc.identity(8), rot)
    assert shown[0] == 2                          # Engine-Mann 1 erscheint als Mann 2


def test_gerissene_kette_beginnt_mit_eigenen_partnern():
    sq = _square()
    perm = sc.end_permutation(sq, _progressed(sq))
    chain = sc.PartnerChain(8)
    chain.record(0, perm)
    chain.record(1, None)
    assert chain.ids_for(2) == (sc.identity(8), True)
    chain.record(2, perm)
    ids, broken = chain.ids_for(3)
    assert not broken and ids != sc.identity(8)
