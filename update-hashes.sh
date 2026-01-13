#!/usr/bin/env bash
set -euo pipefail

# Update SHA256 hashes in the Scoop manifest
# Run this after changing font files

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFEST="$SCRIPT_DIR/bucket/dotfiles-fonts.json"

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

# Update manifest using jq
jq --arg h0 "${HASHES[0]}" \
   --arg h1 "${HASHES[1]}" \
   --arg h2 "${HASHES[2]}" \
   --arg h3 "${HASHES[3]}" \
   '.hash = [$h0, $h1, $h2, $h3]' \
   "$MANIFEST" > "$MANIFEST.tmp" && mv "$MANIFEST.tmp" "$MANIFEST"

echo ""
echo "Updated $MANIFEST"
