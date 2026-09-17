# Building MesloLGS NF DF

```sh
./build/build.sh               # Docker (nothing to install)
DF_NATIVE=1 ./build/build.sh   # local fontforge + fonttools
```

Four `.ttf` files land in the repository root. See **Releasing** below for the
rest of the path.

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

## Releasing, and upgrading to a newer Nerd Fonts

The whole path, in order. Steps 1–2 are the upgrade; 3–6 are every release.

```sh
# 1. Point at the new upstream release
$EDITOR build/build.sh                 # bump NF_VERSION

# 2. Build. git apply fails loudly if the patch no longer applies.
./build/build.sh

# 3. Keep a copy of what you are replacing, for the regression diff
git worktree add /tmp/prev HEAD        # or any checkout of the last release

# 4. Sanity: is the output a well-formed font that does what we want?
python3 build/verify.py --baseline /tmp/prev \
    --csv ../dotfiles/.dotfiles/resources/nerdfonts/nerdfont.csv

# 5. Accountability: is every difference one we meant to cause?
./build/build.sh --stock               # control build, no --df
./build/fetch-release.sh               # upstream's own binaries
python3 build/compare.py --upstream --baseline /tmp/prev

# 6. Version bump, tag, hashes
$EDITOR Casks/dotfiles-fonts.rb bucket/dotfiles-fonts.json   # bump version
git commit -a && git push
git tag vX.Y.Z && git push origin vX.Y.Z
./update-hashes.sh && git commit -a    # see that script's header for why
```

Then, downstream in `dotfiles`, regenerate the icon cache against the new face:

```sh
_df_icon --generate --add-missing
```

### Why both verify.py and compare.py

They fail on different things, and an upgrade can break either one alone.

`verify.py` asks **is this a good font**: monospaced, line height unmoved, icons
oversized and centered, block glyphs overhanging, braille and Font Awesome 6
present, every cheat-sheet entry resolving. It catches a patch hunk that stopped
applying.

`compare.py` asks **is this font different from stock in exactly the ways we
intended**. It catches the subtler failure: a re-anchored hunk that still
applies but now lands on the wrong glyphs, or reaches glyphs it never used to.
It works in four steps, each of which makes the next one meaningful:

| | claim |
| --- | --- |
| 0 | control build == upstream's published binary, glyph for glyph. Until this holds, a difference below could be theirs rather than ours. |
| 1 | shipped vs control differs only in box drawing, pasted-in icons, and the name IDs `rename.py` rewrites. A glyph that came from the Meslo source face must be untouched — a provenance test, not a codepoint list, so it stays correct as upstream adds glyph sets. |
| 2 | vs the previous release: coverage moves only where upstream said it would, Latin text does not move, and our box-drawing geometry is unchanged. |
| 3 | an independent rebuild produces the same glyphs. |

Upstream refactors the scaling code fairly often, so on a bad upgrade expect to
re-anchor the hunks by hand rather than rebase them mechanically — then let
these two tell you whether you re-anchored them correctly.

### A note on determinism

Builds are not byte-identical: FontForge stamps `head.modified` with the build
time, so two builds of the same input have different checksums. `compare.py`
section 3 compares glyphs rather than bytes for that reason, and says so when
the timestamp is the only difference. It follows that the `.ttf` files have to
be committed rather than rebuilt on demand, and that the Scoop hashes in
`bucket/` pin the committed files specifically.


## Files

| | |
| --- | --- |
| `build.sh` | fetch + patch upstream, run font-patcher, rename. `--stock` builds the unpatched control |
| `patches/0001-df-icon-and-block-scaling.patch` | the two changes, against upstream `font-patcher` |
| `rename.py` | rewrites the name table to the `MesloLGS NF DF` family |
| `verify.py` | release gate: is this a good font |
| `compare.py` | release gate: is every difference from stock one we intended |
| `fetch-release.sh` | downloads upstream's published faces for `compare.py` section 0 |
| `.work/` | cached upstream checkout, control build, and intermediate output (git-ignored) |
