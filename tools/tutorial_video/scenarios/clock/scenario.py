"""Tutorial clock: das Widget "Clock" / "Uhr" (intern#235) vorstellen.

Begriffe nach GLOSSARY.md: Widget (nicht Dock), Tanzveranstaltung /
Dance-Event (nicht Tanzabend), Caller. Sprechtext je Sprache als dict.

Die Uhr ist (noch) nicht in der TutorialEngine registriert; SETUP holt das
von aussen nach, App-Code bleibt unveraendert. Die Optionen werden ueber das
echte Kontextmenue geschaltet (Stage.context_menu), eingeblendet wird sie
ueber das Menue View (Stage.open_menu).
"""

LAYOUT = None
SKIN = "win11"
CLOCK = "clock"


def _key(name):
    # Erst zur Laufzeit: beim Laden des Drehbuchs liegt src/ noch nicht im Pfad.
    from caddy.clock import clock_widget
    return getattr(clock_widget, name)


def SETUP(a):
    win = a.win
    win.tutorial_engine.register_widget(CLOCK, win.clock_widget)
    clock = win.clock_widget
    # Ausgangslage: nur Stunden und Minuten
    clock._set_option("_show_seconds", _key("_KEY_SECONDS"), False)
    clock._set_option("_show_date", _key("_KEY_DATE"), False)
    clock._set_option("_twelve_hour", _key("_KEY_12H"), False)
    win.dock_clock.hide()   # wird im Video ueber das Menue View eingeblendet


STEPS = [
    dict(say={
        "en": "Callers Caddy now has a clock. It keeps the time in view during "
              "your dance event, so you never have to reach for your phone.",
        "de": "Callers Caddy hat jetzt eine Uhr. So behältst du während der "
              "Tanzveranstaltung die Zeit im Blick, ohne aufs Handy zu schauen.",
    }),
    dict(say={
        "en": "You find it in the View menu. Click Clock to show it.",
        "de": "Du findest sie im Menü Ansicht. Ein Klick auf Uhr blendet sie ein.",
    },
         do=lambda a: a.open_menu("menu_view", "dock_clock"),
         hold=5),
    dict(say={
        "en": "Like every widget, you can dock the clock or place it anywhere "
              "on your screen.",
        "de": "Wie jedes Widget kannst du die Uhr andocken oder frei auf den "
              "Bildschirm legen.",
    },
         point=CLOCK,
         zoom=CLOCK),
    dict(say={
        "en": "The digits grow with the widget: make it larger, and the time "
              "gets larger too.",
        "de": "Die Ziffern wachsen mit: Machst du das Widget größer, wird auch "
              "die Uhrzeit größer.",
    },
         point=CLOCK),
    dict(say={
        "en": "Right-click the clock to open its menu. Here you turn on the seconds.",
        "de": "Mit einem Rechtsklick auf die Uhr öffnest du ihr Menü. Hier "
              "schaltest du die Sekunden ein.",
    },
         point=CLOCK,
         do=lambda a: a.context_menu(CLOCK, "clock_menu_seconds"),
         hold=4),
    dict(say={
        "en": "The same way, you add the date below the time.",
        "de": "Genauso blendest du das Datum darunter ein.",
    },
         point=CLOCK,
         do=lambda a: a.context_menu(CLOCK, "clock_menu_date"),
         hold=4),
    dict(say={
        "en": "And if you prefer, switch to the twelve-hour format with AM and PM.",
        "de": "Und wer es gewohnt ist, stellt auf zwölf Stunden mit AM und PM um.",
    },
         point=CLOCK,
         do=lambda a: a.context_menu(CLOCK, "clock_menu_12h"),
         hold=4),
    dict(say={
        "en": "Callers Caddy remembers your choice for the next start.",
        "de": "Deine Auswahl merkt sich Callers Caddy für den nächsten Start.",
    },
         zoom=None),
]
