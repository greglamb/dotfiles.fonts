cask "dotfiles-fonts" do
  version "2.0.0"
  sha256 "0000000000000000000000000000000000000000000000000000000000000000"

  url "https://github.com/greglamb/dotfiles.fonts/archive/refs/tags/v#{version}.tar.gz"
  name "MesloLGS NF DF"
  desc "Nerd Font patched Meslo for terminals and editors"
  homepage "https://github.com/greglamb/dotfiles.fonts"

  # GitHub source archives extract into a "<repo>-<ref>" wrapper directory, and
  # `font` paths resolve against the staged root -- so the prefix is required.
  # For the tag "v2.0.0" GitHub strips the leading "v", giving "dotfiles.fonts-2.0.0".
  font "dotfiles.fonts-#{version}/MesloLGS NF DF Regular.ttf"
  font "dotfiles.fonts-#{version}/MesloLGS NF DF Bold.ttf"
  font "dotfiles.fonts-#{version}/MesloLGS NF DF Italic.ttf"
  font "dotfiles.fonts-#{version}/MesloLGS NF DF Bold Italic.ttf"

  caveats <<~EOS
    This release renames the family from "MesloLGS NF" to "MesloLGS NF DF".
    Anything still configured for the old name falls back to another font until
    you point it at "MesloLGS NF DF". The old faces are not removed for you:

      brew uninstall --cask dotfiles-fonts  # if you installed 1.x via this cask
      rm ~/Library/Fonts/MesloLGS\\ NF*.ttf   # if you installed them by hand
  EOS
end
