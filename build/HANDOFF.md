# Handoff: the gap-fill stage

State of the `claude/wonderful-darwin-2d5pyt` branch, for whoever picks this up
next. Delete this file when the work below is finished and released.

## What this branch does

It adds a third build stage. After font-patcher and `rename.py`, `fill.py`
looks at every codepoint a face does not map -- a *gap* -- and fills it from
the Noto fonts:

| the gap | it is filled from | presentation |
| --- | --- | --- |
| is listed in `colour-overrides.txt` / `monochrome-overrides.txt` | Noto Color Emoji / the monochrome sources below | colour / monochrome |
| is mapped by Segoe UI Symbol, and Unicode shows it as an emoji by default (🌈 ⏰ ✅) | Noto Color Emoji | colour |
| is mapped by Segoe UI Symbol | Noto Sans Symbols 2, else Noto Sans Symbols, else Noto Emoji | monochrome |
| is mapped by Noto Color Emoji only | Noto Color Emoji | colour |
| neither | nothing; it stays a gap | -- |

Segoe UI Symbol is the reference for "this is a monochrome symbol, not an
emoji", except where Unicode says it is an emoji by default
(`Emoji_Presentation=Yes` in `emoji-data.txt`, pinned at 16.0). Those, and
the emoji newer than Segoe UI Symbol, are colour; everything else Segoe covers
is monochrome, with its colour form one U+FE0F away. The two override files,
kept by hand and empty so far, settle single codepoints either way.
`build/README.md` has the rules numbered 0-5 with their reasons, the
exclusions, how glyphs are fitted, and why the colour is encoded the way it
is. Read that first; this file only covers what is left to do.

Three commits, oldest first:

| | |
| --- | --- |
| `59a9df0` | the stage itself: `fill.py`, `charset.py`, `fetch-sources.sh`, the Segoe charset, the `verify.py`/`compare.py` checks |
| `05dae44` | emoji as COLRv0 instead of COLRv1, ZWJ sequences, the U+FE0F selector |
| `9760d2e` | Segoe-covered emoji stay monochrome; the `SVG` table for CoreText apps |

Then, from the first real terminal test (2026-09-18): Segoe-covered gaps
that Unicode shows as emoji by default are filled in colour, with the two
override files for exceptions and `emoji-data.txt` pinned beside the Noto
sources; U+FE0F selectors cut to the 371 Unicode defines; the Docker build
pinned to `linux/amd64`; and the ligature order made independent of the
fontTools version. After that commit: skin-tone and hair variants fold onto
the untoned emoji by ligature (👍🏽 draws 👍, no glyphs added), and the
sequence ligatures accept the colour glyph HarfBuzz and CoreText substitute
for `<cp> FE0F` before GSUB -- without it, 🏳️‍🌈 and ❤️‍🔥 came apart in
every HarfBuzz shaper. Checked by shaping with HarfBuzz.

## Where it stands

Per face, against Nerd Fonts 3.5.1 and Noto Color Emoji 2.051:

| | main | this branch |
| --- | --- | --- |
| Size | 3.0 MB | 9.2 MB |
| Glyphs | 13,579 | 41,124 |
| Codepoints | 13,554 | 16,455 |

What the Regular face gained: 1149 codepoints from Noto Sans Symbols 2, 567
from Noto Sans Symbols, 9 monochrome from Noto Emoji, 1174 in colour from Noto
Color Emoji (865 Segoe-covered that Unicode shows as emoji by default, 309
newer than Segoe), and the two zero-width glyphs the sequences need. On top of
that, 237 ZWJ sequences as `ccmp` ligatures and 371 U+FE0F selectors. 2432
Segoe-covered gaps stay gaps because no Noto font has them. The italic faces
gain ~250 more codepoints, because their Meslo sources map fewer symbols to
begin with.

**Verified.** `verify.py` and `compare.py` pass on all four faces, including
the baseline diff against the last release and `compare.py` section 0 against
upstream's published binaries. Builds are identical under fontTools 4.46 (what
Ubuntu 24.04 ships, so what the Docker build uses) and 4.65, now that `fill.py`
sorts the sequence ligatures itself; before, the two wrote them into `GSUB` in
different orders. Chromium renders the monochrome defaults, their U+FE0F colour
forms, the ZWJ sequences, the two-cell layout and the monochrome fallback
correctly. Ghostty 1.3.1 on macOS: colour from the `SVG` table, monochrome
defaults, colour with U+FE0F, the ZWJ sequences as one glyph, two cells, and
Latin, powerline and icons unchanged; and, on the final rules (2026-09-18),
🌈 🌊 🆗 👩 📈 ⏰ ⌚ ✅ ❌ ⭐ ⚽ in Noto's colour, with ℹ ⏸ ⛈ monochrome and
colour after U+FE0F.

**Not verified.** Everything below was reasoned from source code and platform
documentation, never run:

- iTerm2, Terminal.app, kitty and WezTerm on macOS.
- Windows Terminal.
- Any Linux terminal (only Chromium was available).

## What is left

### 1. Try it in a terminal -- Ghostty done, the rest open

Install the four faces from this branch and check:

- An emoji newer than Segoe UI Symbol is in colour. 🥺 U+1F97A is a good one.
- A Segoe-covered emoji Unicode shows as emoji by default is in colour:
  🌈 U+1F308, ⏰ U+23F0, ✅ U+2705.
- A text-style symbol is monochrome, and it + U+FE0F is in colour: ℹ U+2139,
  ⏸ U+23F8.
- 🏳️‍🌈 forms one glyph rather than three.
- Emoji occupy two cells, and the prompt does not reflow.
- Latin text, powerline separators and Nerd Font icons look exactly as before.

Colour in Noto's flat style is our glyph; colour in the system font's style
(Apple's, on macOS) means the terminal went past us to the emoji font.

Ghostty 1.3.1 on macOS passed on 2026-09-18, and reading its source explained
the rest (`src/font/shaper/run.zig`, `src/terminal/Terminal.zig`):

- It finds colour through the `SVG` table, as intended.
- It strips U+FE0F before shaping and uses it only to pick a font whose glyph
  for the codepoint is colour. So on the build of that day ✅️, 🏳️‍🌈 and ❤️‍🔥
  came from Apple Color Emoji, and our selectors are never used there. 👩‍💻,
  with no U+FE0F in it, is our ligature.
- It drops a U+FE0F that Unicode does not define, so 🌈️ stayed monochrome. That
  is what showed that 732 Segoe-covered emoji had no way to colour, which led
  to the Unicode-emoji rule (rule 2 in `README.md`).

Still to look at: the other terminals in the list above, then Windows
Terminal and a Linux terminal.

### 2. Decide the three knobs, and fill the override lists

Both override files are empty. The plan is to add to
`build/monochrome-overrides.txt` whatever looks wrong in colour while using
the font (✅ and ❌ in prompts are the likely first ones), and to
`build/colour-overrides.txt` any text-style symbol that should be colour (the
128 Segoe-covered ones that Unicode shows as text by default: ℹ ⏸ ⛈ ...).
Each is one line, then `./build/build.sh --fill-only`.

All pass through `DF_FILL_ARGS`, e.g.
`DF_FILL_ARGS="--emoji-format both" ./build/build.sh --fill-only`.

Measured on the Regular face, against the committed 9.17 MB / 41,124 glyphs:

| flag | effect | size | glyphs |
| --- | --- | --- | --- |
| `--emoji-format both` | gradients where COLRv1 renders (Chromium, Firefox, VTE, kitty on Linux) | +2.68 MB | 60,746 |
| `--no-svg` | drops the `SVG` table; Alacritty gets its colour back, Ghostty on macOS goes monochrome | -2.15 MB | unchanged |
| `--no-sequences` | no ZWJ ligatures, no U+FE0F selectors | -1.58 MB | 34,136 |

`--emoji-format both` leaves only ~4,800 glyphs of headroom under the 65,535 a
TrueType font can hold, so it does not combine with much else.
`--no-sequences` saved 4 MB before the selectors were cut from 1092 to 371.
In Ghostty it would now cost only the ligatures (👩‍💻 as one glyph), since
Ghostty never uses the selectors and sends a sequence with U+FE0F inside it
to the system emoji font anyway.

The committed defaults are `--emoji-format colrv0`, with the `SVG` table and
the sequences on. Change them only with a terminal in front of you.

### 3. Run a full build -- done 2026-09-18

A full Docker build now reproduces everything. The patcher and rename stages
match the v2.0.0 faces except for `head.modified`. The stock control matches
upstream's v3.5.1 binaries glyph for glyph. `verify.py` and all of
`compare.py` pass, and the shipped faces were replaced with this build's. They
differ from the earlier ones only in `GSUB` ligature order.

That took one fix: on arm64, FontForge draws about 300 icons differently from
the amd64 build upstream releases with, so `compare.py` section 0 failed.
`build.sh` now runs the container as `linux/amd64` (see "A note on
determinism" in `README.md`). Section 3 (determinism, `--rebuild DIR`) still
has not run.

The commands, for the next upgrade:

```sh
./build/build.sh                       # needs fontforge + fonttools, or Docker
./build/build.sh --stock               # control build, no --df
./build/fetch-release.sh               # upstream's own binaries
git worktree add /tmp/prev v2.0.0
python3 build/verify.py --baseline /tmp/prev \
    --csv ../dotfiles/.dotfiles/resources/nerdfonts/nerdfont.csv
python3 build/compare.py --upstream --baseline /tmp/prev
```

`compare.py` section 0 proves the toolchain still reproduces upstream's
binaries exactly; everything else in that report is only meaningful once it
holds. If the full build's faces differ from the committed ones by more than
`head.modified`, the committed faces are wrong -- commit the full build's.

### 4. Release

The version is still `2.0.0` in both `Casks/dotfiles-fonts.rb` and
`bucket/dotfiles-fonts.json`. This is a coverage addition with no rename, so
`2.1.0` fits. Follow the order in `update-hashes.sh`'s header: bump both files,
push, tag, then run the script, then commit the hashes.

The header now also says why the hash commit has to follow the merge
straight away: the Scoop manifest pins the hashes of the files as served from
`main`, so between the merge and that commit `scoop install` fails on a hash
mismatch.

Already done for this release: the README's "What changes in 2.1.0" section,
the cask caveats rewritten for 2.1.0 (and with a `rm` that no longer matches
the new faces), and the licensing. The faces are now stated as SIL OFL 1.1 as
a whole (they contain OFL glyphs, and OFL condition 5 requires it), with the
parts' own notices in `MesloLGS NF DF License.txt`, `Nerd Fonts License.txt`
and `Noto License.txt`; the faces carry the same in name IDs 0, 13 and 14;
and Scoop downloads the three license files with the fonts, so its installs
carry them too. `update-hashes.sh` hashes them along with the fonts.

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
GSUB, so it would show ZWJ sequences as their parts regardless. The
Unicode-emoji rule widened this: the 865 Segoe-covered emoji it moved to
colour were monochrome, which Alacritty draws, and are now colour, which it
does not.

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
codepoint we fill monochrome cannot fall back to a colour system font. A
U+FE0F gets the colour back only where Unicode defines one, which is why
everything Unicode shows as emoji by default is filled in colour. An entry in
`monochrome-overrides.txt` for one without a defined U+FE0F (🌈, say) is
monochrome for good.

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
| `fill.py` | the whole stage: the rules, the fitting, the COLRv0 flattening, the SVG table, the ligatures, the manifest |
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
