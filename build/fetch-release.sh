#!/usr/bin/env bash
set -euo pipefail

# Download the Meslo faces from the pinned Nerd Fonts release, so compare.py can
# check our control build against the binaries upstream actually published.
#
#   ./build/fetch-release.sh
#   python3 build/compare.py --upstream build/.work/upstream-release
#
# This is the check that says our toolchain is faithful: build without --df and
# the result should equal upstream's own file, glyph for glyph. Once that holds,
# every difference between what we ship and what upstream ships is attributable
# to our patch, and compare.py's other sections can be read at face value.
#
# The release asset is ~110MB and holds every Meslo variant; we keep the four
# Mono faces our build corresponds to and drop the rest.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="$SCRIPT_DIR/.work"
DEST="$WORK_DIR/upstream-release"

# Read the pin from build.sh rather than repeating it, so they cannot drift.
NF_VERSION="$(sed -nE 's/^NF_VERSION="(.*)"$/\1/p' "$SCRIPT_DIR/build.sh")"
if [[ -z "$NF_VERSION" ]]; then
    echo "error: could not read NF_VERSION from build.sh" >&2
    exit 1
fi

FACES=(
    "MesloLGSNerdFontMono-Regular.ttf"
    "MesloLGSNerdFontMono-Bold.ttf"
    "MesloLGSNerdFontMono-Italic.ttf"
    "MesloLGSNerdFontMono-BoldItalic.ttf"
)

STAMP="$DEST/.version"
if [[ -f "$STAMP" ]] && [[ "$(cat "$STAMP")" == "$NF_VERSION" ]]; then
    have_all=1
    for face in "${FACES[@]}"; do
        [[ -f "$DEST/$face" ]] || have_all=0
    done
    if [[ "$have_all" == "1" ]]; then
        echo "Already have $NF_VERSION in $DEST"
        exit 0
    fi
fi

URL="https://github.com/ryanoasis/nerd-fonts/releases/download/${NF_VERSION}/Meslo.zip"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "==> Downloading $URL"
curl -fsSL -o "$TMP/Meslo.zip" "$URL"

echo "==> Extracting ${#FACES[@]} faces"
rm -rf "$DEST"
mkdir -p "$DEST"
unzip -o -q "$TMP/Meslo.zip" -d "$DEST" "${FACES[@]}"

for face in "${FACES[@]}"; do
    if [[ ! -f "$DEST/$face" ]]; then
        echo "error: $face was not in the release archive" >&2
        exit 1
    fi
done

printf '%s\n' "$NF_VERSION" > "$STAMP"
echo "==> $NF_VERSION faces in $DEST"
