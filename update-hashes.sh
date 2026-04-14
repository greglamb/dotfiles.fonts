#!/usr/bin/env bash
set -euo pipefail

# Update SHA256 hashes in Scoop manifest and Homebrew cask
# Run this after changing font files and pushing the commit to GitHub.
#
# The Homebrew cask pins to a specific commit tarball on GitHub, so this
# script fetches the latest origin/main commit SHA, downloads the tarball,
# and rewrites the cask's URL + sha256 to match.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCOOP_MANIFEST="$SCRIPT_DIR/bucket/dotfiles-fonts.json"
HOMEBREW_CASK="$SCRIPT_DIR/Casks/dotfiles-fonts.rb"
REPO_SLUG="greglamb/dotfiles.fonts"

# Portable in-place sed (GNU sed vs BSD sed)
sed_i() {
    if sed --version >/dev/null 2>&1; then
        sed -i "$@"
    else
        sed -i '' "$@"
    fi
}

# Font files in same order as manifest URLs
FONTS=(
    "MesloLGS NF Regular.ttf"
    "MesloLGS NF Bold.ttf"
    "MesloLGS NF Italic.ttf"
    "MesloLGS NF Bold Italic.ttf"
)

# Generate per-font hashes (used by Scoop)
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

# --- Homebrew cask: pin to latest origin/main commit tarball ---
echo ""
echo "Fetching latest origin/main commit for Homebrew cask pin..."

git -C "$SCRIPT_DIR" fetch origin main --quiet
COMMIT_SHA=$(git -C "$SCRIPT_DIR" rev-parse origin/main)
echo "origin/main = $COMMIT_SHA"

TARBALL_URL="https://github.com/${REPO_SLUG}/archive/${COMMIT_SHA}.tar.gz"
TARBALL_TMP=$(mktemp)
trap 'rm -f "$TARBALL_TMP"' EXIT

echo "Downloading $TARBALL_URL"
curl -fsSL -o "$TARBALL_TMP" "$TARBALL_URL"
TARBALL_SHA=$(shasum -a 256 "$TARBALL_TMP" | cut -d' ' -f1)
echo "Tarball sha256 = $TARBALL_SHA"

# Rewrite the cask's sha256 and archive URL
sed_i -E "s|^  sha256 \"[a-f0-9]+\"|  sha256 \"${TARBALL_SHA}\"|" "$HOMEBREW_CASK"
sed_i -E "s|archive/[a-f0-9]{40}\.tar\.gz|archive/${COMMIT_SHA}.tar.gz|" "$HOMEBREW_CASK"

echo "Updated $HOMEBREW_CASK"
echo ""
echo "NOTE: Commit and push the cask changes so users see the new pin."
