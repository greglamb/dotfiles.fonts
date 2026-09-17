# dotfiles.fonts

MesloLGS NF DF font family - a Nerd Font patched version of Meslo, optimized for
terminal and editor use with powerline/icon support.

Built from upstream Nerd Fonts sources by [`build/build.sh`](build/), with two
glyph-geometry changes ported from romkatv's fork: icons are scaled to 1.2 cell
widths instead of being clamped to one, and box-drawing glyphs overhang the cell
so prompt frames have no seams. See [build/README.md](build/README.md).

See [MesloLGSNF-web-fonts](https://github.com/greglamb/MesloLGSNF-web-fonts) for Chrome OS support

## Upgrading from 1.x

2.0.0 renames the family from `MesloLGS NF` to `MesloLGS NF DF` and moves from a
vendored Nerd Fonts 2.3.3 binary to a build against 3.5.1. Point your terminal,
editor and prompt config at the new name, then remove the old faces --
`brew uninstall --cask dotfiles-fonts` if you installed 1.x through this cask,
or delete `MesloLGS NF *.ttf` from `~/Library/Fonts` if you installed them by
hand. Nothing removes them for you, and leaving them installed is harmless
beyond the clutter.

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

Apache License 2.0 - See [MesloLGS NF DF License.txt](MesloLGS%20NF%20DF%20License.txt)
