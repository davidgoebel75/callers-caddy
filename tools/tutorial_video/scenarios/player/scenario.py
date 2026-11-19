"""Tutorial player: Song aus der Song List laden und im Player abspielen.

Urspruenglich aus PR #171, jetzt zweisprachig. Begriffe nach
GLOSSARY.md und den Beschriftungen der App: Song List / Songliste, Patter,
Tip, Loop-In/Loop-Out, Today's Tempo / Heutiges Tempo (gilt fuer die
Tanzveranstaltung), Fade Out, Audition.

Je Schritt: say = Sprechtext je Sprache, point = Element fuer Rahmen und
Mauszeiger (Pfad wie in den Touren, optional mit Zeile), do = Bedienung nach
dem Satz, hold = Sekunden danach stehen lassen, zoom = Element, auf das das
Bild ab diesem Schritt zoomt (None = wieder ganzes Fenster). SETUP laeuft vor
der Aufnahme. Braucht den Song "Electro Blues" (YRR 049) in der Song List.

LAYOUT = Layout-Datei aus skins/ ohne ".ini" (in der App: Layout speichern),
SKIN = Farbtheme, also ein Ordner in skins/. None nimmt jeweils, was in der
App gerade eingestellt ist; dann bleibt auch gespeichert, was SETUP am Layout
aendert.
"""

LAYOUT = None
SKIN = "win11"
SONGS = "song_list.table"
SEARCH = "song_list._filter_bar.edit_search"
# Nur Songs von YRR-Labels zeigen: Open Source, keine Urheberrechtsprobleme.
SONG_QUERY = "YRR 049"   # Electro Blues, mit Loop-Marken


def SETUP(a):
    a.hide_dock("dock_notes")


STEPS = [
    dict(say={
        "en": "Welcome to Callers Caddy. In this video, you load a song into "
              "the player and play it.",
        "de": "Willkommen bei Callers Caddy. In diesem Video holst du einen Song "
              "in den Player und spielst ihn ab.",
    }),
    dict(say={
        "en": "All your songs are in the song list.",
        "de": "Alle deine Songs stehen in der Songliste.",
    },
         point=SONGS),
    dict(say={
        "en": "To find a song quickly, type part of its title or its label into "
              "the search field.",
        "de": "Um einen Song schnell zu finden, tippst du einen Teil des Titels "
              "oder das Label ins Suchfeld.",
    },
         point=SEARCH,
         do=lambda a: a.type_text(SEARCH, SONG_QUERY),
         hold=2),
    dict(say={
        "en": "A single click on a song loads it into the player.",
        "de": "Ein einfacher Klick auf einen Song lädt ihn in den Player.",
    },
         point=(SONGS, 0),
         do=lambda a: a.click(SONGS, 0),
         hold=1.5),
    dict(say={
        "en": "The player now shows the title and length. The song is loaded, "
              "but not playing yet.",
        "de": "Der Player zeigt jetzt Titel und Dauer. Der Song ist geladen, "
              "läuft aber noch nicht.",
    },
         point="player",
         zoom="player"),
    dict(say={
        "en": "The two marks on the position bar are the loop markers: Loop-In "
              "and Loop-Out. When the loop is on, playback jumps from Loop-Out "
              "back to Loop-In. That way a patter keeps running until your tip "
              "is over.",
        "de": "Die zwei Striche auf dem Positionsbalken sind die Loop-Marken: "
              "Loop-In und Loop-Out. Ist der Loop eingeschaltet, springt die "
              "Wiedergabe am Loop-Out zurück zum Loop-In. So läuft ein Patter "
              "weiter, bis dein Tip zu Ende ist.",
    },
         point="player.slider_position"),
    dict(say={
        "en": "There are two buttons for playback. Play sends the song to the "
              "main output, for the dancers.",
        "de": "Zum Abspielen gibt es zwei Knöpfe. Play spielt den Song über "
              "den Hauptausgang, also für die Tänzer.",
    },
         point="player.btn_play"),
    dict(say={
        "en": "Audition is for previewing: the song plays on the secondary "
              "output, usually headphones or the built-in speaker, and nothing "
              "is added to the history.",
        "de": "Audition ist zum Vorhören: Der Song läuft über den sekundären "
              "Ausgang, meist Kopfhörer oder der interne Lautsprecher, und es "
              "entsteht kein Eintrag in der Historie.",
    },
         point="player.btn_audition"),
    dict(say={
        "en": "Click Play to start playback.",
        "de": "Mit Play startest du die Wiedergabe.",
    },
         point="player.btn_play",
         do=lambda a: a.click("player.btn_play"),
         hold=5),
    dict(say={
        "en": "Even faster: a double-click in the song list loads the song and "
              "starts it right away.",
        "de": "Noch schneller geht es mit einem Doppelklick in der Songliste: "
              "Er lädt den Song und startet ihn sofort.",
    },
         point=(SONGS, 0)),
    dict(say={
        "en": "If the music feels too slow today, raise today's tempo. It "
              "applies only to this dance event and is not saved with the song.",
        "de": "Ist dir die Musik heute zu langsam, stellst du sie mit dem "
              "heutigen Tempo nach. Der Wert gilt nur für diese "
              "Tanzveranstaltung und wird nicht am Song gespeichert.",
    },
         point="player.spin_today_tempo",
         do=lambda a: a.keys("player.spin_today_tempo", "Up", 4),
         hold=3),
    dict(say={
        "en": "Look at the BPM display: it shows the new speed right away.",
        "de": "Schau auf die BPM-Anzeige: Sie zeigt das neue Tempo sofort an.",
    },
         point="player.label_bpm",
         hold=2),
    dict(say={
        "en": "At the end of a tip, Fade Out gently fades the song out.",
        "de": "Am Ende eines Tips blendest du den Song mit Fade Out sanft aus.",
    },
         point="player.btn_fade",
         do=lambda a: a.click("player.btn_fade"),
         hold=6),
    dict(say={
        "en": "That's the way from song to music: click a song, press Play, done.",
        "de": "Das war der Weg vom Song zur Musik: anklicken, Play drücken, fertig.",
    },
         zoom=None),
]
