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

## How it renders

- The game's text engine does bidi itself; strings are stored in logical order and wrapped in RLI…PDI
  (U+2067/U+2069) so mixed Hebrew/Latin lines are right-to-left.
- Glyphs: none of the game's fonts has Hebrew. TextMeshPro's fallback `LiberationSans` (in `resources.assets`)
  gets Noto Sans + Noto Sans Hebrew (OFL, `fonts/src`).
- Addressables checks bundle CRCs from `catalog.bin`; our copy of the catalog sets the CRC of the replaced
  bundle to 0 and its new size (`tools/build.py`).

## Hebrew only from the launcher

`version.dll` next to the exe is our proxy (`tools/proxy`, Rust; UnityPlayer imports VERSION.dll). With
`-tirgumim_he` it hooks file opens in `UnityPlayer.dll` and `GameAssembly.dll` and sends the game to our copies
in `tirgumim\he\` (`pack/redirect.cfg`): the string-table bundle, `catalog.bin`, `resources.assets`,
`global-metadata.dat`. Nothing in the game folder is replaced; a Steam launch is the original English game.

## Build

```
python tools/extract.py                      # English tables -> work/en
python tools/literals.py                     # code-literal candidates -> work/literal_candidates.json
python tools/coverage.py                     # tables 100% + every literal decided
tools\proxy\build.cmd version %CD%\work\proxy-target
python tools/build.py                        # -> work/build (+ work/pack/files)
tools\make-pack.cmd 1.0.0                    # launcher make-pack: bsdiff patches with output into tirgumim\he
```

Tools used: UnityPy, fontTools, zstandard (PyPI); UnrealPak is not needed here.
