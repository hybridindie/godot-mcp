"""Generates the godot-mcp marketing kit (SVGs) at 1920x1080.

Design coordinates are 16:9 (800x450 tiles, 1280x720 cover, 1200x675 panel);
the SVG width/height is 1920x1080 so every asset exports at Full HD with crisp text.

Run from the repo root:  python3 scripts/dev/gen_marketing.py
Then rasterize each .svg to 1920x1080, e.g.:
  for f in docs/assets/cover-1920x1080.svg docs/assets/marketing/*.svg; do
    magick -background none -density 288 "$f" -resize 1920x1080 "${f%.svg}.png"
  done
"""
import pathlib

ASSETS = pathlib.Path("docs/assets")
OUT = ASSETS / "marketing"
OUT.mkdir(parents=True, exist_ok=True)

SANS = "Segoe UI, Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace"
GREEN = "#3fbf7a"
BLUE = "#9cc3e6"
WHITE = "#ffffff"
CARD = "#1b2230"
BORDER = "#2b3444"

MARK = (
    '<rect x="4" y="13" width="38" height="38" rx="10" fill="#3f86c4"/>'
    '<circle cx="17" cy="29" r="5" fill="#fff"/><circle cx="29" cy="29" r="5" fill="#fff"/>'
    '<circle cx="19" cy="29" r="2.3" fill="#18202e"/>'
    '<circle cx="31" cy="29" r="2.3" fill="#18202e"/>'
    '<rect x="15" y="39" width="16" height="3.5" rx="1.75" fill="#18202e" fill-opacity=".55"/>'
    '<path d="M42 32H50" stroke="#3fbf7a" stroke-width="4.5" '
    'stroke-linecap="round"/>'
    '<circle cx="55" cy="32" r="5" fill="none" stroke="#3fbf7a" stroke-width="4.5"/>'
)
DEFS = (
    '<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">'
    '<stop offset="0" stop-color="#121925"/><stop offset="1" stop-color="#1d2a3d"/>'
    '</linearGradient></defs>'
)


def svg(dw, dh, body):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080" '
        f'viewBox="0 0 {dw} {dh}">{DEFS}{body}</svg>\n'
    )


def mark(cx, cy, s):
    return f'<g transform="translate({cx},{cy}) scale({s}) translate(-32,-32)">{MARK}</g>'


def write(path, dw, dh, body):
    path.write_text(svg(dw, dh, body))


# ---------- featured cover (design 1280x720) ----------
dw, dh = 1280, 720
b = [f'<rect width="{dw}" height="{dh}" fill="url(#bg)"/>']
b.append(mark(640, 150, 4))
b.append(
    f'<text x="640" y="470" text-anchor="middle" font-family="{SANS}" font-size="230" '
    f'font-weight="700" fill="{WHITE}">godot-mcp</text>'
)
b.append(
    f'<text x="640" y="575" text-anchor="middle" font-family="{SANS}" font-size="64" '
    f'fill="{BLUE}">Drive a live Godot editor</text>'
)
b.append(
    f'<text x="640" y="650" text-anchor="middle" font-family="{SANS}" font-size="64" '
    f'fill="{BLUE}">from an AI agent — over MCP</text>'
)
write(ASSETS / "cover-1920x1080.svg", dw, dh, "".join(b))

# ---------- logo only (design 1280x720) ----------
b = [f'<rect width="{dw}" height="{dh}" fill="url(#bg)"/>', mark(640, 360, 8)]
write(ASSETS / "logo-1920x1080.svg", dw, dh, "".join(b))

# ---------- feature tiles (design 800x450) ----------
def tile(name, headline, detail):
    dw, dh = 800, 450
    b = [f'<rect width="{dw}" height="{dh}" fill="url(#bg)"/>']
    b.append(
        f'<rect x="1" y="1" width="798" height="448" rx="18" fill="none" '
        f'stroke="{BORDER}" stroke-width="2"/>'
    )
    b.append(mark(82, 84, 1.05))
    y = 214
    for hl in headline:
        b.append(
            f'<text x="66" y="{y}" font-family="{SANS}" font-size="56" '
            f'font-weight="700" fill="{WHITE}">{hl}</text>'
        )
        y += 66
    b.append(f'<rect x="66" y="{y - 6}" width="72" height="7" rx="3.5" fill="{GREEN}"/>')
    y += 54
    for dl in detail:
        b.append(
            f'<text x="66" y="{y}" font-family="{SANS}" font-size="27" fill="{BLUE}">{dl}</text>'
        )
        y += 38
    write(OUT / f"{name}.svg", dw, dh, "".join(b))


tile(
    "feature-works-in-editor",
    ["Works in your", "real editor"],
    ["Every edit lands on Godot's own", "undo stack — Ctrl+Z just works."],
)
tile(
    "feature-tells-the-truth",
    ["It tells", "the truth"],
    ["Results never fake success; a timeout", "isn't dressed up as a crash."],
)
tile(
    "feature-small-surface",
    ["A small,", "sharp surface"],
    ["A few tools on by default; the agent", "pulls in more only when a task needs them."],
)
tile(
    "feature-safe-by-construction",
    ["Safe by", "construction"],
    ["Destructive actions ask first, previews", "are free, safety lives on the server."],
)

# ---------- "It caught my mistake" panel (design 1200x675) ----------
dw, dh = 1200, 675
p = [f'<rect width="{dw}" height="{dh}" fill="url(#bg)"/>']
p.append(
    f'<rect x="60" y="64" width="1080" height="547" rx="16" fill="{CARD}" '
    f'stroke="{BORDER}" stroke-width="2"/>'
)
p.append(f'<line x1="60" y1="140" x2="1140" y2="140" stroke="{BORDER}" stroke-width="2"/>')
p.append(mark(112, 102, 0.72))
p.append(
    f'<text x="176" y="112" font-family="{SANS}" font-size="27" font-weight="700" '
    f'fill="{WHITE}">godot-mcp</text>'
)
p.append(
    f'<text x="1076" y="112" text-anchor="end" font-family="{MONO}" font-size="19" '
    f'fill="{GREEN}">result</text>'
)
p.append(
    f'<text x="104" y="196" font-family="{MONO}" font-size="24" fill="#7f8aa0">'
    f'&gt; add a marker node under  Relic/Cold</text>'
)
json_lines = [
    ('{ "node_path": "Relic/Cold/Marker", "created": true,', WHITE),
    ('  "persisted": false,', "#e0b64a"),
    ('  "reason": "instanced_child_not_editable",', "#e0b64a"),
    ("  \"hint\": \"'Relic/Cold' is inside the instanced", BLUE),
    ("           scene 'Relic', which doesn't have", BLUE),
    ('           editable children." }', BLUE),
]
y = 258
for text, color in json_lines:
    p.append(
        f'<text x="104" y="{y}" font-family="{MONO}" font-size="24" fill="{color}">{text}</text>'
    )
    y += 40
p.append('<rect x="60" y="535" width="1080" height="76" fill="#161c27"/>')
p.append('<circle cx="104" cy="573" r="9" fill="#e0b64a"/>')
p.append(
    f'<text x="128" y="582" font-family="{SANS}" font-size="27" fill="#e6eaf0">'
    f'It reports the truth: the node was created, but it will not be saved.</text>'
)
write(OUT / "caught-my-mistake.svg", dw, dh, "".join(p))

# ---------- OG / social card (design 1280x720) ----------
dw, dh = 1280, 720
o = [f'<rect width="{dw}" height="{dh}" fill="url(#bg)"/>']
o.append(mark(640, 150, 3.4))
o.append(
    f'<text x="640" y="410" text-anchor="middle" font-family="{SANS}" font-size="150" '
    f'font-weight="700" fill="{WHITE}">godot-mcp</text>'
)
o.append(
    f'<text x="640" y="492" text-anchor="middle" font-family="{SANS}" font-size="46" '
    f'fill="{BLUE}">Drive a live Godot editor from an AI agent</text>'
)
o.append(
    f'<text x="640" y="552" text-anchor="middle" font-family="{SANS}" font-size="46" '
    f'fill="{BLUE}">— over MCP</text>'
)
o.append(
    f'<text x="640" y="636" text-anchor="middle" font-family="{SANS}" font-size="32" '
    f'fill="{GREEN}">hybridindie.github.io/godot-mcp</text>'
)
write(OUT / "og-card.svg", dw, dh, "".join(o))

print(
    "wrote:",
    sorted(p.name for p in list(ASSETS.glob("*-1920x1080.svg")) + list(OUT.glob("*.svg"))),
)
