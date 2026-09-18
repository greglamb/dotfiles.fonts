# dotfiles.fonts

MesloLGS NF DF font family - a Nerd Font patched version of Meslo, optimized for
terminal and editor use with powerline/icon support.

Built from upstream Nerd Fonts sources by [`build/build.sh`](build/), with two
glyph-geometry changes ported from romkatv's fork: icons are scaled to 1.2 cell
widths instead of being clamped to one, and box-drawing glyphs overhang the cell
so prompt frames have no seams. A third stage then fills the codepoints Nerd
Fonts leaves unmapped: monochrome symbols from Noto Sans Symbols / Symbols 2
and Noto Emoji wherever Segoe UI Symbol would draw one, and colour emoji from
Noto Color Emoji as COLRv0 layers plus an SVG table (between them, what
Windows Terminal, macOS, Linux terminals and Chromium render) for the rest and
for whatever Unicode shows as an emoji by default, including the ZWJ sequences
and the U+FE0F presentation selector that turns any of the monochrome ones into
its colour form. See [build/README.md](build/README.md) for the rules, and the
two override lists there for changing single characters.

See [dotfiles.fonts-web](https://github.com/greglamb/dotfiles.fonts-web) for Chrome OS support

## What changes in 2.1.0

2.1.0 adds the fill stage; the family name and everything 2.0.0 had are
unchanged. What you will notice:

- **About 2,900 more characters** (per face; a few hundred more in the italic
  faces), from the Noto fonts: arrows, dingbats, geometric and technical
  symbols in monochrome, and emoji in colour. Characters that used to fall
  back to another installed font now come from this one, in Noto's style: on
  macOS that means Noto's emoji rather than Apple's. Flags, and emoji newer
  than Unicode 16, still come from your system emoji font.
- **Skin-tone and hair-style variants show as the default emoji**: 👍🏽 draws
  as 👍 and 👩🏽‍💻 as 👩‍💻. They are left out to keep the size down.
- **Emoji stay colour where Unicode says they are emoji** (🌈 ⏰ ✅), and
  text-style symbols stay monochrome (ℹ ⏸), one U+FE0F away from colour.
  Anything that looks wrong can be switched per character: see
  [the override lists](build/README.md#filling-the-gaps).
- **Each face grows from 3.0 MB to 9.2 MB**, most of it the colour emoji.
- **Alacritty is expected to show the added emoji blank**, since it has no
  renderer for the `SVG` table they carry (not yet tried); everything else in
  the face is unaffected.
- **The license is now stated as SIL OFL 1.1 for the faces as a whole** -- see
  [License](#license).

## Upgrading from 1.x

2.0.0 renames the family from `MesloLGS NF` to `MesloLGS NF DF` and moves from a
vendored Nerd Fonts 2.3.3 binary to a build against 3.5.1. Point your terminal,
editor and prompt config at the new name, then remove the old faces --
`brew uninstall --cask dotfiles-fonts` if you installed 1.x through this cask,
or delete `MesloLGS NF Regular.ttf`, `MesloLGS NF Bold.ttf`, `MesloLGS NF
Italic.ttf` and `MesloLGS NF Bold Italic.ttf` from `~/Library/Fonts` if you
installed them by hand. Not `MesloLGS NF *.ttf`: that also matches the
`MesloLGS NF DF` faces. Nothing removes them for you, and leaving them
installed is harmless beyond the clutter.

Coverage against 1.x: +1829 codepoints (Font Awesome 6, braille, current
Material Design and codicons), -2066 (the legacy Material Design aliases
upstream retired in 3.4.0, all of which have replacements in the new range).

## Installation

### macOS (Homebrew)

```bash
# Add this tap (one-time)
brew tap greglamb/fonts https://github.com/greglamb/dotfiles.fonts

# Install fonts
brew install --cask greglamb/fonts/dotfiles-fonts

# Uninstall
brew uninstall --cask dotfiles-fonts
```

If the fonts are already in `~/Library/Fonts`, add `--adopt` so Homebrew takes
ownership of the existing files instead of refusing to overwrite them.

#### Tap trust

Homebrew requires third-party taps to be trusted. Installing by the
fully-qualified name above trusts this cask automatically, so nothing extra is
needed for the interactive flow.

For an unattended bootstrap, trust it up front — **but tap first**:

```bash
brew tap greglamb/fonts https://github.com/greglamb/dotfiles.fonts
brew trust --cask greglamb/fonts/dotfiles-fonts
```

Order matters. Because the tap is added with an explicit remote URL, Homebrew
keys trust by that URL (`https://github.com/greglamb/dotfiles.fonts/dotfiles-fonts`).
It can only resolve that key once the tap exists locally — run `brew trust`
first and it records the short name instead, which the trust check will not
match. `brew untrust --cask greglamb/fonts/dotfiles-fonts` removes either form.

Trust lives entirely on the client, in `$XDG_CONFIG_HOME/homebrew/trust.json`
or `~/.homebrew/trust.json`. There is nothing this repo can ship to pre-trust
itself.

### Windows (Scoop)

```powershell
# Add this bucket (one-time)
scoop bucket add dotfiles-fonts https://github.com/greglamb/dotfiles.fonts

# Install fonts
scoop install dotfiles-fonts

# Uninstall
scoop uninstall dotfiles-fonts
```

Fonts are installed per-user (no admin required).

## Included Fonts

- MesloLGS NF DF Regular
- MesloLGS NF DF Bold
- MesloLGS NF DF Italic
- MesloLGS NF DF Bold Italic

## License

The faces are distributed under the SIL Open Font License 1.1 as a whole:
they contain glyphs copied from OFL fonts, and the OFL asks that a font built
with those be distributed under it. Each part keeps its own notices as well:

| part | license | notices |
| --- | --- | --- |
| Meslo LG S: the Latin text and metrics | Apache License 2.0 | [MesloLGS NF DF License.txt](MesloLGS%20NF%20DF%20License.txt) |
| Nerd Fonts glyph sets: icons, powerline, braille | MIT, CC BY 4.0, Apache 2.0, OFL 1.1, public domain, by set | [Nerd Fonts License.txt](Nerd%20Fonts%20License.txt) |
| Noto: the symbols and emoji the fill stage adds | SIL OFL 1.1 | [Noto License.txt](Noto%20License.txt) |

The build scripts in this repository are not part of the fonts.
