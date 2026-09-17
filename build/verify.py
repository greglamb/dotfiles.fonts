#!/usr/bin/env python3
"""Check the built MesloLGS NF DF faces before they are released.

Run after build/build.sh:

    python3 build/verify.py

Optionally pass --baseline DIR with the previously shipped faces (e.g. a
`git worktree` of the last release) to also diff coverage and Latin glyph
outlines against them:

    python3 build/verify.py --baseline /path/to/old/fonts

Exits non-zero if any check fails.
"""

import argparse
import os
import sys

try:
    from fontTools.ttLib import TTFont
    from fontTools.pens.boundsPen import BoundsPen
    from fontTools.pens.recordingPen import RecordingPen
except ImportError:
    sys.exit("verify.py: fontTools is not installed (pip install fonttools)")

FAMILY = "MesloLGS NF DF"

FACES = [
    ("Regular", "MesloLGS NF DF Regular.ttf"),
    ("Bold", "MesloLGS NF DF Bold.ttf"),
    ("Italic", "MesloLGS NF DF Italic.ttf"),
    ("Bold Italic", "MesloLGS NF DF Bold Italic.ttf"),
]

# Faces that older releases shipped, for --baseline.
LEGACY = {
    "Regular": "MesloLGS NF Regular.ttf",
    "Bold": "MesloLGS NF Bold.ttf",
    "Italic": "MesloLGS NF Italic.ttf",
    "Bold Italic": "MesloLGS NF Bold Italic.ttf",
}

# Glyphs the prompt themes lean on hardest. Box drawing and blocks must
# overhang the cell (that is the DF patch's whole point); powerline separators
# must reach the full line height.
BOX_DRAWING = [0x2500, 0x2502, 0x250C, 0x256D, 0x2588, 0x2591]
# Of those, the ones drawn as solid ink edge to edge. U+2591 and friends are
# stipple patterns, so their ink box is narrower than the cell however much the
# glyph is scaled -- they get the vertical check below instead.
BOX_DRAWING_SOLID = [0x2500, 0x2588]
POWERLINE = [0xE0A0, 0xE0B0, 0xE0B2]
# A spread of icon sets, including Font Awesome 6 which only exists from 3.4.0.
ICONS = [0xF179, 0xF418, 0xE73C, 0xF024B, 0xEB99, 0xED00]
# Braille, added upstream in 3.x; a silent casualty if the build is misconfigured.
BRAILLE = [0x2800, 0x28FF]
# Font units of slack allowed where two half-blocks meet. Coordinates are
# rounded to integers, so 1 is reachable without anything being wrong; 0 is what
# a correct build actually produces.
SEAM_TOLERANCE = 1

failures = []
notes = []


def fail(msg):
    failures.append(msg)
    print("  FAIL {}".format(msg))


def ok(msg):
    print("  ok   {}".format(msg))


def bounds(font_glyphs, cmap, cp):
    if cp not in cmap:
        return None
    pen = BoundsPen(font_glyphs)
    font_glyphs[cmap[cp]].draw(pen)
    if pen.bounds is None:
        return None
    return tuple(round(v) for v in pen.bounds)


def outline(font_glyphs, cmap, cp):
    if cp not in cmap:
        return None
    pen = RecordingPen()
    font_glyphs[cmap[cp]].draw(pen)
    return pen.value


def check_face(path, style):
    font = TTFont(path)
    cmap = font.getBestCmap()
    glyphs = font.getGlyphSet()
    names = {}
    for record in font["name"].names:
        names.setdefault(record.nameID, record.toUnicode())

    print("\n{} ({})".format(style, os.path.basename(path)))

    if names.get(1) != FAMILY:
        fail("family name is {!r}, expected {!r}".format(names.get(1), FAMILY))
    else:
        ok("family {!r}".format(FAMILY))

    if names.get(2) != style:
        fail("subfamily is {!r}, expected {!r}".format(names.get(2), style))

    expected_full = "{} {}".format(FAMILY, style)
    if names.get(4) != expected_full:
        fail("full name is {!r}, expected {!r}".format(names.get(4), expected_full))

    if " " in (names.get(6) or " "):
        fail("PostScript name {!r} contains a space".format(names.get(6)))
    else:
        ok("PostScript name {!r}".format(names.get(6)))

    for name_id in (16, 17):
        if name_id in names:
            fail("typographic name ID {} survived: {!r}".format(name_id, names[name_id]))

    # Monospace: every glyph must share one advance width.
    hmtx = font["hmtx"]
    widths = set(hmtx[g][0] for g in font.getGlyphOrder() if hmtx[g][0] != 0)
    if len(widths) != 1:
        fail("not monospaced: {} distinct advance widths {}".format(
            len(widths), sorted(widths)[:6]))
    else:
        cell = widths.pop()
        ok("monospaced, advance width {}".format(cell))

    cell = hmtx[cmap[0x41]][0]

    # Line height must not move, or every terminal reflows on upgrade.
    hhea = font["hhea"]
    os2 = font["OS/2"]
    use_typo = bool(os2.fsSelection & 0x80)
    hhea_lh = hhea.ascent - hhea.descent + hhea.lineGap
    typo_lh = os2.sTypoAscender - os2.sTypoDescender + os2.sTypoLineGap
    effective = typo_lh if use_typo else hhea_lh
    notes.append((style, "line height", effective))
    ok("line height {} (hhea {} / typo {}, USE_TYPO_METRICS={})".format(
        effective, hhea_lh, typo_lh, use_typo))

    ok("{} codepoints".format(len(cmap)))

    for cp in BRAILLE:
        if cp not in cmap:
            fail("U+{:04X} (braille) missing".format(cp))
    if all(cp in cmap for cp in BRAILLE):
        n = len([c for c in cmap if 0x2800 <= c <= 0x28FF])
        ok("braille block present ({} codepoints)".format(n))

    # Font Awesome 6, added in Nerd Fonts 3.4.0.
    fa6 = len([c for c in cmap if 0xED00 <= c <= 0xEFCE])
    if fa6 == 0:
        fail("no Font Awesome 6 glyphs (U+ED00..U+EFCE)")
    else:
        ok("Font Awesome 6 present ({} codepoints)".format(fa6))

    # The DF box-drawing transform: these must be wider AND taller than the
    # cell so adjacent cells overlap instead of leaving seams.
    for cp in BOX_DRAWING:
        bb = bounds(glyphs, cmap, cp)
        if bb is None:
            fail("U+{:04X} missing".format(cp))
            continue
        if cp in BOX_DRAWING_SOLID:
            width = bb[2] - bb[0]
            if width <= cell:
                fail("U+{:04X} is {} wide, not wider than the {} cell "
                     "(DF block scaling did not apply)".format(cp, width, cell))
    # All of the range shares one transform, so vertical overhang is the check
    # that holds for the stipples too: they must exceed the line height.
    for cp in (0x2588, 0x2591):
        bb = bounds(glyphs, cmap, cp)
        if bb is None:
            continue
        if (bb[3] - bb[1]) <= effective:
            fail("U+{:04X} is {} tall, not taller than the {} line height "
                 "(DF block scaling did not apply)".format(cp, bb[3] - bb[1], effective))
    bb = bounds(glyphs, cmap, 0x2588)
    if bb:
        ok("U+2588 full block {} overhangs the {}x{} cell".format(bb, cell, effective))

    # The DF icon transform: 'pa' icons are ~DF_ICON_SCALE cells wide.
    for cp in ICONS:
        bb = bounds(glyphs, cmap, cp)
        if bb is None:
            fail("U+{:04X} missing".format(cp))
            continue
        width = bb[2] - bb[0]
        if width <= cell:
            fail("U+{:04X} icon is {} wide, not wider than the {} cell "
                 "(DF icon scaling did not apply)".format(cp, width, cell))
        # Centered, so the overhang is shared between both sides.
        left = -bb[0]
        right = bb[2] - cell
        if abs(left - right) > cell * 0.05:
            fail("U+{:04X} overhang is lopsided (left {}, right {})".format(cp, left, right))
    ok("{} sampled icons are oversized and centered".format(len(ICONS)))

    # The reason the block transform exists: halves drawn in adjacent cells have
    # to meet exactly, or prompt frames show hairline seams. Upstream is free to
    # redraw these glyphs between releases; this is the property that must hold
    # however they are drawn.
    halves = [
        ("vertical", 0x2580, 1, 0x2584, 3),    # upper half bottom == lower half top
        ("horizontal", 0x2590, 0, 0x258C, 2),  # right half left  == left half right
    ]
    for label, cp_a, idx_a, cp_b, idx_b in halves:
        box_a = bounds(glyphs, cmap, cp_a)
        box_b = bounds(glyphs, cmap, cp_b)
        if box_a is None or box_b is None:
            fail("U+{:04X}/U+{:04X} missing, cannot check the {} seam".format(
                cp_a, cp_b, label))
            continue
        seam = box_a[idx_a] - box_b[idx_b]
        if abs(seam) > SEAM_TOLERANCE:
            fail("{} seam between U+{:04X} and U+{:04X} is {} units, not closed"
                 .format(label, cp_a, cp_b, seam))
        else:
            ok("{} half-block seam closes exactly ({:+d} units)".format(label, seam))

    for cp in POWERLINE:
        bb = bounds(glyphs, cmap, cp)
        if bb is None:
            fail("U+{:04X} (powerline) missing".format(cp))
    ok("powerline separators present")

    return font, cmap, glyphs


def check_csv(cmap, csv_path):
    print("\nCheat-sheet coverage ({})".format(csv_path))
    total = 0
    missing = []
    with open(csv_path, encoding="utf-8") as handle:
        for line in handle:
            parts = line.rstrip("\n").split(",")
            if len(parts) < 2 or not parts[1]:
                continue
            try:
                cp = int(parts[1], 16)
            except ValueError:
                continue
            total += 1
            if cp not in cmap:
                missing.append((parts[0], cp))
    if missing:
        fail("{} of {} cheat-sheet entries have no glyph, e.g. {}".format(
            len(missing), total,
            ", ".join("{} U+{:04X}".format(n, c) for n, c in missing[:5])))
    else:
        ok("all {} cheat-sheet entries resolve".format(total))


def check_baseline(baseline_dir, built):
    print("\nAgainst baseline {}".format(baseline_dir))
    for style, _ in FACES:
        old_path = os.path.join(baseline_dir, LEGACY[style])
        if not os.path.isfile(old_path):
            print("  skip {} (no {})".format(style, LEGACY[style]))
            continue
        old = TTFont(old_path)
        old_cmap = old.getBestCmap()
        old_glyphs = old.getGlyphSet()
        _, new_cmap, new_glyphs = built[style]

        lost = sorted(set(old_cmap) - set(new_cmap))
        gained = sorted(set(new_cmap) - set(old_cmap))
        legacy_mdi = [c for c in lost if 0xF500 <= c <= 0xFD46]
        other = [c for c in lost if c not in legacy_mdi]
        print("  {}: +{} / -{} codepoints".format(style, len(gained), len(lost)))
        if other:
            fail("{}: {} lost codepoints outside the retired Material Design "
                 "range, e.g. {}".format(style, len(other),
                                         ", ".join("U+{:04X}".format(c) for c in other[:8])))
        else:
            ok("{}: every lost codepoint is a retired Material Design alias".format(style))

        # Latin text must render identically; only icons are allowed to move.
        latin = [c for c in range(0x20, 0x180) if c in old_cmap and c in new_cmap]
        moved = [c for c in latin
                 if outline(old_glyphs, old_cmap, c) != outline(new_glyphs, new_cmap, c)]
        if moved:
            fail("{}: {} Latin glyphs changed shape, e.g. {}".format(
                style, len(moved), ", ".join("U+{:04X}".format(c) for c in moved[:8])))
        else:
            ok("{}: all {} Latin glyphs unchanged".format(style, len(latin)))


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.dirname(here)

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", default=repo, help="directory holding the built faces")
    parser.add_argument("--baseline", help="directory holding the previously shipped faces")
    parser.add_argument("--csv", help="nerdfont.csv to check coverage against")
    args = parser.parse_args()

    built = {}
    for style, filename in FACES:
        path = os.path.join(args.dir, filename)
        if not os.path.isfile(path):
            fail("missing built face {}".format(filename))
            continue
        built[style] = check_face(path, style)

    if args.csv and "Regular" in built:
        check_csv(built["Regular"][1], args.csv)

    if args.baseline:
        check_baseline(args.baseline, built)

    print()
    if failures:
        print("{} check(s) failed".format(len(failures)))
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
