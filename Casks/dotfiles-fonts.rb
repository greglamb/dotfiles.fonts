cask "dotfiles-fonts" do
  version "1.0.1"
  sha256 "6438aa3ed4e8cadeba32e7f05bd444680a6353625b4647abab889a44cbb591a8"

  url "https://github.com/greglamb/dotfiles.fonts/archive/9f4c7873918c19abbd9c186106107cd7ea7aafff.tar.gz",
      verified: "github.com/greglamb/dotfiles.fonts/"
  name "MesloLGS NF"
  desc "Nerd Font patched Meslo for terminals and editors"
  homepage "https://github.com/greglamb/dotfiles.fonts"

  font "MesloLGS NF Regular.ttf"
  font "MesloLGS NF Bold.ttf"
  font "MesloLGS NF Italic.ttf"
  font "MesloLGS NF Bold Italic.ttf"
end
