#!/usr/bin/env python3
"""Build the REITHOMATO language card and a single, fixed two-panel SVG."""

from __future__ import annotations

import copy
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LANGUAGE_OUTPUT = ROOT / "languages-mono.svg"
COMBINED_OUTPUT = ROOT / "royal-panels.svg"

STATS_URL = (
    "https://github-stats-extended.vercel.app/api"
    "?username=ReiThomato"
    "&hide_rank=true"
    "&show_icons=true"
    "&include_all_commits=true"
    "&card_width=440"
    "&line_height=23"
    "&number_format=long"
    "&bg_color=0D080B00"
    "&title_color=B33A35"
    "&text_color=E2DAD2"
    "&icon_color=B33A35"
    "&hide_border=true"
    "&contribs_include_own_repos=true"
    "&custom_title=%E2%99%9B%20THE%20ROYAL%20RECORD"
)

LANGUAGES_URL = (
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


def fetch_svg(url: str) -> ET.Element:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "REITHOMATO-GitHub-Profile/1.0",
            "Accept": "image/svg+xml",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read().decode("utf-8")
    root = ET.fromstring(raw)
    if local_name(root.tag) != "svg":
        raise ValueError(f"Expected SVG from {url}")
    return root


def recolor_languages(root: ET.Element) -> ET.Element:
    """Apply the same muted crimson palette without external image embedding."""
    root = copy.deepcopy(root)
    root.set("width", "440")
    root.set("height", "175")
    root.set("viewBox", "0 0 415 165")

    for element in root.iter():
        tag = local_name(element.tag)

        if tag == "style" and element.text:
            css = element.text
            replacements = (
                (r"(\.header\s*\{[^}]*?\bfill:\s*)#[0-9a-fA-F]{3,8}", r"\1#B33A35"),
                (r"(\.stat\s*\{[^}]*?\bfill:\s*)#[0-9a-fA-F]{3,8}", r"\1#E2DAD2"),
                (r"(\.lang-name\s*\{[^}]*?\bfill:\s*)#[0-9a-fA-F]{3,8}", r"\1#E2DAD2"),
                (r"(\.progress-background\s*\{\s*fill:\s*)#[0-9a-fA-F]{3,8}", r"\1#562528"),
            )
            for pattern, replacement in replacements:
                css = re.sub(pattern, replacement, css, count=1)
            element.text = css

        elif tag == "circle":
            element.set("fill", "#B33A35")

        elif tag == "rect" and element.get("data-testid") == "lang-progress":
            element.set("fill", "#B33A35")

    return root


def get_viewbox(root: ET.Element) -> str:
    viewbox = root.get("viewBox") or root.get("viewbox")
    if viewbox:
        return viewbox

    def number(value: str | None, fallback: float) -> float:
        if value is None:
            return fallback
        match = re.search(r"[-+]?\d*\.?\d+", value)
        return float(match.group()) if match else fallback

    width = number(root.get("width"), 440)
    height = number(root.get("height"), 175)
    return f"0 0 {width:g} {height:g}"


def namespace_panel_ids(panel: ET.Element, prefix: str) -> None:
    """Avoid CSS, mask, gradient and accessibility ID collisions between cards."""
    id_map: dict[str, str] = {}
    class_map: dict[str, str] = {}
    animation_map: dict[str, str] = {}

    for element in panel.iter():
        old_id = element.get("id")
        if old_id:
            id_map[old_id] = f"{prefix}-{old_id}"

        for class_name in element.get("class", "").split():
            class_map[class_name] = f"{prefix}-{class_name}"

        if local_name(element.tag) == "style" and element.text:
            for animation_name in re.findall(r"@keyframes\s+([\w-]+)", element.text):
                animation_map[animation_name] = f"{prefix}-{animation_name}"

    for element in panel.iter():
        old_id = element.get("id")
        if old_id in id_map:
            element.set("id", id_map[old_id])

        classes = element.get("class")
        if classes:
            element.set(
                "class",
                " ".join(class_map.get(name, name) for name in classes.split()),
            )

        for key, value in list(element.attrib.items()):
            if key == "id" or key == "class":
                continue
            for old_id, new_id in id_map.items():
                value = value.replace(f"url(#{old_id})", f"url(#{new_id})")
                if value == f"#{old_id}":
                    value = f"#{new_id}"
            if key.endswith("labelledby") or key.endswith("describedby"):
                value = " ".join(id_map.get(part, part) for part in value.split())
            element.set(key, value)

        if local_name(element.tag) == "style" and element.text:
            css = element.text
            for old_class, new_class in class_map.items():
                css = re.sub(
                    rf"\.{re.escape(old_class)}(?![\w-])",
                    f".{new_class}",
                    css,
                )
            for old_id, new_id in id_map.items():
                css = css.replace(f"#{old_id}", f"#{new_id}")
            for old_name, new_name in animation_map.items():
                css = re.sub(
                    rf"\b{re.escape(old_name)}\b",
                    new_name,
                    css,
                )
            element.text = css


def embed_panel(
    source: ET.Element,
    *,
    prefix: str,
    x: int,
) -> ET.Element:
    panel = ET.Element(
        f"{{{SVG_NS}}}svg",
        {
            "x": str(x),
            "y": "0",
            "width": "440",
            "height": "175",
            "viewBox": get_viewbox(source),
            "preserveAspectRatio": "xMidYMid meet",
        },
    )
    for child in list(source):
        panel.append(copy.deepcopy(child))
    namespace_panel_ids(panel, prefix)
    return panel


def build_combined_svg(stats: ET.Element, languages: ET.Element) -> str:
    # One SVG canvas means GitHub cannot wrap one panel beneath the other.
    # Each visual retains its own 440 x 175 viewport; 40 px separate them.
    root = ET.Element(
        f"{{{SVG_NS}}}svg",
        {
            "width": "920",
            "height": "175",
            "viewBox": "0 0 920 175",
            "role": "img",
            "aria-labelledby": "reithomato-title reithomato-desc",
        },
    )
    title = ET.SubElement(root, f"{{{SVG_NS}}}title", {"id": "reithomato-title"})
    title.text = "REITHOMATO — THE ROYAL RECORD and LANGUAGES"
    desc = ET.SubElement(root, f"{{{SVG_NS}}}desc", {"id": "reithomato-desc"})
    desc.text = "Two equal-height panels fixed side by side: THE ROYAL RECORD first, LANGUAGES second."

    root.append(embed_panel(stats, prefix="record", x=0))
    root.append(embed_panel(languages, prefix="languages", x=480))

    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def main() -> int:
    try:
        stats = fetch_svg(STATS_URL)
        languages = recolor_languages(fetch_svg(LANGUAGES_URL))

        language_text = ET.tostring(
            languages, encoding="unicode", xml_declaration=True
        )
        LANGUAGE_OUTPUT.write_text(language_text + "\n", encoding="utf-8")

        combined = build_combined_svg(stats, languages)
        COMBINED_OUTPUT.write_text(combined + "\n", encoding="utf-8")

        print(
            "Updated languages-mono.svg and royal-panels.svg "
            f"({COMBINED_OUTPUT.stat().st_size} bytes)."
        )
        return 0
    except Exception as exc:
        print(f"Could not refresh REITHOMATO profile panels: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
