#!/usr/bin/env python3
"""Render the REITHOMATO profile visuals straight from the GitHub API.

Everything shown is measured, never hand-typed:

* statistics come from REST/GraphQL calls made with the workflow token,
* languages come from the byte totals GraphQL reports per repository.

Colour policy
-------------
The card uses GitHub's own neutral palette so it never fights the theme, and
every language keeps its official ``linguist`` colour. If a repository uses a
language outside the table below it falls back to a neutral grey instead of
inventing a hue.

The artwork has no background, so two palettes are emitted with identical
animation code. The README picks one with GitHub's own theme tokens
(``#gh-light-mode-only`` / ``#gh-dark-mode-only``).

Files produced:

* ``royal-panels.svg``      - light theme palette
* ``royal-panels-dark.svg`` - dark theme palette
* ``languages-mono.svg``    - standalone language card

Standard library only: no third-party dependency to install or pin.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
LIGHT_OUTPUT = ROOT / "royal-panels.svg"
DARK_OUTPUT = ROOT / "royal-panels-dark.svg"
LANGUAGES_OUTPUT = ROOT / "languages-mono.svg"
TAGLINE_LIGHT = ROOT / "assets" / "tagline-light.svg"
TAGLINE_DARK = ROOT / "assets" / "tagline-dark.svg"

API = "https://api.github.com"
USER_AGENT = "REITHOMATO-profile-renderer/5.0"

# ---------------------------------------------------------------- art direction

SERIF = "Georgia, 'Times New Roman', 'DejaVu Serif', serif"
SANS = "'Segoe UI', Ubuntu, 'Helvetica Neue', Helvetica, Arial, sans-serif"

#: GitHub's own foreground/neutral ramp plus its accent blue.
THEMES = {
    "light": {
        "ink": "#1F2328",
        "dim": "#59636E",
        "faint": "#818B98",
        "accent": "#0969DA",
        "divider": "#1F2328",
    },
    "dark": {
        "ink": "#E6EDF3",
        "dim": "#9198A1",
        "faint": "#6E7681",
        "accent": "#4493F8",
        "divider": "#E6EDF3",
    },
}

#: Official GitHub language colours (github-linguist).
LANGUAGE_COLORS = {
    "Kotlin": "#A97BFF",
    "TypeScript": "#3178C6",
    "JavaScript": "#F1E05A",
    "CSS": "#663399",
    "HTML": "#E34C26",
    "Go": "#00ADD8",
    "Shell": "#89E051",
    "Python": "#3572A5",
    "Makefile": "#427819",
    "Rust": "#DEA584",
    "Java": "#B07219",
    "C#": "#178600",
    "C++": "#F34B7D",
    "C": "#555555",
    "Ruby": "#701516",
    "PHP": "#4F5D95",
    "Swift": "#F05138",
    "Dart": "#00B4AB",
    "Vue": "#41B883",
    "Svelte": "#FF3E00",
    "Lua": "#000080",
    "Nix": "#7E7EFF",
    "Dockerfile": "#384D54",
    "PowerShell": "#012456",
    "Batchfile": "#C1F12E",
    "SCSS": "#C6538C",
    "Astro": "#FF5A03",
}

FALLBACK_COLOR = "#8B949E"

# ------------------------------------------------------------------- geometry

WIDTH = 890
PAD = 24
COL_W = 414
PANEL_H = 224
TOP_Y = 12
HEIGHT = 244

# Staggered delays keep the original "assembly" feel of the old cards.
HEADER_DELAY = 0
ROW_DELAYS = [180, 300, 420, 540, 660, 780]
BAR_DELAY = 120
LIST_DELAYS = [380, 470, 560, 650, 740, 830, 920]


# ------------------------------------------------------------------- API layer


def _open(url: str, token: str, *, data: bytes | None = None,
          accept: str = "application/vnd.github+json") -> bytes:
    request = urllib.request.Request(
        url,
        data=data,
        method="POST" if data is not None else "GET",
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": USER_AGENT,
            "Accept": accept,
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        return response.read()


def get_json(url: str, token: str) -> dict:
    return json.loads(_open(url, token).decode("utf-8"))


def graphql(query: str, token: str, variables: dict | None = None) -> dict:
    payload = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    body = json.loads(_open(f"{API}/graphql", token, data=payload).decode("utf-8"))
    if body.get("errors"):
        raise RuntimeError("; ".join(error.get("message", "?") for error in body["errors"]))
    return body["data"]


def search_total(kind: str, query: str, token: str) -> int:
    url = f"{API}/search/{kind}?q={urllib.parse.quote(query)}&per_page=1"
    return int(get_json(url, token).get("total_count", 0))


# --------------------------------------------------------------- data gathering


def collect(login: str, token: str) -> dict:
    repositories: list[dict] = []
    page = 1
    while True:
        batch = get_json(
            f"{API}/user/repos?per_page=100&page={page}"
            "&visibility=all&affiliation=owner&sort=pushed",
            token,
        )
        repositories.extend(batch)
        if len(batch) < 100:
            break
        page += 1

    owned = [r for r in repositories if not r.get("fork") and not r.get("archived")]
    profile = get_json(f"{API}/users/{login}", token)

    query = """
    query($login: String!) {
      user(login: $login) {
        repositories(first: 100, ownerAffiliations: OWNER, isFork: false,
                     orderBy: {field: PUSHED_AT, direction: DESC}) {
          nodes {
            languages(first: 25, orderBy: {field: SIZE, direction: DESC}) {
              edges { size node { name } }
            }
          }
        }
        contributionsCollection {
          contributionCalendar { totalContributions }
        }
      }
    }
    """
    data = graphql(query, token, {"login": login})["user"]

    totals: dict[str, int] = {}
    for node in data["repositories"]["nodes"]:
        for edge in node["languages"]["edges"]:
            name = edge["node"]["name"]
            totals[name] = totals.get(name, 0) + int(edge["size"])

    return {
        "login": profile.get("login", login),
        "name": profile.get("name") or login,
        "since": (profile.get("created_at") or "2022-01-01")[:4],
        "repos_owned": len(owned),
        "stars": sum(int(r.get("stargazers_count") or 0) for r in owned),
        "commits": search_total("commits", f"author:{login}", token),
        "pull_requests": search_total("issues", f"author:{login} type:pr", token),
        "issues": search_total("issues", f"author:{login} type:issue", token),
        "contributions": int(
            data["contributionsCollection"]["contributionCalendar"]["totalContributions"]
        ),
        "languages": totals,
    }


# ----------------------------------------------------------------- SVG helpers


def pretty(value: int) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M".replace(".0M", "M")
    if value >= 10_000:
        return f"{value / 1_000:.1f}k".replace(".0k", "k")
    return f"{value:,}".replace(",", "\u2009")


def text(x: float, y: float, value: str, *, size: float = 11, weight: int = 400,
         fill: str, family: str = SANS, anchor: str = "start",
         spacing: float | None = None, cls: str | None = None,
         delay: int | None = None) -> str:
    parts = [
        f'x="{x:.1f}"', f'y="{y:.1f}"',
        f'font-family="{family}"', f'font-size="{size}"',
        f'font-weight="{weight}"', f'fill="{fill}"',
    ]
    if anchor != "start":
        parts.append(f'text-anchor="{anchor}"')
    if spacing is not None:
        parts.append(f'letter-spacing="{spacing}"')
    if cls:
        parts.append(f'class="{cls}"')
        if delay is not None:
            parts.append(f'style="animation-delay:{delay}ms"')
    return f"<text {' '.join(parts)}>{escape(value)}</text>"


def glyph(kind: str, x: float, y: float, colour: str, delay: int = 0) -> str:
    """Hand drawn marks: font glyphs render too differently across systems."""
    if kind == "crown":
        inner = (
            f'<path d="M2 12.4 L3.1 4.1 L6.6 7.9 L9.5 1.6 L12.4 7.9 L15.9 4.1 '
            f'L17 12.4 Z" fill="{colour}"/>'
            f'<rect x="2" y="12.9" width="15" height="3.1" rx="1" fill="{colour}"/>'
        )
    else:  # stacked code marks
        inner = (
            f'<path d="M6.9 4.2 L2.4 8.7 L6.9 13.2" fill="none" stroke="{colour}" '
            f'stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/>'
            f'<path d="M13.1 4.2 L17.6 8.7 L13.1 13.2" fill="none" stroke="{colour}" '
            f'stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/>'
            f'<path d="M11.4 2.6 L9.6 14.8" stroke="{colour}" stroke-width="1.9" '
            f'stroke-linecap="round"/>'
        )
    return (
        f'<g transform="translate({x:.1f}, {y:.1f})">'
        f'<g class="glyph" style="animation-delay:{delay}ms">{inner}</g>'
        "</g>"
    )


def panel_header(title: str, kind: str, width: float, theme: dict) -> str:
    return (
        glyph(kind, 0, 1, theme["accent"], HEADER_DELAY)
        + text(26, 17, title, size=16.5, weight=400, fill=theme["ink"],
               family=SERIF, spacing=0.3, cls="head", delay=HEADER_DELAY)
        + f'<rect x="0" y="27" width="{width:.1f}" height="1" '
        f'fill="url(#rule-{theme["name"]})" class="head" '
        f'style="animation-delay:{HEADER_DELAY}ms"/>'
    )


def figure(x: float, y: float, label: str, value: str, theme: dict,
           delay: int) -> str:
    return (
        f'<g class="row" style="animation-delay:{delay}ms">'
        + text(x, y, label, size=8.5, weight=600, fill=theme["dim"], spacing=1.3)
        + text(x, y + 25, value, size=22, weight=700, fill=theme["ink"])
        + "</g>"
    )


# --------------------------------------------------------------- panels: build


def stats_panel(d: dict, width: float, height: float, theme: dict) -> str:
    left = [
        ("ESTRELAS", pretty(d["stars"])),
        ("PULL REQUESTS", pretty(d["pull_requests"])),
        ("REPOSIT\u00d3RIOS", pretty(d["repos_owned"])),
    ]
    right = [
        ("COMMITS", pretty(d["commits"])),
        ("ISSUES", pretty(d["issues"])),
        ("CONTRIBUI\u00c7\u00d5ES / ANO", pretty(d["contributions"])),
    ]

    body = [panel_header("O REGISTRO REAL", "crown", width, theme)]
    rows = [48, 110, 172]
    for index, y in enumerate(rows):
        delay = ROW_DELAYS[index * 2]
        body.append(figure(0, y, left[index][0], left[index][1], theme, delay))
        body.append(
            figure(width - 196, y, right[index][0], right[index][1], theme, delay + 60)
        )
        if index < len(rows) - 1:
            body.append(
                f'<rect x="0" y="{y + 44}" width="{width:.1f}" height="1" '
                f'fill="{theme["divider"]}" opacity="0.14" class="row" '
                f'style="animation-delay:{delay + 90}ms"/>'
            )

    body.append(
        text(0, height - 4, f"DESDE {d['since']}", size=8.5, weight=600,
             fill=theme["faint"], spacing=1.2, cls="row",
             delay=ROW_DELAYS[-1] + 120)
    )
    return "".join(body)


def languages_panel(d: dict, width: float, height: float, theme: dict) -> str:
    ranked = sorted(d["languages"].items(), key=lambda item: item[1], reverse=True)
    total = sum(d["languages"].values()) or 1
    shown = ranked[:7]

    def colour_of(name: str) -> str:
        return LANGUAGE_COLORS.get(name, FALLBACK_COLOR)

    body = [panel_header("LINGUAGENS", "code", width, theme)]

    bar_y, bar_h = 43, 11
    clip = (
        f'<clipPath id="bar-{theme["name"]}" clipPathUnits="userSpaceOnUse">'
        f'<rect class="wipe" x="0" y="{bar_y}" width="{width:.1f}" height="{bar_h}" '
        f'style="animation-delay:{BAR_DELAY}ms"/></clipPath>'
    )

    segments = []
    offset = 0.0
    for _, (name, size) in enumerate(shown):
        segment = width * (size / total)
        segments.append(
            f'<rect x="{offset:.2f}" y="{bar_y}" width="{max(segment, 0.9):.2f}" '
            f'height="{bar_h}" fill="{colour_of(name)}"/>'
        )
        offset += segment

    body.append(clip)
    body.append(f'<g clip-path="url(#bar-{theme["name"]})">{"".join(segments)}</g>')

    columns = [shown[:4], shown[4:]]
    for column_index, column in enumerate(columns):
        col_x = column_index * 210
        for row_index, (name, size) in enumerate(column):
            cy = 87 + row_index * 27
            global_index = column_index * 4 + row_index
            delay = LIST_DELAYS[global_index]
            body.append(
                f'<g class="row" style="animation-delay:{delay}ms">'
                f'<circle cx="{col_x + 4.5:.1f}" cy="{cy - 3.5:.1f}" r="4.5" '
                f'fill="{colour_of(name)}"/>'
                + text(col_x + 16, cy, name, size=11.5, fill=theme["ink"])
                + text(col_x + 190, cy, f"{size / total * 100:.1f}%", size=11.5,
                       weight=600, fill=theme["dim"], anchor="end")
                + "</g>"
            )

    body.append(
        text(width, height - 4, "PONDERADO POR BYTES", size=8.5, weight=600,
             fill=theme["faint"], spacing=1.2, anchor="end", cls="row",
             delay=LIST_DELAYS[-1] + 140)
    )
    return "".join(body)


# --------------------------------------------------------------------- assembly

#: Animations mirror the original cards: a fade for headers, a staggered fade
#: for each row and a left-to-right wipe for the language bar.
#:
#: ``animation-fill-mode: backwards`` (not ``both``) is deliberate. It still
#: hides the element during its delay and animates it in, but once finished the
#: element returns to its natural style, which has no opacity/transform set.
#: If a renderer skips CSS animations entirely the content stays visible instead
#: of remaining at the invisible first keyframe.
ANIMATIONS = """
  .head  { animation: fade 700ms ease-in-out backwards; }
  .row   { animation: fade 340ms ease-in-out backwards; }
  .glyph { animation: jewel 620ms cubic-bezier(.22,1,.36,1) backwards;
           transform-box: fill-box; transform-origin: center; }
  .wipe  { animation: wipe 950ms cubic-bezier(.4,0,.2,1) backwards;
           transform-box: fill-box; transform-origin: left center; }
  @keyframes fade  { from { opacity: 0; } to { opacity: 1; } }
  @keyframes jewel { from { opacity: 0; transform: scale(.6); }
                     to   { opacity: 1; transform: scale(1); } }
  @keyframes wipe  { from { transform: scaleX(0); } to { transform: scaleX(1); } }
  @media (prefers-reduced-motion: reduce) {
    .head, .row, .glyph, .wipe { animation: none !important; }
  }
"""


def defs(theme: dict) -> str:
    return (
        "<defs>"
        f'<linearGradient id="rule-{theme["name"]}" x1="0" y1="0" x2="1" y2="0">'
        f'<stop offset="0" stop-color="{theme["accent"]}" stop-opacity="0.85"/>'
        f'<stop offset="0.55" stop-color="{theme["divider"]}" stop-opacity="0.16"/>'
        f'<stop offset="1" stop-color="{theme["divider"]}" stop-opacity="0"/>'
        "</linearGradient>"
        "</defs>"
    )


def build_combined_svg(d: dict, theme_name: str) -> str:
    theme = dict(THEMES[theme_name], name=theme_name)
    summary = (
        f"N\u00fameros de {d['name']}: {d['stars']} estrelas, {d['commits']} commits, "
        f"{d['pull_requests']} pull requests, {d['issues']} issues, "
        f"{d['repos_owned']} reposit\u00f3rios e {d['contributions']} contribui\u00e7\u00f5es no ano."
    )
    divider = PAD + COL_W + 23

    parts = [
        "<?xml version='1.0' encoding='utf-8'?>",
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
        f'viewBox="0 0 {WIDTH} {HEIGHT}" role="img" '
        f'aria-labelledby="real-titulo real-descricao">',
        '<title id="real-titulo">REITHOMATO \u2014 n\u00fameros do perfil</title>',
        f'<desc id="real-descricao">{escape(summary)}</desc>',
        f"<style>{ANIMATIONS}</style>",
        defs(theme),
        f'<g transform="translate({PAD}, {TOP_Y})">'
        f"{stats_panel(d, COL_W, PANEL_H, theme)}</g>",
        f'<rect x="{divider}" y="{TOP_Y + 2}" width="1" height="{PANEL_H - 26}" '
        f'fill="{theme["divider"]}" opacity="0.16"/>',
        f'<g transform="translate({PAD + COL_W + 28}, {TOP_Y})">'
        f"{languages_panel(d, COL_W, PANEL_H, theme)}</g>",
        "</svg>",
    ]
    return "\n".join(parts)


def build_tagline_svg(colour: str) -> str:
    """The cycling phrases that fade in, hold, and fade out one after another."""
    width, height = 400, 24
    lines = [
        "CONSTRUINDO COM PROP\u00d3SITO",
        "IDEIAS EM SISTEMAS",
        "CRIAR. REFINAR. REPETIR.",
    ]
    slot = 3.4  # seconds each phrase stays on screen
    total = slot * len(lines)
    parts = [
        "<?xml version='1.0' encoding='utf-8'?>",
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="Construindo com prop\u00f3sito">',
        "<style>",
        f"  .t {{ font-family: {SANS}; font-size: 11.5px; font-weight: 500; "
        f"letter-spacing: 1.5px; fill: {colour}; }}",
        "  @keyframes cycle {",
        "    0%   { opacity: 0; }",
        "    6%   { opacity: 1; }",
        "    27%  { opacity: 1; }",
        "    33%  { opacity: 0; }",
        "    100% { opacity: 0; }",
        "  }",
        f"  .b {{ animation: cycle {total:.1f}s linear infinite; }}",
        "  @media (prefers-reduced-motion: reduce) { .b { animation: none; opacity: 1; } }",
        "</style>",
    ]
    for index, line in enumerate(lines):
        # Negative delays start each phrase at its own point in the cycle.
        delay = -slot * (len(lines) - 1 - index)
        parts.append(
            f'<text class="t b" x="{width / 2:.0f}" y="16" text-anchor="middle" '
            f'style="animation-delay:{delay:.1f}s">{escape(line)}</text>'
        )
    parts.append("</svg>")
    return "\n".join(parts)


def build_languages_svg(d: dict) -> str:
    width, height = 440, 236
    theme = dict(THEMES["dark"], name="dark")
    parts = [
        "<?xml version='1.0' encoding='utf-8'?>",
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" '
        f'aria-labelledby="linguas-titulo">',
        '<title id="linguas-titulo">Linguagens mais usadas, ponderadas por bytes</title>',
        f"<style>{ANIMATIONS}</style>",
        defs(theme),
        f'<g transform="translate({PAD}, 18)">'
        f"{languages_panel(d, width - PAD * 2, 196, theme)}</g>",
        "</svg>",
    ]
    return "\n".join(parts)


def main() -> int:
    login = (os.environ.get("PROFILE_LOGIN") or "ReiThomato").strip()
    token = (os.environ.get("PROFILE_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()
    if not token:
        print("Missing PROFILE_TOKEN (or GITHUB_TOKEN).", file=sys.stderr)
        return 2

    try:
        data = collect(login, token)
    except (urllib.error.URLError, RuntimeError, KeyError, ValueError) as exc:
        print(f"Could not read GitHub data: {exc}", file=sys.stderr)
        return 1

    LIGHT_OUTPUT.write_text(build_combined_svg(data, "light") + "\n", encoding="utf-8")
    DARK_OUTPUT.write_text(build_combined_svg(data, "dark") + "\n", encoding="utf-8")
    LANGUAGES_OUTPUT.write_text(build_languages_svg(data) + "\n", encoding="utf-8")
    TAGLINE_LIGHT.write_text(
        build_tagline_svg(THEMES["light"]["accent"]) + "\n", encoding="utf-8"
    )
    TAGLINE_DARK.write_text(
        build_tagline_svg(THEMES["dark"]["accent"]) + "\n", encoding="utf-8"
    )

    print(
        f"{data['login']}: {data['stars']} estrelas, {data['commits']} commits, "
        f"{data['contributions']} contribuicoes, {len(data['languages'])} linguagens"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
