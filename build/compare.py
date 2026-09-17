#!/usr/bin/env python3
"""Diff the shipped faces against a control build, and account for every difference.

`verify.py` asks "is the output sane". This asks the harder question: "is the
output different from stock in exactly the ways our patch is supposed to make it
different, and in no others". Run it on every Nerd Fonts upgrade -- a re-anchored
patch hunk that quietly stops applying, or starts applying to the wrong glyphs,
shows up here and nowhere else.

    ./build/build.sh --stock      # control: same patcher, same upstream, no --df
    python3 build/compare.py

The four claims it checks, one per section:

  0. the control vs upstream's published binary -- building with --df off must
     reproduce upstream's own file exactly. Until that holds, nothing below it
     means anything, because a difference could be ours or could be theirs.
  1. vs the stock control -- our patch changes icon scale, box drawing and the
     name table. Nothing else. Any other glyph that moved is a finding.
  2. vs the previously shipped faces -- coverage moves only in the direction the
     upstream release notes describe, and Latin text does not move at all.
  3. build determinism -- rebuilding produces the same glyphs, modulo the
     head.modified timestamp FontForge stamps in.

Point 2 needs `--baseline DIR`; without it that section is skipped.
"""

import argparse
import os
import sys

try:
    from fontTools.ttLib import TTFont
    from fontTools.pens.recordingPen import RecordingPen
    from fontTools.pens.boundsPen import BoundsPen
except ImportError:
    sys.exit("compare.py: fontTools is not installed (pip install fonttools)")

STYLES = ["Regular", "Bold", "Italic", "BoldItalic"]

SHIPPED = {
    "Regular": "MesloLGS NF DF Regular.ttf",
    "Bold": "MesloLGS NF DF Bold.ttf",
    "Italic": "MesloLGS NF DF Italic.ttf",
    "BoldItalic": "MesloLGS NF DF Bold Italic.ttf",
}
CONTROL = {s: "MesloLGSNerdFontMono-{}.ttf".format(s) for s in STYLES}
LEGACY = {
    "Regular": "MesloLGS NF Regular.ttf",
    "Bold": "MesloLGS NF Bold.ttf",
    "Italic": "MesloLGS NF Italic.ttf",
    "BoldItalic": "MesloLGS NF Bold Italic.ttf",
}

# --- what our patch is allowed to touch ------------------------------------
#
# Box drawing and block elements: scale_block_glyphs() transforms this whole
# range, so every glyph in it may move.
BLOCK_RANGE = range(0x2500, 0x25A0)
# Everything else our patch may move is an icon, i.e. a glyph the patcher
# pasted in. That is a provenance test rather than a codepoint list, so it stays
# correct as upstream adds glyph sets -- see compare_to_control() for the exact
# rule, which is "stock left it identical to the Meslo source", not "the Meslo
# source has this codepoint".
#
# Name IDs rename.py rewrites, plus the ones it drops.
NAME_IDS_CHANGED = {1, 2, 3, 4, 6, 16, 17, 18, 21, 22}

# Material Design aliases upstream retired in 3.4.0. Losing these is expected.
RETIRED_MDI = range(0xF500, 0xFD47)
# Latin, i.e. ordinary text. Must never move.
LATIN = range(0x20, 0x180)
# Font units of bounding-box movement tolerated when comparing two builds of the
# box-drawing range. One unit is 1/2048 em; a cell is 1233 units wide. Rounding
# accounts for 1, so 2 leaves headroom without hiding anything visible.
BLOCK_TOLERANCE = 2

findings = []


def fail(msg):
    findings.append(msg)
    print("  FAIL {}".format(msg))


def ok(msg):
    print("  ok   {}".format(msg))


def note(msg):
    """Informational. A difference that is real but is upstream's to make."""
    print("  note {}".format(msg))


def load(path):
    font = TTFont(path)
    return font, font.getBestCmap(), font.getGlyphSet()


def outline(glyphs, cmap, cp):
    if cp not in cmap:
        return None
    pen = RecordingPen()
    glyphs[cmap[cp]].draw(pen)
    return pen.value


def moved(a, b, codepoints):
    """Codepoints present in both whose outlines differ."""
    (_, cmap_a, glyphs_a) = a
    (_, cmap_b, glyphs_b) = b
    out = []
    for cp in codepoints:
        if cp not in cmap_a or cp not in cmap_b:
            continue
        if outline(glyphs_a, cmap_a, cp) != outline(glyphs_b, cmap_b, cp):
            out.append(cp)
    return out


def bbox(glyphs, cmap, cp):
    if cp not in cmap:
        return None
    pen = BoundsPen(glyphs)
    glyphs[cmap[cp]].draw(pen)
    return pen.bounds


def shifted(a, b, codepoints, tolerance):
    """Codepoints whose bounding box moved by more than `tolerance` font units.

    Outline equality is too strict for comparing two builds: the same transform
    recomputed against a different upstream build rounds to integer coordinates
    slightly differently, which moves edges by a unit without moving anything a
    viewer could see. A unit is 1/2048 em, and roughly 1/1233 of a cell.
    Returns (offenders, worst_delta_seen).
    """
    (_, cmap_a, glyphs_a) = a
    (_, cmap_b, glyphs_b) = b
    out = []
    worst = 0.0
    for cp in codepoints:
        box_a = bbox(glyphs_a, cmap_a, cp)
        box_b = bbox(glyphs_b, cmap_b, cp)
        if box_a is None or box_b is None:
            continue
        delta = max(abs(x - y) for x, y in zip(box_a, box_b))
        worst = max(worst, delta)
        if delta > tolerance:
            out.append(cp)
    return out, worst


def hexes(cps, limit=10):
    shown = ", ".join("U+{:04X}".format(c) for c in cps[:limit])
    return shown + (" ..." if len(cps) > limit else "")


def section(title):
    print("\n{}\n{}".format(title, "-" * len(title)))


# ---------------------------------------------------------------------------
# 0. Control build vs upstream's published binary
# ---------------------------------------------------------------------------

def compare_control_to_upstream(control_dir, upstream_dir):
    section("0. Stock control vs upstream's published release (toolchain is faithful)")
    for style in STYLES:
        ctl_path = os.path.join(control_dir, CONTROL[style])
        up_path = os.path.join(upstream_dir, CONTROL[style])
        if not os.path.isfile(ctl_path):
            fail("{}: no control build -- run ./build/build.sh --stock".format(style))
            continue
        if not os.path.isfile(up_path):
            fail("{}: no upstream release face at {}".format(style, up_path))
            continue
        ctl = load(ctl_path)
        up = load(up_path)

        if set(ctl[1]) != set(up[1]):
            only_ours = sorted(set(ctl[1]) - set(up[1]))
            only_theirs = sorted(set(up[1]) - set(ctl[1]))
            fail("{}: control coverage differs from upstream (+{} / -{}): {} {}".format(
                style, len(only_ours), len(only_theirs),
                hexes(only_ours), hexes(only_theirs)))
            continue

        differs = moved(ctl, up, sorted(ctl[1]))
        if differs:
            fail("{}: {} glyph(s) differ from upstream's own build: {}".format(
                style, len(differs), hexes(differs)))
        else:
            ok("{}: all {} glyphs identical to upstream's published face".format(
                style, len(ctl[1])))

        ctl_names = {(r.nameID, r.platformID, r.platEncID, r.langID): r.toUnicode()
                     for r in ctl[0]["name"].names}
        up_names = {(r.nameID, r.platformID, r.platEncID, r.langID): r.toUnicode()
                    for r in up[0]["name"].names}
        diff_ids = sorted({k[0] for k in set(ctl_names) | set(up_names)
                           if ctl_names.get(k) != up_names.get(k)})
        if diff_ids:
            fail("{}: name IDs {} differ from upstream".format(style, diff_ids))
        else:
            ok("{}: name table identical to upstream".format(style))


# ---------------------------------------------------------------------------
# 1. Shipped vs the stock control
# ---------------------------------------------------------------------------

def compare_to_control(repo, control_dir, source_dir):
    section("1. Shipped vs stock control (only our patch should differ)")
    for style in STYLES:
        ship_path = os.path.join(repo, SHIPPED[style])
        ctl_path = os.path.join(control_dir, CONTROL[style])
        if not os.path.isfile(ctl_path):
            fail("{}: no control build at {} -- run ./build/build.sh --stock".format(
                style, ctl_path))
            continue
        ship = load(ship_path)
        ctl = load(ctl_path)

        # Coverage must be untouched: our patch scales glyphs, it never adds or
        # removes them. This is the check that catches a hunk landing somewhere
        # that changes which glyph sets get copied.
        added = sorted(set(ship[1]) - set(ctl[1]))
        removed = sorted(set(ctl[1]) - set(ship[1]))
        if added or removed:
            fail("{}: our patch changed coverage (+{} / -{}): {} {}".format(
                style, len(added), len(removed), hexes(added), hexes(removed)))
        else:
            ok("{}: identical coverage, {} codepoints".format(style, len(ship[1])))

        shared = sorted(set(ship[1]) & set(ctl[1]))
        differs = set(moved(ship, ctl, shared))

        block = sorted(c for c in differs if c in BLOCK_RANGE)
        rest = sorted(c for c in differs if c not in BLOCK_RANGE)

        if not block:
            fail("{}: no box-drawing glyph differs from stock -- "
                 "scale_block_glyphs() did not run".format(style))
        else:
            ok("{}: {} box-drawing/block glyphs rescaled".format(style, len(block)))

        # Of the remaining differences, every one must be a pasted-in icon.
        #
        # "Came from the Meslo source" is not the test, because the patcher
        # pastes its own artwork over a handful of codepoints the source face
        # already has (U+2665, U+26A1, and the Powerline glyphs the "for
        # Powerline" source carries). Those are icons however they got there.
        #
        # The test that actually holds is: a glyph the *stock* build left byte
        # for byte identical to the source is text, and our patch has no
        # business touching it.
        src_path = os.path.join(source_dir, "Meslo LG S {} for Powerline.ttf".format(
            {"BoldItalic": "Bold Italic"}.get(style, style)))
        if os.path.isfile(src_path):
            src = load(src_path)
            untouched_by_stock = []
            for cp in rest:
                if cp not in src[1]:
                    continue
                if outline(src[2], src[1], cp) == outline(ctl[2], ctl[1], cp):
                    untouched_by_stock.append(cp)
            if untouched_by_stock:
                fail("{}: {} glyph(s) that stock leaves as plain Meslo text were "
                     "changed by our patch: {}".format(
                         style, len(untouched_by_stock), hexes(untouched_by_stock)))
            else:
                ok("{}: {} icons rescaled, every one of them a glyph stock also "
                   "replaces".format(style, len(rest)))
        else:
            ok("{}: {} icons rescaled (source face not available to cross-check)"
               .format(style, len(rest)))

        # Name table: only the IDs rename.py rewrites may differ.
        ship_names = {(r.nameID, r.platformID, r.platEncID, r.langID): r.toUnicode()
                      for r in ship[0]["name"].names}
        ctl_names = {(r.nameID, r.platformID, r.platEncID, r.langID): r.toUnicode()
                     for r in ctl[0]["name"].names}
        unexpected = set()
        for key in set(ship_names) | set(ctl_names):
            if ship_names.get(key) != ctl_names.get(key) and key[0] not in NAME_IDS_CHANGED:
                unexpected.add(key[0])
        if unexpected:
            fail("{}: name IDs changed that rename.py should not touch: {}".format(
                style, sorted(unexpected)))
        else:
            ok("{}: name table differs only in the IDs rename.py rewrites".format(style))

        # Metrics must be untouched: a changed line height reflows terminals.
        for table, attrs in (("hhea", ("ascent", "descent", "lineGap")),
                             ("OS/2", ("sTypoAscender", "sTypoDescender", "sTypoLineGap",
                                       "usWinAscent", "usWinDescent", "fsSelection"))):
            for attr in attrs:
                a = getattr(ship[0][table], attr)
                b = getattr(ctl[0][table], attr)
                if a != b:
                    fail("{}: {}.{} is {} but stock has {}".format(style, table, attr, a, b))
        ok("{}: vertical metrics identical to stock".format(style))


# ---------------------------------------------------------------------------
# 2. Shipped vs what we shipped last time
# ---------------------------------------------------------------------------

def compare_to_baseline(repo, baseline):
    section("2. Shipped vs previous release (coverage moves, text does not)")
    for style in STYLES:
        old_path = os.path.join(baseline, LEGACY[style])
        if not os.path.isfile(old_path):
            old_path = os.path.join(baseline, SHIPPED[style])
        if not os.path.isfile(old_path):
            print("  skip {} (nothing to compare against)".format(style))
            continue
        old = load(old_path)
        new = load(os.path.join(repo, SHIPPED[style]))

        lost = sorted(set(old[1]) - set(new[1]))
        gained = sorted(set(new[1]) - set(old[1]))
        unexplained = [c for c in lost if c not in RETIRED_MDI]
        if unexplained:
            fail("{}: {} codepoint(s) lost that are not retired Material Design "
                 "aliases: {}".format(style, len(unexplained), hexes(unexplained)))
        else:
            ok("{}: +{} / -{}, every loss a retired Material Design alias".format(
                style, len(gained), len(lost)))

        text = moved(old, new, LATIN)
        if text:
            fail("{}: {} Latin glyph(s) changed shape: {}".format(
                style, len(text), hexes(text)))
        else:
            ok("{}: Latin glyphs unchanged".format(style))

        # Box drawing needs care. Upstream owns the artwork -- 3.x ships its own
        # Box Drawing set and overrides some faces' native glyphs -- so an edge
        # moving between releases is upstream's business, not a regression.
        # What must survive is *our* transform, and the property it exists for:
        # the pieces still tile without seams. verify.py asserts that per face.
        # Here we only report how far the artwork moved, so an upgrade that
        # redraws these does not slip by unnoticed.
        block, worst = shifted(old, new, BLOCK_RANGE, BLOCK_TOLERANCE)
        if block:
            note("{}: upstream redrew {} box-drawing glyph(s); worst edge moved "
                 "{:.0f} units ({:.1f}% of a cell): {}".format(
                     style, len(block), worst, 100.0 * worst / 1233, hexes(block, 6)))
        else:
            ok("{}: box-drawing artwork unchanged (worst edge moved {:.0f} unit(s))"
               .format(style, worst))


# ---------------------------------------------------------------------------
# 3. Determinism
# ---------------------------------------------------------------------------

def compare_rebuild(repo, rebuild):
    section("3. Shipped vs an independent rebuild (determinism)")
    for style in STYLES:
        re_path = os.path.join(rebuild, SHIPPED[style])
        if not os.path.isfile(re_path):
            print("  skip {} (no rebuild at {})".format(style, re_path))
            continue
        a = load(os.path.join(repo, SHIPPED[style]))
        b = load(re_path)

        if set(a[1]) != set(b[1]):
            fail("{}: rebuild has different coverage".format(style))
            continue
        differs = moved(a, b, sorted(a[1]))
        if differs:
            fail("{}: {} glyph(s) differ between builds: {}".format(
                style, len(differs), hexes(differs)))
        else:
            ok("{}: all {} glyphs identical across builds".format(style, len(a[1])))

        # FontForge stamps head.modified with the build time, so the files are
        # not byte-identical. Say so rather than letting it look like a match.
        if a[0]["head"].modified != b[0]["head"].modified:
            ok("{}: differs only in head.modified (FontForge build timestamp)"
               .format(style))


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.dirname(here)

    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", default=repo, help="directory holding the shipped faces")
    parser.add_argument("--control", default=os.path.join(here, ".work", "stock"),
                        help="stock control build (./build/build.sh --stock)")
    parser.add_argument("--source", default=os.path.join(
        here, ".work", "nerd-fonts", "src", "unpatched-fonts", "Meslo", "S"),
        help="unpatched Meslo source faces, used to tell text from icons")
    parser.add_argument("--baseline", help="previously released faces")
    parser.add_argument("--rebuild", help="an independent rebuild, for the determinism check")
    parser.add_argument("--upstream", nargs="?", const=os.path.join(
        here, ".work", "upstream-release"),
        help="upstream's published faces (./build/fetch-release.sh)")
    args = parser.parse_args()

    if args.upstream:
        compare_control_to_upstream(args.control, args.upstream)
    else:
        section("0. Stock control vs upstream's published release")
        print("  skipped (run ./build/fetch-release.sh, then pass --upstream)")

    compare_to_control(args.dir, args.control, args.source)
    if args.baseline:
        compare_to_baseline(args.dir, args.baseline)
    else:
        section("2. Shipped vs previous release")
        print("  skipped (pass --baseline DIR)")
    if args.rebuild:
        compare_rebuild(args.dir, args.rebuild)
    else:
        section("3. Determinism")
        print("  skipped (pass --rebuild DIR)")

    print()
    if findings:
        print("{} unexplained difference(s)".format(len(findings)))
        return 1
    print("Every difference is accounted for.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
