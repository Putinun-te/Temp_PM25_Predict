"""Draw docs/architecture.svg, the architecture diagram in the README, with each service's logo.

GitHub strips images from Mermaid diagrams, so the diagram is a plain SVG with
the logos embedded as data URIs. It follows GitHub's light or dark theme.
Run it again after changing the layout or a label:

    python docs/architecture.py

Logos are in docs/icons. Simple Icons (CC0) for GitHub, Git, NASA, Next.js
and Firebase; Devicon (MIT) for Azure and Azure SQL; Microsoft's Power BI icon
set; the OpenAQ, Open-Meteo and GISTDA site icons. Each belongs to its owner and
only names the service.
"""

from __future__ import annotations

import base64
from pathlib import Path
from xml.sax.saxutils import escape

HERE = Path(__file__).parent
ICONS = HERE / "icons"
OUT = HERE / "architecture.svg"
WIDTH, HEIGHT = 1200, 620
ICON = 28

STYLE = """
  .group { fill: #f6f8fa; stroke: #d0d7de; }
  .box { fill: #ffffff; stroke: #8c959f; }
  .text { fill: #1f2328; font: 13px -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif; }
  .title { font-weight: 600; font-size: 14px; }
  .small { fill: #59636e; font-size: 12px; }
  .edge { fill: none; stroke: #6e7781; stroke-width: 1.5; }
  .head { fill: #6e7781; }
  .label { fill: #f6f8fa; }
  @media (prefers-color-scheme: dark) {
    .group { fill: #151b23; stroke: #3d444d; }
    .box { fill: #0d1117; stroke: #656c76; }
    .text { fill: #e6edf3; }
    .small { fill: #9198a1; }
    .edge { stroke: #9198a1; }
    .head { fill: #9198a1; }
    .label { fill: #151b23; }
  }
"""


def icon(name: str, x: float, y: float) -> str:
    path = next(ICONS.glob(f"{name}.*"))
    kind = "svg+xml" if path.suffix == ".svg" else "png"
    data = base64.b64encode(path.read_bytes()).decode()
    return f'<image x="{x}" y="{y}" width="{ICON}" height="{ICON}" href="data:image/{kind};base64,{data}"/>'


def lines(cx: float, y: float, title: str, rest: list[str]) -> str:
    out = [f'<text class="text title" x="{cx}" y="{y}" text-anchor="middle">{escape(title)}</text>']
    for i, line in enumerate(rest, 1):
        out.append(f'<text class="text small" x="{cx}" y="{y + 17 * i}" text-anchor="middle">{escape(line)}</text>')
    return "\n".join(out)


def box(x: float, y: float, w: float, h: float, logo: str, title: str, rest: list[str]) -> str:
    cx = x + w / 2
    return "\n".join([
        f'<rect class="box" x="{x}" y="{y}" width="{w}" height="{h}" rx="6"/>',
        icon(logo, cx - ICON / 2, y + 10),
        lines(cx, y + 58, title, rest),
    ])


def store(x: float, y: float, w: float, h: float, logo: str, title: str, rest: list[str]) -> str:
    """A cylinder, for places that hold data."""
    rx, ry = w / 2, 9
    cx = x + w / 2
    body = (
        f'<path class="box" d="M{x},{y + ry} A{rx},{ry} 0 0 0 {x + w},{y + ry} V{y + h - ry} '
        f'A{rx},{ry} 0 0 1 {x},{y + h - ry} Z"/>'
        f'<ellipse class="box" cx="{cx}" cy="{y + ry}" rx="{rx}" ry="{ry}"/>'
    )
    return "\n".join([body, icon(logo, cx - ICON / 2, y + 22), lines(cx, y + 70, title, rest)])


def group(x: float, y: float, w: float, h: float, title: str) -> str:
    return (
        f'<rect class="group" x="{x}" y="{y}" width="{w}" height="{h}" rx="8"/>'
        f'<text class="text title" x="{x + w / 2}" y="{y + 22}" text-anchor="middle">{escape(title)}</text>'
    )


def edge(points: list[tuple[float, float]], both: bool = False, label: str | None = None, above: bool = False) -> str:
    d = "M" + " L".join(f"{x},{y}" for x, y in points)
    marker = ' marker-end="url(#arrow)"' + (' marker-start="url(#arrow-start)"' if both else "")
    out = f'<path class="edge" d="{d}"{marker}/>'
    if label:
        (x1, y1), (x2, y2) = points[-2], points[-1]
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        if above:
            # A short edge: the label sits over the line instead of on it.
            my -= 20
        width = 7.2 * len(label) + 10
        if not above:
            out += f'<rect class="label" x="{mx - width / 2}" y="{my - 11}" width="{width}" height="20" rx="4"/>'
        out += f'<text class="text small" x="{mx}" y="{my + 4}" text-anchor="middle">{escape(label)}</text>'
    return out


def draw() -> str:
    parts = [
        group(20, 20, 240, 580, "Public sources"),
        box(40, 55, 200, 120, "openaq", "OpenAQ", ["Air4Thai stations,", "hourly"]),
        box(40, 190, 200, 120, "openmeteo", "Open-Meteo", ["weather, past forecasts,", "CAMS"]),
        box(40, 325, 200, 120, "nasa", "NASA FIRMS", ["fires"]),
        box(40, 460, 200, 120, "gistda", "TMD and GISTDA", ["reference forecasts"]),
        group(310, 20, 290, 580, "GitHub Actions"),
        box(330, 55, 250, 110, "gha", "Health check", ["10:37, 14:37, 20:37"]),
        box(330, 190, 250, 110, "gha", "Hourly update", ["13:03 and 19:03,", "newer station hours"]),
        box(330, 325, 250, 160, "gha", "Daily forecast, 07:17", [
            "backfill, quality check,", "train weekly, predict, report,", "score, load SQL"]),
        store(660, 170, 220, 140, "git", "data branch", ["bronze, silver, gold CSV and", "JSON, models, metrics"]),
        store(660, 350, 220, 120, "azuresql", "Azure SQL", ["bronze, silver, gold, views"]),
        store(660, 495, 220, 105, "firebase", "Firebase", ["/predictions"]),
        box(985, 40, 200, 100, "github", "GitHub issue", ["emails the owner"]),
        box(985, 165, 200, 105, "nextjs", "Dashboard", ["Next.js static,", "App Service and Blob"]),
        box(985, 290, 200, 85, "azure", "JSON API", ["Azure Functions"]),
        box(985, 395, 200, 95, "powerbi", "Power BI report", []),
        # Sources into the jobs
        edge([(260, 405), (330, 405)]),
        edge([(240, 115), (285, 115), (285, 245), (330, 245)]),
        # Jobs and the data branch
        edge([(580, 245), (660, 245)], both=True),
        edge([(580, 360), (620, 360), (620, 285), (660, 285)], both=True),
        edge([(770, 170), (770, 125), (580, 125)]),
        edge([(580, 90), (985, 90)], label="problem"),
        # Outputs
        edge([(580, 420), (660, 420)]),
        edge([(455, 485), (455, 548), (660, 548)]),
        edge([(880, 450), (985, 450)], label="refresh 10:00", above=True),
        edge([(880, 217), (985, 217)]),
        edge([(880, 270), (930, 270), (930, 332), (985, 332)]),
    ]
    return "\n".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" width="{WIDTH}" height="{HEIGHT}" '
        'role="img" aria-label="Architecture: public sources feed GitHub Actions jobs, which keep everything on the '
        'data branch and load Azure SQL and Firebase; the dashboard, API and Power BI read from them">',
        f"<style>{STYLE}</style>",
        "<defs>",
        '<marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto">'
        '<path class="head" d="M0,0 L10,5 L0,10 z"/></marker>',
        '<marker id="arrow-start" viewBox="0 0 10 10" refX="1" refY="5" markerWidth="8" markerHeight="8" '
        'orient="auto-start-reverse"><path class="head" d="M0,0 L10,5 L0,10 z"/></marker>',
        "</defs>",
        *parts,
        "</svg>",
        "",
    ])


if __name__ == "__main__":
    OUT.write_text(draw(), encoding="utf-8")
    print(f"wrote {OUT}")
