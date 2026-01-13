#!/usr/bin/env bash
set -euo pipefail

# Update SHA256 hashes in Scoop manifest and Homebrew cask
# Run this after changing font files

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCOOP_MANIFEST="$SCRIPT_DIR/bucket/dotfiles-fonts.json"
HOMEBREW_CASK="$SCRIPT_DIR/Casks/dotfiles-fonts.rb"

# Font files in same order as manifest URLs
FONTS=(
    "MesloLGS NF Regular.ttf"
    "MesloLGS NF Bold.ttf"
    "MesloLGS NF Italic.ttf"
    "MesloLGS NF Bold Italic.ttf"
)

# Generate hashes
HASHES=()
for font in "${FONTS[@]}"; do
    if [[ ! -f "$SCRIPT_DIR/$font" ]]; then
        echo "Error: Font file not found: $font" >&2
        exit 1
    fi
    hash=$(shasum -a 256 "$SCRIPT_DIR/$font" | cut -d' ' -f1)
    HASHES+=("$hash")
    echo "$font: $hash"
done

# Update Scoop manifest using jq
jq --arg h0 "${HASHES[0]}" \
   --arg h1 "${HASHES[1]}" \
   --arg h2 "${HASHES[2]}" \
   --arg h3 "${HASHES[3]}" \
   '.hash = [$h0, $h1, $h2, $h3]' \
   "$SCOOP_MANIFEST" > "$SCOOP_MANIFEST.tmp" && mv "$SCOOP_MANIFEST.tmp" "$SCOOP_MANIFEST"

echo ""
echo "Updated $SCOOP_MANIFEST"

# Update Homebrew cask using sed
# Regular (main sha256)
sed -i '' "s/^  sha256 \"[a-f0-9]*\"/  sha256 \"${HASHES[0]}\"/" "$HOMEBREW_CASK"

# Bold (resource "bold")
sed -i '' "/resource \"bold\"/,/end/ s/sha256 \"[a-f0-9]*\"/sha256 \"${HASHES[1]}\"/" "$HOMEBREW_CASK"

# Italic (resource "italic")
sed -i '' "/resource \"italic\"/,/end/ s/sha256 \"[a-f0-9]*\"/sha256 \"${HASHES[2]}\"/" "$HOMEBREW_CASK"

# Bold Italic (resource "bold-italic")
sed -i '' "/resource \"bold-italic\"/,/end/ s/sha256 \"[a-f0-9]*\"/sha256 \"${HASHES[3]}\"/" "$HOMEBREW_CASK"

echo "Updated $HOMEBREW_CASK"
