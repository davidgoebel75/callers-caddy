"""Suchfeld im Lokationsdialog.

Der Dialog liest die Liste ausschliesslich ueber db.get_all_locations().
Mehr braucht dieser Test nicht: kein Datenbankschema, keine Datei auf der
Platte, kein sichtbares Fenster. Deshalb laeuft er in Millisekunden und kann
Faelle pruefen, die von Hand muehsam herzustellen waeren.
"""
import pytest

from dialogs_location_program import LocationDialog
from song_db import Location


class FakeDb:
    """Nur die eine Methode, die der Dialog wirklich benutzt."""

    def __init__(self, *locations):
        self._locations = list(locations)

    def get_all_locations(self):
        return list(self._locations)


@pytest.fixture
def dlg(qapp):
    """Dialog mit vier Lokationen, alphabetisch wie aus der Datenbank.

    'Dienstagsrunde' ist eine Unter-Lokation von 'Hamburg Nord' und wird
    deshalb als "Dienstagsrunde  ->  Hamburg Nord" angezeigt.
    """
    db = FakeDb(
        Location(id=3, name="Bremen"),
        Location(id=4, name="Dienstagsrunde", shared_history_with=1),
        Location(id=1, name="Hamburg Nord"),
        Location(id=2, name="Hamburg Sued"),
    )
    return LocationDialog(db)


@pytest.fixture
def leerer_dlg(qapp):
    """Dialog ohne eine einzige Lokation — der Zustand beim allerersten Start."""
    return LocationDialog(FakeDb())


def sichtbar(dlg):
    """Die Eintraege, die der Nutzer gerade sieht."""
    lw = dlg.list_widget
    return [lw.item(i).text() for i in range(lw.count())
            if not lw.item(i).isHidden()]


def test_ohne_suchtext_sind_alle_lokationen_sichtbar(dlg):
    assert len(sichtbar(dlg)) == 4


def test_sucht_ohne_ruecksicht_auf_gross_und_kleinschreibung(dlg):
    dlg.edit_search.setText("hAmBuRg SuEd")
    assert sichtbar(dlg) == ["Hamburg Sued"]


def test_sucht_auch_mitten_im_wort(dlg):
    # "Bremen" enthaelt "eme" — eine Suche nur am Wortanfang faende das nicht.
    dlg.edit_search.setText("eme")
    assert sichtbar(dlg) == ["Bremen"]


def test_suche_nach_hauptlokation_findet_auch_ihre_unter_lokationen(dlg):
    # Gesucht wird im angezeigten Text, und der enthaelt bei einer
    # Unter-Lokation die Kennzeichnung der Hauptlokation.
    dlg.edit_search.setText("hamburg nord")
    assert len(sichtbar(dlg)) == 2
    assert sichtbar(dlg)[0].startswith("Dienstagsrunde")


def test_geleertes_suchfeld_zeigt_wieder_alles(dlg):
    # Das X im Feld macht genau das: den Text loeschen.
    dlg.edit_search.setText("bremen")
    assert len(sichtbar(dlg)) == 1
    dlg.edit_search.clear()
    assert len(sichtbar(dlg)) == 4


def test_ohne_treffer_wird_die_auswahl_aufgehoben(dlg):
    # Eine ausgeblendete Auswahl bliebe sonst aktiv: Loeschen oder Umbenennen
    # wuerden eine Lokation treffen, die der Nutzer gar nicht sieht.
    assert dlg.get_selected_location() is not None

    dlg.edit_search.setText("gibtesnicht")

    assert sichtbar(dlg) == []
    assert dlg.get_selected_location() is None
    assert not dlg.btn_ok.isEnabled()
    assert not dlg.btn_rename.isEnabled()
    assert not dlg.btn_delete.isEnabled()


def test_neu_geladene_liste_ist_ungefiltert(dlg):
    # _refresh_list laeuft nach jeder Aenderung an der Liste. Bliebe der Filter
    # stehen, koennte eine gerade angelegte Lokation versteckt sein, waehrend
    # _on_add sie selektiert — unsichtbare Auswahl mit aktivem OK-Knopf.
    dlg.edit_search.setText("bremen")
    dlg._refresh_list()
    assert dlg.edit_search.text() == ""
    assert len(sichtbar(dlg)) == 4


# ---------------------------------------------------------------------------
# Fokus beim Oeffnen
# ---------------------------------------------------------------------------
# Geprueft wird ueber dlg.focusWidget(), nicht ueber widget.hasFocus():
# hasFocus() ist zusaetzlich daran gebunden, dass das Fenster aktiv ist, und
# das ist es beim Rendern ohne Bildschirm nie. focusWidget() liefert den
# Fokus-Empfaenger des Dialogs unabhaengig davon.

def test_beim_oeffnen_liegt_der_fokus_auf_der_liste(dlg):
    # Das Suchfeld steht ueber der Liste und ist damit das erste Element im
    # Layout — ohne das setFocus() in _refresh_list bekaeme es den Fokus. Dann
    # waere die aktuelle Lokation zwar vorausgewaehlt, die Pfeiltasten wuerden
    # aber ins Suchfeld tippen statt durch die Liste zu wandern.
    assert dlg.focusWidget() is dlg.list_widget


def test_ohne_lokationen_liegt_der_fokus_auf_neu_anlegen(leerer_dlg):
    # Beim allerersten Start gibt es nichts zu durchsuchen. Sinnvoll ist nur
    # der Weg zur ersten Lokation.
    assert leerer_dlg.focusWidget() is leerer_dlg.btn_add
