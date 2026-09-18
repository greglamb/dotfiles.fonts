#!/usr/bin/env python3
"""Fill coverage gaps in a built MesloLGS NF DF face from the Noto fonts.

Runs after font-patcher and rename.py, once per face:

    python3 build/fill.py SRC.ttf DST.ttf Regular --sources build/.work/sources

A gap is a codepoint the face does not map. For every gap, first match wins:

  0. Never filled             -> controls, format characters, variation
                                 selectors, Private Use, regional indicators
                                 (see below).
  1. Listed in an override    -> build/colour-overrides.txt: the colour glyph
     file                        from Noto Color Emoji. build/monochrome-
                                 overrides.txt: the monochrome glyph, from the
                                 sources of rule 3 in order.
  2. Segoe UI Symbol maps it, -> the colour glyph from Noto Color Emoji.
     and Unicode shows it as
     an emoji by default
  3. Segoe UI Symbol maps it  -> the glyph from Noto Sans Symbols 2, else from
                                 Noto Sans Symbols, else (see --no-emoji-fallthrough)
                                 the monochrome one from Noto Emoji; else a gap.
  4. Noto Color Emoji maps it -> the colour glyph from Noto Color Emoji.
  5. Neither maps it          -> left as it is.

Segoe UI Symbol is the reference for "this is a monochrome symbol, not an
emoji": Windows draws everything it covers in monochrome, so we do too -- from
the Noto symbol fonts, or from Noto Emoji, the monochrome sister of Noto Color
Emoji, for the emoji-presentation characters the symbol fonts leave out. All
of them carry a license that lets us redistribute them. Segoe's character set
is read from build/charsets/segoe-ui-symbol.txt (see charset.py) because the
font itself cannot be checked in.

Rule 2 carves out what Unicode itself treats as an emoji: Emoji_Presentation=Yes
in emoji-data.txt (pinned by fetch-sources.sh), such as U+1F308 RAINBOW or
U+23F0 ALARM CLOCK. Segoe covers several hundred of those, from the years
Windows drew emoji in monochrome. The override files, kept by hand, settle
single codepoints either way ahead of that. build/README.md has the rules with
their reasons and numbers.

On top of the single codepoints, the emoji ZWJ sequences Noto Color Emoji
draws are carried over as ligatures (family, profession and flag sequences,
minus every variant with a skin tone or hair component, which fold onto the
untoned emoji instead, again by ligature and without a glyph), and the emoji
presentation selector U+FE0F gets its meaning: `<symbol> FE0F` draws the
colour emoji wherever the plain symbol is monochrome. That covers exactly the
variation sequences Unicode defines, which every text-by-default emoji has, so
its colour art is one selector away. --no-sequences turns both off.

Emoji are embedded as COLRv0 layers by default, the one vector colour format
that Windows Terminal, macOS CoreText, Chromium, FreeType and so every Linux
terminal all draw, and again as an OpenType SVG table carrying the same flat
layers, for the CoreText apps that only look for `sbix` or `SVG` when deciding
a glyph is colour (Ghostty). Every emoji glyph also carries a monochrome
outline from Noto Emoji, so a renderer with no colour support at all still
shows something. --emoji-format colrv1 embeds Noto's COLRv1 paint graphs
instead (gradients, but Chromium/GTK/kitty-on-Linux only), `both` ships the
two side by side, and --no-svg drops the SVG table.

What is never filled, whatever the sources map: control, format and variation
selector codepoints, Private Use, and the regional indicator letters -- those
only mean something in pairs, and leaving both halves unmapped lets the system
emoji font compose the flag. (U+200D and U+FE0F are the one exception: the
sequences need them, so they get empty zero-width glyphs.)

Every glyph keeps the face monospaced: one cell of advance, with the ink fitted
(scaled down if needed, never up) into one cell, or two for East Asian Wide
codepoints and emoji sequences, which is how terminals lay those out. It
writes a manifest of what it did, which verify.py and compare.py read.
"""

import argparse
import gzip
import itertools
import json
import math
import os
import sys
import unicodedata

try:
    from fontTools import subset
    from fontTools.colorLib.builder import buildCOLR, populateCOLRv0
    from fontTools.misc.transform import Transform
    from fontTools.otlLib.builder import buildLigatureSubstSubtable
    from fontTools.pens.basePen import BasePen
    from fontTools.pens.boundsPen import BoundsPen
    from fontTools.pens.recordingPen import DecomposingRecordingPen
    from fontTools.pens.transformPen import TransformPen
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    from fontTools.ttLib import TTFont, newTable
    from fontTools.ttLib.tables import otTables as ot
    from fontTools.ttLib.tables._c_m_a_p import CmapSubtable
    from fontTools.ttLib.tables._g_l_y_f import (
        ARGS_ARE_XY_VALUES, ROUND_XY_TO_GRID, Glyph, GlyphComponent)
    from fontTools.ttLib.tables.C_P_A_L_ import Color
    from fontTools.ttLib.tables.S_V_G_ import SVGDocument
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
# Not a font: the empty zero-width glyphs for U+200D and U+FE0F.
GLUE = "glue"

SOURCE_FILES = {
    SYMBOLS2: {"Regular": "NotoSansSymbols2-Regular.ttf", "Bold": "NotoSansSymbols2-Regular.ttf"},
    SYMBOLS: {"Regular": "NotoSansSymbols-Regular.ttf", "Bold": "NotoSansSymbols-Bold.ttf"},
    EMOJI: {"Regular": "Noto-COLRv1.ttf", "Bold": "Noto-COLRv1.ttf"},
    EMOJI_MONO: {"Regular": "NotoEmoji[wght].ttf", "Bold": "NotoEmoji[wght].ttf"},
}
EMOJI_MONO_WEIGHT = {"Regular": 400, "Bold": 700}
# Unicode's emoji properties, pinned next to the fonts by fetch-sources.sh.
EMOJI_DATA = "emoji-data.txt"

# Glyph name prefixes, so nothing can collide with what the patcher named.
PREFIX = {SYMBOLS2: "sym2.", SYMBOLS: "sym1.", EMOJI: "nce.", EMOJI_MONO: "mono."}
MONO_SOURCES = (SYMBOLS2, SYMBOLS, EMOJI_MONO)

EMOJI_FORMATS = ("colrv0", "colrv1", "both")
DEFAULT_EMOJI_FORMAT = "colrv0"
# Emoji glyphs per SVG document. One document per glyph costs a header and a
# fresh gzip window each; one document for everything makes a renderer parse
# megabytes of XML for the first emoji it draws.
SVG_CHUNK = 16

ZWJ = 0x200D
VS16 = 0xFE0F
# Sequences containing one of these are not carried over: they multiply the
# glyph count several times over for variants terminals rarely see.
SKIN_TONES = (0x1F3FB, 0x1F3FF)
HAIR = (0x1F9B0, 0x1F9B3)
MODIFIER_RANGES = (SKIN_TONES, HAIR)
# The GSUB feature the sequence ligatures go under. `ccmp` is what Noto uses,
# and it is on by default in every shaper, unlike `liga` which terminals let
# users switch off.
LIGATURE_FEATURE = "ccmp"

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


def is_modifier(cp):
    return any(lo <= cp <= hi for lo, hi in MODIFIER_RANGES)


def font_version(font):
    record = font["name"].getName(5, 3, 1) or font["name"].getName(5, 1, 0)
    return record.toUnicode() if record else ""


def hexseq(cps):
    return "_".join("{:04X}".format(cp) for cp in cps)


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


def transformed_glyph(recording, affine):
    """A new TrueType glyph: `recording` (a DecomposingRecordingPen) replayed
    through `affine`. Returns (glyph, bbox), or (None, None) if it has no
    contours."""
    pen = TTGlyphPen(None)
    recording.replay(TransformPen(pen, affine))
    glyph = pen.glyph()
    if not glyph.numberOfContours:
        return None, None
    # The control-point box, which is what the glyf bbox and the left side
    # bearing have to agree on; the ink itself is inside the fitted box.
    glyph.recalcBounds(None)
    return glyph, (glyph.xMin, glyph.yMin, glyph.xMax, glyph.yMax)


def record_outline(glyph_set, name):
    rec = DecomposingRecordingPen(glyph_set)
    glyph_set[name].draw(rec)
    bp = BoundsPen(glyph_set)
    glyph_set[name].draw(bp)
    return rec, bp.bounds


def outline_glyph(glyph_set, name, k, box):
    """Copy one outline into a new TrueType glyph, fitted into `box`.

    `k` is the unitsPerEm ratio between target and source. Returns (glyph,
    bbox) or (None, None) for a blank source glyph.
    """
    rec, bounds = record_outline(glyph_set, name)
    if bounds is None:
        return None, None
    scale, dx, dy = fit(scaled_bounds(bounds, k), box)
    return transformed_glyph(rec, Transform(k * scale, 0, 0, k * scale, dx, dy))


def empty_glyph():
    return TTGlyphPen(None).glyph()


def composite_glyph(name, bbox):
    """A glyph that is `name` drawn in place: one component, no offset."""
    component = GlyphComponent()
    component.glyphName = name
    component.flags = ARGS_ARE_XY_VALUES | ROUND_XY_TO_GRID
    component.x = 0
    component.y = 0
    glyph = Glyph()
    glyph.numberOfContours = -1
    glyph.components = [component]
    glyph.xMin, glyph.yMin, glyph.xMax, glyph.yMax = bbox
    return glyph, tuple(bbox)


def union(boxes):
    boxes = [b for b in boxes if b is not None]
    if not boxes:
        return None
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


# ---------------------------------------------------------------------------
# COLRv1 paint graphs
# ---------------------------------------------------------------------------

PF = ot.PaintFormat
GRADIENTS = {PF.PaintLinearGradient, PF.PaintVarLinearGradient,
             PF.PaintRadialGradient, PF.PaintVarRadialGradient,
             PF.PaintSweepGradient, PF.PaintVarSweepGradient}
RADIAL = {PF.PaintRadialGradient, PF.PaintVarRadialGradient}


def paint_transform(paint):
    """The affine a transform-type paint applies to its child, as a fontTools
    Transform, or None if `paint` is not one of those."""
    f = paint.Format
    if f in (PF.PaintTransform, PF.PaintVarTransform):
        a = paint.Transform
        return Transform(a.xx, a.yx, a.xy, a.yy, a.dx, a.dy)
    if f in (PF.PaintTranslate, PF.PaintVarTranslate):
        return Transform(1, 0, 0, 1, paint.dx, paint.dy)
    if f in (PF.PaintScale, PF.PaintVarScale):
        return Transform(paint.scaleX, 0, 0, paint.scaleY, 0, 0)
    if f in (PF.PaintScaleAroundCenter, PF.PaintVarScaleAroundCenter):
        cx, cy = paint.centerX, paint.centerY
        return Transform(1, 0, 0, 1, cx, cy).scale(paint.scaleX, paint.scaleY).translate(-cx, -cy)
    if f in (PF.PaintScaleUniform, PF.PaintVarScaleUniform):
        return Transform(paint.scale, 0, 0, paint.scale, 0, 0)
    if f in (PF.PaintScaleUniformAroundCenter, PF.PaintVarScaleUniformAroundCenter):
        cx, cy = paint.centerX, paint.centerY
        return Transform(1, 0, 0, 1, cx, cy).scale(paint.scale, paint.scale).translate(-cx, -cy)
    if f in (PF.PaintRotate, PF.PaintVarRotate):
        return Transform().rotate(math.radians(paint.angle))
    if f in (PF.PaintRotateAroundCenter, PF.PaintVarRotateAroundCenter):
        cx, cy = paint.centerX, paint.centerY
        return Transform(1, 0, 0, 1, cx, cy).rotate(math.radians(paint.angle)).translate(-cx, -cy)
    if f in (PF.PaintSkew, PF.PaintVarSkew):
        return Transform().skew(math.radians(-paint.xSkewAngle), math.radians(paint.ySkewAngle))
    if f in (PF.PaintSkewAroundCenter, PF.PaintVarSkewAroundCenter):
        cx, cy = paint.centerX, paint.centerY
        return Transform(1, 0, 0, 1, cx, cy).skew(
            math.radians(-paint.xSkewAngle), math.radians(paint.ySkewAngle)).translate(-cx, -cy)
    return None


def unwrap(paint):
    """Strip transform paints; for a fill they only move the gradient."""
    while paint_transform(paint) is not None:
        paint = paint.Paint
    return paint


class Palette(object):
    """Palette 0 of a CPAL table, with lookup and appending of colours.

    COLRv0 layers can only name a palette entry, so alpha and the flattened
    gradients need entries of their own; they go on the end, after everything
    the COLRv1 paints reference.
    """

    def __init__(self, cpal):
        self.cpal = cpal
        self.colors = cpal.palettes[0]
        self.lookup = {}
        for index, color in enumerate(self.colors):
            self.lookup.setdefault((color.red, color.green, color.blue, color.alpha), index)
        self.added = 0

    def rgba(self, index, alpha=1.0):
        c = self.colors[index]
        return (c.red, c.green, c.blue, c.alpha / 255.0 * alpha)

    def index(self, rgba):
        r, g, b, a = rgba
        key = (int(round(r)), int(round(g)), int(round(b)),
               max(0, min(255, int(round(a * 255)))))
        if key not in self.lookup:
            for palette in self.cpal.palettes:
                palette.append(Color(blue=key[2], green=key[1], red=key[0], alpha=key[3]))
            self.lookup[key] = len(self.colors) - 1
            self.added += 1
        return self.lookup[key]

    def finish(self):
        self.cpal.numPaletteEntries = len(self.colors)
        if self.cpal.version >= 1:
            labels = getattr(self.cpal, "paletteEntryLabels", None) or []
            self.cpal.paletteEntryLabels = labels + [0xFFFF] * (len(self.colors) - len(labels))


class CompactPathPen(BasePen):
    """SVG path data as short as it goes: integer coordinates, relative
    commands, h/v where a line is axis-aligned, no separator a parser does
    not need."""

    def __init__(self):
        BasePen.__init__(self, None)
        self.parts = []
        self.cur = (0, 0)

    @staticmethod
    def _round(p):
        return (int(round(p[0])), int(round(p[1])))

    @staticmethod
    def _numbers(values):
        out = ""
        for v in values:
            text = str(v)
            if out and not text.startswith("-"):
                out += " "
            out += text
        return out

    def _moveTo(self, p):
        p = self._round(p)
        self.parts.append("M" + self._numbers(p))
        self.cur = p

    def _lineTo(self, p):
        p = self._round(p)
        dx, dy = p[0] - self.cur[0], p[1] - self.cur[1]
        if dy == 0:
            self.parts.append("h%d" % dx)
        elif dx == 0:
            self.parts.append("v%d" % dy)
        else:
            self.parts.append("l" + self._numbers((dx, dy)))
        self.cur = p

    def _curveToOne(self, c1, c2, p):
        c1, c2, p = self._round(c1), self._round(c2), self._round(p)
        x, y = self.cur
        self.parts.append("c" + self._numbers(
            (c1[0] - x, c1[1] - y, c2[0] - x, c2[1] - y, p[0] - x, p[1] - y)))
        self.cur = p

    def _qCurveToOne(self, c, p):
        c, p = self._round(c), self._round(p)
        x, y = self.cur
        self.parts.append("q" + self._numbers((c[0] - x, c[1] - y, p[0] - x, p[1] - y)))
        self.cur = p

    def _closePath(self):
        self.parts.append("z")

    def _endPath(self):
        pass

    def getCommands(self):
        return "".join(self.parts)


def svg_body(leaves, recordings, palette_rgba, k):
    """The <path> elements for one emoji: the flattened layers, drawn in the
    source font's units so the numbers stay short. The group that wraps them
    scales by `k` (source units to font units) and flips y, as SVG's y runs
    down and the font's up."""
    paths = []
    for src, affine, rgba in leaves:
        pen = CompactPathPen()
        recordings[src].replay(TransformPen(pen, Transform(1.0 / k, 0, 0, 1.0 / k, 0, 0).transform(affine)))
        d = pen.getCommands()
        if not d:
            continue
        r, g, b, a = rgba
        fill = "#{:02x}{:02x}{:02x}".format(int(round(r)), int(round(g)), int(round(b)))
        opacity = "" if a >= 0.999 else ' fill-opacity="{:.3g}"'.format(a)
        paths.append('<path fill="{}"{} d="{}"/>'.format(fill, opacity, d))
    return "".join(paths)


def svg_documents(bodies, glyph_map, k):
    """SVG table documents for {glyph name: body}, `SVG_CHUNK` glyphs each,
    gzip-compressed."""
    by_gid = sorted((glyph_map[name], body) for name, body in bodies.items())
    documents = []
    for i in range(0, len(by_gid), SVG_CHUNK):
        chunk = by_gid[i:i + SVG_CHUNK]
        xml = '<svg xmlns="http://www.w3.org/2000/svg">' + "".join(
            '<g id="glyph{}" transform="scale({:g},-{:g})">{}</g>'.format(gid, k, k, body)
            for gid, body in chunk) + "</svg>"
        data = gzip.compress(xml.encode("utf-8"), 9, mtime=0)
        documents.append(SVGDocument(data, chunk[0][0], chunk[-1][0], True))
    return documents


class Flattener(object):
    """Turns a COLRv1 paint graph into COLRv0 layers: (glyph, affine, rgba).

    Solid fills survive exactly. A gradient becomes its area-weighted average
    colour. Transforms compose into the layer. A composite that only masks its
    source with a solid (how Noto fades a layer) becomes that alpha; any other
    blend just draws backdrop then source.
    """

    def __init__(self, table, palette):
        self.layers = table.LayerList.Paint if table.LayerList else []
        self.bases = {r.BaseGlyph: r.Paint for r in table.BaseGlyphList.BaseGlyphPaintRecord}
        self.palette = palette

    def flatten(self, paint, affine, alpha, out):
        f = paint.Format
        if f == PF.PaintColrLayers:
            for layer in self.layers[paint.FirstLayerIndex:paint.FirstLayerIndex + paint.NumLayers]:
                self.flatten(layer, affine, alpha, out)
        elif f == PF.PaintGlyph:
            rgba = self.fill(paint.Paint)
            if rgba is not None:
                out.append((paint.Glyph, affine, (rgba[0], rgba[1], rgba[2], rgba[3] * alpha)))
        elif f == PF.PaintColrGlyph:
            base = self.bases.get(paint.Glyph)
            if base is not None:
                self.flatten(base, affine, alpha, out)
        elif paint_transform(paint) is not None:
            self.flatten(paint.Paint, affine.transform(paint_transform(paint)), alpha, out)
        elif f == PF.PaintComposite:
            self.composite(paint, affine, alpha, out)
        # A bare fill with nothing to clip it is unbounded; nothing to draw.

    def composite(self, paint, affine, alpha, out):
        mode = paint.CompositeMode
        source, backdrop = paint.SourcePaint, paint.BackdropPaint
        if mode in (ot.CompositeMode.SRC_IN, ot.CompositeMode.SRC_ATOP):
            self.flatten(source, affine, alpha * self.mask_alpha(backdrop), out)
        elif mode in (ot.CompositeMode.DEST_IN, ot.CompositeMode.DEST_ATOP):
            self.flatten(backdrop, affine, alpha * self.mask_alpha(source), out)
        elif mode == ot.CompositeMode.SRC:
            self.flatten(source, affine, alpha, out)
        elif mode == ot.CompositeMode.DEST:
            self.flatten(backdrop, affine, alpha, out)
        elif mode in (ot.CompositeMode.CLEAR, ot.CompositeMode.SRC_OUT, ot.CompositeMode.DEST_OUT):
            pass
        else:
            self.flatten(backdrop, affine, alpha, out)
            self.flatten(source, affine, alpha, out)

    def mask_alpha(self, paint):
        paint = unwrap(paint)
        if paint.Format in (PF.PaintSolid, PF.PaintVarSolid):
            return self.palette.rgba(paint.PaletteIndex, paint.Alpha)[3]
        return 1.0

    def fill(self, paint):
        paint = unwrap(paint)
        if paint.Format in (PF.PaintSolid, PF.PaintVarSolid):
            return self.palette.rgba(paint.PaletteIndex, paint.Alpha)
        if paint.Format in GRADIENTS:
            return self.average(paint)
        return None

    def average(self, paint, samples=32):
        stops = sorted((s.StopOffset, self.palette.rgba(s.PaletteIndex, s.Alpha))
                       for s in paint.ColorLine.ColorStop)
        if not stops:
            return None
        radial = paint.Format in RADIAL
        total = 0.0
        acc = [0.0, 0.0, 0.0, 0.0]
        for i in range(samples):
            t = (i + 0.5) / samples
            # Rings of a radial gradient grow with the radius; a linear one is
            # uniform along its axis.
            weight = t if radial else 1.0
            color = self.sample(stops, t)
            for j in range(4):
                acc[j] += weight * color[j]
            total += weight
        return tuple(v / total for v in acc)

    @staticmethod
    def sample(stops, t):
        if t <= stops[0][0]:
            return stops[0][1]
        if t >= stops[-1][0]:
            return stops[-1][1]
        for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
            if t0 <= t <= t1:
                if t1 == t0:
                    return c1
                u = (t - t0) / (t1 - t0)
                return tuple(a + (b - a) * u for a, b in zip(c0, c1))
        return stops[-1][1]


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

def collect_ligatures(font, cmap):
    """Every GSUB ligature as (codepoints) -> ligature glyph, for ligatures
    whose components are all cmap-mapped glyphs."""
    reverse = {}
    for cp, name in cmap.items():
        reverse.setdefault(name, cp)
    out = {}
    if "GSUB" not in font:
        return out
    for lookup in font["GSUB"].table.LookupList.Lookup:
        for st in lookup.SubTable:
            if st.LookupType != 4:
                continue
            for first, ligatures in st.ligatures.items():
                for lig in ligatures:
                    names = (first,) + tuple(lig.Component)
                    cps = tuple(reverse.get(n) for n in names)
                    if None not in cps:
                        out.setdefault(cps, lig.LigGlyph)
    return out


def presentation_codepoints(font):
    """Codepoints the font lists under U+FE0F in its format 14 cmap: the ones
    whose emoji presentation is opt-in."""
    for table in font["cmap"].tables:
        if table.format == 14:
            return {cp for cp, _ in table.uvsDict.get(VS16, [])}
    return set()


def load_emoji_property(path, prop):
    """The codepoints Unicode's emoji-data.txt gives `prop`."""
    out = set()
    with open(path, encoding="utf-8") as handle:
        for raw in handle:
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            span, _, name = (part.strip() for part in line.partition(";"))
            if name != prop:
                continue
            first, _, last = span.partition("..")
            out.update(range(int(first, 16), int(last or first, 16) + 1))
    if not out:
        sys.exit("fill.py: {} lists no {} codepoints".format(path, prop))
    return out


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
        self.ligatures = {key: collect_ligatures(self.fonts[key], self.cmaps[key])
                          for key in (EMOJI, EMOJI_MONO)}
        self.presentation = presentation_codepoints(self.fonts[EMOJI])
        colr = self.fonts[EMOJI]["COLR"]
        if colr.version != 1:
            sys.exit("fill.py: expected a COLRv1 emoji source, got version {}".format(colr.version))
        self.painted = {r.BaseGlyph for r in colr.table.BaseGlyphList.BaseGlyphPaintRecord}
        path = os.path.join(directory, EMOJI_DATA)
        if not os.path.isfile(path):
            sys.exit("fill.py: missing {} (run build/fetch-sources.sh)".format(path))
        self.emoji_presentation = load_emoji_property(path, "Emoji_Presentation")

    def upm(self, key):
        return self.fonts[key]["head"].unitsPerEm

    def emoji_default(self, cp):
        """Unicode shows it as an emoji by default (Emoji_Presentation=Yes)."""
        return cp in self.emoji_presentation

    def has_colour(self, cp):
        """Noto Color Emoji draws it in colour."""
        return self.cmaps[EMOJI].get(cp) in self.painted

    def mono_source(self, cp):
        """The first monochrome source that has it, in rule 2's order."""
        for key in MONO_SOURCES:
            if cp in self.cmaps[key]:
                return key
        return None

    def path(self, key):
        return os.path.join(self.directory, SOURCE_FILES[key][self.weight])


def subset_emoji(path, codepoints, glyph_names):
    """Noto-COLRv1 cut down to `codepoints` and `glyph_names` (sequence and
    presentation glyphs, which no codepoint reaches), their paint graphs and
    the component glyphs those reach. GSUB goes: we rebuild the ligatures we
    want ourselves, and its closure would drag in every glyph they reach."""
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
    subsetter.populate(unicodes=codepoints, glyphs=glyph_names)
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
    outer.Format = PF.PaintTransform
    outer.Transform = affine
    outer.Paint = paint
    return outer


# ---------------------------------------------------------------------------
# OpenType layout additions
# ---------------------------------------------------------------------------

def empty_gsub():
    table = newTable("GSUB")
    table.table = ot.GSUB()
    table.table.Version = 0x00010000
    langsys = ot.LangSys()
    langsys.LookupOrder = None
    langsys.ReqFeatureIndex = 0xFFFF
    langsys.FeatureIndex = []
    langsys.FeatureCount = 0
    script = ot.Script()
    script.DefaultLangSys = langsys
    script.LangSysRecord = []
    script.LangSysCount = 0
    record = ot.ScriptRecord()
    record.ScriptTag = "DFLT"
    record.Script = script
    table.table.ScriptList = ot.ScriptList()
    table.table.ScriptList.ScriptRecord = [record]
    table.table.ScriptList.ScriptCount = 1
    table.table.FeatureList = ot.FeatureList()
    table.table.FeatureList.FeatureRecord = []
    table.table.FeatureList.FeatureCount = 0
    table.table.LookupList = ot.LookupList()
    table.table.LookupList.Lookup = []
    table.table.LookupList.LookupCount = 0
    return table


def add_ligatures(font, mappings, tag=LIGATURE_FEATURE):
    """Append one ligature lookup per mapping ((component names) -> glyph), in
    order, and hang them off `tag` in every language system the font has. A
    shaper runs a feature's lookups in that order, each over the whole run."""
    if "GSUB" not in font:
        font["GSUB"] = empty_gsub()
    gsub = font["GSUB"].table

    indices = []
    for mapping in mappings:
        lookup = ot.Lookup()
        lookup.LookupType = 4
        lookup.LookupFlag = 0
        lookup.SubTable = [buildLigatureSubstSubtable(mapping)]
        lookup.SubTableCount = 1
        gsub.LookupList.Lookup.append(lookup)
        gsub.LookupList.LookupCount = len(gsub.LookupList.Lookup)
        indices.append(gsub.LookupList.LookupCount - 1)

    feature = ot.Feature()
    feature.FeatureParams = None
    feature.LookupListIndex = indices
    feature.LookupCount = len(indices)
    record = ot.FeatureRecord()
    record.FeatureTag = tag
    record.Feature = feature
    # Feature records are kept sorted by tag; every index at or past the
    # insertion point shifts by one.
    records = gsub.FeatureList.FeatureRecord
    position = len([r for r in records if r.FeatureTag <= tag])
    records.insert(position, record)
    gsub.FeatureList.FeatureCount = len(records)
    for script_record in gsub.ScriptList.ScriptRecord:
        script = script_record.Script
        systems = [script.DefaultLangSys] + [r.LangSys for r in script.LangSysRecord]
        for langsys in systems:
            if langsys is None:
                continue
            langsys.FeatureIndex = [i + 1 if i >= position else i for i in langsys.FeatureIndex]
            langsys.FeatureIndex.append(position)
            langsys.FeatureCount = len(langsys.FeatureIndex)
            if langsys.ReqFeatureIndex != 0xFFFF and langsys.ReqFeatureIndex >= position:
                langsys.ReqFeatureIndex += 1
    return indices


def add_variation_sequences(font, entries):
    """A format 14 cmap subtable mapping (codepoint, U+FE0F) to `entries`:
    {codepoint: glyph name or None for the default glyph}."""
    for table in font["cmap"].tables:
        if table.format == 14:
            sys.exit("fill.py: the face already has a format 14 cmap subtable")
    uvs = CmapSubtable.newSubtable(14)
    uvs.platformID = 0
    uvs.platEncID = 5
    uvs.language = 0
    uvs.cmap = {}
    uvs.uvsDict = {VS16: sorted(entries.items())}
    font["cmap"].tables.append(uvs)


# ---------------------------------------------------------------------------
# The fill
# ---------------------------------------------------------------------------

class Filler(object):
    def __init__(self, font, style, sources, segoe, overrides, emoji_fallthrough,
                 emoji_format, sequences, svg):
        self.font = font
        self.style = style
        self.sources = sources
        self.segoe = segoe
        self.colour_overrides = overrides["colour"]
        self.mono_overrides = overrides["monochrome"]
        self.emoji_fallthrough = emoji_fallthrough
        self.emoji_format = emoji_format
        self.want_sequences = sequences
        self.want_svg = svg

        self.cmap = font.getBestCmap()
        self.upm = font["head"].unitsPerEm
        hmtx = font["hmtx"]
        self.cell = hmtx[self.cmap[0x41]][0]
        self.ascent = font["hhea"].ascent
        self.descent = font["hhea"].descent
        if len({hmtx[g][0] for g in font.getGlyphOrder() if hmtx[g][0]}) != 1:
            sys.exit("fill.py: {} is not monospaced before filling".format(style))
        if "COLR" in font or "CPAL" in font or "SVG " in font:
            sys.exit("fill.py: {} already has a COLR/CPAL/SVG table".format(style))

        self.filled = {}        # cp -> manifest entry
        self.sequences = {}     # cps -> manifest entry
        self.presentation = {}  # cp -> manifest entry (the extra emoji glyph)
        self.uvs = {}           # cp -> glyph name or None (the format 14 entries)
        self.glue = {}          # cp -> glyph name
        self.ligatures = 0
        self.layer_glyphs = 0
        self.svg_glyphs = 0
        self.svg_documents = 0
        self.unfilled = []      # Segoe-covered gaps no source can fill
        self.overrides_mapped = []  # overridden codepoints the face already maps
        self.copyrights = []    # source copyright lines appended to name ID 0
        self.modifier_ligatures = 0  # skin-tone and hair ligatures to the base
        self.skipped = {}       # reason -> [cp]
        self.blank = []         # source had the codepoint but no ink

    def box(self, wide):
        return (0, self.descent, self.cell * (2 if wide else 1), self.ascent)

    # -- planning -----------------------------------------------------------

    def plan(self):
        """Decide the source for every gap. Returns [(cp, source_key)]."""
        candidates = set(self.segoe) | set(self.sources.cmaps[EMOJI])
        # Before anything is filled: self.cmap is the font's own cmap dict,
        # which run() adds to.
        self.overrides_mapped = sorted(cp for cp in self.colour_overrides | self.mono_overrides
                                       if cp in self.cmap)
        plan = []
        for cp in sorted(candidates):
            if cp in self.cmap:
                continue
            why = skip_reason(cp)
            if why:
                self.skipped.setdefault(why, []).append(cp)
                continue
            if cp in self.mono_overrides:
                plan.append((cp, self.sources.mono_source(cp)))
            elif cp in self.segoe and not self.colour_by_rule1(cp):
                if cp in self.sources.cmaps[SYMBOLS2]:
                    plan.append((cp, SYMBOLS2))
                elif cp in self.sources.cmaps[SYMBOLS]:
                    plan.append((cp, SYMBOLS))
                elif self.emoji_fallthrough and cp in self.sources.cmaps[EMOJI_MONO]:
                    plan.append((cp, EMOJI_MONO))
                else:
                    self.unfilled.append(cp)
            else:
                plan.append((cp, EMOJI))
        return plan

    def colour_by_rule1(self, cp):
        """A Segoe-covered gap that is colour anyway: one Unicode shows as an
        emoji by default and Noto Color Emoji draws, or one listed in
        build/colour-overrides.txt."""
        return (cp in self.colour_overrides
                or (self.sources.emoji_default(cp) and self.sources.has_colour(cp)))

    def override(self, cp):
        if cp in self.colour_overrides:
            return "colour"
        if cp in self.mono_overrides:
            return "monochrome"
        return None

    def plan_sequences(self, mapped):
        """The ZWJ sequences to carry over: every component mapped (once the
        gaps are filled), nothing with a skin tone or hair component."""
        out = []
        for cps, glyph in sorted(self.sources.ligatures[EMOJI].items()):
            if ZWJ not in cps or any(is_modifier(cp) for cp in cps):
                continue
            if all(cp == ZWJ or cp in mapped for cp in cps) and glyph in self.sources.painted:
                out.append((cps, glyph))
        return out

    def plan_presentation(self, mapped, emoji_cps):
        """`<cp> FE0F` for every codepoint Noto lists as opt-in emoji, which
        is every variation sequence Unicode defines: the codepoint's own glyph
        if that is already the colour emoji, else Noto Color Emoji's glyph as
        an extra, reachable only through the selector. Nothing else gets one;
        a selector Unicode does not define is dropped by the terminals that
        check (Ghostty) and never typed by anyone else."""
        extras, defaults = [], []
        for cp in sorted(self.sources.presentation):
            if cp not in mapped:
                continue
            if cp in emoji_cps:
                defaults.append(cp)
            elif self.sources.cmaps[EMOJI].get(cp) in self.sources.painted:
                extras.append((cp, self.sources.cmaps[EMOJI][cp]))
        return extras, defaults

    # -- applying -----------------------------------------------------------

    def run(self):
        plan = self.plan()
        order = list(self.font.getGlyphOrder())
        new_glyphs = {}   # name -> (Glyph, advance, lsb)
        new_cmap = {}     # cp -> name

        # Monochrome glyphs first, in codepoint order.
        for cp, key in plan:
            if key == EMOJI:
                continue
            k = float(self.upm) / self.sources.upm(key)
            wide = is_wide(cp, key == EMOJI_MONO)
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
                               "segoe": cp in self.segoe,
                               "emoji_default": self.sources.emoji_default(cp),
                               "override": self.override(cp),
                               "bounds": list(bounds)}

        emoji_cps = [cp for cp, key in plan if key == EMOJI]
        mapped = set(self.cmap) | set(new_cmap) | set(emoji_cps)
        sequences, extras, defaults = [], [], []
        if self.want_sequences:
            sequences = self.plan_sequences(mapped)
            extras, defaults = self.plan_presentation(mapped, set(emoji_cps))
        if emoji_cps or sequences or extras:
            self.add_emoji(emoji_cps, sequences, extras, order, new_glyphs, new_cmap)
        for cp in defaults:
            self.uvs[cp] = None

        if self.want_sequences:
            self.add_glue(order, new_glyphs, new_cmap)

        # Install.
        if len(order) > 65535:
            sys.exit("fill.py: {} glyphs, over the 65535 a TrueType font can hold".format(len(order)))
        self.font.setGlyphOrder(order)
        glyf = self.font["glyf"]
        hmtx = self.font["hmtx"]
        for name, (glyph, advance, lsb) in new_glyphs.items():
            glyf[name] = glyph
            hmtx[name] = (advance, lsb)
        for table in self.font["cmap"].tables:
            if not table.isUnicode() or table.format == 14:
                continue
            for cp, name in new_cmap.items():
                if table.format == 4 and cp > 0xFFFF:
                    continue
                table.cmap[cp] = name
        if any(cp > 0xFFFF for cp in new_cmap) and not any(
                t.isUnicode() and t.format == 12 for t in self.font["cmap"].tables):
            sys.exit("fill.py: no format 12 cmap subtable for supplementary codepoints")
        if self.uvs:
            add_variation_sequences(self.font, self.uvs)
        lookups = []
        if self.want_sequences:
            tones, hair = self.modifier_mappings()
            self.modifier_ligatures = len(tones) + len(hair)
            lookups += [m for m in (tones, hair) if m]
        if self.sequences:
            mapping = self.ligature_mapping(new_cmap)
            self.ligatures = len(mapping)
            lookups.append(mapping)
        if lookups:
            add_ligatures(self.font, lookups)
        self.add_copyrights()

    def modifier_mappings(self):
        """Ligatures that fold the variants the fill leaves out back onto what
        it keeps, without adding a glyph: a skin tone after an emoji becomes
        that emoji's own glyph, and a person followed by U+200D and a hair
        component becomes the person. Tones first, as a lookup of its own, so
        that a toned person with hair loses both, and a toned ZWJ sequence
        reaches the sequence ligatures as its untoned form. The pairs are the
        ones Noto Color Emoji draws, so only what Unicode defines is folded."""
        def glyph(cp):
            return self.cmap.get(cp) or self.glue.get(cp)

        def tone(cp):
            return SKIN_TONES[0] <= cp <= SKIN_TONES[1]

        tones, hair = {}, {}
        for cps in sorted(self.sources.ligatures[EMOJI]):
            for before, cp in zip(cps, cps[1:]):
                if tone(cp) and before != ZWJ and glyph(before) and glyph(cp):
                    tones[(glyph(before), glyph(cp))] = glyph(before)
            bare = tuple(cp for cp in cps if not tone(cp))
            if (len(bare) == 3 and bare[1] == ZWJ and HAIR[0] <= bare[2] <= HAIR[1]
                    and all(glyph(cp) for cp in bare)):
                hair[tuple(glyph(cp) for cp in bare)] = glyph(bare[0])
        return tones, hair

    def add_copyrights(self):
        """Append the copyright line of every Noto font a glyph came from to
        name ID 0, so each copy of the face carries it -- the OFL's condition 2
        -- even where it is installed without the license files."""
        used = {e["source"] for e in self.filled.values()} - {GLUE}
        emoji = list(self.filled.values()) + list(self.sequences.values()) + \
            list(self.presentation.values())
        if any(e.get("mono") for e in emoji if e.get("source", EMOJI) == EMOJI):
            used.add(EMOJI_MONO)  # the monochrome fallback outlines
        lines = []
        for key in (SYMBOLS2, SYMBOLS, EMOJI, EMOJI_MONO):
            line = self.sources.fonts[key]["name"].getDebugName(0) if key in used else None
            if line and line not in lines:
                lines.append(line)
        self.copyrights = lines
        name = self.font["name"]
        for record in [r for r in name.names if r.nameID == 0]:
            text = record.toUnicode()
            extra = [line for line in lines if line not in text]
            if extra:
                name.setName(" ".join([text] + extra), 0,
                             record.platformID, record.platEncID, record.langID)

    def add_glue(self, order, new_glyphs, new_cmap):
        """U+200D and U+FE0F as empty zero-width glyphs, so a sequence stays
        in this font for the ligature lookup to see."""
        for cp in (ZWJ, VS16):
            if cp in self.cmap:
                self.glue[cp] = self.cmap[cp]
                continue
            name = "{}u{:04X}".format(PREFIX[EMOJI], cp)
            new_glyphs[name] = (empty_glyph(), 0, 0)
            new_cmap[cp] = name
            order.append(name)
            self.glue[cp] = name
            self.filled[cp] = {"source": GLUE, "glyph": name, "wide": False,
                               "segoe": cp in self.segoe, "emoji_default": False,
                               "override": None, "bounds": None}

    def glyph_for(self, cp, new_cmap):
        if cp in self.glue:
            return self.glue[cp]
        return self.cmap.get(cp) or new_cmap[cp]

    def ligature_mapping(self, new_cmap):
        """(component glyph names) -> sequence glyph. After every component
        whose emoji presentation is opt-in -- where the RGI sequences carry
        U+FE0F -- three spellings are accepted: the plain glyph alone (a
        shaper that dropped the selector, or none was typed), the plain glyph
        and U+FE0F (a shaper that keeps it), and the colour glyph our format
        14 cmap maps the pair to (HarfBuzz and CoreText resolve the selector
        before GSUB, and drop it)."""
        mapping = {}
        for cps, entry in sorted(self.sequences.items()):
            options = []
            for cp in cps:
                plain = self.glyph_for(cp, new_cmap)
                if cp != ZWJ and cp in self.sources.presentation:
                    spellings = [(plain,), (plain, self.glue[VS16])]
                    if self.uvs.get(cp):
                        spellings.append((self.uvs[cp],))
                    options.append(spellings)
                else:
                    options.append([(plain,)])
            for combo in itertools.product(*options):
                mapping[tuple(name for part in combo for name in part)] = entry["glyph"]
        # Longest first, then by name: the order fontTools 4.46 sorts into.
        # Newer fontTools sorts by length only and keeps insertion order for
        # the rest, so handing it this order makes both write the same GSUB.
        return dict(sorted(mapping.items(), key=lambda item: (-len(item[0]), item[0])))

    def add_emoji(self, codepoints, sequences, extras, order, new_glyphs, new_cmap):
        key = EMOJI
        keep_v1 = self.emoji_format in ("colrv1", "both")
        keep_v0 = self.emoji_format in ("colrv0", "both")
        wanted_glyphs = sorted({g for _, g in sequences} | {g for _, g in extras})
        sub = subset_emoji(self.sources.path(key), codepoints, wanted_glyphs)
        sub_cmap = sub.getBestCmap()
        missing = [cp for cp in codepoints if cp not in sub_cmap]
        if missing:
            sys.exit("fill.py: subset lost {} emoji, e.g. U+{:04X}".format(len(missing), missing[0]))
        k = float(self.upm) / sub["head"].unitsPerEm
        sub_glyphs = sub.getGlyphSet()
        km = float(self.upm) / self.sources.upm(EMOJI_MONO)
        mono_glyphs = self.sources.glyph_sets[EMOJI_MONO]

        # What each COLR base glyph is for: (new name, wide, mono source glyph,
        # (kind, what)). Noto may point two things at one glyph; the second
        # shares the first's entry and is noted as such.
        roles = {}
        shared_sequences, shared_extras = [], []
        for cp in codepoints:
            roles[sub_cmap[cp]] = ("{}u{:04X}".format(PREFIX[key], cp), is_wide(cp, True),
                                   self.sources.cmaps[EMOJI_MONO].get(cp), ("base", cp))
        for cps, glyph in sequences:
            if glyph in roles:
                shared_sequences.append((cps, glyph))
                continue
            roles[glyph] = ("{}seq.{}".format(PREFIX[key], hexseq(cps)), True,
                            self.sources.ligatures[EMOJI_MONO].get(cps), ("sequence", cps))
        for cp, glyph in extras:
            if glyph in roles:
                shared_extras.append((cp, glyph))
                continue
            roles[glyph] = ("{}u{:04X}.emoji".format(PREFIX[key], cp), True,
                            self.sources.cmaps[EMOJI_MONO].get(cp), ("presentation", cp))

        # New names: base glyphs by role, components by their old name.
        mapping = {}
        for old in sub.getGlyphOrder():
            if old == ".notdef":
                continue
            mapping[old] = roles[old][0] if old in roles else "{}{}".format(PREFIX[key], old)
        if len(set(mapping.values())) != len(mapping):
            sys.exit("fill.py: emoji glyph names collide after renaming")

        colr = sub["COLR"]
        table = colr.table
        if table.BaseGlyphRecordCount or table.LayerRecordCount:
            sys.exit("fill.py: emoji source carries COLRv0 records; not handled")
        clips = table.ClipList.clips if table.ClipList else {}
        palette = Palette(sub["CPAL"])
        flattener = Flattener(table, palette)
        recordings = {}
        layer_cache = {}
        entries = {}      # old base glyph -> manifest entry
        v0 = {}
        svg = {}          # new base glyph -> SVG paths

        for record in table.BaseGlyphList.BaseGlyphPaintRecord:
            old = record.BaseGlyph
            if old not in roles:
                sys.exit("fill.py: COLR base glyph {} has no role in this face".format(old))
            name, wide, mono_name, (kind, what) = roles[old]
            box = self.box(wide)
            clip = clips.get(old)
            if clip is None:
                clip = record.Paint.computeClipBox(colr, sub_glyphs, quantization=1)
                if clip is None:
                    sys.exit("fill.py: cannot bound the paint of {}".format(name))
            scale, dx, dy = fit(scaled_bounds((clip.xMin, clip.yMin, clip.xMax, clip.yMax), k), box)
            root = Transform(k * scale, 0, 0, k * scale, dx, dy)
            bounds = None

            leaves = []
            if keep_v0 or self.want_svg:
                flattener.flatten(record.Paint, root, 1.0, leaves)
                for src, _, _ in leaves:
                    if src not in recordings:
                        recordings[src] = record_outline(sub_glyphs, src)[0]
            if self.want_svg:
                svg[name] = svg_body(leaves, recordings, palette.rgba, k)
            if keep_v0:
                layers = []
                for src, affine, rgba in leaves:
                    cache_key = (src, tuple(round(v, 3) for v in affine))
                    if cache_key not in layer_cache:
                        glyph, bbox = transformed_glyph(recordings[src], affine)
                        if glyph is None:
                            layer_cache[cache_key] = None
                        else:
                            layer_name = "{}l{}".format(PREFIX[key], self.layer_glyphs)
                            self.layer_glyphs += 1
                            new_glyphs[layer_name] = (glyph, 0, bbox[0])
                            order.append(layer_name)
                            layer_cache[cache_key] = (layer_name, bbox)
                    if layer_cache[cache_key] is None:
                        continue
                    layer_name, bbox = layer_cache[cache_key]
                    layers.append((layer_name, palette.index(rgba)))
                    bounds = union([bounds, bbox])
                if layers:
                    v0[name] = layers

            if keep_v1:
                record.Paint = wrap_transform(record.Paint, k * scale, dx, dy)
                new_clip = ot.ClipBox()
                new_clip.Format = 1
                new_clip.xMin = int(math.floor(clip.xMin * k * scale + dx))
                new_clip.yMin = int(math.floor(clip.yMin * k * scale + dy))
                new_clip.xMax = int(math.ceil(clip.xMax * k * scale + dx))
                new_clip.yMax = int(math.ceil(clip.yMax * k * scale + dy))
                clips[old] = new_clip
                if bounds is None:
                    bounds = (new_clip.xMin, new_clip.yMin, new_clip.xMax, new_clip.yMax)

            # Monochrome fallback outline, for renderers with no colour support.
            # A presentation extra whose plain glyph is already that outline,
            # at the same width, just points at it.
            fallback, fb_bounds = None, None
            plain = self.filled.get(what) if kind == "presentation" else None
            if plain and plain["source"] == EMOJI_MONO and plain["wide"] == wide:
                fallback, fb_bounds = composite_glyph(plain["glyph"], plain["bounds"])
            elif mono_name is not None:
                fallback, fb_bounds = outline_glyph(mono_glyphs, mono_name, km, box)
            if fallback is None:
                new_glyphs[name] = (empty_glyph(), self.cell, 0)
            else:
                new_glyphs[name] = (fallback, self.cell, fb_bounds[0])

            entry = {"glyph": name, "wide": wide, "mono": fallback is not None,
                     "bounds": list(bounds) if bounds else None}
            entries[old] = entry
            if kind == "base":
                new_cmap[what] = name
                entry.update({"source": key, "segoe": what in self.segoe,
                              "emoji_default": self.sources.emoji_default(what),
                              "override": self.override(what)})
                self.filled[what] = entry
            elif kind == "sequence":
                self.sequences[what] = entry
            else:
                self.presentation[what] = entry
                self.uvs[what] = name

        for cps, glyph in shared_sequences:
            self.sequences[cps] = dict(entries[glyph], shared=True)
        for cp, glyph in shared_extras:
            self.presentation[cp] = dict(entries[glyph], shared=True)
            self.uvs[cp] = entries[glyph]["glyph"]

        # Deterministic order: bases by codepoint, then sequences, then the
        # presentation extras, then the COLRv1 components as the subset ordered
        # them (the COLRv0 layer glyphs were appended as they were made).
        for cp in sorted(codepoints):
            order.append(mapping[sub_cmap[cp]])
        for cps, glyph in sequences:
            if (cps, glyph) not in shared_sequences:
                order.append(mapping[glyph])
        for cp, glyph in extras:
            if (cp, glyph) not in shared_extras:
                order.append(mapping[glyph])

        glyph_map = {name: i for i, name in enumerate(order)}
        if keep_v1:
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
                if old == ".notdef" or old in roles:
                    continue
                glyph = sub_glyf[old]
                if glyph.isComposite():
                    for component in glyph.components:
                        component.glyphName = mapping[component.glyphName]
                new_glyphs[mapping[old]] = (glyph, 0, sub_hmtx[old][1])
                order.append(mapping[old])
            if keep_v0:
                populateCOLRv0(table, v0, glyph_map)
            self.font["COLR"] = colr
        else:
            self.font["COLR"] = buildCOLR(v0, version=0, glyphMap=glyph_map)
        palette.finish()
        self.font["CPAL"] = sub["CPAL"]
        if self.want_svg:
            table = newTable("SVG ")
            table.docList = svg_documents(svg, glyph_map, k)
            self.font["SVG "] = table
            self.svg_glyphs = len(svg)
            self.svg_documents = len(table.docList)

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
            "policy": {"emoji_fallthrough": self.emoji_fallthrough,
                       "emoji_format": self.emoji_format,
                       "sequences": self.want_sequences,
                       "svg": self.want_svg},
            "sources": self.sources.versions,
            "copyrights": self.copyrights,
            "summary": {
                "filled": len(self.filled),
                "by_source": by_source,
                "segoe_fallthrough_to_mono_emoji": len([
                    e for e in self.filled.values() if e["source"] == EMOJI_MONO]),
                "segoe_emoji_default_in_colour": len([
                    e for e in self.filled.values()
                    if e["source"] == EMOJI and e["segoe"] and e["emoji_default"]
                    and not e["override"]]),
                "colour_by_override": len([
                    e for e in self.filled.values() if e["override"] == "colour"]),
                "monochrome_by_override": len([
                    e for e in self.filled.values() if e["override"] == "monochrome"]),
                "sequences": len(self.sequences),
                "ligatures": self.ligatures,
                "modifier_ligatures": self.modifier_ligatures,
                "presentation": len(self.presentation),
                "variation_sequences": len(self.uvs),
                "layer_glyphs": self.layer_glyphs,
                "svg_glyphs": self.svg_glyphs,
                "svg_documents": self.svg_documents,
                "unfilled_segoe": len(self.unfilled),
                "blank_in_source": len(self.blank),
                "skipped": {why: len(cps) for why, cps in sorted(self.skipped.items())},
            },
            "filled": {"{:04X}".format(cp): entry for cp, entry in sorted(self.filled.items())},
            "sequences": {hexseq(cps): entry for cps, entry in sorted(self.sequences.items())},
            "presentation": {"{:04X}".format(cp): entry for cp, entry in sorted(self.presentation.items())},
            "variation_sequences": {"{:04X}".format(cp): name for cp, name in sorted(self.uvs.items())},
            "glue": {"{:04X}".format(cp): name for cp, name in sorted(self.glue.items())},
            "unfilled_segoe": ["{:04X}".format(cp) for cp in self.unfilled],
            "overrides_not_gaps": ["{:04X}".format(cp) for cp in self.overrides_mapped],
            "blank_in_source": ["{:04X}".format(cp) for cp in self.blank],
            "skipped": {why: ["{:04X}".format(cp) for cp in cps]
                        for why, cps in sorted(self.skipped.items())},
        }

    def summary(self):
        m = self.manifest()["summary"]
        parts = ["{} {}".format(m["by_source"].get(k, 0), k)
                 for k in (SYMBOLS2, SYMBOLS, EMOJI_MONO, EMOJI)]
        not_gaps = len(self.overrides_mapped)
        return ("{}: +{} codepoints ({}; {} Segoe-covered emoji in colour by default, "
                "overrides {} colour / {} monochrome{}), {} ZWJ sequences, "
                "{} presentation selectors; {} Segoe-covered gaps left unfilled; "
                "{} skipped".format(
                    self.style, m["filled"], ", ".join(parts),
                    m["segoe_emoji_default_in_colour"], m["colour_by_override"],
                    m["monochrome_by_override"],
                    ", {} already mapped".format(not_gaps) if not_gaps else "",
                    m["sequences"], m["variation_sequences"], m["unfilled_segoe"],
                    sum(m["skipped"].values())))


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
    parser.add_argument("--colour-overrides", default=os.path.join(here, "colour-overrides.txt"),
                        help="codepoints to fill in colour whatever the rules say "
                             "(default: %(default)s)")
    parser.add_argument("--monochrome-overrides",
                        default=os.path.join(here, "monochrome-overrides.txt"),
                        help="codepoints to fill in monochrome whatever the rules say "
                             "(default: %(default)s)")
    parser.add_argument("--manifest", help="write a JSON record of what was filled here")
    parser.add_argument("--emoji-format", choices=EMOJI_FORMATS, default=DEFAULT_EMOJI_FORMAT,
                        help="colour format for the emoji (default: %(default)s)")
    parser.add_argument("--no-svg", action="store_true",
                        help="skip the OpenType SVG table (Ghostty on macOS then draws "
                             "the emoji monochrome)")
    parser.add_argument("--no-sequences", action="store_true",
                        help="skip the ZWJ sequence ligatures and the U+FE0F presentation "
                             "selectors (and the U+200D/U+FE0F glyphs they need)")
    parser.add_argument("--no-emoji-fallthrough", action="store_true",
                        help="leave a Segoe-covered gap alone when neither Noto symbol "
                             "font has it, instead of taking Noto Emoji's monochrome glyph")
    args = parser.parse_args()

    if not os.path.isfile(args.source):
        sys.exit("fill.py: no such file: {}".format(args.source))
    weight = "Bold" if args.style in ("Bold", "BoldItalic") else "Regular"

    segoe = charset.load(args.charset)
    overrides = {"colour": charset.load(args.colour_overrides),
                 "monochrome": charset.load(args.monochrome_overrides)}
    sources = Sources(args.sources, weight)

    def check(path, cps, why):
        if cps:
            sys.exit("fill.py: {}: {} for {}".format(
                path, why, ", ".join("U+{:04X}".format(cp) for cp in sorted(cps))))
    both = overrides["colour"] & overrides["monochrome"]
    check(args.monochrome_overrides, both, "also listed in {}".format(args.colour_overrides))
    check(args.colour_overrides, {cp for cp in overrides["colour"]
                                  if skip_reason(cp) or not sources.has_colour(cp)},
          "Noto Color Emoji has no colour glyph")
    check(args.monochrome_overrides, {cp for cp in overrides["monochrome"]
                                      if skip_reason(cp) or not sources.mono_source(cp)},
          "no monochrome source has a glyph")
    font = TTFont(args.source)
    filler = Filler(font, args.style, sources, segoe, overrides, not args.no_emoji_fallthrough,
                    args.emoji_format, not args.no_sequences, not args.no_svg)
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
