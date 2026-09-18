# Handoff: the gap-fill stage

State of the `claude/wonderful-darwin-2d5pyt` branch, for whoever picks this up
next. Delete this file when the work below is finished and released.

## What this branch does

It adds a third build stage. After font-patcher and `rename.py`, `fill.py`
looks at every codepoint a face does not map -- a *gap* -- and fills it from
the Noto fonts:

| the gap is mapped by | it is filled from | presentation |
| --- | --- | --- |
| Segoe UI Symbol | Noto Sans Symbols 2, else Noto Sans Symbols | monochrome |
| Segoe UI Symbol, neither symbol font has it | Noto Emoji | monochrome |
| Noto Color Emoji only | Noto Color Emoji | colour |
| neither | nothing; it stays a gap | -- |

Segoe UI Symbol is the reference for "this is a monochrome symbol, not an
emoji". Colour by default is therefore only for the emoji newer than Segoe UI
Symbol; everything Segoe covers is monochrome, and its colour form is one
U+FE0F away. `build/README.md` has the full rule, the exclusions, how glyphs
are fitted, and why the colour is encoded the way it is. Read that first; this
file only covers what is left to do.

Three commits, oldest first:

| | |
| --- | --- |
| `59a9df0` | the stage itself: `fill.py`, `charset.py`, `fetch-sources.sh`, the Segoe charset, the `verify.py`/`compare.py` checks |
| `05dae44` | emoji as COLRv0 instead of COLRv1, ZWJ sequences, the U+FE0F selector |
| `9760d2e` | Segoe-covered emoji stay monochrome; the `SVG` table for CoreText apps |

## Where it stands

Per face, against Nerd Fonts 3.5.1 and Noto Color Emoji 2.051:

| | main | this branch |
| --- | --- | --- |
| Size | 3.0 MB | 9.2 MB |
| Glyphs | 13,579 | 41,874 |
| Codepoints | 13,554 | 16,455 |

What the Regular face gained: 1267 codepoints from Noto Sans Symbols 2, 576
from Noto Sans Symbols, 747 monochrome from Noto Emoji, 309 in colour from
Noto Color Emoji, and the two zero-width glyphs the sequences need. On top of
that, 237 ZWJ sequences as `ccmp` ligatures and 1092 U+FE0F selectors. 2432
Segoe-covered gaps stay gaps because no Noto font has them. The italic faces
gain ~250 more codepoints, because their Meslo sources map fewer symbols to
begin with.

**Verified.** `verify.py` and `compare.py` pass on all four faces, including
the baseline diff against the last release and `compare.py` section 0 against
upstream's published binaries. Builds are identical under fontTools 4.46 (what
Ubuntu 24.04 ships, so what the Docker build uses) and 4.65. Chromium renders
the monochrome defaults, their U+FE0F colour forms, the ZWJ sequences, the
two-cell layout and the monochrome fallback correctly.

**Not verified.** Everything below was reasoned from source code and platform
documentation, never run:

- Ghostty, iTerm2, Terminal.app, kitty and WezTerm on macOS.
- Windows Terminal.
- Any Linux terminal (only Chromium was available).
- The patcher stage. The sandbox had no fontforge and no Docker daemon, so
  only `--fill-only` ever ran. The four committed faces were produced by the
  fill stage from the previously committed faces, which are exactly the rename
  stage's output.

## What is left

### 1. Try it in a terminal, especially Ghostty on macOS

This is the real gate. Install the four faces from this branch and check:

- An emoji newer than Segoe UI Symbol is in colour. 🥺 U+1F97A is a good one.
- ✅ U+2705 is monochrome, and `✅` + U+FE0F is in colour.
- 🏳️‍🌈 forms one glyph rather than three.
- Emoji occupy two cells, and the prompt does not reflow.
- Latin text, powerline separators and Nerd Font icons look exactly as before.

Ghostty on macOS is the one to watch. It decides a glyph is colour by finding
an `sbix` or `SVG` table and never looks at `COLR`, which is the whole reason
the `SVG` table is there. If it draws these emoji monochrome, the `SVG` table
is not doing its job and that is the first thing to debug.

### 2. Decide the three knobs

All pass through `DF_FILL_ARGS`, e.g.
`DF_FILL_ARGS="--emoji-format both" ./build/build.sh --fill-only`.

Measured on the Regular face, against the committed 9.25 MB / 41,874 glyphs:

| flag | effect | size | glyphs |
| --- | --- | --- | --- |
| `--emoji-format both` | gradients where COLRv1 renders (Chromium, Firefox, VTE, kitty on Linux) | +2.68 MB | 61,453 |
| `--no-svg` | drops the `SVG` table; Alacritty gets its colour back, Ghostty on macOS goes monochrome | -2.14 MB | unchanged |
| `--no-sequences` | no ZWJ ligatures, no U+FE0F selectors | -4.06 MB | 21,700 |

`--emoji-format both` leaves only ~4000 glyphs of headroom under the 65,535 a
TrueType font can hold, so it does not combine with much else. `--no-sequences`
is the big saving because the 1092 U+FE0F selectors each need their own colour
glyph, layers and SVG document, on top of the 237 sequences.

The committed defaults are `--emoji-format colrv0`, with the `SVG` table and
the sequences on. Change them only with a terminal in front of you.

### 3. Run a full build

```sh
./build/build.sh                       # needs fontforge + fonttools, or Docker
./build/build.sh --stock               # control build, no --df
./build/fetch-release.sh               # upstream's own binaries
git worktree add /tmp/prev v2.0.0
python3 build/verify.py --baseline /tmp/prev \
    --csv ../dotfiles/.dotfiles/resources/nerdfonts/nerdfont.csv
python3 build/compare.py --upstream --baseline /tmp/prev
```

`compare.py` section 0 is the one that has not run against a locally patched
control on this branch: it proves the toolchain still reproduces upstream's
binaries exactly, and everything else in that report is only meaningful once it
holds. If the full build's faces differ from the committed ones by more than
`head.modified`, the committed faces are wrong -- commit the full build's.

### 4. Release

The version is still `2.0.0` in both `Casks/dotfiles-fonts.rb` and
`bucket/dotfiles-fonts.json`. This is a coverage addition with no rename, so
`2.1.0` fits. Follow the order in `update-hashes.sh`'s header: bump both files,
push, tag, then run the script, then commit the hashes.

One caveat that is not in that header: the Scoop manifest pins the hashes of
the `.ttf` files as served from `main`, so between merging this branch and
committing the new hashes, `scoop install` fails on a hash mismatch. Keep the
gap short, or push the hash commit immediately after the merge.

### 5. Regenerate the icon cache downstream

In `dotfiles`, after installing the new faces:

```sh
_df_icon --generate --add-missing
```

Coverage grew by ~2900 codepoints, so the cache is stale.

## Known issues

**Alacritty shows the filled emoji blank.** FreeType hands a client that asks
for colour the `SVG` glyph rather than the COLR layers unless it passes
`FT_LOAD_NO_SVG`. WezTerm and Ghostty pass it, kitty reads the COLR layers
directly, foot and VTE can render SVG. Alacritty does none of those and has no
SVG renderer. `--no-svg` fixes Alacritty and breaks Ghostty on macOS; there is
no setting that satisfies both. Alacritty also does not shape with the font's
GSUB, so it would show ZWJ sequences as their parts regardless.

**30 colour glyphs have no monochrome fallback.** Noto Emoji 3.002 predates
them, so on a renderer with no colour support at all they are blank cells.
Fourteen are single codepoints (U+1F6D8, U+1FA89, U+1FA8A, U+1FA8E, U+1FA8F,
U+1FABE, U+1FAC6, U+1FAC8, U+1FACD, U+1FADC, U+1FADF, U+1FAE9, U+1FAEA,
U+1FAEF) and sixteen are directional-person ZWJ sequences. A newer Noto Emoji
release fixes this for free; the pin is in `fetch-sources.sh`.

**Flags are deliberately absent.** Regional indicators are left unmapped in
pairs so the system emoji font composes them. If your terminal has no emoji
font configured, flags will be tofu. That is the intended trade.

**Anything this font maps, the system emoji font no longer draws.** That is
inherent to filling gaps, and it is why the monochrome rule matters: a
codepoint we fill monochrome cannot fall back to a colour system font.

## Open questions worth a look later

- Ghostty honouring `COLR` on macOS would let the `SVG` table go, which is
  2.1 MB per face and the Alacritty problem at once. Worth an upstream issue.
- The `SVG` chunk size (`SVG_CHUNK` in `fill.py`, currently 16 glyphs per
  gzip document) was picked from a size curve, not from measured decode time
  in a terminal. One glyph per document costs 0.6 MB more; 64 costs 0.1 MB
  less. If emoji-heavy output feels slow to render, this is the dial.
- Noto pins in `fetch-sources.sh` are from 2025. Bumping them is one edit plus
  `./build/build.sh --fill-only`, and picks up new Unicode emoji.

## File map

| | |
| --- | --- |
| `fill.py` | the whole stage: the rule, the fitting, the COLRv0 flattening, the SVG table, the ligatures, the manifest |
| `charset.py` | dumps a font's character set as hex ranges |
| `charsets/segoe-ui-symbol.txt` | Segoe UI Symbol 6.23's character set, the reference the rule reads |
| `fetch-sources.sh` | the four Noto sources, pinned by version and sha256 |
| `.work/fill/<style>.json` | what the stage did, per face: every codepoint, sequence and selector with its source. `verify.py` and `compare.py` read it |
| `build.sh --fill-only` | reruns the stage in ~25 s per face, without fontforge |

Regenerating `charsets/segoe-ui-symbol.txt` needs a copy of
`C:\Windows\Fonts\seguisym.ttf`:

```sh
python3 build/charset.py /path/to/seguisym.ttf -o build/charsets/segoe-ui-symbol.txt
```

The character set is not copyrightable, which is why it can be committed when
the font itself cannot.
