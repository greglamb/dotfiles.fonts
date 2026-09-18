#!/usr/bin/env bash
set -euo pipefail

# Build the MesloLGS NF DF family from upstream Nerd Fonts sources.
#
#   ./build/build.sh              # build in Docker (nothing to install)
#   DF_NATIVE=1 ./build/build.sh  # build with the local fontforge + fonttools
#   ./build/build.sh --stock      # build WITHOUT our patch, into build/.work/stock
#   ./build/build.sh --fill-only  # re-run only the gap fill on the last build
#
# The four .ttf files land in the repository root, replacing the vendored ones.
# Run ./update-hashes.sh afterwards, per the release workflow in that script.
#
# --fill-only skips font-patcher and reruns build/fill.py over the renamed
# faces the previous build left in build/.work/renamed. Patching takes minutes
# and needs fontforge; the fill takes seconds and needs only fonttools, so this
# is the loop for working on fill.py, the Segoe charset or the source pins.
#
# --stock produces the same four faces as upstream would, with neither --df nor
# the rename. It is the control build: build/compare.py diffs it against ours so
# an upgrade can show that our patch still changes exactly what it is supposed
# to and nothing else. Nothing in the repository root is touched.
#
# What this builds
# ----------------
# Upstream Nerd Fonts, pinned to $NF_VERSION, patched with
# build/patches/*.patch and run over "Meslo LG S for Powerline" with
# `--mono --complete --df`. The DF patch carries the two glyph-geometry
# deviations that the original MesloLGS NF had (see the patch header); `--df`
# is the flag it adds, so the same checkout still builds stock output without
# it. build/rename.py then renames the family to "MesloLGS NF DF", and
# build/fill.py fills the coverage gaps that are left from the Noto symbol and
# emoji fonts (build/fetch-sources.sh pins those) -- see build/README.md for
# the rule it follows.
#
# The upstream source faces are byte-identical across Nerd Fonts releases and
# to the ones romkatv/nerd-fonts used, so the Latin glyphs do not move when
# this is rebuilt against a newer $NF_VERSION.

NF_VERSION="v3.5.1"
NF_REPO="https://github.com/ryanoasis/nerd-fonts.git"

# Docker image used for the containerised build. Needs fontforge with Python
# bindings; Ubuntu 24.04 ships 20230101, which font-patcher accepts.
DF_IMAGE="${DF_IMAGE:-ubuntu:24.04}"
# fontforge's arm64 build draws ~300 Nerd Font icons differently from the
# amd64 one upstream releases with (other point counts, other start points),
# so the build runs as amd64 everywhere -- emulated on Apple Silicon, about
# four minutes -- and compare.py section 0 can hold on any machine.
DF_PLATFORM="${DF_PLATFORM:-linux/amd64}"

# Source face -> RIBBI style token understood by rename.py.
STYLES="Regular Bold Italic BoldItalic"

source_face() {
    case "$1" in
        Regular)    echo "Meslo LG S Regular for Powerline.ttf" ;;
        Bold)       echo "Meslo LG S Bold for Powerline.ttf" ;;
        Italic)     echo "Meslo LG S Italic for Powerline.ttf" ;;
        BoldItalic) echo "Meslo LG S Bold Italic for Powerline.ttf" ;;
    esac
}

# Name font-patcher gives its output, which rename.py then reads.
patched_face() {
    echo "MesloLGSNerdFontMono-$1.ttf"
}

# Name we ship.
output_face() {
    case "$1" in
        Regular)    echo "MesloLGS NF DF Regular.ttf" ;;
        Bold)       echo "MesloLGS NF DF Bold.ttf" ;;
        Italic)     echo "MesloLGS NF DF Italic.ttf" ;;
        BoldItalic) echo "MesloLGS NF DF Bold Italic.ttf" ;;
    esac
}

# --stock builds the unpatched control; --fill-only reruns stage 3. See the header.
DF_STOCK="${DF_STOCK:-0}"
DF_FILL_ONLY="${DF_FILL_ONLY:-0}"
# Extra arguments for build/fill.py, e.g. "--emoji-format both" or
# "--no-sequences"; see `python3 build/fill.py --help`.
DF_FILL_ARGS="${DF_FILL_ARGS:-}"
for arg in "$@"; do
    case "$arg" in
        --stock) DF_STOCK=1 ;;
        --fill-only) DF_FILL_ONLY=1 ;;
        *) echo "error: unknown argument: $arg" >&2; exit 2 ;;
    esac
done
if [[ "$DF_STOCK" == "1" && "$DF_FILL_ONLY" == "1" ]]; then
    echo "error: --stock and --fill-only are exclusive; the control build has no fill" >&2
    exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
WORK_DIR="$SCRIPT_DIR/.work"

# ---------------------------------------------------------------------------
# Stage 1: fetch and patch upstream
# ---------------------------------------------------------------------------

prepare_upstream() {
    local src="$WORK_DIR/nerd-fonts"

    if [[ -d "$src/.git" ]]; then
        local have
        have="$(git -C "$src" describe --tags --exact-match 2>/dev/null || echo "")"
        if [[ "$have" != "$NF_VERSION" ]]; then
            echo "==> Cached checkout is $have, want $NF_VERSION; refetching"
            rm -rf "$src"
        fi
    fi

    if [[ ! -d "$src/.git" ]]; then
        echo "==> Fetching Nerd Fonts $NF_VERSION"
        mkdir -p "$WORK_DIR"
        # Blobless + sparse: the full history and every patched font in that
        # repo is several GB, and we need four source faces and the glyph sets.
        git clone --depth=1 --branch "$NF_VERSION" --filter=blob:none --no-checkout \
            "$NF_REPO" "$src"
        git -C "$src" sparse-checkout init --no-cone
        git -C "$src" sparse-checkout set \
            "/font-patcher" \
            "/glyphnames.json" \
            "/bin/scripts/name_parser/*" \
            "/bin/scripts/braille/*" \
            "/src/glyphs/*" \
            "/src/unpatched-fonts/Meslo/*" \
            "/LICENSE"
        git -C "$src" checkout
    fi

    echo "==> Applying DF patches"
    git -C "$src" checkout -- font-patcher
    local patch
    for patch in "$SCRIPT_DIR"/patches/*.patch; do
        echo "    $(basename "$patch")"
        git -C "$src" apply --verbose "$patch" 2>&1 | sed 's/^/      /'
    done
}

# ---------------------------------------------------------------------------
# Stage 2: patch the fonts
# ---------------------------------------------------------------------------

# Picks an interpreter that can `import fontforge`. On Debian/Ubuntu the
# bindings install into the distro python3 only, which is not always the
# python3 first on PATH.
find_fontforge_python() {
    local candidate
    for candidate in /usr/bin/python3 /usr/bin/python3.12 /usr/bin/python3.11 python3; do
        if command -v "$candidate" >/dev/null 2>&1 &&
           "$candidate" -c "import fontforge, psMat" >/dev/null 2>&1; then
            echo "$candidate"
            return 0
        fi
    done
    return 1
}

# The fill stage only needs fontTools, so --fill-only can run without fontforge.
find_fonttools_python() {
    local candidate
    for candidate in python3 /usr/bin/python3 /usr/bin/python3.12 /usr/bin/python3.11; do
        if command -v "$candidate" >/dev/null 2>&1 &&
           "$candidate" -c "import fontTools" >/dev/null 2>&1; then
            echo "$candidate"
            return 0
        fi
    done
    return 1
}

build_native() {
    local src="$WORK_DIR/nerd-fonts"
    local out="$WORK_DIR/out"
    if [[ "$DF_STOCK" == "1" ]]; then
        out="$WORK_DIR/stock"
    fi
    local py
    if ! py="$(find_fontforge_python)"; then
        echo "error: no python3 with the fontforge module." >&2
        echo "  Debian/Ubuntu: sudo apt install fontforge python3-fontforge" >&2
        echo "  macOS:         brew install fontforge" >&2
        exit 1
    fi
    if ! "$py" -c "import fontTools" >/dev/null 2>&1; then
        echo "error: $py cannot import fontTools (pip install fonttools)" >&2
        exit 1
    fi

    rm -rf "$out"
    mkdir -p "$out"

    # The control build runs the same patched font-patcher without --df, so a
    # difference between the two can only come from the flag, never from a
    # different patcher or a different upstream revision.
    local df_flag="--df"
    if [[ "$DF_STOCK" == "1" ]]; then
        df_flag=""
    fi

    local style
    for style in $STYLES; do
        echo "==> Patching $style"
        ( cd "$src" && "$py" ./font-patcher \
            "src/unpatched-fonts/Meslo/S/$(source_face "$style")" \
            --quiet --mono --complete $df_flag --ext ttf --out "$out" )
    done

    if [[ "$DF_STOCK" == "1" ]]; then
        echo "==> Stock control build left in $out (not renamed, repo untouched)"
        return 0
    fi

    echo "==> Renaming to MesloLGS NF DF"
    local renamed="$WORK_DIR/renamed"
    rm -rf "$renamed"
    mkdir -p "$renamed"
    for style in $STYLES; do
        "$py" "$SCRIPT_DIR/rename.py" \
            "$out/$(patched_face "$style")" \
            "$renamed/$(output_face "$style")" \
            "$style"
    done

    fill_faces "$py"
}

# ---------------------------------------------------------------------------
# Stage 3: fill the coverage gaps
# ---------------------------------------------------------------------------

# Reads build/.work/renamed, writes the shipped faces into the repository root
# and a manifest per face into build/.work/fill, which verify.py and compare.py
# read. The rule, the sources and their licenses are documented in fill.py and
# build/README.md.
fill_faces() {
    local py="$1"
    local renamed="$WORK_DIR/renamed"
    local manifests="$WORK_DIR/fill"
    local style

    for style in $STYLES; do
        if [[ ! -f "$renamed/$(output_face "$style")" ]]; then
            echo "error: no renamed face for $style in $renamed (run a full build first)" >&2
            exit 1
        fi
    done

    "$SCRIPT_DIR/fetch-sources.sh"

    echo "==> Filling coverage gaps from Noto${DF_FILL_ARGS:+ ($DF_FILL_ARGS)}"
    rm -rf "$manifests"
    mkdir -p "$manifests"
    for style in $STYLES; do
        # shellcheck disable=SC2086  # DF_FILL_ARGS is a list of arguments
        "$py" "$SCRIPT_DIR/fill.py" \
            "$renamed/$(output_face "$style")" \
            "$REPO_DIR/$(output_face "$style")" \
            "$style" \
            --sources "$WORK_DIR/sources" \
            --manifest "$manifests/$style.json" \
            $DF_FILL_ARGS
    done
}

build_docker() {
    echo "==> Building in $DF_IMAGE ($DF_PLATFORM)"
    # Mount the whole repo so the script sees the same layout it does natively:
    # /df/build/build.sh writing its output to /df.
    docker run --rm \
        --platform "$DF_PLATFORM" \
        -v "$REPO_DIR":/df \
        -e DF_NATIVE=1 \
        -e DF_STOCK="$DF_STOCK" \
        -e DF_FILL_ONLY="$DF_FILL_ONLY" \
        -e DF_FILL_ARGS="$DF_FILL_ARGS" \
        -e DEBIAN_FRONTEND=noninteractive \
        -- "$DF_IMAGE" bash -uexc '
            apt-get update -qq
            apt-get install -y -qq --no-install-recommends \
                git ca-certificates curl unzip \
                fontforge python3-fontforge python3-fonttools
            /df/build/build.sh
        '
}

# ---------------------------------------------------------------------------

report_built() {
    local style
    echo
    echo "==> Built:"
    for style in $STYLES; do
        ls -l "$REPO_DIR/$(output_face "$style")" | sed 's/^/    /'
    done
    echo
    echo "Next: python3 build/verify.py, then ./update-hashes.sh (see the release"
    echo "workflow documented there)."
}

main() {
    local style

    if [[ "$DF_FILL_ONLY" == "1" ]]; then
        local py
        if ! py="$(find_fonttools_python)"; then
            echo "error: no python3 with fontTools (pip install fonttools)" >&2
            exit 1
        fi
        fill_faces "$py"
        report_built
        return 0
    fi

    prepare_upstream

    for style in $STYLES; do
        if [[ ! -f "$WORK_DIR/nerd-fonts/src/unpatched-fonts/Meslo/S/$(source_face "$style")" ]]; then
            echo "error: missing source face for $style" >&2
            exit 1
        fi
    done

    build_native

    if [[ "$DF_STOCK" == "1" ]]; then
        echo
        echo "Next: python3 build/compare.py"
        return 0
    fi

    report_built
}

# In Docker we re-enter this same script with DF_NATIVE=1 set, so the branch
# below only decides which side of the container we are on.
if [[ "${DF_NATIVE:-0}" == "1" ]] || ! command -v docker >/dev/null 2>&1; then
    if [[ "${DF_NATIVE:-0}" != "1" ]]; then
        echo "==> docker not found, building natively"
    fi
    main
else
    build_docker
fi
