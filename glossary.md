# Glossary: Esports Manager 2026 (Hebrew)

A management sim for a Counter-Strike-style esports club (CS2 terms, maps, transfers, sponsors, emails from
staff and media). Tone: modern, sporty Hebrew, like an Israeli esports/gaming site. UI labels short.
Address the player (the manager) in masculine singular unless a gender choice is available.

## Esports / CS terms

| English | Hebrew |
|---|---|
| esports | ספורט אלקטרוני (אי-ספורט in casual lines) |
| club / organization / team | מועדון / ארגון / קבוצה |
| roster / lineup | סגל / הרכב |
| player / coach / analyst / manager / CEO | שחקן / מאמן / אנליסט / מנהל / מנכ"ל |
| match / series / Best of 3 | משחק / סדרה / הטוב מ-3 |
| map / map veto / pick / ban | מפה / וטו מפות / בחירה / פסילה (PICK = בחר, BAN = פסול) |
| round / half / overtime | סיבוב / מחצית / הארכה |
| T side / CT side | צד T / צד CT (keep T/CT) |
| kill / death / assist / K/D / ADR / rating | הריגה / מוות / אסיסט / K/D / ADR / דירוג (keep stat acronyms) |
| clutch / entry / AWPer / IGL / rifler / lurker / support | קלאץ' / אנטרי / AWPer / IGL / רייפלר / לורקר / תומך |
| utility / smoke / flash / molotov / grenade | יוטיליטי / עשן / פלאש / מולוטוב / רימון |
| eco / force buy / full buy | אקו / קנייה בכוח / קנייה מלאה |
| economy / budget / salary / transfer fee / buyout | כלכלה / תקציב / משכורת / דמי העברה / סעיף שחרור |
| transfer / loan / free agent / contract | העברה / השאלה / שחקן חופשי / חוזה |
| sponsor / sponsorship | ספונסר / חסות |
| tournament / league / qualifier / playoffs / final / LAN | טורניר / ליגה / מוקדמות / פלייאוף / גמר / LAN |
| bootcamp / scrim / practice | מחנה אימונים / סקרים / אימון |
| morale / form / fatigue / chemistry | מורל / כושר / עייפות / כימיה |
| tactics / strategy / role | טקטיקה / אסטרטגיה / תפקיד |
| fans / hype / reputation | אוהדים / הייפ / מוניטין |
| inbox / email | תיבת דואר / אימייל |
| Save / Load / Continue / New Game / Settings / Exit | שמירה / טעינה / המשך / משחק חדש / הגדרות / יציאה |

## Names

- Map names (Mirage, Inferno, Nuke, Ancient, Anubis, Dust2, Train, Vertigo, Overpass) stay in Latin.
- Brand parodies (Nvidio, Samsunq, Tindel, AMDy...) and team/player names stay in Latin.
- @handles (e.g. @CS2News) stay as they are.

## Markup rules

- Keep `{placeholders}` exactly: `{0}`, `{club}`, `{player}`, `{tournament}`, `{price}` and so on (same names,
  same count). They are filled in at run time, often with Latin names.
- Gender choices `{м:him|ж:her}`: keep the structure `{м:...|ж:...}` and write Hebrew inside, e.g.
  `{м:שיחק|ж:שיחקה}`, `{м:הוא|ж:היא}`. Use them ONLY in strings whose English already has a `{м:..|ж:..}`
  choice (the game passes a gender only to those); there you may add more choices for other gendered words.
  Everywhere else write masculine Hebrew.
- Keep TextMeshPro tags: `<b>`…`</b>`, `<color=...>`…`</color>`, `<style=...>`…`</style>`,
  `<uppercase>`…`</uppercase>` (harmless for Hebrew), `<br>`. Wrap the matching Hebrew words.
- Keep line breaks where they separate paragraphs (emails). Write Hebrew in logical order; the game lays it out.
