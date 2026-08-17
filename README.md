# dotfiles.fonts

MesloLGS NF font family - a Nerd Font patched version of Meslo, optimized for terminal and editor use with powerline/icon support.

See [MesloLGSNF-web-fonts](https://github.com/greglamb/MesloLGSNF-web-fonts) for Chrome OS support

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

- MesloLGS NF Regular
- MesloLGS NF Bold
- MesloLGS NF Italic
- MesloLGS NF Bold Italic

## License

Apache License 2.0 - See [MesloLGS NF License.txt](MesloLGS%20NF%20License.txt)
