cask "dotfiles-fonts" do
  version "1.0.2"
  sha256 "0000000000000000000000000000000000000000000000000000000000000000"

  url "https://github.com/greglamb/dotfiles.fonts/archive/refs/tags/v#{version}.tar.gz"
  name "MesloLGS NF"
  desc "Nerd Font patched Meslo for terminals and editors"
  homepage "https://github.com/greglamb/dotfiles.fonts"

  # GitHub source archives extract into a "<repo>-<ref>" wrapper directory, and
  # `font` paths resolve against the staged root -- so the prefix is required.
  # For the tag "v1.0.2" GitHub strips the leading "v", giving "dotfiles.fonts-1.0.2".
  font "dotfiles.fonts-#{version}/MesloLGS NF Regular.ttf"
  font "dotfiles.fonts-#{version}/MesloLGS NF Bold.ttf"
  font "dotfiles.fonts-#{version}/MesloLGS NF Italic.ttf"
  font "dotfiles.fonts-#{version}/MesloLGS NF Bold Italic.ttf"
end
