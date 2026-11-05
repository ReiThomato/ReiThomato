#!/usr/bin/env python3
"""Refresh the REITHOMATO language card with a restrained crimson palette."""

from __future__ import annotations

import re
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
    "&title_color=B33A35"
    "&text_color=E2DAD2"
    "&prog_bar_bg_color=562528"
    "&bg_color=0D080B00"
    "&hide_border=true"
    "&cache_seconds=21600"
)

SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def monochrome_crimson(svg_text: str) -> str:
    root = ET.fromstring(svg_text)
    if local_name(root.tag) != "svg":
        raise ValueError("The language endpoint did not return an SVG document.")

    # Slightly enlarge the content while keeping both README panels the same size.
    root.set("width", "440")
    root.set("height", "175")
    root.set("viewBox", "0 0 415 165")

    for element in root.iter():
        tag = local_name(element.tag)

        if tag == "style" and element.text:
            css = element.text
            css = re.sub(
                r"(\.header\s*\{[^}]*?\bfill:\s*)#[0-9a-fA-F]{3,8}",
                r"\1#B33A35",
                css,
                count=1,
            )
            css = re.sub(
                r"(\.stat\s*\{[^}]*?\bfill:\s*)#[0-9a-fA-F]{3,8}",
                r"\1#E2DAD2",
                css,
                count=1,
            )
            css = re.sub(
                r"(\.lang-name\s*\{[^}]*?\bfill:\s*)#[0-9a-fA-F]{3,8}",
                r"\1#E2DAD2",
                css,
                count=1,
            )
            css = re.sub(
                r"(\.progress-background\s*\{\s*fill:\s*)#[0-9a-fA-F]{3,8}",
                r"\1#562528",
                css,
                count=1,
            )
            element.text = css

        elif tag == "circle":
            element.set("fill", "#B33A35")

        elif tag == "rect" and element.get("data-testid") == "lang-progress":
            element.set("fill", "#B33A35")

    # Keep the SVG self-contained: no nested remote image and no color filter.
    keep_outside_group = {"defs", "style", "title", "desc", "metadata"}
    group = ET.Element(f"{{{SVG_NS}}}g")

    for child in list(root):
        if local_name(child.tag) in keep_outside_group:
            continue
        root.remove(child)
        group.append(child)

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
        rendered = monochrome_crimson(svg_text)
        OUTPUT.write_text(rendered + "\n", encoding="utf-8")
        print(f"Updated {OUTPUT.name} ({OUTPUT.stat().st_size} bytes).")
        return 0
    except Exception as exc:
        print(f"Could not refresh the language card: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
