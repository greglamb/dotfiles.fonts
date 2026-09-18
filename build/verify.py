#!/usr/bin/env python3
"""Check the built MesloLGS NF DF faces before they are released.

Run after build/build.sh:

    python3 build/verify.py

Optionally pass --baseline DIR with the previously shipped faces (e.g. a
`git worktree` of the last release) to also diff coverage and Latin glyph
outlines against them:

    python3 build/verify.py --baseline /path/to/old/fonts

When build/.work/fill/<style>.json is present (fill.py writes it during the
build) the glyphs the fill stage added are checked too: each maps, keeps the
cell advance, has its ink inside its one or two cells, and the emoji carry a
COLRv1 paint. Pass --manifests DIR to read them from elsewhere.

Exits non-zero if any check fails.
"""

import argparse
import json
import os
import sys

try:
    from fontTools.ttLib import TTFont
    from fontTools.pens.boundsPen import BoundsPen
    from fontTools.pens.recordingPen import RecordingPen
except ImportError:
    sys.exit("verify.py: fontTools is not installed (pip install fonttools)")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fill  # noqa: E402  (skip_reason, the fill stage's own exclusions)

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
# Font units a filled glyph's ink may stick out of its cell box: fill.py fits
# in floating point and the outline is then rounded to integers.
FIT_TOLERANCE = 2
# Manifest file per face, as fill.py names them.
MANIFEST = {
    "Regular": "Regular.json",
    "Bold": "Bold.json",
    "Italic": "Italic.json",
    "Bold Italic": "BoldItalic.json",
}

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


def colr_bases(font):
    """What the COLR table paints: v0 base -> [(layer glyph, palette index)],
    and v1 base -> clip box (or None). Either may be empty."""
    v0, v1 = {}, {}
    colr = font.get("COLR")
    if colr is None:
        return v0, v1
    if colr.version == 0:
        for base, layers in colr.ColorLayers.items():
            v0[base] = [(layer.name, layer.colorID) for layer in layers]
        return v0, v1
    table = colr.table
    if table.BaseGlyphRecordArray:
        records = table.LayerRecordArray.LayerRecord
        for r in table.BaseGlyphRecordArray.BaseGlyphRecord:
            v0[r.BaseGlyph] = [(l.LayerGlyph, l.PaletteIndex)
                               for l in records[r.FirstLayerIndex:r.FirstLayerIndex + r.NumLayers]]
    if table.BaseGlyphList:
        clips = table.ClipList.clips if table.ClipList else {}
        for r in table.BaseGlyphList.BaseGlyphPaintRecord:
            clip = clips.get(r.BaseGlyph)
            v1[r.BaseGlyph] = (clip.xMin, clip.yMin, clip.xMax, clip.yMax) if clip else None
    return v0, v1


def glyph_bounds(glyphs, name):
    pen = BoundsPen(glyphs)
    glyphs[name].draw(pen)
    if pen.bounds is None:
        return None
    return tuple(round(v) for v in pen.bounds)


def ligatures_to(font, feature_tag):
    """Every ligature glyph reachable through `feature_tag`, with a count of
    the component sequences that produce it."""
    out = {}
    gsub = font.get("GSUB")
    if gsub is None:
        return out
    table = gsub.table
    indices = set()
    for record in table.FeatureList.FeatureRecord:
        if record.FeatureTag == feature_tag:
            indices.update(record.Feature.LookupListIndex)
    for index in sorted(indices):
        for st in table.LookupList.Lookup[index].SubTable:
            if st.LookupType != 4:
                continue
            for ligatures in st.ligatures.values():
                for lig in ligatures:
                    out[lig.LigGlyph] = out.get(lig.LigGlyph, 0) + 1
    return out


def check_fill(font, cmap, glyphs, style, manifest_path):
    """The glyphs fill.py added: present, monospaced, inside their cells, and
    for emoji, painted in the format the manifest names; the sequences
    reachable as ligatures, the selectors present. The manifest is what
    fill.py says it did; this checks the face agrees."""
    print("\nFill stage ({})".format(os.path.relpath(manifest_path)))
    with open(manifest_path, encoding="utf-8") as handle:
        manifest = json.load(handle)
    if manifest.get("style") != os.path.splitext(MANIFEST[style])[0]:
        fail("manifest is for {!r}, not {}".format(manifest.get("style"), style))
        return
    filled = manifest["filled"]
    summary = manifest["summary"]
    policy = manifest["policy"]
    ok("{} codepoints filled ({}); {} Segoe-covered gaps left alone".format(
        summary["filled"],
        ", ".join("{} from {}".format(n, s) for s, n in sorted(summary["by_source"].items())),
        summary["unfilled_segoe"]))

    hmtx = font["hmtx"]
    cell = hmtx[cmap[0x41]][0]
    ascent, descent = font["hhea"].ascent, font["hhea"].descent
    emoji_format = policy.get("emoji_format", "colrv1")
    need_v0 = emoji_format in ("colrv0", "both")
    need_v1 = emoji_format in ("colrv1", "both")
    v0, v1 = colr_bases(font)

    def inside(box, wide):
        width = cell * (2 if wide else 1)
        return (box[0] >= -FIT_TOLERANCE and box[1] >= descent - FIT_TOLERANCE and
                box[2] <= width + FIT_TOLERANCE and box[3] <= ascent + FIT_TOLERANCE)

    missing, renamed, advance, outside, blank, unpainted, broken = [], [], [], [], [], [], []
    emoji, mono = 0, 0

    def check_paint(label, name, wide, has_mono):
        """One emoji glyph, whatever reaches it."""
        nonlocal emoji, mono
        emoji += 1
        if need_v0:
            layers = v0.get(name)
            if not layers:
                unpainted.append(label)
            else:
                boxes = [glyph_bounds(glyphs, layer) for layer, _ in layers]
                if any(b is None for b in boxes):
                    unpainted.append(label)
                elif not inside((min(b[0] for b in boxes), min(b[1] for b in boxes),
                                 max(b[2] for b in boxes), max(b[3] for b in boxes)), wide):
                    outside.append(label)
        if need_v1:
            if name not in v1 or v1[name] is None:
                unpainted.append(label)
            elif not inside(v1[name], wide):
                outside.append(label)
        ink = glyph_bounds(glyphs, name)
        if ink is not None:
            mono += 1
            if not inside(ink, wide):
                outside.append(label)
        if has_mono != (ink is not None):
            broken.append(label)

    for hexcp, entry in sorted(filled.items()):
        cp = int(hexcp, 16)
        if cp not in cmap:
            missing.append(hexcp)
            continue
        name = cmap[cp]
        if name != entry["glyph"]:
            renamed.append(hexcp)
        if entry["source"] == fill.GLUE:
            if hmtx[name][0] != 0 or glyph_bounds(glyphs, name) is not None:
                broken.append(hexcp)
            continue
        if hmtx[name][0] != cell:
            advance.append(hexcp)
        if entry["source"] == fill.EMOJI:
            check_paint(hexcp, name, entry["wide"], entry["mono"])
        else:
            ink = glyph_bounds(glyphs, name)
            if ink is None:
                blank.append(hexcp)
            elif not inside(ink, entry["wide"]):
                outside.append(hexcp)
        # The rules fill.py is supposed to follow.
        if fill.skip_reason(cp):
            broken.append(hexcp)
        if entry["source"] != fill.EMOJI and not entry["segoe"]:
            broken.append(hexcp)
        if entry["source"] == fill.EMOJI and entry["segoe"] and not policy["emoji_fallthrough"]:
            broken.append(hexcp)

    order = set(font.getGlyphOrder())
    for hexseq, entry in sorted(manifest.get("sequences", {}).items()):
        if entry["glyph"] not in order:
            missing.append(hexseq)
            continue
        if any(fill.is_modifier(int(h, 16)) for h in hexseq.split("_")):
            broken.append(hexseq)
        if not entry.get("shared"):
            check_paint(hexseq, entry["glyph"], True, entry["mono"])
    for hexcp, entry in sorted(manifest.get("presentation", {}).items()):
        if entry["glyph"] not in order:
            missing.append(hexcp + " FE0F")
            continue
        if not entry.get("shared"):
            check_paint(hexcp + " FE0F", entry["glyph"], True, entry["mono"])

    for items, what in ((missing, "not in the face"),
                        (renamed, "mapped to a different glyph than recorded"),
                        (advance, "not one cell of advance"),
                        (blank, "filled with a blank glyph"),
                        (outside, "ink outside its cell box"),
                        (unpainted, "emoji with no {} paint".format(emoji_format)),
                        (broken, "against the fill rules or the manifest")):
        if items:
            fail("{} filled item(s) {}: {}".format(len(items), what, ", ".join(items[:6])))
    if not (missing or renamed or advance):
        ok("every filled codepoint maps to its glyph at one cell of advance")
    if not (outside or blank):
        ok("ink of every filled glyph is inside its cell box (tolerance {})".format(FIT_TOLERANCE))
    if emoji:
        if "COLR" not in font or "CPAL" not in font:
            fail("emoji were filled but there is no COLR/CPAL table")
        elif not unpainted:
            ok("{} emoji glyphs painted as {}; {} of them have a monochrome fallback outline".format(
                emoji, emoji_format, mono))
        painted = len(v0) if need_v0 else len(v1)
        if painted != emoji:
            fail("COLR paints {} base glyphs but the manifest accounts for {}".format(painted, emoji))
        if need_v0 and need_v1 and set(v0) != set(v1):
            fail("COLRv0 and COLRv1 paint different glyph sets")
    elif "COLR" in font:
        fail("no emoji were filled but the face has a COLR table")

    sequences = manifest.get("sequences", {})
    if sequences:
        reachable = ligatures_to(font, fill.LIGATURE_FEATURE)
        unreachable = [h for h, e in sorted(sequences.items()) if e["glyph"] not in reachable]
        total = sum(reachable.get(e["glyph"], 0) for e in sequences.values()
                    if not e.get("shared"))
        if unreachable:
            fail("{} sequence(s) not reachable through '{}': {}".format(
                len(unreachable), fill.LIGATURE_FEATURE, ", ".join(unreachable[:4])))
        elif total != summary["ligatures"]:
            fail("'{}' has {} ligature entries for the sequences, manifest says {}".format(
                fill.LIGATURE_FEATURE, total, summary["ligatures"]))
        else:
            ok("{} ZWJ sequences reachable through '{}' ({} ligature entries)".format(
                len(sequences), fill.LIGATURE_FEATURE, total))
    uvs = manifest.get("variation_sequences", {})
    if uvs:
        table = next((t for t in font["cmap"].tables if t.format == 14), None)
        have = {cp: g for cp, g in table.uvsDict.get(0xFE0F, [])} if table else {}
        wrong = [h for h, g in sorted(uvs.items()) if int(h, 16) not in have or have[int(h, 16)] != g]
        if wrong:
            fail("{} U+FE0F variation sequence(s) missing or wrong: {}".format(
                len(wrong), ", ".join(wrong[:6])))
        else:
            ok("{} U+FE0F variation sequences present ({} to an extra emoji glyph)".format(
                len(uvs), len([g for g in uvs.values() if g])))
    if not broken:
        ok("fill rules respected (Segoe-covered gaps monochrome, exclusions honoured)")


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
    for style, filename in FACES:
        old_path = os.path.join(baseline_dir, LEGACY[style])
        if not os.path.isfile(old_path):
            old_path = os.path.join(baseline_dir, filename)
        if not os.path.isfile(old_path):
            print("  skip {} (no {} or {})".format(style, LEGACY[style], filename))
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
    parser.add_argument("--manifests", default=os.path.join(here, ".work", "fill"),
                        help="directory of the fill.py manifests (default: build/.work/fill)")
    args = parser.parse_args()

    built = {}
    for style, filename in FACES:
        path = os.path.join(args.dir, filename)
        if not os.path.isfile(path):
            fail("missing built face {}".format(filename))
            continue
        built[style] = check_face(path, style)
        manifest = os.path.join(args.manifests, MANIFEST[style])
        if os.path.isfile(manifest):
            check_fill(built[style][0], built[style][1], built[style][2], style, manifest)
        else:
            print("\nFill stage: skip {} (no manifest at {})".format(style, os.path.relpath(manifest)))

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
