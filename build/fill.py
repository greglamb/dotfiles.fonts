#!/usr/bin/env python3
"""Fill coverage gaps in a built MesloLGS NF DF face from the Noto fonts.

Runs after font-patcher and rename.py, once per face:

    python3 build/fill.py SRC.ttf DST.ttf Regular --sources build/.work/sources

A gap is a codepoint the face does not map. For every gap, in this order:

  1. Segoe UI Symbol maps it   -> the glyph from Noto Sans Symbols 2, else from
                                  Noto Sans Symbols, else (see --no-emoji-fallthrough)
                                  from Noto Color Emoji.
  2. Noto Color Emoji maps it  -> the glyph from Noto Color Emoji.
  3. Neither maps it           -> left as it is.

Segoe UI Symbol is the reference for "this is a monochrome symbol, not an
emoji": Windows draws everything it covers in monochrome, so we do too, from
the Noto symbol fonts, whose license lets us redistribute them. Its character
set is read from build/charsets/segoe-ui-symbol.txt (see charset.py) because
the font itself cannot be checked in.

Emoji are embedded as COLRv1 paint graphs plus a monochrome outline from Noto
Emoji, so a renderer without COLRv1 support (macOS CoreText, Windows Terminal
at the time of writing) still draws something rather than a blank cell.

What is never filled, whatever the sources map: control, format and variation
selector codepoints, Private Use, and the regional indicator letters -- those
only mean something in pairs, and leaving both halves unmapped lets the system
emoji font compose the flag.

Every glyph keeps the face monospaced: one cell of advance, with the ink fitted
(scaled down if needed, never up) into one cell, or two for East Asian Wide
codepoints, which is how terminals lay those out. It writes a manifest of what
it did, which verify.py and compare.py read.
"""

import argparse
import json
import os
import sys
import unicodedata

try:
    from fontTools import subset
    from fontTools.misc.transform import Transform
    from fontTools.pens.boundsPen import BoundsPen
    from fontTools.pens.recordingPen import DecomposingRecordingPen
    from fontTools.pens.transformPen import TransformPen
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    from fontTools.ttLib import TTFont
    from fontTools.ttLib.tables import otTables as ot
    from fontTools.varLib import instancer
except ImportError:
    sys.exit("fill.py: fontTools is not installed (pip install fonttools)")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import charset  # noqa: E402

STYLES = ("Regular", "Bold", "Italic", "BoldItalic")

# Source faces, by weight. Noto Sans Symbols 2 and Noto Color Emoji have one
# weight; Noto Emoji is a variable font we instance. Nothing has an italic --
# symbols and emoji stay upright in the italic faces, as the Nerd Fonts icons do.
SYMBOLS2 = "NotoSansSymbols2"
SYMBOLS = "NotoSansSymbols"
EMOJI = "NotoColorEmoji"
EMOJI_MONO = "NotoEmoji"

SOURCE_FILES = {
    SYMBOLS2: {"Regular": "NotoSansSymbols2-Regular.ttf", "Bold": "NotoSansSymbols2-Regular.ttf"},
    SYMBOLS: {"Regular": "NotoSansSymbols-Regular.ttf", "Bold": "NotoSansSymbols-Bold.ttf"},
    EMOJI: {"Regular": "Noto-COLRv1.ttf", "Bold": "Noto-COLRv1.ttf"},
    EMOJI_MONO: {"Regular": "NotoEmoji[wght].ttf", "Bold": "NotoEmoji[wght].ttf"},
}
EMOJI_MONO_WEIGHT = {"Regular": 400, "Bold": 700}

# Glyph name prefixes, so nothing can collide with what the patcher named.
PREFIX = {SYMBOLS2: "sym2.", SYMBOLS: "sym1.", EMOJI: "nce."}

# Ranges never filled, and why. Everything else that is skipped is skipped by
# Unicode general category (controls, format characters, surrogates, private
# use, line and paragraph separators).
SKIP_RANGES = [
    (0x1F1E6, 0x1F1FF, "regional indicator"),
    (0xFE00, 0xFE0F, "variation selector"),
    (0xE0100, 0xE01EF, "variation selector"),
    (0xE000, 0xF8FF, "private use"),
    (0xF0000, 0x10FFFF, "private use"),
]
SKIP_CATEGORIES = {"Cc": "control", "Cf": "format", "Cs": "surrogate",
                   "Co": "private use", "Zl": "separator", "Zp": "separator"}


def skip_reason(cp):
    if cp < 0x20:
        return "control"
    for lo, hi, why in SKIP_RANGES:
        if lo <= cp <= hi:
            return why
    return SKIP_CATEGORIES.get(unicodedata.category(chr(cp)))


def is_wide(cp, from_emoji):
    """Two terminal cells? East Asian Wide/Fullwidth, or an emoji newer than
    this Python's Unicode tables (every emoji added since Unicode 9 is Wide)."""
    ch = chr(cp)
    if unicodedata.east_asian_width(ch) in ("W", "F"):
        return True
    return from_emoji and unicodedata.category(ch) == "Cn"


def font_version(font):
    record = font["name"].getName(5, 3, 1) or font["name"].getName(5, 1, 0)
    return record.toUnicode() if record else ""


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------

def fit(bounds, box):
    """Uniform scale (<= 1) and translation that put `bounds` inside `box`.

    Shrinks only when the ink is too wide or too tall, centres it horizontally,
    and keeps it on the baseline unless it would poke out of the line box.
    """
    xmin, ymin, xmax, ymax = bounds
    bx0, by0, bx1, by1 = box
    scale = 1.0
    if xmax - xmin > bx1 - bx0:
        scale = min(scale, (bx1 - bx0) / (xmax - xmin))
    if ymax - ymin > by1 - by0:
        scale = min(scale, (by1 - by0) / (ymax - ymin))
    xmin, xmax, ymin, ymax = xmin * scale, xmax * scale, ymin * scale, ymax * scale
    dx = (bx0 + bx1) / 2.0 - (xmin + xmax) / 2.0
    dy = 0.0
    if ymax > by1:
        dy = by1 - ymax
    elif ymin < by0:
        dy = by0 - ymin
    return scale, dx, dy


def scaled_bounds(bounds, k):
    return tuple(v * k for v in bounds)


def outline_glyph(glyph_set, name, k, box):
    """Copy one outline into a new TrueType glyph, fitted into `box`.

    `k` is the unitsPerEm ratio between target and source. Returns (glyph,
    bbox) or (None, None) for a blank source glyph.
    """
    rec = DecomposingRecordingPen(glyph_set)
    glyph_set[name].draw(rec)
    bp = BoundsPen(glyph_set)
    glyph_set[name].draw(bp)
    if bp.bounds is None:
        return None, None
    scale, dx, dy = fit(scaled_bounds(bp.bounds, k), box)
    transform = Transform(k * scale, 0, 0, k * scale, dx, dy)
    pen = TTGlyphPen(None)
    rec.replay(TransformPen(pen, transform))
    glyph = pen.glyph()
    # The control-point box, which is what the glyf bbox and the left side
    # bearing have to agree on; the ink itself is inside `box`.
    glyph.recalcBounds(None)
    return glyph, (glyph.xMin, glyph.yMin, glyph.xMax, glyph.yMax)


def empty_glyph():
    return TTGlyphPen(None).glyph()


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

class Sources(object):
    def __init__(self, directory, weight):
        self.directory = directory
        self.weight = weight
        self.fonts = {}
        self.versions = {}
        for key, files in SOURCE_FILES.items():
            path = os.path.join(directory, files[weight])
            if not os.path.isfile(path):
                sys.exit("fill.py: missing source font {} (run build/fetch-sources.sh)".format(path))
            font = TTFont(path)
            if key == EMOJI_MONO:
                font = instancer.instantiateVariableFont(
                    font, {"wght": EMOJI_MONO_WEIGHT[weight]}, inplace=True)
            self.fonts[key] = font
            self.versions[key] = {"file": files[weight], "version": font_version(font)}
        self.cmaps = {key: font.getBestCmap() for key, font in self.fonts.items()}
        self.glyph_sets = {key: font.getGlyphSet() for key, font in self.fonts.items()}

    def upm(self, key):
        return self.fonts[key]["head"].unitsPerEm


def subset_emoji(path, codepoints):
    """Noto-COLRv1 cut down to `codepoints`, their paint graphs and the
    component glyphs those reach. GSUB goes: sequences (ZWJ, skin tone, flags)
    need shaping we are not carrying over, and its closure would drag in every
    glyph they reach."""
    options = subset.Options()
    options.drop_tables = sorted(set(options.drop_tables) | {
        "GSUB", "GPOS", "GDEF", "vhea", "vmtx", "VVAR", "HVAR", "STAT", "DSIG"})
    options.layout_features = []
    options.layout_closure = False
    options.glyph_names = True
    options.notdef_outline = False
    options.hinting = False
    options.recalc_bounds = False
    options.prune_unicode_ranges = False
    font = TTFont(path)
    subsetter = subset.Subsetter(options)
    subsetter.populate(unicodes=codepoints)
    subsetter.subset(font)
    return font


def rename_paint(paint, mapping):
    if hasattr(paint, "Glyph"):
        paint.Glyph = mapping[paint.Glyph]
    for attr in ("Paint", "SourcePaint", "BackdropPaint"):
        child = getattr(paint, attr, None)
        if child is not None:
            rename_paint(child, mapping)


def wrap_transform(paint, xx, dx, dy):
    """A PaintTransform of uniform scale `xx` and offset (dx, dy) over `paint`."""
    affine = ot.Affine2x3()
    affine.xx = xx
    affine.yx = 0
    affine.xy = 0
    affine.yy = xx
    affine.dx = dx
    affine.dy = dy
    outer = ot.Paint()
    outer.Format = ot.PaintFormat.PaintTransform
    outer.Transform = affine
    outer.Paint = paint
    return outer


# ---------------------------------------------------------------------------
# The fill
# ---------------------------------------------------------------------------

class Filler(object):
    def __init__(self, font, style, sources, segoe, emoji_fallthrough):
        self.font = font
        self.style = style
        self.sources = sources
        self.segoe = segoe
        self.emoji_fallthrough = emoji_fallthrough

        self.cmap = font.getBestCmap()
        self.upm = font["head"].unitsPerEm
        hmtx = font["hmtx"]
        self.cell = hmtx[self.cmap[0x41]][0]
        self.ascent = font["hhea"].ascent
        self.descent = font["hhea"].descent
        if len({hmtx[g][0] for g in font.getGlyphOrder() if hmtx[g][0]}) != 1:
            sys.exit("fill.py: {} is not monospaced before filling".format(style))
        if "COLR" in font or "CPAL" in font:
            sys.exit("fill.py: {} already has a COLR/CPAL table".format(style))

        self.filled = {}      # cp -> manifest entry
        self.unfilled = []    # Segoe-covered gaps no source can fill
        self.skipped = {}     # reason -> [cp]
        self.blank = []       # source had the codepoint but no ink

    def box(self, wide):
        return (0, self.descent, self.cell * (2 if wide else 1), self.ascent)

    # -- planning -----------------------------------------------------------

    def plan(self):
        """Decide the source for every gap. Returns [(cp, source_key)]."""
        candidates = set(self.segoe) | set(self.sources.cmaps[EMOJI])
        plan = []
        for cp in sorted(candidates):
            if cp in self.cmap:
                continue
            why = skip_reason(cp)
            if why:
                self.skipped.setdefault(why, []).append(cp)
                continue
            if cp in self.segoe:
                if cp in self.sources.cmaps[SYMBOLS2]:
                    plan.append((cp, SYMBOLS2))
                elif cp in self.sources.cmaps[SYMBOLS]:
                    plan.append((cp, SYMBOLS))
                elif self.emoji_fallthrough and cp in self.sources.cmaps[EMOJI]:
                    plan.append((cp, EMOJI))
                else:
                    self.unfilled.append(cp)
            else:
                plan.append((cp, EMOJI))
        return plan

    # -- applying -----------------------------------------------------------

    def run(self):
        plan = self.plan()
        order = list(self.font.getGlyphOrder())
        new_glyphs = {}   # name -> (Glyph, advance, lsb)
        new_cmap = {}     # cp -> name

        # Monochrome symbols first, in codepoint order.
        for cp, key in plan:
            if key == EMOJI:
                continue
            k = float(self.upm) / self.sources.upm(key)
            wide = is_wide(cp, False)
            src_name = self.sources.cmaps[key][cp]
            glyph, bounds = outline_glyph(self.sources.glyph_sets[key], src_name, k, self.box(wide))
            if glyph is None:
                self.blank.append(cp)
                continue
            name = "{}u{:04X}".format(PREFIX[key], cp)
            new_glyphs[name] = (glyph, self.cell, bounds[0])
            new_cmap[cp] = name
            order.append(name)
            self.filled[cp] = {"source": key, "glyph": name, "wide": wide,
                               "segoe": cp in self.segoe, "bounds": list(bounds)}

        # Then the emoji: the COLRv1 subset, renamed, each base glyph wrapped
        # in the transform that fits it, and given a monochrome outline.
        emoji = [cp for cp, key in plan if key == EMOJI]
        if emoji:
            self.add_emoji(emoji, order, new_glyphs, new_cmap)

        # Install.
        self.font.setGlyphOrder(order)
        glyf = self.font["glyf"]
        hmtx = self.font["hmtx"]
        for name, (glyph, advance, lsb) in new_glyphs.items():
            glyf[name] = glyph
            hmtx[name] = (advance, lsb)
        for table in self.font["cmap"].tables:
            if not table.isUnicode():
                continue
            for cp, name in new_cmap.items():
                if table.format == 4 and cp > 0xFFFF:
                    continue
                table.cmap[cp] = name
        if any(cp > 0xFFFF for cp in new_cmap) and not any(
                t.isUnicode() and t.format == 12 for t in self.font["cmap"].tables):
            sys.exit("fill.py: no format 12 cmap subtable for supplementary codepoints")

    def add_emoji(self, codepoints, order, new_glyphs, new_cmap):
        key = EMOJI
        sub = subset_emoji(os.path.join(self.sources.directory,
                                        SOURCE_FILES[key][self.sources.weight]), codepoints)
        sub_cmap = sub.getBestCmap()
        missing = [cp for cp in codepoints if cp not in sub_cmap]
        if missing:
            sys.exit("fill.py: subset lost {} emoji, e.g. U+{:04X}".format(len(missing), missing[0]))
        k = float(self.upm) / sub["head"].unitsPerEm
        base_of = {name: cp for cp, name in sub_cmap.items()}

        # New names: base glyphs by codepoint, components by their old name.
        mapping = {}
        for old in sub.getGlyphOrder():
            if old == ".notdef":
                continue
            if old in base_of:
                mapping[old] = "{}u{:04X}".format(PREFIX[key], base_of[old])
            else:
                mapping[old] = "{}{}".format(PREFIX[key], old)
        if len(set(mapping.values())) != len(mapping):
            sys.exit("fill.py: emoji glyph names collide after renaming")

        colr = sub["COLR"]
        if colr.version != 1:
            sys.exit("fill.py: expected a COLRv1 emoji source, got version {}".format(colr.version))
        table = colr.table
        if table.BaseGlyphRecordCount or table.LayerRecordCount:
            sys.exit("fill.py: emoji source carries COLRv0 records; not handled")
        clips = table.ClipList.clips if table.ClipList else {}

        for record in table.BaseGlyphList.BaseGlyphPaintRecord:
            old = record.BaseGlyph
            cp = base_of.get(old)
            if cp is None:
                sys.exit("fill.py: COLR base glyph {} is not mapped by the subset".format(old))
            wide = is_wide(cp, True)
            box = self.box(wide)
            clip = clips.get(old)
            if clip is None:
                clip = record.Paint.computeClipBox(colr, sub.getGlyphSet(), quantization=1)
                if clip is None:
                    sys.exit("fill.py: cannot bound the paint of U+{:04X}".format(cp))
            bounds = scaled_bounds((clip.xMin, clip.yMin, clip.xMax, clip.yMax), k)
            scale, dx, dy = fit(bounds, box)
            xx = k * scale
            record.Paint = wrap_transform(record.Paint, xx, dx, dy)
            new_clip = ot.ClipBox()
            new_clip.Format = 1
            new_clip.xMin = int((clip.xMin * xx + dx) // 1)
            new_clip.yMin = int((clip.yMin * xx + dy) // 1)
            new_clip.xMax = int(-((-(clip.xMax * xx + dx)) // 1))
            new_clip.yMax = int(-((-(clip.yMax * xx + dy)) // 1))
            clips[old] = new_clip

            # Monochrome fallback outline, for renderers without COLRv1.
            mono_name = self.sources.cmaps[EMOJI_MONO].get(cp)
            fallback, fb_bounds = None, None
            if mono_name is not None:
                km = float(self.upm) / self.sources.upm(EMOJI_MONO)
                fallback, fb_bounds = outline_glyph(
                    self.sources.glyph_sets[EMOJI_MONO], mono_name, km, box)
            name = mapping[old]
            if fallback is None:
                new_glyphs[name] = (empty_glyph(), self.cell, 0)
            else:
                new_glyphs[name] = (fallback, self.cell, fb_bounds[0])
            new_cmap[cp] = name
            self.filled[cp] = {"source": key, "glyph": name, "wide": wide,
                               "segoe": cp in self.segoe, "mono": fallback is not None,
                               "bounds": [new_clip.xMin, new_clip.yMin, new_clip.xMax, new_clip.yMax]}

        # Rename every glyph reference in the paint graphs.
        for record in table.BaseGlyphList.BaseGlyphPaintRecord:
            record.BaseGlyph = mapping[record.BaseGlyph]
            rename_paint(record.Paint, mapping)
        if table.LayerList:
            for paint in table.LayerList.Paint:
                rename_paint(paint, mapping)
        if table.ClipList:
            table.ClipList.clips = {mapping[g]: box for g, box in clips.items()}

        # Component glyphs come over untouched, in the source's units: the
        # transform wrapped around each base glyph rescales them. They are
        # never mapped, so their advance is zero and the face stays monospaced.
        sub_glyf = sub["glyf"]
        sub_hmtx = sub["hmtx"]
        for old in sub.getGlyphOrder():
            if old == ".notdef" or old in base_of:
                continue
            glyph = sub_glyf[old]
            if glyph.isComposite():
                for component in glyph.components:
                    component.glyphName = mapping[component.glyphName]
            new_glyphs[mapping[old]] = (glyph, 0, sub_hmtx[old][1])

        # Deterministic order: bases by codepoint, then components as the
        # subset ordered them.
        for cp in sorted(cp for cp in codepoints):
            order.append(mapping[sub_cmap[cp]])
        for old in sub.getGlyphOrder():
            if old != ".notdef" and old not in base_of:
                order.append(mapping[old])

        self.font["COLR"] = colr
        self.font["CPAL"] = sub["CPAL"]

    # -- reporting ----------------------------------------------------------

    def manifest(self):
        by_source = {}
        for entry in self.filled.values():
            by_source[entry["source"]] = by_source.get(entry["source"], 0) + 1
        return {
            "style": self.style,
            "cell": self.cell,
            "ascent": self.ascent,
            "descent": self.descent,
            "policy": {"emoji_fallthrough": self.emoji_fallthrough},
            "sources": self.sources.versions,
            "summary": {
                "filled": len(self.filled),
                "by_source": by_source,
                "segoe_fallthrough_to_emoji": len([
                    e for e in self.filled.values() if e["source"] == EMOJI and e["segoe"]]),
                "unfilled_segoe": len(self.unfilled),
                "blank_in_source": len(self.blank),
                "skipped": {why: len(cps) for why, cps in sorted(self.skipped.items())},
            },
            "filled": {"{:04X}".format(cp): entry for cp, entry in sorted(self.filled.items())},
            "unfilled_segoe": ["{:04X}".format(cp) for cp in self.unfilled],
            "blank_in_source": ["{:04X}".format(cp) for cp in self.blank],
            "skipped": {why: ["{:04X}".format(cp) for cp in cps]
                        for why, cps in sorted(self.skipped.items())},
        }

    def summary(self):
        m = self.manifest()["summary"]
        parts = ["{} {}".format(m["by_source"].get(k, 0), k) for k in (SYMBOLS2, SYMBOLS, EMOJI)]
        return ("{}: +{} codepoints ({}); {} Segoe-covered gaps left unfilled; "
                "{} skipped".format(self.style, m["filled"], ", ".join(parts),
                                    m["unfilled_segoe"], sum(m["skipped"].values())))


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", help="renamed face from rename.py")
    parser.add_argument("dest", help="output TTF path")
    parser.add_argument("style", choices=STYLES, help="RIBBI style of this face")
    parser.add_argument("--sources", default=os.path.join(here, ".work", "sources"),
                        help="directory with the Noto source fonts (build/fetch-sources.sh)")
    parser.add_argument("--charset", default=os.path.join(here, "charsets", "segoe-ui-symbol.txt"),
                        help="Segoe UI Symbol character set (build/charset.py)")
    parser.add_argument("--manifest", help="write a JSON record of what was filled here")
    parser.add_argument("--no-emoji-fallthrough", action="store_true",
                        help="leave a Segoe-covered gap alone when neither Noto symbol "
                             "font has it, instead of taking Noto Color Emoji's glyph")
    args = parser.parse_args()

    if not os.path.isfile(args.source):
        sys.exit("fill.py: no such file: {}".format(args.source))
    weight = "Bold" if args.style in ("Bold", "BoldItalic") else "Regular"

    segoe = charset.load(args.charset)
    sources = Sources(args.sources, weight)
    font = TTFont(args.source)
    filler = Filler(font, args.style, sources, segoe, not args.no_emoji_fallthrough)
    filler.run()
    font.save(args.dest)

    if args.manifest:
        os.makedirs(os.path.dirname(os.path.abspath(args.manifest)), exist_ok=True)
        with open(args.manifest, "w", encoding="utf-8") as handle:
            json.dump(filler.manifest(), handle, indent=1, sort_keys=True)
            handle.write("\n")
    print("  " + filler.summary())


if __name__ == "__main__":
    main()
