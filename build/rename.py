#!/usr/bin/env python3
"""Rewrite a patched Nerd Font's name table to the MesloLGS NF DF family.

font-patcher names its output after the upstream family ("MesloLGS Nerd Font
Mono"). We ship a font whose glyph geometry deliberately differs from stock
Nerd Fonts, so it gets its own family name rather than shadowing theirs.

Reads one TTF, writes one TTF. Everything except the name table is untouched.
"""

import argparse
import os
import sys

try:
    from fontTools.ttLib import TTFont
except ImportError:
    sys.exit("rename.py: fontTools is not installed (pip install fonttools)")

FAMILY = "MesloLGS NF DF"
PS_FAMILY = "MesloLGSNFDF"

# The four RIBBI styles, keyed by the style token in the patched filename.
STYLES = {
    "Regular": ("Regular", "Regular"),
    "Bold": ("Bold", "Bold"),
    "Italic": ("Italic", "Italic"),
    "BoldItalic": ("Bold Italic", "BoldItalic"),
}

# Name IDs we set explicitly. Anything else is left as font-patcher wrote it.
NAME_FAMILY = 1
NAME_SUBFAMILY = 2
NAME_UNIQUE = 3
NAME_FULL = 4
NAME_VERSION = 5
NAME_PS = 6
NAME_LICENSE = 13
NAME_LICENSE_URL = 14

# What the faces are distributed under; "MesloLGS NF DF License.txt" says why
# and has the parts' own notices. The OFL asks for its text or a pointer to it
# with every copy, and a font installed from the Scoop bucket arrives alone.
LICENSE = ("This Font Software is licensed under the SIL Open Font License, "
           "Version 1.1. Its Meslo LG glyphs are also available under the Apache "
           "License, Version 2.0, and its Nerd Fonts glyph sets under their own "
           "licenses. Notices and full texts: https://github.com/greglamb/dotfiles.fonts")
LICENSE_URL = "https://openfontlicense.org"
# Typographic family/subfamily and the WWS pair. A RIBBI family does not need
# them, and leaving upstream's values behind would make the font report two
# different families depending on which name the consumer reads.
NAME_DROP = (16, 17, 18, 21, 22)


def rename(src, dst, style_key):
    subfamily, ps_style = STYLES[style_key]
    font = TTFont(src)
    name = font["name"]

    version = ""
    record = name.getName(NAME_VERSION, 3, 1) or name.getName(NAME_VERSION, 1, 0)
    if record:
        version = record.toUnicode()

    full = "{} {}".format(FAMILY, subfamily)
    values = {
        NAME_FAMILY: FAMILY,
        NAME_SUBFAMILY: subfamily,
        NAME_UNIQUE: "{}; {}".format(full, version) if version else full,
        NAME_FULL: full,
        NAME_PS: "{}-{}".format(PS_FAMILY, ps_style),
        NAME_LICENSE: LICENSE,
        NAME_LICENSE_URL: LICENSE_URL,
    }

    # Keep every (platform, encoding, language) the font already advertises so
    # we do not drop the Mac records some older macOS font pickers still read.
    for name_id, value in values.items():
        targets = [r for r in name.names if r.nameID == name_id]
        if not targets:
            name.setName(value, name_id, 3, 1, 0x409)
            continue
        for r in targets:
            name.setName(value, name_id, r.platformID, r.platEncID, r.langID)

    name.names = [r for r in name.names if r.nameID not in NAME_DROP]

    if len(values[NAME_PS]) > 63:
        sys.exit("rename.py: PostScript name is longer than 63 characters")

    font.save(dst)
    return full, values[NAME_PS]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="patched TTF produced by font-patcher")
    parser.add_argument("dest", help="output TTF path")
    parser.add_argument("style", choices=sorted(STYLES), help="RIBBI style of this face")
    args = parser.parse_args()

    if not os.path.isfile(args.source):
        sys.exit("rename.py: no such file: {}".format(args.source))

    full, ps = rename(args.source, args.dest, args.style)
    print("  {} -> {} ({})".format(os.path.basename(args.dest), full, ps))


if __name__ == "__main__":
    main()
