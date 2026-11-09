#!/usr/bin/env python3
"""Render the REITHOMATO profile visuals straight from the GitHub API.

Everything shown is measured, never hand-typed:

* statistics come from REST/GraphQL calls made with the workflow token,
* languages come from the byte totals GraphQL reports per repository,
* the contribution heatmap comes from the contribution calendar,
* streak and best day are derived from that same calendar.

Two files are produced:

* ``royal-panels.svg``   - the full profile canvas
* ``languages-mono.svg`` - a standalone language card, kept for reuse

Standard library only: no third-party dependency to install or pin.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
COMBINED_OUTPUT = ROOT / "royal-panels.svg"
LANGUAGES_OUTPUT = ROOT / "languages-mono.svg"

API = "https://api.github.com"
USER_AGENT = "REITHOMATO-profile-renderer/2.0"

# ---------------------------------------------------------------- art direction

BG = "#0D080B"
INK = "#E2DAD2"
INK_DIM = "#93867D"
INK_FAINT = "#584E48"
CRIMSON = "#B33A35"
CRIMSON_LIGHT = "#CC3655"
GOLD = "#C8A96A"

CRIMSON_RAMP = ["#C2403A", "#A83734", "#8E2E31", "#7A2B2D", "#61252B", "#4E2026", "#3B1B21"]

SERIF = "Georgia, 'Times New Roman', 'DejaVu Serif', serif"
SANS = "'Segoe UI', Ubuntu, 'Helvetica Neue', Helvetica, Arial, sans-serif"

HEAT_LEVELS = ["#241519", "#4A1E24", "#7A2B2D", "#A13433", "#CC3655"]

# ------------------------------------------------------------------- geometry

WIDTH = 890
HEIGHT = 470
PAD = 24
COL_W = 414
TOP_H = 248
TOP_Y = 24
YEAR_H = 156
YEAR_Y = 288


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
    public = [r for r in owned if not r.get("private")]

    pushes = [r.get("pushed_at") or "" for r in owned]
    last_push = max((p for p in pushes if p), default="")

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
          contributionCalendar {
            totalContributions
            weeks { contributionDays { date contributionCount } }
          }
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

    days = [
        day
        for week in data["contributionsCollection"]["contributionCalendar"]["weeks"]
        for day in week["contributionDays"]
    ]

    return {
        "login": profile.get("login", login),
        "name": profile.get("name") or login,
        "since": (profile.get("created_at") or "2022-01-01")[:4],
        "repos_owned": len(owned),
        "repos_public": len(public),
        "active_repos": sum(
            1 for r in owned
            if (r.get("pushed_at") or "") >= (
                dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=90)
            ).strftime("%Y-%m-%d")
        ),
        "last_push": last_push,
        "stars": sum(int(r.get("stargazers_count") or 0) for r in owned),
        "commits": search_total("commits", f"author:{login}", token),
        "pull_requests": search_total("issues", f"author:{login} type:pr", token),
        "issues": search_total("issues", f"author:{login} type:issue", token),
        "contributions": int(
            data["contributionsCollection"]["contributionCalendar"]["totalContributions"]
        ),
        "languages": totals,
        "days": days,
    }


def streaks(days: list[dict]) -> tuple[int, int, dict | None]:
    parsed = sorted(
        ((dt.date.fromisoformat(d["date"]), int(d["contributionCount"])) for d in days),
        key=lambda item: item[0],
    )

    longest = running = 0
    for _, count in parsed:
        running = running + 1 if count > 0 else 0
        longest = max(longest, running)

    current = 0
    for index, (_, count) in enumerate(reversed(parsed)):
        if count > 0:
            current += 1
        elif index == 0:      # today may still be quiet without breaking the streak
            continue
        else:
            break

    best = max(parsed, key=lambda item: item[1], default=None)
    return current, longest, (
        {"date": best[0].isoformat(), "count": best[1]} if best else None
    )


# ----------------------------------------------------------------- SVG helpers


def pretty(value: int) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M".replace(".0M", "M")
    if value >= 10_000:
        return f"{value / 1_000:.1f}k".replace(".0k", "k")
    return f"{value:,}".replace(",", "\u2009")


def text(x: float, y: float, value: str, *, size: float = 11, weight: int = 400,
         fill: str = INK, family: str = SANS, anchor: str = "start",
         spacing: float | None = None, opacity: float | None = None) -> str:
    parts = [
        f'x="{x:.1f}"', f'y="{y:.1f}"',
        f'font-family="{family}"', f'font-size="{size}"',
        f'font-weight="{weight}"', f'fill="{fill}"',
    ]
    if anchor != "start":
        parts.append(f'text-anchor="{anchor}"')
    if spacing is not None:
        parts.append(f'letter-spacing="{spacing}"')
    if opacity is not None:
        parts.append(f'opacity="{opacity}"')
    return f"<text {' '.join(parts)}>{escape(value)}</text>"


def panel_header(title: str, glyph: str, width: float) -> str:
    return (
        text(0, 21, f"{glyph}  {title}", size=16.5, weight=400, fill=CRIMSON, family=SERIF)
        + f'<rect x="0" y="32" width="{width:.1f}" height="1" fill="url(#rule)"/>'
    )


def tile(x: float, y: float, label: str, value: str, accent: str, width: float = 196) -> str:
    return (
        f'<g transform="translate({x:.1f}, {y:.1f})">'
        f'<rect width="{width}" height="56" rx="10" fill="#150D11" stroke="#251519"/>'
        f'<rect x="0" y="11" width="2.5" height="34" rx="1.25" fill="{accent}"/>'
        + text(15, 23, label, size=8.5, weight=600, fill=INK_DIM, spacing=1.3)
        + text(15, 46, value, size=21, weight=700)
        + "</g>"
    )


def credits(y: float, left_value: str, width: float, right_value: str = "") -> str:
    out = text(0, y, left_value, size=8.5, weight=500, fill=INK_FAINT, spacing=0.9)
    if right_value:
        out += text(width, y, right_value, size=8.5, weight=500, fill=INK_FAINT,
                    spacing=0.9, anchor="end")
    return out


# --------------------------------------------------------------- panels: build


def stats_panel(d: dict, width: float, height: float) -> str:
    tiles = [
        ("TOTAL STARGAZERS", pretty(d["stars"])),
        ("COMMITS", pretty(d["commits"])),
        ("PULL REQUESTS", pretty(d["pull_requests"])),
        ("ISSUES", pretty(d["issues"])),
        ("REPOSITORIES", pretty(d["repos_owned"])),
        ("CONTRIBUTIONS / YEAR", pretty(d["contributions"])),
    ]
    body = [panel_header("THE ROYAL RECORD", "\u265b", width)]
    right = width - 196
    spots = [(0, 42), (right, 42), (0, 106), (right, 106), (0, 170), (right, 170)]
    for (x, y), (label, value) in zip(spots, tiles):
        body.append(tile(x, y, label, value, CRIMSON_LIGHT if "CONTRIBUTIONS" in label else CRIMSON))
    body.append(credits(height - 8, f"SINCE {d['since']}  \u00b7  {d['repos_owned']} OWNED", width))
    return "".join(body)


def languages_panel(d: dict, width: float, height: float) -> str:
    ranked = sorted(d["languages"].items(), key=lambda item: item[1], reverse=True)
    total = sum(d["languages"].values()) or 1
    shown = ranked[:7]

    body = [panel_header("THE KINGDOM'S TONGUE", "\u2318", width)]

    bar_y, bar_h = 46, 12
    offset = 0.0
    for index, (_, size) in enumerate(shown):
        segment = width * (size / total)
        colour = CRIMSON_RAMP[min(index, len(CRIMSON_RAMP) - 1)]
        body.append(
            f'<rect x="{offset:.2f}" y="{bar_y}" width="{max(segment, 0.9):.2f}" '
            f'height="{bar_h}" rect-fill="{colour}" fill="{colour}" '
            f'opacity="{1 - index * 0.04:.2f}"/>'
        )
        offset += segment
    body.append(
        f'<rect x="0" y="{bar_y}" width="{width}" height="{bar_h}" rx="4" '
        f'fill="none" stroke="#2A181C" stroke-width="1"/>'
    )

    columns = [shown[:4], shown[4:]]
    for column_index, column in enumerate(columns):
        col_x = column_index * 210
        for row_index, (name, size) in enumerate(column):
            cy = 86 + row_index * 26
            global_index = column_index * 4 + row_index
            colour = CRIMSON_RAMP[min(global_index, len(CRIMSON_RAMP) - 1)]
            body.append(
                f'<g transform="translate({col_x}, {cy})">'
                f'<circle cx="4.5" cy="-3.5" r="4.5" fill="{colour}"/>'
                + text(16, 0, name, size=11.5)
                + text(190, 0, f"{size / total * 100:.1f}%", size=11.5, weight=600,
                       fill=INK_DIM, anchor="end")
                + "</g>"
            )

    # Fill the quiet lower band with facts that change over time.
    active = d.get("active_repos", 0)
    last_push = d.get("last_push", "")
    last_label = ""
    if last_push:
        stamp = dt.datetime.fromisoformat(last_push.replace("Z", "+00:00"))
        last_label = stamp.strftime("%d %b %Y").upper()

    body.append(
        f'<rect x="0" y="{height - 58}" width="{width}" height="1" fill="#241519"/>'
    )
    facts = [
        (0, "ACTIVE (90 DAYS)", f"{active} of {d['repos_owned']}"),
        (210, "LAST PUSH", last_label or "\u2014"),
    ]
    for x, label, value in facts:
        body.append(
            f'<g transform="translate({x}, {height - 44})">'
            + text(0, 0, label, size=7.5, weight=600, fill=INK_DIM, spacing=1.1)
            + text(0, 13, value, size=11.5, weight=700)
            + "</g>"
        )

    body.append(text(width, height - 8, "WEIGHTED BY BYTES", size=8.5, weight=500,
                     fill=INK_FAINT, spacing=0.9, anchor="end"))
    return "".join(body)

def year_panel(d: dict, width: float, height: float) -> str:
    days = d["days"]
    current, longest, best = streaks(days)

    body = [
        panel_header("THE YEAR IN CRIMSON", "\u2694", width),
        text(width, 21, f"{pretty(d['contributions'])} CONTRIBUTIONS  \u00b7  LAST 12 MONTHS",
             size=9.5, weight=600, fill=INK_DIM, anchor="end", spacing=1.5),
    ]

    step, cell = 11.2, 8.2
    columns = 53
    grid_x, grid_y = 0, 54
    trimmed = days[-columns * 7:]
    peak = max((int(day["contributionCount"]) for day in trimmed), default=1) or 1

    def level(count: int) -> int:
        if count <= 0:
            return 0
        ratio = count / peak
        return 1 if ratio < 0.2 else 2 if ratio < 0.42 else 3 if ratio < 0.7 else 4

    for column in range(columns):
        for row in range(7):
            index = column * 7 + row
            if index >= len(trimmed):
                continue
            day = trimmed[index]
            count = int(day["contributionCount"])
            body.append(
                f'<rect x="{grid_x + column * step}" y="{grid_y + row * step}" '
                f'width="{cell}" height="{cell}" rx="2" fill="{HEAT_LEVELS[level(count)]}">'
                f"<title>{escape(day['date'])} \u00b7 {count} "
                f"contribution{'s' if count != 1 else ''}</title></rect>"
            )

    # Month labels: one per month, skipped when it would collide with the previous.
    last_column = -99
    for column in range(columns):
        index = column * 7
        if index >= len(trimmed):
            break
        month = trimmed[index]["date"][:7]
        if column == 0:
            previous_month = None
        else:
            previous_month = trimmed[index - 7]["date"][:7]
        if month != previous_month and column - last_column >= 4:
            label = dt.date.fromisoformat(trimmed[index]["date"]).strftime("%b").upper()
            body.append(text(grid_x + column * step, grid_y - 7, label,
                             size=7.5, weight=500, fill=INK_FAINT, spacing=0.8))
            last_column = column

    summary_x = 626
    summary_w = width - summary_x
    summary = [
        ("CURRENT STREAK", f"{current} day{'s' if current != 1 else ''}"),
        ("LONGEST STREAK", f"{longest} day{'s' if longest != 1 else ''}"),
        ("BEST DAY", f"{best['count']} \u00b7 {dt.date.fromisoformat(best['date']).strftime('%d %b').upper()}"
         if best else "0"),
    ]
    for index, (label, value) in enumerate(summary):
        y = 48 + index * 30
        body.append(
            f'<g transform="translate({summary_x}, {y})">'
            f'<rect width="{summary_w}" height="26" rx="8" fill="#150D11" stroke="#251519"/>'
            + text(11, 11, label, size=7, weight=600, fill=INK_DIM, spacing=1.1)
            + text(11, 22, value, size=11.5, weight=700)
            + "</g>"
        )

    legend_label_x = width - 110
    body.append(text(legend_label_x, height - 8, "LESS", size=7.5, weight=500,
                     fill=INK_FAINT, spacing=0.8))
    for index, colour in enumerate(HEAT_LEVELS):
        body.append(
            f'<rect x="{legend_label_x + 22 + index * 11}" y="{height - 15}" width="8" '
            f'height="8" rx="2" fill="{colour}"/>'
        )
    body.append(text(width, height - 8, "MORE", size=7.5, weight=500,
                     fill=INK_FAINT, anchor="end", spacing=0.8))
    return "".join(body)


# --------------------------------------------------------------------- assembly

CARD_STYLE = """
  text { shape-rendering: geometricPrecision; }
  svg { shape-rendering: geometricPrecision; }
"""


def defs() -> str:
    return (
        "<defs>"
        '<linearGradient id="rule" x1="0" y1="0" x2="1" y2="0">'
        f'<stop offset="0" stop-color="{CRIMSON}" stop-opacity="0.65"/>'
        f'<stop offset="0.55" stop-color="{INK_FAINT}" stop-opacity="0.22"/>'
        f'<stop offset="1" stop-color="{INK_FAINT}" stop-opacity="0"/>'
        "</linearGradient>"
        '<linearGradient id="glow" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{CRIMSON}" stop-opacity="0.13"/>'
        f'<stop offset="0.45" stop-color="{CRIMSON}" stop-opacity="0.03"/>'
        f'<stop offset="1" stop-color="{CRIMSON}" stop-opacity="0"/>'
        "</linearGradient>"
        "</defs>"
    )


def build_combined_svg(d: dict) -> str:
    summary = (
        f"{d['name']} statistics: {d['stars']} stars, {d['commits']} commits, "
        f"{d['pull_requests']} pull requests, {d['issues']} issues, "
        f"{d['repos_owned']} owned repositories, {d['contributions']} contributions."
    )
    parts = [
        "<?xml version='1.0' encoding='utf-8'?>",
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
        f'viewBox="0 0 {WIDTH} {HEIGHT}" fill="none" role="img" '
        f'aria-labelledby="royal-title royal-desc">',
        '<title id="royal-title">REITHOMATO \u2014 statistics, languages and the year in contributions</title>',
        f'<desc id="royal-desc">{escape(summary)}</desc>',
        f"<style>{CARD_STYLE}</style>",
        defs(),
        f'<rect width="{WIDTH}" height="{HEIGHT}" rx="14" fill="{BG}"/>',
        f'<rect width="{WIDTH}" height="170" fill="url(#glow)"/>',
        '<g class="sheet">',
        f'<g transform="translate({PAD}, {TOP_Y})">'
        f"{stats_panel(d, COL_W, TOP_H)}</g>",
        f'<rect x="445" y="{TOP_Y + 4}" width="1" height="{TOP_H - 16}" '
        f'fill="{INK_FAINT}" opacity="0.3"/>',
        f'<g transform="translate({PAD + COL_W + 28}, {TOP_Y})">'
        f"{languages_panel(d, COL_W, TOP_H)}</g>",
        f'<g transform="translate({PAD}, {YEAR_Y})">{year_panel(d, WIDTH - PAD * 2, YEAR_H)}</g>',
        "</g>",
        "</svg>",
    ]
    return "\n".join(parts)


def build_languages_svg(d: dict) -> str:
    width, height = 440, 272
    parts = [
        "<?xml version='1.0' encoding='utf-8'?>",
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" fill="none" role="img" aria-labelledby="lang-title">',
        '<title id="lang-title">Most used languages, weighted by bytes</title>',
        f"<style>{CARD_STYLE}</style>",
        defs(),
        f'<rect width="{width}" height="{height}" rx="12" fill="{BG}"/>',
        f'<g class="sheet" transform="translate({PAD}, 24)">'
        f"{languages_panel(d, width - PAD * 2, height - 24)}</g>",
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

    COMBINED_OUTPUT.write_text(build_combined_svg(data) + "\n", encoding="utf-8")
    LANGUAGES_OUTPUT.write_text(build_languages_svg(data) + "\n", encoding="utf-8")

    print(
        f"{data['login']}: {data['stars']} stars, {data['commits']} commits, "
        f"{data['contributions']} contributions, {len(data['languages'])} languages"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
