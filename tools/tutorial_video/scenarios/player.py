"""Szenario: Song aus der Songliste laden und im Player abspielen.

Je Schritt: say = Sprechtext, point = Element fuer Rahmen und Mauszeiger
(Pfad wie in den Touren, optional mit Zeile), do = Bedienung nach dem Satz,
hold = Sekunden danach stehen lassen, zoom = Element, auf das das Bild ab
diesem Schritt zoomt (None = wieder ganzes Fenster). SETUP laeuft vor der
Aufnahme. Braucht mindestens einen Song in der Songliste.

LAYOUT = Layout-Datei aus skins/ ohne ".ini" (in der App: Layout speichern),
SKIN = Farbtheme, also ein Ordner in skins/. None nimmt jeweils, was in der
App gerade eingestellt ist; dann bleibt auch gespeichert, was SETUP am Layout
aendert.
"""

LAYOUT = None
SKIN = "Win11"
SONGS = "song_list.table"


def SETUP(a):
    a.hide_dock("dock_notes")


STEPS = [
    dict(say="Willkommen bei Callers Caddy. In diesem Video holst du einen Song "
             "in den Player und spielst ihn ab."),
    dict(say="Alle deine Songs stehen in der Songliste.",
         point=SONGS),
    dict(say="Ein einfacher Klick auf einen Song lädt ihn in den Player.",
         point=(SONGS, 0),
         do=lambda a: a.click(SONGS, 0),
         hold=1.5),
    dict(say="Der Player zeigt jetzt Titel und Dauer. Der Song ist geladen, "
             "läuft aber noch nicht.",
         point="player",
         zoom="player"),
    dict(say="Die zwei Striche auf dem Positionsbalken sind die Loop-Marken: "
             "Loop-In und Loop-Out. Ist der Loop eingeschaltet, springt die "
             "Wiedergabe am Loop-Out zurück zum Loop-In. So läuft ein "
             "Patter-Song weiter, bis dein Tip zu Ende ist.",
         point="player.slider_position"),
    dict(say="Zum Abspielen gibt es zwei Knöpfe. Play spielt den Song über "
             "den Hauptausgang, also für die Tänzer.",
         point="player.btn_play"),
    dict(say="Audition ist zum Vorhören: Der Song läuft über den sekundären "
             "Ausgang, meist Kopfhörer oder der interne Lautsprecher, und es "
             "entsteht kein Eintrag in der Historie.",
         point="player.btn_audition"),
    dict(say="Mit Play startest du die Wiedergabe.",
         point="player.btn_play",
         do=lambda a: a.click("player.btn_play"),
         hold=5),
    dict(say="Noch schneller geht es mit einem Doppelklick in der Songliste: "
             "Er lädt den Song und startet ihn sofort.",
         point=(SONGS, 0)),
    dict(say="Ist dir die Musik heute zu langsam, stellst du sie mit dem "
             "heutigen Tempo nach. Der Wert gilt nur für heute und wird nicht "
             "am Song gespeichert.",
         point="player.spin_today_tempo",
         do=lambda a: a.keys("player.spin_today_tempo", "Up", 4),
         hold=5),
    dict(say="Am Ende eines Tips blendest du den Song mit Fade Out sanft aus.",
         point="player.btn_fade",
         do=lambda a: a.click("player.btn_fade"),
         hold=6),
    dict(say="Das war der Weg vom Song zur Musik: anklicken, Play drücken, fertig.",
         zoom=None),
]
