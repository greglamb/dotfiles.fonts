cask "dotfiles-fonts" do
  version "2.1.0"
  sha256 "7d291ea3cd320156aa63ee68626bff6b20df371f8e5e9d43525711d7da363e07"

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
    Since 2.1.0 the faces carry their own symbols and emoji, drawn from the Noto
    fonts, so characters another font used to supply now come from this one.

    Coming from 1.x: the family is now "MesloLGS NF DF" (it was "MesloLGS NF").
    Point your terminal at the new name, and if the old faces are still in
    ~/Library/Fonts, remove them:

      rm ~/Library/Fonts/MesloLGS\\ NF\\ {Regular,Bold,Italic,Bold\\ Italic}.ttf
  EOS
end
