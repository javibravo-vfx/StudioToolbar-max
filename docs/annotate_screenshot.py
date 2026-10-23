"""Builds docs/screenshot.png from docs/screenshot_raw.png: toolbar split in two rows with English callouts.
Usage:  python docs/annotate_screenshot.py docs/screenshot_raw.png docs/screenshot.png
Callout x-positions are measured on a 3840 px wide capture — update LEFT/RIGHT and ROW_Y0/ROW_Y1 if the layout changes.
Needs the Inter font (any OpenType path works — edit F)."""
import sys
from PIL import Image, ImageDraw, ImageFont

SRC, OUT = sys.argv[1], sys.argv[2]
F = "/usr/share/fonts/opentype/inter/"
f_title = ImageFont.truetype(F + "Inter-SemiBold.otf", 30)
f_sub   = ImageFont.truetype(F + "Inter-Regular.otf", 18)
f_head  = ImageFont.truetype(F + "Inter-Bold.otf", 17)
f_lbl   = ImageFont.truetype(F + "Inter-SemiBold.otf", 17)
f_desc  = ImageFont.truetype(F + "Inter-Regular.otf", 15)

BG, PANEL, TXT, DIM, LINE, ACC = "#1e1e1e", "#262626", "#e8e8e8", "#9a9a9a", "#6a6a6a", "#d9b25a"
SECT = ["#d9b25a", "#5aa9d9", "#6cc28a", "#c97bd6", "#e07b6a"]

src = Image.open(SRC).convert("RGB")
ROW_Y0, ROW_Y1 = 124, 162                      # toolbar strip in the raw capture (v2.6 layout)
row = src.crop((0, ROW_Y0, 3840, ROW_Y1))
HALF = 1920
STRIP_H, BAND, PAD = ROW_Y1 - ROW_Y0, 150, 40
TIER = 44                                       # vertical step between label tiers

# (x in the 3840 capture — right list measured from 1920, label, description, band "t"/"b", section)
LEFT = [
    (62,   "TOOLS menu",     "Scripts in the tools/ folder",      "t", 0),
    (129,  "Overscan",       "Add bleed outside frame",           "b", 0),
    (173,  "Image Plane",    "Camera reference image",            "t", 0),
    (218,  "Remove BG",      "Clear viewport backgrounds",        "b", 0),
    (263,  "Paste Cam",      "Camera from 3D Camera Pin",         "t", 0),
    (308,  "Bake Camera",    "Alembic cam → Max camera",          "b", 0),
    (357,  "Studio Library", "Pose / animation library",          "t", 0),
    (600,  "Render size",    "Width × height, synced live",       "b", 1),
    (727,  "Aspect",         "Width ÷ height",                    "t", 1),
    (761,  "Lock",           "Keep aspect ratio",                 "b", 1),
    (789,  "×2",             "Double resolution",                 "t", 1),
    (815,  "½",              "Halve resolution",                  "b", 1),
    (900,  "Preset list",    "Saved + standard formats",          "t", 1),
    (1047, "Save preset",    "Uses the label",                    "b", 1),
    (1074, "Delete preset",  "",                                  "t", 1),
    (1185, "Film source",    "Standard · V-Ray · Physical",       "b", 2),
    (1307, "Film gate",      "Aperture width (mm)",               "t", 2),
    (1510, "Preset list",    "Saved + camera sensors",            "b", 2),
    (1677, "Save preset",    "",                                  "t", 2),
    (1703, "Delete preset",  "",                                  "b", 2),
    (1780, "FPS",            "Click to change",                   "t", 2),
    (1858, "Units",          "System units",                      "b", 2),
]
RIGHT = [
    (250,  "Project",        "Projects on the root drive",        "t", 3),
    (370,  "Sequence",       "",                                  "b", 3),
    (510,  "Shot",           "",                                  "t", 3),
    (790,  "Task",           "Department folder",                 "b", 3),
    (888,  "+ Task",         "Create task folders",               "t", 3),
    (916,  "Folders",        "Open shot / task in Explorer",      "b", 3),
    (976,  "Snapshot",       "Viewport JPG · right-click: folder","t", 4),
    (1022, "BG",             "Viewport background color",         "b", 4),
    (1094, "OPEN",           "Browse · arrow: recent versions",   "t", 4),
    (1190, "SAVE",           "Dialog · arrow: next version now",  "b", 4),
    (1272, "GET",            "Shot/task from file · amber = mismatch", "t", 4),
    (1346, "PATHS",          "Project paths, kept in the .max",   "b", 4),
    (1455, "SET RENDER",     "Output to publish folder",          "t", 4),
    (1592, "SHOT NAME",      "Render named after dropdowns",      "b", 4),
    (1699, "RESET",          "Paths back to defaults",            "t", 4),
    (1792, "Status",         "Click for history",                 "b", 4),
    (1893, "Setup",          "Pipeline configuration",            "t", 4),
]
SECTIONS_L = [(20, 395, "TOOLS", 0), (405, 1100, "RESOLUTION", 1), (1110, 1920, "FILM · FPS · UNITS", 2)]
SECTIONS_R = [(130, 960, "PIPELINE", 3), (965, 1920, "SCENE ACTIONS", 4)]

SPLIT = 2010                                    # cut just before PIPELINE, keeps "UNIT (Meters)" together

def text_w(t, f): return f.getbbox(t)[2] if t else 0

def layout(items, W):
    """Left-aligned labels hanging off a leader line; tiers chosen so that
    no label overlaps another and no leader line crosses any label text."""
    placed = []                                  # dicts: band, tier, x0, x1, lx
    # right → left: each label's line runs along its left edge, so labels to the
    # left climb above their right-hand neighbours (staircase) without crossings
    for x, lbl, desc, band, ci in sorted(items, key=lambda i: -i[0]):
        cx = PAD + x
        w = max(text_w(lbl, f_lbl), text_w(desc, f_desc)) + 4
        x0 = cx - 1 if cx + w < W - 10 else cx - w + 1     # flip to right-aligned at the edge
        box = (x0 - 8, x0 + w + 8)
        tier = 0
        while True:
            ok = True
            for p in placed:
                if p["band"] != band: continue
                if p["tier"] == tier and not (box[1] < p["x0"] or box[0] > p["x1"]): ok = False
                if p["tier"] < tier and p["x0"] <= cx <= p["x1"]: ok = False      # my line crosses p
                if p["tier"] > tier and box[0] <= p["lx"] <= box[1]: ok = False   # p's line crosses me
                if not ok: break
            if ok or tier >= 6: break
            tier += 1
        placed.append(dict(band=band, tier=tier, x0=box[0], x1=box[1], lx=cx,
                           tx=x0, lbl=lbl, desc=desc, ci=ci))
    return placed

def panel(items, sections, strip):
    W = SPLIT + 2 * PAD
    placed = layout(items, W)
    nt = max([p["tier"] for p in placed if p["band"] == "t"] + [0]) + 1
    nb = max([p["tier"] for p in placed if p["band"] == "b"] + [0]) + 1
    top, bot = 36 + nt * TIER, 36 + nb * TIER
    H = top + STRIP_H + bot
    im = Image.new("RGB", (W, H), PANEL)
    d = ImageDraw.Draw(im)
    sy = top
    im.paste(strip, (PAD, sy))
    d.rectangle((PAD - 1, sy - 1, PAD + strip.width, sy + STRIP_H), outline="#3a3a3a")
    for x0, x1, name, ci in sections:
        d.rectangle((PAD + x0, sy + STRIP_H + 3, PAD + x1, sy + STRIP_H + 6), fill=SECT[ci])
    for p in placed:
        cx, col = p["lx"], SECT[p["ci"]]
        if p["band"] == "t":
            ty = sy - 18 - (p["tier"] + 1) * TIER + 4
            d.line((cx, ty + 42, cx, sy - 4), fill=LINE)
            d.ellipse((cx - 3, sy - 7, cx + 3, sy - 1), fill=col)
        else:
            ty = sy + STRIP_H + 18 + p["tier"] * TIER
            d.line((cx, sy + STRIP_H + 8, cx, ty), fill=LINE)
            d.ellipse((cx - 3, sy + STRIP_H + 2, cx + 3, sy + STRIP_H + 8), fill=col)
        d.text((p["tx"], ty), p["lbl"], font=f_lbl, fill=TXT)
        if p["desc"]: d.text((p["tx"], ty + 20), p["desc"], font=f_desc, fill=DIM)
    return im

shift = SPLIT - HALF                              # right-half coordinates were measured from 1920
RIGHT = [(x - shift, *r) for x, *r in RIGHT]
SECTIONS_R = [(a - shift, b - shift, n, c) for a, b, n, c in SECTIONS_R]
SECTIONS_L[-1] = (1110, SPLIT - 6, "FILM · FPS · UNITS", 2)
pL = panel(LEFT, SECTIONS_L, row.crop((0, 0, SPLIT, STRIP_H)))
pR = panel(RIGHT, SECTIONS_R, row.crop((SPLIT, 0, 3840, STRIP_H)))

# legend
legend = [("TOOLS", 0), ("RESOLUTION", 1), ("FILM · FPS · UNITS", 2), ("PIPELINE", 3), ("SCENE ACTIONS", 4)]
HEAD = 110
W = pL.width
out = Image.new("RGB", (W, HEAD + pL.height + 24 + pR.height + 40), BG)
d = ImageDraw.Draw(out)
d.text((PAD, 28), "Studio Toolbar for 3ds Max", font=f_title, fill=TXT)
d.text((PAD, 68), "v2.6 — one dockable row: viewport tools, render size, film gate and the shot pipeline. "
                  "Shown in two halves (left → right).", font=f_sub, fill=DIM)
lx = W - PAD
for name, ci in reversed(legend):
    w = text_w(name, f_head)
    lx -= w
    d.text((lx, 44), name, font=f_head, fill=TXT)
    d.rectangle((lx - 22, 50, lx - 8, 64), fill=SECT[ci])
    lx -= 46
out.paste(pL, (0, HEAD))
out.paste(pR, (0, HEAD + pL.height + 24))
out.save(OUT, optimize=True)
print(out.size)
