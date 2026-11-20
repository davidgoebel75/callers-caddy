# Callers Caddy

Werkzeug fuer Square-Dance-Caller: Songs, Sequenzen und Tanzveranstaltungen
verwalten und live abspielen.

## Language

### Rollen und Veranstaltung

**Caller**:
Der Nutzer des Programms. Waehlt die Musik, ruft die Figuren und plant die
Veranstaltung.
_Avoid_: Anwender, User

**Lokation**:
Dauerhafter Kontext, in dem der Caller auftritt — ein Club oder ein wiederkehrender
Veranstaltungsort. Bestimmt Historie, Empfehlungen, Notizen und Tanzprogramm-Wahl.
_EN_: Location
_Avoid_: Club, Verein, Kontext

**Special**:
Einzelveranstaltung mit eigenem Termin, im Gegensatz zum regelmaessigen Clubabend.

**Tanzveranstaltung**:
Ein Auftritt an einer Lokation, von der ersten bis zur letzten Musik. Allgemeiner
Oberbegriff — eine Veranstaltung ist nicht zwingend abends.
_EN_: Dance-Event
_Avoid_: Tanzabend, Clubabend, Session, Gig

**Aktuelle Sitzung**:
Was gerade im Programm gilt, vom Start bis zum Beenden: aktueller Song,
aktuelle Lokation und Tanzprogramm-Wahl. Nicht die Tanzveranstaltung selbst.
_EN_: Current Session
_Avoid_: Zustand, State, Kontext

**Tip**:
Tanzeinheit aus einem Patter und einem Singing Call, typisch rund 15 Minuten.
_Avoid_: Runde, Tanzblock

**Block**:
Folge von drei bis fuenf Tips zwischen zwei Pausen.

**ERR (Emotional Response Rate)**:
Bewertung 1 bis 4, wie stark ein Song die Taenzer emotional mitnimmt
(1 = Hoehepunkt, 2 = Vorbereitung, 3 = Baseline, 4 = Beruhigung; 0 = nicht bewertet).

**Class**:
Anfaengerkurs ueber mehrere Abende, in dem die Figuren eines Programms in
Teaching-Order beigebracht werden.

**Square**:
Die acht Taenzer eines Sets, aufgestellt als vier Paare (Couple 1 bis 4).

### Songs und Wiedergabe

**Patter**:
Song ohne gesungene Choreografie, zu dem der Caller frei ruft. Laeuft per Loop,
bis der Tip endet. "to patter" heisst plappern — daher ohne "-n" am Ende.
_Avoid_: Pattern (englisch "Muster", fachlich falsch; bleibt nur als interner
Code-Bezeichner und als Programmierbegriff stehen), Hoedown, Rhythmus-Song

**Singing Call**:
Song mit fest gesungener Choreografie. Jeder Song kann beides sein — Patter oder
Singing Call —, die Nutzungsart ergibt sich aus dem Playlist-Eintrag.
_Avoid_: Singer

**Other** (deutsch "Sonstiges"):
Song, der weder Patter noch Singing Call ist, etwa Friendship Ring oder Happy
Birthday. Wird nicht in Tips eingeplant.
_Avoid_: Round Dance als eigener Typ, "ohne Typ"

**Abspielart**:
Wie ein Playlist-Eintrag laeuft: endlos loopen (mit Patter-Fuellung) oder einmal
durchspielen. Folgt beim Einfuegen dem Song-Typ — Other und Songs ohne
Loop-Punkte spielen einmal durch, ausser reine Patter — und laesst sich im
Loop-Dialog umstellen.
_EN_: Play Mode
_Avoid_: Modus, P/S (meint mal den Song-Typ, mal die Abspielart)

**Body**:
Der gesungene Kern eines Singing Calls: sieben Abschnitte à 64 Beats. Intro und
Outro liegen davor und danach.

**Abschnitt**:
Einer der sieben Teile eines Body — Opener, vier Figures, Middle Break, Closer.
_EN_: Section
_Avoid_: Teil, Siebtel

**Label**:
Plattenlabel eines Square-Dance-Songs (z. B. ESP, Global). Zusammen mit der
Plattennummer identifiziert es die Aufnahme — u. a. fuer Cue-Sheet-Suche und
GEMA-Musikfolgeliste.

**Song-Katalog**:
Mitgelieferte Liste veroeffentlichter Square-Dance-Songs mit Titel, Label und
Plattennummer. Referenz beim Import, damit Titel und Label einheitlich sind.
_EN_: Song Catalog
_Avoid_: Katalog (allein, meint den Figurenkatalog), music_extended_data

**Empfehlungs-Score**:
Qualitaet des Songs mal Tage seit zuletzt gespielt; nie gespielte Songs zaehlen ab
dem Erstaufnahme-Datum. Je hoeher, desto eher kommt der Song wieder dran.
_EN_: Recommendation score

**Cue Sheet**:
Fremdes Blatt zu einem Singing Call: Songtext plus die gesungene Choreografie.
Wird als Lyrics-Datei beim Song abgelegt.

**Lyrics**:
Die dem Song zugeordnete Textdatei im Programm, egal woher sie stammt.
_Avoid_: Songtext (mehrdeutig: meint mal die Datei, mal den Text darin)

**Textsprung**:
Moment, in dem der Auto-Scroll der Lyrics an einem SyncPoint die naechste
Sprungmarke erreicht. "Textsprung timen" verschiebt ihn um ganze Sekunden.
_EN_: Text Jump

**Texttausch**:
Moment, in dem Dynamic Lyrics an einer Figure-Grenze die eingeblendete Sequenz
wechselt oder Heads und Sides tauscht. "Texttausch timen" verschiebt ihn um ganze
Sekunden.
_EN_: Text Swap

**Leseposition**:
Hoehe im Lyric-Fenster, auf der der gerade gesungene Text steht, in Prozent von
oben (0 % = ganz oben, 100 % = ganz unten). Gilt mit und ohne SyncPoints.
_EN_: Reading Position
_Avoid_: Lese-Zone, Viewport-Anteil

**Lesebalken**:
Farbig hinterlegter Bereich im Lyric-Fenster ueber dem Text, der gerade zu singen
ist. Folgt dem gesungenen Text, auch wenn "Textsprung timen" frueher scrollt.
_EN_: Reading Band
_Avoid_: Band, Leseband

**In-Lesebalken Countdown**:
Zahl am rechten Rand des Lesebalkens, die die Beats bis zum naechsten
Abschnittswechsel herunterzaehlt (Opener, Figure, Middle Break, Closer). Braucht
SyncPoints und einen BPM-Wert des Songs.
_EN_: In-band countdown

**Loop**:
Der Ausschnitt zwischen Loop-In und Loop-Out, den ein Patter beliebig oft
wiederholt, damit der Song so lange laeuft wie der Tip.

**Suchfenster**:
Die beiden Bereiche, in denen der Loop Finder nach Loop-In und Loop-Out sucht.
Angabe in Prozent der Songdauer oder als Zeit: Loop-In ab Songbeginn, Loop-Out
vor Songende. Passen die Fenster nicht zur Songlaenge, wird nicht gesucht.
_EN_: Search Window

**Pausen-Uhr**:
Countdown fuer die Pause zwischen zwei Tips, auf Wunsch mit Wartemusik.
_EN_: Break Clock

**Uhr**:
Widget mit der aktuellen Uhrzeit als Digitaluhr. Nicht verwechseln mit der
Pausen-Uhr, die rueckwaerts zaehlt.
_EN_: Clock

**Wartemusik**:
Song, der waehrend der Pausen-Uhr laeuft (der zuletzt gespielte). Zaehlt nicht
als gespielt und schaltet die Playlist nicht weiter.
_EN_: Break Music

**Abgebrochene Pause**:
Pause, die vor Ablauf der Pausen-Uhr endet. Anders als eine abgelaufene Pause
loest sie kein "Break Finished" aus.
_EN_: Cancelled Break

**Heutiges Tempo**:
Tempo-Faktor fuer die laufende Tanzveranstaltung. Wirkt zusaetzlich auf jeden
Song und wird nicht am Song gespeichert — im Gegensatz zum Song-Tempo.
_EN_: Today's Tempo
_Avoid_: Session-Tempo, Global-Tempo

**Massenlauf**:
Eine Pruefung oder Reparatur im Potential-Widget, die viele Songs nacheinander
bearbeitet (z. B. BPM ermitteln, Loops suchen). Ab einer gewissen Menge erst ein
Probelauf mit wenigen Songs zur Zeitschaetzung; abbrechen laesst Bearbeitetes stehen.
_EN_: Bulk Run
_Avoid_: Batch-Lauf, Bulk-Job

### Figuren und Programme

**Programm**:
Offizielle Stufe des Square-Dance-Figurenkatalogs (Basic, Mainstream, Plus, A1, A2, C1 …).
_EN_: Program
_Avoid_: Level, Stufe

**Programm-Reihe**:
Satz aufeinander aufbauender Programme, der als Einheit gewaehlt wird — die alte
Reihe (Basic, Mainstream, Plus, A1) und die 2026er-Reihe. Waehlt man ein hoeheres
Programm, gehoeren die tieferen derselben Reihe dazu.
_EN_: Program Line
_Avoid_: Band (nur die interne Nummer), Familie

**Tanzprogramm-Wahl**:
Die Programme, die eine Lokation tatsaechlich tanzt. Begrenzt zusammen mit dem
Limit, welche Sequenzen angezeigt werden.
_EN_: Dance Program Selection
_Avoid_: Programmfilter

**Figur**:
Eine im offiziellen Katalog definierte Tanzbewegung mit festem Namen, z. B. "Swing Thru".
Gehoert zu mindestens einem Programm.
_EN_: Figure
_Avoid_: Entity

**Konzept**:
Eintrag des Katalogs, der eine andere Figur abwandelt statt selbst getanzt zu werden,
z. B. "All 8 Concept" in "All 8 Right & Left Thru". Zaehlt beim Limit wie eine Figur.
_EN_: Concept

**Fuellwoerter**:
Zuordnungsziel fuer Call-Texte, die keine Figur sind, z. B. "Back Away", "Join Hands",
"Boys go Right". Steht vor allen Programmen und schliesst keine Sequenz aus der
Tanzprogramm-Wahl aus.
_EN_: Filler Words
_Avoid_: Noise, Stoppwort

**Teaching-Order**:
Offizielle Reihenfolge, in der die Figuren eines Programms beigebracht werden.
_EN_: Teaching Order

**Programm-Grenze**:
Uebergang zwischen zwei Programmen in der Teaching-Order, z. B. nach der letzten
Plus-Figur und vor der ersten A1-Figur.
_EN_: Program Boundary

**(Anything)-Figur**:
Figur mit dem Platzhalter "(Anything)", in den eine beliebige andere Figur eingesetzt
wird, z. B. "(Anything) & Roll". Gibt es ab Plus.
_EN_: (Anything) Figure
_Avoid_: (Anything)-Vorlage, Vorlage

**(Named Dancers)-Figur**:
Figur mit dem Platzhalter "(Named Dancers)", fuer den der Caller eine beliebige Gruppe
von Taenzern nennt, z. B. "Heads Circulate" oder "Boys Cross". Eine Figur, die eine
Gruppe fest im Namen traegt, z. B. "All Eight Circulate", ist eine eigene Figur.
_EN_: (Named Dancers) Figure

### Sequenzen

**Sequenz**:
Geordnete Folge von Call-Texten, die zusammen eine Choreografie ergeben.
_EN_: Sequence

**Call-Text**:
Eine Zeile einer Sequenz, so wie der Caller sie ruft, z. B. "Heads Chase Right and Roll".
Kann mehrere Figuren enthalten.
_EN_: Call Text
_Avoid_: Feld

**Call**:
Das, was der Caller ruft. In Texten fuer den Nutzer (Menues, Changelog) der kurze
Name fuer einen Call-Text, z. B. "Call-Mapping fuer diesen Call aendern". Kommt es
auf den Unterschied an, heisst es weiter Call-Text (die Zeile) oder Figur (der
Katalog-Eintrag).
_EN_: Call

**Zusammengesetzter Call-Text**:
Call-Text, der erkennbar mehrere Figuren enthaelt, z. B. "All 8 Right & Left Thru"
oder "Tag The Line, Face In".
_EN_: Composite Call Text

**Zuordnung**:
Verknuepfung eines Call-Texts mit einer Menge gleichrangiger Figuren (eine oder
mehrere), z. B. "Chase Right and Roll" mit {Chase Right, (Anything) & Roll}.
_EN_: Assignment
_Avoid_: Mapping

**Figuren-Menge**:
Die Figuren einer Zuordnung. Alle sind gleichrangig: jede muss unter dem Limit
liegen, damit die Sequenz erscheint.
_EN_: Figure Set
_Avoid_: Tags, Figurenliste

**Mengen-Vorschlag**:
Automatisch erkannte Figuren-Menge fuer einen zusammengesetzten Call-Text. Ist nur
ein Vorschlag — er wird markiert und erst nach Bestaetigung des Callers zur Zuordnung.
_EN_: Figure Set Suggestion
_Avoid_: Automapping, Mustererkennung

**Zuordnungs-Datei**:
JSON-Datei, mit der Caller ihre Zuordnungen exportieren und bei anderen importieren
(Menue „Zuordnungen exportieren/importieren“). Weicht eine importierte Figuren-Menge
von der lokalen ab, klaert der Caller je Call-Text: A lokal behalten, B aus der Datei
uebernehmen, C selbst waehlen.
_EN_: Mapping File
_Avoid_: Call-Map, Mapping (im Deutschen)

**Optimieren**:
Aktion im Call-Mapping, die alle abweichenden Mengen-Vorschlaege auf einen Schlag
uebernimmt, nach Rueckfrage je Art der Abweichung. Ergebnis sind abgeleitete Zuordnungen.
_EN_: Optimize

**Abgeleitete Zuordnung**:
Zuordnung, die aus einem Mengen-Vorschlag gesammelt uebernommen wurde, statt vom
Caller einzeln bestaetigt. Bleibt von automatischen und von Hand gesetzten
Zuordnungen unterscheidbar.
_EN_: Inferred Assignment

**Teilung**:
Zerlegen eines zusammengesetzten Call-Texts in zwei eigenstaendige Call-Texte.
Alternative zur Figuren-Menge, der Caller entscheidet je Call-Text.
_EN_: Split

**Limit**:
Figur in der Teaching-Order, bis zu der eine Sequenz tanzbar sein muss, um angezeigt
zu werden. Eine Sequenz liegt darunter, wenn jede Figur jeder ihrer Zuordnungen darunter liegt.
_Synonym_: Figuren-Grenze
_Avoid_: Grenze (allein), Programm-Grenze (ist etwas anderes)

**Nur-Filter**:
Zeigt nur Sequenzen, die das oberste gewaehlte Programm wirklich brauchen, also mit
den tieferen Programmen der Tanzprogramm-Wahl allein nicht tanzbar sind. Ohne
Tanzprogramm-Wahl gilt das Programm des Limits.
_EN_: Only Filter

**Ausgeblendete Sequenz**:
Sequenz, die nur wegen fehlender Zuordnungen ihrer Call-Texte nicht in der Liste
erscheint, typischerweise frisch importiert. "Auch ausgeblendete Sequenzen anzeigen"
holt sie zurueck, ohne Typ, Schwierigkeit oder Tags anzutasten.
_EN_: Hidden Sequence
_Avoid_: Neueste Sequenz, versteckte Sequenz

**Square Flow**:
Fenster, das die Sequenz aus dem Sequenz-Detail als tanzenden Square zeigt und
pruefen kann, ob sie korrekt aufloest. Optional, nur nach Freigabe in den Einstellungen.
_EN_: Square Flow
_Avoid_: Mitlaufender Square, Square-Ansicht

### Regeln

**Regel**:
Automatik nach dem Muster Ausloeser, Bedingung, Aktion, die bei einem Ereignis im
Programm selbst etwas ausfuehrt, etwa beim Song-Start oder per Stream-Deck-Taste.
_EN_: Rule

**System-Regel**:
Regel, die mit dem Programm ausgeliefert wird. Der Caller kann sie nur ein- und
ausschalten und einer Taste zuordnen, nicht aendern oder loeschen.
_EN_: System Rule

**Eigene Regel**:
Regel, die der Caller selbst anlegt, aendert, loescht oder importiert.
_EN_: Custom Rule
_Avoid_: User-Regel, Benutzerregel

### Oberflaeche

**Widget**:
Teilfenster des Hauptfensters (z. B. Uhr, Potential, Lyrics), das sich ueber das
Menue Ansicht ein- und ausblenden, verschieben und als loses Fenster herausziehen laesst.
_EN_: Widget
_Avoid_: Dock, Panel (Dock bleibt nur als interner Code-Bezeichner stehen)
