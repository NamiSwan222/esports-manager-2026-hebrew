# Esports Manager 2026: Hebrew translation (fan project)

Full Hebrew translation of **Esports Manager 2026** (Neurona Games, Steam app 2749950; Unity 6000.5, IL2CPP):
menus, club and match screens, tactics, emails from staff/media/board, sponsor and trait descriptions, the
tutorial, and the English text that is hard-coded in the game's code. Translated by us.

Unofficial fan project, for personal use. Not affiliated with Neurona Games. This repository holds only our
tools, our Hebrew text and OFL fonts; game files are changed only through binary patches built on your PC.

## Where the text is

1. **Unity Localization tables**: `StreamingAssets/aa/StandaloneWindows64/localization-string-tables-en_assets_all.bundle`
   (14 tables, ~4,500 used strings, ~55k words). `tools/extract.py` reads them with UnityPy (keys from the
   shared table data); `translation/he/<table>.json` holds `{entry id: Hebrew}`.
2. **Code literals**: much UI text is hard-coded in C# and lives in `il2cpp_data/Metadata/global-metadata.dat`
   (version 107). `tools/metadata.py` reads and rewrites the literal table (moving the later sections).
   `tools/literals.py` picks ~7,800 sentence-like candidates; translators translate what a player sees and set
   `null` for other languages, developer messages and names. `translation/he/_literals.json` is
   `{English: Hebrew | null}`; short labels are added via `translation/literal_labels.json` after checking in game.

3. **The term glossary** (main menu -> Glossary): ~123 markdown articles per language, each a code literal
   (`**bold**`, `[[entry.id|link]]`, `# heading`, `!tip`, `=see ids`). `tools/glossary.py` lists the English ones
   (`work/glossary_en.json`); they are translated in `_literals.json` like other literals.
4. **Display labels**: short English strings (glossary titles and categories, "SEE ALSO"...) are not changed in
   the code, where 1-2 word literals are often keys. `translation/he/_labels.json` maps the exact text shown in
   TextMeshPro to Hebrew; the proxy swaps it at display time (`labels=labels.txt`).
5. **What was really on screen**: started with `-tirgumim_textlog`, the proxy writes every English text shown in
   TextMeshPro to `%TEMP%\tirgumim_text.log`. Copies go in `translation/seen_in_game.txt`; `coverage.py` fails on
   any line that is not a label, a translated glossary paragraph or a name kept in Latin (`keep.json` "seen").

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
in `tirgumim\he\` (`pack/redirect.cfg`): the string-table bundle, `catalog.bin`, `resources.assets`,
`global-metadata.dat`. It also hooks TextMeshPro for right-to-left (above). Nothing in the game folder is
replaced; a Steam launch is the original English game (the proxy stays inert without `-tirgumim_he`).

## Build

```
python tools/extract.py                      # English tables -> work/en
python tools/glossary.py                     # English glossary articles -> work/glossary_en.json
python tools/literals.py                     # code-literal candidates -> work/literal_candidates.json
python tools/coverage.py                     # tables 100% + every literal decided
tools\proxy\build.cmd version %CD%\work\proxy-target
python tools/build.py                        # -> work/build (+ work/pack/files)
tools\make-pack.cmd 1.0.0                    # launcher make-pack: bsdiff patches with output into tirgumim\he
```

Tools used: UnityPy, fontTools, zstandard (PyPI); UnrealPak is not needed here.
