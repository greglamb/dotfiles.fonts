#!/usr/bin/env bash
set -euo pipefail

# Download the Noto fonts that build/fill.py copies glyphs from, pinned by
# version and sha256, into build/.work/sources.
#
#   ./build/fetch-sources.sh
#
# build.sh runs this itself; it is separate so the pins live in one place and
# so the fill stage can be re-run without a network (see build.sh --fill-only).
#
# Sources
# -------
# Noto Sans Symbols and Noto Sans Symbols 2 come from notofonts/symbols release
# archives; we keep the unhinted faces (fill.py drops instructions anyway).
# Noto Color Emoji is the COLRv1 build in googlefonts/noto-emoji, and Noto
# Emoji is the monochrome variable font from google/fonts, both fetched from
# the repository at a pinned commit because those releases carry no assets.
#
# Every file is licensed under the SIL Open Font License 1.1; the notice we
# ship with the built faces is "Noto License.txt" in the repository root.
# Bumping a pin means checking that notice still names the right copyright.
#
# To upgrade: change the version, download once, paste in the new sha256.

SYMBOLS_VERSION="v2.003"
SYMBOLS_SHA256="0c113cdcf6c31d050b80dac39fba2d804a6985281012e76e9220c0a00da007f3"

SYMBOLS2_VERSION="v2.008"
SYMBOLS2_SHA256="346c930bbe8eb946701a05c54e9c11a2094dee1d93c387bf1771c0a3e335688f"

# googlefonts/noto-emoji tag v2.051
COLOR_EMOJI_COMMIT="8998f5dd683424a73e2314a8c1f1e359c19e8742"
COLOR_EMOJI_SHA256="0ae57fe58645638523ba35f388d93739d292539a9acb84df5700c81b1e1a28d2"

# google/fonts main, Noto Emoji 3.002
MONO_EMOJI_COMMIT="a54f7446f84a1125ef6bf08baa46f3639e8905e0"
MONO_EMOJI_SHA256="de6c18832938afc99caf132b39d6a30a19bac7f2e812e28db2535b4608d27551"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="$SCRIPT_DIR/.work"
DEST="$WORK_DIR/sources"
STAMP="$DEST/.pins"

# What fill.py expects to find in $DEST.
WANT=(
    "NotoSansSymbols-Regular.ttf"
    "NotoSansSymbols-Bold.ttf"
    "NotoSansSymbols2-Regular.ttf"
    "Noto-COLRv1.ttf"
    "NotoEmoji[wght].ttf"
)

PINS="symbols=$SYMBOLS_VERSION symbols2=$SYMBOLS2_VERSION color-emoji=$COLOR_EMOJI_COMMIT mono-emoji=$MONO_EMOJI_COMMIT"

sha256() {
    if command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$1" | cut -d' ' -f1
    else
        sha256sum "$1" | cut -d' ' -f1
    fi
}

fetch() {
    # fetch URL DEST SHA256
    echo "==> $1"
    curl -fsSL --retry 3 -o "$2" "$1"
    local have
    have="$(sha256 "$2")"
    if [[ "$have" != "$3" ]]; then
        echo "error: sha256 mismatch for $(basename "$2")" >&2
        echo "  want $3" >&2
        echo "  have $have" >&2
        rm -f "$2"
        exit 1
    fi
}

if [[ -f "$STAMP" ]] && [[ "$(cat "$STAMP")" == "$PINS" ]]; then
    have_all=1
    for face in "${WANT[@]}"; do
        [[ -f "$DEST/$face" ]] || have_all=0
    done
    if [[ "$have_all" == "1" ]]; then
        echo "Already have the pinned sources in $DEST"
        exit 0
    fi
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

rm -rf "$DEST"
mkdir -p "$DEST"

fetch "https://github.com/notofonts/symbols/releases/download/NotoSansSymbols-${SYMBOLS_VERSION}/NotoSansSymbols-${SYMBOLS_VERSION}.zip" \
    "$TMP/symbols.zip" "$SYMBOLS_SHA256"
unzip -q -o -j "$TMP/symbols.zip" \
    "NotoSansSymbols/unhinted/ttf/NotoSansSymbols-Regular.ttf" \
    "NotoSansSymbols/unhinted/ttf/NotoSansSymbols-Bold.ttf" \
    -d "$DEST"

fetch "https://github.com/notofonts/symbols/releases/download/NotoSansSymbols2-${SYMBOLS2_VERSION}/NotoSansSymbols2-${SYMBOLS2_VERSION}.zip" \
    "$TMP/symbols2.zip" "$SYMBOLS2_SHA256"
unzip -q -o -j "$TMP/symbols2.zip" \
    "NotoSansSymbols2/unhinted/ttf/NotoSansSymbols2-Regular.ttf" \
    -d "$DEST"

fetch "https://raw.githubusercontent.com/googlefonts/noto-emoji/${COLOR_EMOJI_COMMIT}/fonts/Noto-COLRv1.ttf" \
    "$DEST/Noto-COLRv1.ttf" "$COLOR_EMOJI_SHA256"

fetch "https://raw.githubusercontent.com/google/fonts/${MONO_EMOJI_COMMIT}/ofl/notoemoji/NotoEmoji%5Bwght%5D.ttf" \
    "$DEST/NotoEmoji[wght].ttf" "$MONO_EMOJI_SHA256"

for face in "${WANT[@]}"; do
    if [[ ! -f "$DEST/$face" ]]; then
        echo "error: $face did not arrive" >&2
        exit 1
    fi
done

printf '%s\n' "$PINS" > "$STAMP"
echo "==> ${#WANT[@]} source faces in $DEST"
