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

## Roles (unified to the UI, 2026-11-27)
| English | Hebrew | Note |
|---|---|---|
| In-game leader (label) | מוביל במשחק | prose/bios: "מוביל במשחק (IGL)"; the UI also uses plain IGL ("מנה ל-IGL") |
| Rifler / Lurker / Support / Entry (fragger) | רייפלר / לורקר / תומך / אנטרי | as the role labels; never "אנטרי פראגר", never מנהיג המשחק |
| Sniper / AWPer | צלף / AWPer | "2 Snipers" = 2 צלפים; a player's role "AWPer" stays Latin |
Run `python tools/unify_terms.py` after any new batch: it applies these rows to work/done and the literal/label files.

## Bios and tournament descriptions (unified 2026-11-27, `BIO_RULES` in tools/unify_terms.py)
| English | Hebrew |
|---|---|
| X (born <date>) is a retired <nationality> professional CS:GO player | X (נולד ב-<תאריך>) הוא שחקן <לאום> מקצועי בדימוס של Counter-Strike: Global Offensive |
| a former CS:GO and CS player | שחקן לשעבר של Counter-Strike: Global Offensive ושל Counter-Strike (always "ושל", not "ו-") |
| (formerly known as A and B) / (formerly stylized as A) | (בעבר A ו-B) / (בעבר נכתב A) |
| (also known as A) / (also stylized as A) | (ידוע גם בשם A) / (נכתב גם A) |
| (known as A prior to 2017) / (stylized as A prior to 2022) | (עד 2017 נקרא A) / (עד 2022 נכתב A) |
| (briefly known as A) / (briefly stylized as A) | (לזמן קצר נקרא A) / (לזמן קצר נכתב A) |
| Kazakh / Kazakhstani, Azerbaijani | קזחי (קזחית), אזרבייג'אני |
| (female) professional player | שחקנית ... מקצועית (not מקצוענית) |
| a Major, Major titles, two Majors | מייג'ור, תארי מייג'ור, שני מייג'ורים (tournament names such as "PGL Major Stockholm" stay Latin) |
| the Tier 2 circuit | מעגל דרג 2 (as the "Tier 1" = "דרג 1" label) |
| grassroots scene | הסצנה העממית (not "סצנת השורשים") |

## Dialogs (club conversations, edit pass 2026-11-27)
Spoken, casual Hebrew; staff and players speak to the manager in masculine singular, the manager answers in
the first person masculine. Imperatives in the colloquial future form ("תשקול", "תעדכן", "תתחיל").
| English | Hebrew | Note |
|---|---|---|
| put on the transfer list / list him for transfer | להכניס לרשימת ההעברות | not "להעמיד להעברה" |
| sign (a player) | להחתים / החתמה | "לחתום" only for the player himself |
| business class | ביזנס / מחלקת ביזנס | not מחלקת עסקים |
| merch | מרצ'נדייז | not סחורה |
| fans / supporters | אוהדים | not תומכים |
| session (psychologist, mental training) | פגישה / מפגש | not סשן |
| "Fair point" / "Good point" / "You have a point" | צודק / יש בזה משהו / בצדק | not נקודה הוגנת, יש לך נקודה |
| assess / evaluate (a decision) | לבחון / לבדוק | not להעריך (reads as "appreciate") |
| tight budget | תקציב דחוק / מצומצם | not צפוף |
| schedule is full / at capacity | בעומס מלא / הלו"ז מלא | not קיבולת |
| aim (player skill) | דיוק | |
| Major (tournament tier) | Major (ב-Major) | Latin |
| "Coach" as a form of address | מאמן | the game's English wording |
