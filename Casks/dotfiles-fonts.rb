cask "dotfiles-fonts" do
  version "1.0.1"
  sha256 "d97946186e97f8d7c0139e8983abf40a1d2d086924f2c5dbf1c29bd8f2c6e57d"

  url "https://raw.githubusercontent.com/greglamb/dotfiles.fonts/main/MesloLGS%20NF%20Regular.ttf"
  name "MesloLGS NF"
  desc "Nerd Font patched Meslo for terminals and editors"
  homepage "https://github.com/greglamb/dotfiles.fonts"

  font "MesloLGS NF Regular.ttf"

  # Additional font files
  resource "bold" do
    url "https://raw.githubusercontent.com/greglamb/dotfiles.fonts/main/MesloLGS%20NF%20Bold.ttf"
    sha256 "b6c0199cf7c7483c8343ea020658925e6de0aeb318b89908152fcb4d19226003"
  end

  resource "italic" do
    url "https://raw.githubusercontent.com/greglamb/dotfiles.fonts/main/MesloLGS%20NF%20Italic.ttf"
    sha256 "6f357bcbe2597704e157a915625928bca38364a89c22a4ac36e7a116dcd392ef"
  end

  resource "bold-italic" do
    url "https://raw.githubusercontent.com/greglamb/dotfiles.fonts/main/MesloLGS%20NF%20Bold%20Italic.ttf"
    sha256 "56b4131adecec052c4b324efb818dd326d586dbc316fc68f98f1cae2eb8d1220"
  end

  postflight do
    resource("bold").stage { FileUtils.mv("MesloLGS NF Bold.ttf", "#{Dir.home}/Library/Fonts/") }
    resource("italic").stage { FileUtils.mv("MesloLGS NF Italic.ttf", "#{Dir.home}/Library/Fonts/") }
    resource("bold-italic").stage { FileUtils.mv("MesloLGS NF Bold Italic.ttf", "#{Dir.home}/Library/Fonts/") }
  end

  uninstall delete: [
    "~/Library/Fonts/MesloLGS NF Regular.ttf",
    "~/Library/Fonts/MesloLGS NF Bold.ttf",
    "~/Library/Fonts/MesloLGS NF Italic.ttf",
    "~/Library/Fonts/MesloLGS NF Bold Italic.ttf",
  ]
end
