#!/usr/bin/env python3
"""Fetch GitHub Stats Extended's language card and recolor it in the REITHOMATO palette."""

from __future__ import annotations

import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "languages-mono.svg"

SOURCE_URL = (
    "https://github-stats-extended.vercel.app/api/top-langs/"
    "?username=ReiThomato"
    "&layout=compact"
    "&langs_count=5"
    "&card_width=440"
    "&stats_format=percentages"
    "&size_weight=0.5"
    "&count_weight=0.5"
    "&custom_title=%E2%8C%98%20LANGUAGES"
    "&title_color=E8798E"
    "&text_color=F3E7EA"
    "&prog_bar_bg_color=5A1D2D"
    "&bg_color=0D080B00"
    "&hide_border=true"
    "&cache_seconds=21600"
)

SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def make_monochrome(svg_text: str) -> str:
    root = ET.fromstring(svg_text)
    if local_name(root.tag) != "svg":
        raise ValueError("The language endpoint did not return an SVG document.")

    defs = ET.Element(f"{{{SVG_NS}}}defs")
    filt = ET.SubElement(
        defs,
        f"{{{SVG_NS}}}filter",
        {"id": "reithomato-crimson", "color-interpolation-filters": "sRGB"},
    )
    ET.SubElement(
        filt,
        f"{{{SVG_NS}}}feColorMatrix",
        {"type": "saturate", "values": "0", "result": "gray"},
    )
    transfer = ET.SubElement(
        filt, f"{{{SVG_NS}}}feComponentTransfer", {"in": "gray"}
    )
    ET.SubElement(
        transfer,
        f"{{{SVG_NS}}}feFuncR",
        {"type": "table", "tableValues": "0.055 0.96"},
    )
    ET.SubElement(
        transfer,
        f"{{{SVG_NS}}}feFuncG",
        {"type": "table", "tableValues": "0.012 0.55"},
    )
    ET.SubElement(
        transfer,
        f"{{{SVG_NS}}}feFuncB",
        {"type": "table", "tableValues": "0.025 0.62"},
    )

    group = ET.Element(
        f"{{{SVG_NS}}}g", {"filter": "url(#reithomato-crimson)"}
    )
    keep_outside_group = {"defs", "style", "title", "desc", "metadata"}

    for child in list(root):
        if local_name(child.tag) in keep_outside_group:
            continue
        root.remove(child)
        group.append(child)

    root.insert(0, defs)
    root.append(group)

    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def main() -> int:
    request = urllib.request.Request(
        SOURCE_URL,
        headers={
            "User-Agent": "REITHOMATO-GitHub-Profile/1.0",
            "Accept": "image/svg+xml",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            svg_text = response.read().decode("utf-8")
        rendered = make_monochrome(svg_text)
        OUTPUT.write_text(rendered + "\n", encoding="utf-8")
        print(f"Updated {OUTPUT.name} ({OUTPUT.stat().st_size} bytes).")
        return 0
    except Exception as exc:
        print(f"Could not refresh the language card: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
