# Building MesloLGS NF DF

```sh
./build/build.sh          # Docker (nothing to install)
DF_NATIVE=1 ./build/build.sh   # local fontforge + fonttools
```

Four `.ttf` files land in the repository root. Then:

```sh
python3 build/verify.py   # gate before releasing
./update-hashes.sh        # after tagging, see that script's header
```

## What this font is

`MesloLGS NF DF` is upstream [Nerd Fonts](https://github.com/ryanoasis/nerd-fonts)
`Meslo LG S` built with `--mono --complete`, plus two glyph-geometry changes
carried in `patches/`.

Those two changes are not ours originally. They come from
[romkatv/nerd-fonts](https://github.com/romkatv/nerd-fonts), the fork that
produces the `MesloLGS NF` that powerlevel10k recommends, and that this
repository shipped as a vendored binary until v2.0.0. That fork is pinned to a
Nerd Fonts 2.3.3-era patcher, which is what left us six Nerd Fonts releases
behind — no Font Awesome 6, no braille, and ~1000 cheat-sheet entries with no
glyph behind them. Rather than keep vendoring someone else's binary, we port
the two changes we actually care about onto whatever upstream release
`NF_VERSION` in `build.sh` names.

### The two changes

| | stock Nerd Fonts | MesloLGS NF DF |
| --- | --- | --- |
| Icon size (`pa` sets) | fits inside one cell under `--mono` | `DF_ICON_SCALE` = 1.2 cells, centered, overhanging both sides |
| Box drawing U+2500–U+259F | one cell, 2% overlap | 1.06 × cell width, 1.04 × line height, nudged left and down |

The first keeps icons legible; stock `--mono` shrinks them noticeably. The
second is why powerlevel10k and tide frames have no hairline seams between
adjacent cells.

Both live behind a `--df` flag the patch adds, so the same checkout still
builds stock Nerd Fonts output without it — useful when you want to tell
"upstream changed this" apart from "our patch changed this".

### Everything else is upstream

Notably *not* customised: the Latin glyphs (the source
`Meslo LG S ... for Powerline.ttf` faces are byte-identical across Nerd Fonts
releases, and to the ones romkatv used, so ordinary text does not move when
this is rebuilt), the line metrics, and the advance width.

## Rebuilding against a newer Nerd Fonts

1. Bump `NF_VERSION` in `build.sh`.
2. Run the build. `git apply` will tell you if the patch no longer applies —
   upstream refactors the scaling code fairly often, so expect to re-anchor the
   hunks rather than to rebase them mechanically.
3. Run `build/verify.py`. It checks the things a bad re-anchoring silently
   breaks: that icons really did end up oversized and centered, that block
   glyphs really do overhang the cell, that the font is still monospaced, that
   the line height has not moved, and that braille and Font Awesome 6 survived.
4. `build/verify.py --baseline <dir>` additionally diffs against the previously
   shipped faces and fails if any Latin glyph changed shape or if a codepoint
   disappeared that is not one of the Material Design aliases upstream retired
   in 3.4.0.

## Files

| | |
| --- | --- |
| `build.sh` | fetch + patch upstream, run font-patcher, rename |
| `patches/0001-df-icon-and-block-scaling.patch` | the two changes, against upstream `font-patcher` |
| `rename.py` | rewrites the name table to the `MesloLGS NF DF` family |
| `verify.py` | release gate |
| `.work/` | cached upstream checkout and intermediate output (git-ignored) |
