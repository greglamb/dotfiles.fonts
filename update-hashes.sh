#!/usr/bin/env bash
set -euo pipefail

# Update SHA256 hashes in Scoop manifest and Homebrew cask.
#
# Workflow when releasing a new version:
#   1. bump `version` in Casks/dotfiles-fonts.rb and bucket/dotfiles-fonts.json
#   2. commit and push to main
#   3. git tag v<version> && git push origin v<version>
#   4. run this script, then commit the updated hashes
#
# The cask pins to the *tag* tarball, not a commit tarball. That matters: a tag
# is immutable, so committing the hash this script writes does not invalidate
# the thing it hashed. Pinning to origin/main could never converge, because the
# cask lives in the repo it was hashing.
#
# The cask's url and font paths both interpolate #{version}, so only the sha256
# needs rewriting here.

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

# --- Homebrew cask: pin to the release tag tarball ---
echo ""

VERSION=$(sed -nE 's|^  version "(.*)"$|\1|p' "$HOMEBREW_CASK")
if [[ -z "$VERSION" ]]; then
    echo "Error: could not read version from $HOMEBREW_CASK" >&2
    exit 1
fi
TAG="v${VERSION}"
# GitHub strips a leading "v" from the tag when naming the archive's root directory.
PREFIX="$(basename "$REPO_SLUG")-${VERSION}"
echo "Cask version $VERSION -> tag $TAG, archive prefix $PREFIX/"

git -C "$SCRIPT_DIR" fetch origin --tags --quiet
if ! git -C "$SCRIPT_DIR" rev-parse -q --verify "refs/tags/${TAG}" >/dev/null; then
    echo "Error: tag ${TAG} does not exist. Push the version bump, then:" >&2
    echo "  git tag ${TAG} && git push origin ${TAG}" >&2
    exit 1
fi

TARBALL_URL="https://github.com/${REPO_SLUG}/archive/refs/tags/${TAG}.tar.gz"
TARBALL_TMP=$(mktemp)
trap 'rm -f "$TARBALL_TMP"' EXIT

echo "Downloading $TARBALL_URL"
curl -fsSL -o "$TARBALL_TMP" "$TARBALL_URL"

# Guard against the bug this packaging replaced: confirm every font the cask
# declares is actually at the path the cask expects inside the archive.
LISTING=$(tar tzf "$TARBALL_TMP")
for font in "${FONTS[@]}"; do
    if ! grep -Fqx "${PREFIX}/${font}" <<<"$LISTING"; then
        echo "Error: ${PREFIX}/${font} is not in the tag tarball." >&2
        echo "The cask's font paths would not resolve. Aborting." >&2
        exit 1
    fi
done
echo "Verified all ${#FONTS[@]} fonts are at ${PREFIX}/ inside the tarball"

TARBALL_SHA=$(shasum -a 256 "$TARBALL_TMP" | cut -d' ' -f1)
echo "Tarball sha256 = $TARBALL_SHA"

sed_i -E "s|^  sha256 \"[a-f0-9]+\"|  sha256 \"${TARBALL_SHA}\"|" "$HOMEBREW_CASK"

echo "Updated $HOMEBREW_CASK"
echo ""
echo "NOTE: Commit and push the hash changes so users see the new pin."
