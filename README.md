# Esports Manager 2026: Hebrew translation (fan project)

Full Hebrew translation of **Esports Manager 2026** (Neurona Games, Steam app 2749950; Unity 6000.5, IL2CPP):
menus, club and match screens, tactics, emails from staff/media/board, sponsor and trait descriptions, the
tutorial, and the English text that is hard-coded in the game's code. Translated by us.

Unofficial fan project, for personal use. Not affiliated with Neurona Games. This repository holds only our
tools, our Hebrew text and OFL fonts; game files are changed only through binary patches built on your PC.
Neither the repository nor the pack holds the game's English text (below: "Repository layout: Hebrew only").

## Repository layout: Hebrew only (2026-11-27)

Tracked, all without the game's English:
- `translation/he/<table>.json`: string tables, `{entry id: Hebrew}`.
- `translation/he/_literals.json`, `_labels.json`, `_scenes.json`, `_dialogs.json`, `_emdb.json`:
  `{H(English): Hebrew | null}`. `H(text)` (`tools/common.py`) is the first 16 hex digits of SHA-256 over the
  exact text's UTF-8 bytes, no normalisation.
- `translation/keep.json`: `{"ids": [table|id], "seen": [H], "keep": {reason: [H]}}`, the texts kept in Latin.
- `translation/seen_in_game.txt`: one text-log line per row, `H(line)<TAB>H(plain(line))` (`coverage.plain`: no
  links, tags or bold, spaces collapsed, lower case; for lines of a glossary article).
- `translation/he/dates.txt` (Hebrew month/weekday names, the English weekday and month names, date shapes),
  tools, docs (glossaries with short terms and patterns only), fonts, `pack/`.

Regenerated from your own install into gitignored `work/`: `extract.py` (work/en), `glossary.py`
(work/glossary_en.json), `il2cpp_xrefs.py` + `inventory.py` (work/inventory: every text source with its
English). The tools look each English text up by its hash (`common.ByHash`); `merge_todo.py` writes hashes.
`python tools/no_english.py` checks every tracked file (or `--rev`, or a pack `--zip`) for any run of 6 words of
a game text and fails on a hit. Fresh checkout: the five tools above, then `coverage.py`, the proxy, `build.py`.
The history was rewritten on 2026-11-27 so that no commit holds the English (re-keyed by hash; the tools of the
commits before that date still expect English keys).

## Lookup files of the pack (labels.txt, bios.txt, keep.txt)

The proxy swaps texts at display time, so it needs to recognise English texts without carrying them. Each file
line is keyed by `H(English)`, and the proxy (`tools/proxy/src/sha.rs`, `tmp.rs`) hashes the UTF-16 text
TextMeshPro gets (converted to UTF-8; an unpaired surrogate becomes U+FFFD) or the candidate part of it:
- `labels.txt`: `H<TAB>Hebrew` (exact text) and `^H<TAB>Hebrew` (H of the upper-cased English, Unicode case
  mapping, for a text the game upper-cases; written by `build.py`, the first label in English order wins). The
  proxy tries the whole text, then the whole text without surrounding white space and a trailing colon, then
  each run between rich-text tags and line breaks (trimmed the same way); for a candidate with an ASCII capital
  and no ASCII lower-case letter the `^` keys are tried after the exact ones. White space: space, tab, CR, LF,
  no-break space, zero-width space.
- `bios.txt`: `H<TAB>Hebrew` (the exact whole text, untrimmed) and template lines `*<TAB>H(skeleton)<TAB>Hebrew
  with {0}..`. The skeleton (`sources.skeleton`, the same rules in `tmp.rs`) of the text without surrounding
  white space replaces each hole with `{}`: a hole starts at the start or after a character that is not an
  ASCII letter or digit, and is a number-like token (an ASCII digit, then ASCII letters and digits, a `.`
  between two of them, a space before another digit: `17.02.2019`, `1.47`, `2 308`, `248u`) or a word of 2-4
  ASCII capitals. The holes fill `{N}` in text order; the surrounding white space is kept.
- `keep.txt`: one `H` per line; the text log skips a text whose H, or the H of the text trimmed of Unicode white
  space, is listed.
- `dates.txt` is plain: weekday and month names and date shapes only.
- `work/plain/` gets the same three files with English keys (never shipped); `cargo test` compares the hashed
  lookup with the plain one on every entry.

## Where the text is

`tools/inventory.py` lists every text source the game can show and classifies it; `tools/coverage.py` counts
each source and fails until every player-visible text is Hebrew (or a name kept in Latin).

1. **Unity Localization tables**: `StreamingAssets/aa/StandaloneWindows64/localization-string-tables-en_assets_all.bundle`
   (14 tables, ~4,500 used strings, ~55k words). `tools/extract.py` reads them with UnityPy (keys from the
   shared table data); `translation/he/<table>.json` holds `{entry id: Hebrew}`.
2. **Code literals**: much UI text is hard-coded in C# and lives in `il2cpp_data/Metadata/global-metadata.dat`
   (version 107, 72,667 literals, sorted alphabetically). `tools/metadata.py` reads and rewrites the literal
   table. `tools/il2cpp_xrefs.py` finds, offline, which methods use each literal (the literal slots in
   GameAssembly's `.data`, the RIP-relative loads in the code, `.pdata` functions, method names from the
   code-gen modules + metadata). That decides what a literal is: the game keeps its English UI text in
   `EmailsDataBaseEN` / `GlossaryContentEn` and its other languages in `EmailsDataBaseXX` / `GlossaryContentXx`;
   name pools (`CountiesAndNames`, `NameDatabase`...), ids, log text and Unity/.NET literals are not shown.
   A visible literal is rewritten in the metadata (`translation/he/_literals.json`, `{H(English): Hebrew | null}`,
   null = not shown) when only display code uses it or it is a sentence/format string; a short one the code
   may also use as a key goes to the display labels (5.).
3. **The term glossary** (main menu -> Glossary): ~123 markdown articles per language, each a code literal
   (`**bold**`, `[[entry.id|link]]`, `# heading`, `!tip`, `=see ids`). `tools/glossary.py` lists the English ones
   (`work/glossary_en.json`); they are translated in `_literals.json` like other literals.
4. **Scene texts**: default texts of TextMeshPro components in `level0-3`, `resources.assets`,
   `sharedassets0-3.assets` that no LocalizeStringEvent replaces (~430 English; many are placeholders the code
   overwrites). No type trees in these files: `tools/sources.py` reads/rewrites `m_text` in the raw
   MonoBehaviour data. `translation/he/_scenes.json` (`{H(English): Hebrew | null}`).
5. **Display labels**: `translation/he/_labels.json` maps English texts (by hash) shown in TextMeshPro to Hebrew; the
   proxy swaps them at display time (`labels=labels.txt`): the whole text, its upper-case form, or the runs
   between rich-text tags and line breaks (`<b>Rating</b>\n15`). Short code literals, dropdown options and
   glossary titles go here.
6. **Dialogs**: the manager's chat conversations, `Resources/dialogs/en/*` TextAssets (JSON, 100 dialogs,
   ~1,150 lines) in `resources.assets`. `translation/he/_dialogs.json`.
7. **default.emdb** (StreamingAssets): the database of a new career. `EMDB` + version 3 + AES-256-GCM around a
   zip of `;` CSV files (the key is a code literal; `tools/sources.py` decodes and re-encrypts it). Shown text:
   player bios (6,094; 4,239 FaceIt-style bios are one template, translated by `sources.faceit_he`), tournament
   descriptions; team and sponsor descriptions come from the Descriptions table. `translation/he/_emdb.json`.
   A career copies the bios into its save; the proxy shows Hebrew for careers saved before the pack (below).
8. **Not shown / nothing to translate**: ScriptableObjects (quests, achievements: ids), the other bundles
   (caster voice ids, locale names, shared table keys), other TextAssets (tactics data, licences).
9. **Dates built at run time**: the game formats dates with English culture names (`DateController.UpdateDate`:
   `"<b>" + dddd + "</b>,<br>" + "dd MMM yyyy"`; en-US long dates in email headers; `MMMM yyyy`, `d MMMM yyyy`,
   `dd MMM` in reports). `translation/he/dates.txt` holds the Hebrew weekday/month names and the date shapes; the
   proxy (`dates=dates.txt`) rewrites only whole shapes (names next to day/year numbers) in any displayed text,
   before the right-to-left step: `<b>יום חמישי</b>,<br>1 בינואר 2026`. Tests: `tools/proxy/src/dates.rs`.
   Standalone month names (calendar axis labels, `MMM`) are not rewritten: they cannot be told from a name.
10. **Names kept in Latin**: `translation/keep.json` `"keep": {reason: [H(text)]}` (map, team, language, acronym,
   handle, product, kept-by-translator); database names come from the emdb automatically.

Missing text becomes translator batches: `python tools/coverage.py --todo 12000` writes `work/todo/<source>-NNN.json`
(with context), translators write `work/done/<source>-NNN.json` (`{English: Hebrew | null}`, rules in
`work/TRANSLATOR.md`), `python tools/merge_todo.py --all` merges them into the right file.

## Careers saved before the pack (player bios)

Checked on a copy of a backed-up career (never on the live saves; nothing is written to a save):

- **Save format**: `%USERPROFILE%\AppData\LocalLow\...\Save\<slot>\SlotData.mpack` (plus `SlotMeta`, `DataMatch`,
  `DataTournament`, `MapOverallRecord`, `Backups\prev`) is plain MessagePack-CSharp: no compression (no LZ4 block
  array), no encryption (not the emdb AES key), objects as arrays by key index, dates as Timestamp ext -1.
  `msgpack.unpackb(data, strict_map_key=False)` reads it. SlotData item 9 is the player list; a player is an array
  of 60 and key 20 is `DataPlayer.Biography`. Staff have no bio (no column in `Staff.csv`, no field in `DataStaff`).
- **Bios are copied text, not references**: the import (`ImportDataPlayer`) copies the `Bio` column into
  `DataPlayer.Biography` when the career is created, and the save stores the full string. The getter is a plain
  field read and `SlotData.EmdbSnapshot` is empty in this save; no code path that re-reads bios from
  default.emdb on load was found (not checked in a running game). In the checked career only 95 of 6,133 bios are the same text as
  today's default.emdb: the career was created with an older database with real names ("donk", "Team Spirit",
  "win rate") where today's file has altered ones ("dnok", "Team Siprit", "win raet"). Team and tournament
  descriptions are copied into the save the same way (16 of 299 team descriptions match today's file).
- **How a bio is shown**: `PlayerOverview.Renew` does `_biography.text = player.Biography`, the whole string,
  through the `TMP_Text.text` setter the proxy already hooks (no StringBuilder, no parts).
- **What the proxy does** (`bios=bios.txt`, written by `build.py`): when a TextMeshPro text is exactly a bio it
  shows the Hebrew instead: `H(English)<TAB>Hebrew` lines for the translated bios of default.emdb, and
  `*<TAB>H(skeleton)<TAB>Hebrew` lines for the FaceIt bio (holes for the numbers, the region and the word ELO,
  `{0}`..`{8}` in the Hebrew, from `sources.faceit_templates()`, the same text `faceit_he` gives; "Lookup files"
  above). An older database with an ELO written in words would not match. Only the whole text is swapped (no
  upper-case or partial matching, unlike labels); the RTL step then runs as for any Hebrew text. In the checked
  career this gives Hebrew for all 4,239 FaceIt bios; the other 1,894 are written in the older database's words, so
  an exact English key from today's default.emdb cannot match them (they stay English unless translated from that
  text). Size: a map of all ~1,850 translated non-FaceIt bios is about 1-2 MB; the FaceIt bios need only 4
  templates.
- **Careers created with the pack** copy the Hebrew bios from our default.emdb into their save, so that career
  shows Hebrew bios (drawn left to right, without the RTL fix) when the game is started in English from Steam.
  Leaving the bios out of default.emdb and showing them only through `bios.txt` would keep every save in English.
- **Text log**: a bio that has no Hebrew is logged like any English text; bios from an older career are not
  default.emdb text, so leave them out of `translation/seen_in_game.txt`.

## Finding English that is still on screen (text log)

The proxy can write down every English text the game shows. It is off by default.

1. Turn it on: create an empty file `textlog.on` in `<game folder>\tirgumim\he\` (next to `redirect.cfg`),
   e.g. in a command prompt:
   `type nul > "D:\SteamLibrary\steamapps\common\Esports Manager 2026\tirgumim\he\textlog.on"`
   (or add `-tirgumim_textlog` to the launch arguments).
2. Start the game from the launcher in Hebrew and play through the screens.
3. The log is `<game folder>\tirgumim\he\textlog.txt`: each English text once (no Hebrew letters, not a
   display label, not a kept name), escaped like `labels.txt` (`\n` = line break). It grows across sessions;
   delete it to start over.
4. Turn it off: delete `textlog.on`. A pack update never ships that file.

Add them with `python tools/coverage.py --add-seen <textlog.txt>` (hashes into `translation/seen_in_game.txt`, the
English into the local `work/seen_in_game.txt`); `coverage.py` fails on each one that is not translated
somewhere or kept. Texts a scene shows without ever setting them (scene default texts) are not seen by the
hook: they are covered by source 4 above.

## How it renders

- Right-to-left: TextMeshPro has no bidi and draws a logical Hebrew string left to right (mirrored), so the
  strings are stored in logical order and the proxy fixes them at runtime (`rtl=tmp` in `pack/redirect.cfg`,
  `tools/proxy/src/tmp.rs` + `rtl.rs`). Right after `il2cpp_init` it hooks `TMP_Text.text` (setter) and
  `TMP_Text.SetText(string)` (MethodInfo pointers, vtables, the method pointer table and direct call sites;
  the game's code bytes are not patched in place). When a text with Hebrew letters is set, the component
  gets `isRightToLeftText = true` (TextMeshPro lays it out from the right edge and wraps lines in string
  order, so wrapped text keeps its line order) and the string is reordered by a reduced Unicode bidi
  algorithm for a right-to-left paragraph: Latin/number runs ("Maya Smith", "3-1", "12/05/2026", "50%",
  "(CS2)") are reversed so they come out left to right, brackets in Hebrew text are mirrored, rich-text
  tags stay paired, `\n` and `<br>` split paragraphs. Text without Hebrew (names, numbers) switches the
  component back to left-to-right. `rtl=tmp-right` would also right-align left-aligned Hebrew texts (off).
  Logical text can be checked without the game: `tirgumim_rtl_text` / `tirgumim_rtl_selftest` exports of the
  proxy, unit tests in `rtl.rs` (`cargo test` in `tools/proxy`).
- Limits: text set into a component some other way (StringBuilder/char[] `SetText`, legacy `UnityEngine.UI.Text`)
  is not reordered, and typing Hebrew into input fields is not supported.
- Glyphs: none of the game's fonts has Hebrew. TextMeshPro's fallback `LiberationSans` (in `resources.assets`)
  gets Noto Sans + Noto Sans Hebrew (OFL, `fonts/src`).
- Addressables checks bundle CRCs from `catalog.bin`; our copy of the catalog sets the CRC of the replaced
  bundle to 0 and its new size (`tools/build.py`).

## Hebrew only from the launcher

`version.dll` next to the exe is our proxy (`tools/proxy`, Rust; UnityPlayer imports VERSION.dll). With
`-tirgumim_he` it hooks file opens in `UnityPlayer.dll` and `GameAssembly.dll` and sends the game to our copies
in `tirgumim\he\` (`pack/redirect.cfg`, kept in sync by `build.py`): the string-table bundle, `catalog.bin`,
`global-metadata.dat`, `default.emdb`, `level0-3`, `resources.assets`, `sharedassets1-3.assets`. It also
hooks TextMeshPro for right-to-left and the display labels (above). Nothing in the game folder is replaced; a Steam launch is the original English game (the proxy stays inert without `-tirgumim_he`).

## Build

```
python tools/extract.py                      # English tables -> work/en
python tools/glossary.py                     # English glossary articles -> work/glossary_en.json
python tools/il2cpp_xrefs.py                 # methods using each code literal -> work/inventory/literal_refs.json
python tools/inventory.py                    # every text source, classified -> work/inventory/*.json
python tools/coverage.py                     # per-source counts; exit 1 until all visible text is Hebrew
python tools/no_english.py                   # no game English in the tracked files (--zip <pack> for a pack)
tools\proxy\build.cmd version %CD%\work\proxy-target
python tools/build.py                        # -> work/build (+ work/pack/files); --allow-missing for a test
tools\make-pack.cmd 1.0.0                    # launcher make-pack: bsdiff patches with output into tirgumim\he
```

Tools used: UnityPy, fontTools, zstandard, pefile, numpy, cryptography (PyPI); UnrealPak is not needed here.

### Decision 2026-11-27: default.emdb is not patched
A career copies default.emdb's bios and descriptions into its save, so patching the file would put Hebrew into
saves and a later Steam launch would show it (without RTL). The pack therefore leaves default.emdb untouched and
shows every translated default.emdb text (player bios, team/sponsor/tournament descriptions) at display time
through `bios.txt` (exact text, plus the FaceIt templates). Saves always stay English. Careers made from an
older database keep English for bios whose text differs from today's default.emdb (the FaceIt ones still match).
