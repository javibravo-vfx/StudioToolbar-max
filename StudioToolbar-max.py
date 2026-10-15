# -*- coding: utf-8 -*-
"""
VFX-STUDIO-TOOLBAR for 3dsMax
Author: Javi Bravo (VFX)
Visual design: 3ds Max native ribbon/toolbar look

════════════════════════════════════════════════════════════════════
  QUICK SETUP — edit the USER CONFIG section below to adapt this
  script to your studio without opening the Setup dialog.
  All values here are the fallback defaults used when no
  pipeline_config.ini exists on the machine.
════════════════════════════════════════════════════════════════════

FILES WRITTEN TO  ~/.studio-toolbar/
  pipeline_state.ini      — resolution/film presets + last pipeline state
  pipeline_config.ini   — active pipeline config (written by Setup dialog
                          or auto-generated from USER CONFIG on first run)
  pipeline_presets.json — named pipeline presets saved from Setup dialog
"""

import os, json, re
from PySide6 import QtWidgets, QtCore, QtGui
from PySide6 import QtSvg
from pymxs import runtime as rt
from qtmax import GetQMaxMainWindow
from datetime import datetime

VERSION = "2.6.3"

# ╔══════════════════════════════════════════════════════════════════╗
# ║                        USER CONFIG                              ║
# ║  Edit these values to match your studio pipeline.               ║
# ║  These are used as defaults when no pipeline_config.ini exists. ║
# ╚══════════════════════════════════════════════════════════════════╝

# ── Tool script paths ─────────────────────────────────────────────────────────
PATH_OVERSCAN    = r"T:\.studio-toolbar\max\maintools\STM_Overscan.ms"
PATH_IMAGE_PLANE = r"T:\.studio-toolbar\max\maintools\STM_ImagePlane.ms"
PATH_REMOVE_BACK = r"T:\.studio-toolbar\max\maintools\STM_RemoveBack.ms"
PATH_TEXTURES    = r"T:\.studio-toolbar\max\maintools\STM_ShowTextures.ms"
PATH_BAKE_CAM    = r"T:\.studio-toolbar\max\maintools\STM_BakeAlembic.ms"
PATH_LIBRARY     = r"T:\.studio-toolbar\max\maintools\STM_StudioLibraryMAX.py"
PATH_TOOLS_DIR   = r"T:\.studio-toolbar\max\tools"

# rootNode AppData slot where Set Paths stores the paths inside the .max
STM_APPDATA_PATHS = 731101

# ── Pipeline structure ────────────────────────────────────────────────────────
# Root drive or UNC path where all project folders live
#   e.g.  "T:"  or  r"\\server\projects"
CFG_ROOT_DRIVE      = "T:"

# Prefix that identifies project folders
#   e.g.  "VFX-"  →  folders named  VFX-MOR, VFX-SHR, VFX-COM …
CFG_PROJECT_PREFIX  = "VFX-"

# Folder names inside a project that are NOT sequences (case-insensitive)
CFG_SEQ_EXCLUDE     = "3D,SOURCE,FOOTAGE,AUDIO,RENDER"

# Ordered list of task (department) folders created with the + button
CFG_TASKS = [
    "1_matchmove",
    "2_model",
    "3_retopo",
    "4_rigging",
    "5_shaders",
    "6_animation",
    "7_fx",
    "8_lighting",
]

# Ordered list of subfolders created inside each task folder
#   First  = scenes/working files folder  (also gets a  textures/  subfolder by default)
#   Second = review / playblast folder
#   Third  = publish / render output folder
#   Add more lines for additional folders
CFG_TASK_SUBFOLDERS = [
    "1_projects",
    "2_review",
    "3_publish",
]

# Subfolders created inside each task's SCENES folder (first subfolder above)
# Key   = task name (must match one of CFG_TASKS)
# Value = list of subfolder names to create inside  task/1_projects/
# Tasks not listed here get  ["textures"]  by default
CFG_TASK_PROJECTS_SUBS = {
    "1_matchmove":       ["footage", "textures"],
    "2_model":      ["textures"],
    "3_retopo":     ["textures"],
    "4_rigging":     ["textures"],
    "5_shaders":   ["textures"],
    "6_animation":   ["textures"],
    "7_fx":          ["textures", "cache"],
    "8_lighting":    ["textures", "cache", "import"],
}

# Subfolder where viewport snapshots are saved (must match one of CFG_TASK_SUBFOLDERS)
# Default: second subfolder (review folder)
CFG_THUMB_SUBFOLDER = "2_review"

# Separator between render filename and frame number
#   "_"  →  shot_task_v001_0001.exr  (default)
#   "."  →  shot_task_v001.0001.exr
CFG_RENDER_SEP = "_"

# ╔══════════════════════════════════════════════════════════════════╗
# ║               END OF USER CONFIG                                ║
# ╚══════════════════════════════════════════════════════════════════╝

# ── Internal paths ────────────────────────────────────────────────────────────
PIPE_DIR     = os.path.expanduser(os.path.join("~", ".studio-toolbar"))
INI_PATH     = os.path.join(PIPE_DIR, "pipeline_state.ini")
PIPELINE_CFG = os.path.join(PIPE_DIR, "pipeline_config.ini")

# ── Build PIPELINE_DEFAULTS from USER CONFIG ──────────────────────────────────
# This is what gets used when pipeline_config.ini doesn't exist yet.
# The Setup dialog reads/writes pipeline_config.ini, which overrides these.
PIPELINE_DEFAULTS = {
    "root_drive":         CFG_ROOT_DRIVE,
    "project_prefix":     CFG_PROJECT_PREFIX,
    "seq_exclude":        CFG_SEQ_EXCLUDE,
    "tasks":              ",".join(CFG_TASKS),
    "sub_projects":       CFG_TASK_SUBFOLDERS[0] if len(CFG_TASK_SUBFOLDERS) > 0 else "1_projects",
    "sub_review":         CFG_TASK_SUBFOLDERS[1] if len(CFG_TASK_SUBFOLDERS) > 1 else "2_review",
    "sub_publish":        CFG_TASK_SUBFOLDERS[2] if len(CFG_TASK_SUBFOLDERS) > 2 else "3_publish",
    "extra_subs":         ",".join(CFG_TASK_SUBFOLDERS[3:]) if len(CFG_TASK_SUBFOLDERS) > 3 else "",
    "task_projects_subs": json.dumps(CFG_TASK_PROJECTS_SUBS),
    "thumb_subfolder":    CFG_THUMB_SUBFOLDER,
    "thumb_subdir":       "",
    "snap_inc_maxfile":   True,
    "snap_inc_shot":      False,
    "snap_inc_task":      False,
    "snap_inc_camera":    True,
    "render_sep":         CFG_RENDER_SEP,
}

_CFG_CACHE = {"mtime": None, "data": None}

def load_pipeline_cfg():
    """Load pipeline_config.ini (merged with defaults). Cached: only re-reads
    the file if it changed on disk — _master_sync polls it every 500 ms."""
    try:    mtime = os.path.getmtime(PIPELINE_CFG)
    except OSError: mtime = None
    if _CFG_CACHE["data"] is not None and _CFG_CACHE["mtime"] == mtime:
        return dict(_CFG_CACHE["data"])
    data = dict(PIPELINE_DEFAULTS)
    if mtime is not None:
        try:
            with open(PIPELINE_CFG, "r") as f:
                data.update(json.load(f))
        except Exception as e:
            print(f"[STM] pipeline_config read error: {e}")
    _CFG_CACHE.update(mtime=mtime, data=data)
    return dict(data)

def save_pipeline_cfg(data):
    try:
        os.makedirs(PIPE_DIR, exist_ok=True)
        with open(PIPELINE_CFG, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[STM] pipeline_config write error: {e}")
    _CFG_CACHE["data"] = None   # force re-read

def _cfg():
    """Shortcut to get the active config."""
    return load_pipeline_cfg()

# Derived from config — recomputed at runtime from _cfg()
def get_tasks_template():
    return [t.strip() for t in _cfg()["tasks"].split(",") if t.strip()]

def get_subfolders():
    """Return the ordered list of all task subfolders."""
    c = _cfg()
    subs = []
    for key in ["sub_projects", "sub_review", "sub_publish"]:
        v = c.get(key, "").strip()
        if v: subs.append(v)
    for v in [v.strip() for v in c.get("extra_subs", "").split(",") if v.strip()]:
        subs.append(v)
    return subs

def get_seq_exclude():
    return [s.strip().upper() for s in _cfg()["seq_exclude"].split(",") if s.strip()]

def get_task_projects_subs(task_name):
    """
    Return the list of subfolders to create inside projects/ for a task.
    If the task has no specific config, returns ["textures"] by default.
    """
    raw = _cfg().get("task_projects_subs", "")
    if raw:
        try:
            mapping = json.loads(raw)
            if task_name in mapping:
                return mapping[task_name]
        except: pass
    return ["textures"]

# Keep compatibility with code that uses the constants directly
TASKS_TEMPLATE      = ["1_matchmove","2_model","3_retopo","4_rigging","5_shaders","6_animation","7_fx","8_lighting"]
SUBFOLDERS_TEMPLATE = {"projects":"1_projects","review":"2_review","publish":"3_publish"}

# ── Built-in presets (listed below the user's saved presets) ────────────────────
BUILTIN_RES = [
    ("HD",              1920, 1080), ("HD 720",          1280,  720),
    ("UHD 4K",          3840, 2160), ("DCI 2K",          2048, 1080),
    ("DCI 4K",          4096, 2160), ("2K Scope 2.39",   2048,  858),
    ("Square 1:1",      1080, 1080), ("Vertical 9:16",   1080, 1920),
    ("Social 4:5",      1080, 1350),
]
# Sensor width (mm) of each camera's most common recording mode
BUILTIN_FILM = [
    ("3ds Max default / Full Frame",       36.00),
    ("ARRI Alexa 35 — Open Gate",          27.99),
    ("ARRI Alexa Mini LF — Open Gate",     36.70),
    ("ARRI Alexa Mini — Open Gate 3.4K",   28.25),
    ("RED V-Raptor 8K VV",                 40.96),
    ("RED Komodo 6K",                      27.03),
    ("Sony Venice 2 — 8.6K FF",            35.90),
    ("Blackmagic Pocket 6K",               23.10),
    ("Super 35 — 4-perf full aperture",    24.89),
    ("35mm Academy",                       21.95),
    ("APS-C (Canon)",                      22.30),
]

# ── Palette ───────────────────────────────────────────────────────────────────
MX_BG        = "#3c3c3c"
MX_BG_BTN    = "#3c3c3c"
MX_BG_BTN_HO = "#505050"
MX_BG_BTN_PR = "#282828"
MX_BG_INPUT  = "#2e2e2e"
MX_BORDER    = "#555555"
MX_BORDER_HI = "#7a7a7a"
MX_TEXT      = "#d8d8d8"
MX_TEXT_DIM  = "#909090"
MX_SEP       = "#4a4a4a"
MX_SEL_BG    = "#4a6a8a"

IC_BASE    = "#b8b8b8"
IC_ACCENT  = "#4ec9c9"   # cyan
IC_ACCENT2 = "#d4b44a"   # yellow
IC_HOVER   = "#ffffff"

LIB_BG     = "#1e1e1e"
LIB_BG_HO  = "#2a2a2a"
LIB_BORDER = "#484848"
LIB_TEXT   = "#aaaaaa"
LIB_TEXT_HO= "#d8d8d8"

FONT_MAIN  = "9pt"
FONT_LABEL = "8.5pt"
FONT_SMALL = "8pt"

# Tool button dimensions — square, large icons
TOOL_SZ = 40     # button width and height
ICON_SZ = 28     # SVG size
H       = 22     # standard height of inputs/combos/regular buttons

# ── Combo/spinner arrows as SVG files on disk ─────────────────────────────────
# Triangles made from CSS borders render as an "=" bar in Qt;
# stylesheets need a file for image: url(...), so they are written once.
STYLE_ICON_DIR = os.path.join(PIPE_DIR, "icons")

def _ensure_style_icons():
    arrows = {
        "arrow_down":    '<path d="M3 5.5l4 4 4-4"/>',
        "arrow_up":      '<path d="M3 8.5l4-4 4 4"/>',
        "arrow_down_hi": '<path d="M3 5.5l4 4 4-4"/>',
    }
    try:
        os.makedirs(STYLE_ICON_DIR, exist_ok=True)
        for name, body in arrows.items():
            col = "#ececec" if name.endswith("_hi") else "#b4b4b4"
            svg = (f'<svg viewBox="0 0 14 14" width="14" height="14" xmlns="http://www.w3.org/2000/svg" fill="none" '
                   f'stroke="{col}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{body}</svg>')
            path = os.path.join(STYLE_ICON_DIR, name + ".svg")
            if not os.path.exists(path) or open(path).read() != svg:
                with open(path, "w") as f: f.write(svg)
    except Exception as e:
        print(f"[STM] style icons: {e}")

_ensure_style_icons()

def _icon_url(name):
    return os.path.join(STYLE_ICON_DIR, name + ".svg").replace("\\", "/")

# ── Stylesheet ────────────────────────────────────────────────────────────────
STYLE = f"""
QWidget {{
    background-color: {MX_BG};
    color: {MX_TEXT};
    font-family: "Tahoma", "Segoe UI", sans-serif;
    font-size: {FONT_MAIN};
}}

/* ── inputs — never stretch, always fixed ───────────── */
QComboBox, QLineEdit, QDoubleSpinBox, QSpinBox {{
    background-color: {MX_BG_INPUT};
    color: {MX_TEXT};
    border: 1px solid {MX_BORDER};
    border-radius: 1px;
    padding: 0px 5px;
    height: {H}px;
    font-family: "Tahoma", "Segoe UI", sans-serif;
    font-size: {FONT_MAIN};
    selection-background-color: {MX_SEL_BG};
}}
QComboBox:hover, QLineEdit:hover, QDoubleSpinBox:hover, QSpinBox:hover {{ border-color: {MX_BORDER_HI}; }}
QComboBox:focus, QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus {{ border-color: {MX_BORDER_HI}; outline: none; }}
QComboBox::drop-down {{ border: none; width: 16px; background: transparent; }}
QComboBox::down-arrow {{ image: url({_icon_url("arrow_down")}); width: 10px; height: 10px; margin-right: 3px; }}
QComboBox::down-arrow:hover, QComboBox::down-arrow:on {{ image: url({_icon_url("arrow_down_hi")}); }}
QComboBox QAbstractItemView {{
    background-color: #2a2a2a; color: {MX_TEXT};
    border: 1px solid {MX_BORDER};
    selection-background-color: {MX_SEL_BG};
    outline: none; font-size: {FONT_MAIN};
}}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    background-color: #484848; border: none;
    border-left: 1px solid {MX_BORDER}; width: 14px;
}}
QSpinBox::up-button:hover, QSpinBox::down-button:hover,
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {{ background-color: {MX_BG_BTN_HO}; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url({_icon_url("arrow_up")}); width: 10px; height: 10px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url({_icon_url("arrow_down")}); width: 10px; height: 10px; }}

/* ── base button — fixed, no stretch ──────────────── */
QPushButton {{
    background-color: {MX_BG_BTN};
    color: {MX_TEXT};
    border: 1px solid transparent;
    padding: 0px 8px;
    border-radius: 1px;
    font-family: "Tahoma", "Segoe UI", sans-serif;
    font-size: {FONT_MAIN};
    height: {H}px;
}}
QPushButton:hover {{ background-color: {MX_BG_BTN_HO}; border: 1px solid {MX_BORDER}; }}
QPushButton:pressed {{ background-color: {MX_BG_BTN_PR}; border: 1px solid {MX_BORDER}; }}

/* ── library ──────────────────────────────────────────── */
QPushButton#lib_btn {{
    background-color: {LIB_BG};
    color: {LIB_TEXT};
    border: 1px solid {LIB_BORDER};
    border-radius: 2px;
    font-size: 7pt;
    padding: 0px 6px;
}}
QPushButton#lib_btn:hover {{ background-color: {LIB_BG_HO}; border-color: {MX_BORDER_HI}; color: {LIB_TEXT_HO}; }}
QPushButton#lib_btn:pressed {{ background-color: #111111; }}

/* ── action buttons ───────────────────────────────────── */
QPushButton#action_btn {{
    background-color: #484848;
    color: {MX_TEXT};
    border: 1px solid {MX_BORDER};
    border-radius: 1px;
    padding: 0px 10px;
    font-size: {FONT_MAIN};
}}
QPushButton#action_btn:hover {{ background-color: {MX_BG_BTN_HO}; border-color: {MX_BORDER_HI}; }}
QPushButton#action_btn:pressed {{ background-color: {MX_BG_BTN_PR}; }}

/* ── reset — subtle red tint ──────────────────────────── */
QPushButton#reset_btn {{
    background-color: #3a2e2e;
    color: #c08080;
    border: 1px solid #5a4040;
    border-radius: 1px;
    padding: 0px 10px;
    font-size: {FONT_MAIN};
}}
QPushButton#reset_btn:hover {{ background-color: #583030; color: #e06060; border-color: #884444; }}
QPushButton#reset_btn:pressed {{ background-color: #1e1010; }}

/* ── preset S/L/D ─────────────────────────────────────── */
QPushButton#save_btn, QPushButton#load_btn, QPushButton#del_btn {{
    background-color: #484848; color: {MX_TEXT_DIM};
    border: 1px solid {MX_BORDER}; border-radius: 1px;
    min-width: 20px; max-width: 20px; padding: 0; font-size: {FONT_SMALL};
}}
QPushButton#save_btn:hover, QPushButton#load_btn:hover {{
    background-color: {MX_BG_BTN_HO}; color: {MX_TEXT}; border-color: {MX_BORDER_HI};
}}
QPushButton#del_btn:hover {{ background-color: #583030; color: #e06060; border-color: #884444; }}

/* ── add task ─────────────────────────────────────────── */
QPushButton#add_btn {{
    background-color: #484848; color: {MX_TEXT_DIM};
    border: 1px solid {MX_BORDER}; border-radius: 1px;
    min-width: 20px; max-width: 20px; padding: 0;
    font-size: 12pt; font-weight: bold;
}}
QPushButton#add_btn:hover {{ background-color: {MX_BG_BTN_HO}; color: {MX_TEXT}; border-color: {MX_BORDER_HI}; }}

/* ── note fields ──────────────────────────────────────── */
QLineEdit#note_field {{
    background-color: {MX_BG_INPUT}; border: 1px solid {MX_BORDER};
    color: {MX_TEXT_DIM}; font-style: italic;
    font-size: {FONT_LABEL}; border-radius: 1px;
}}
QLineEdit#note_field:focus {{ border-color: {MX_BORDER_HI}; color: {MX_TEXT}; }}

/* ── labels ───────────────────────────────────────────── */
QLabel {{
    background: transparent; color: {MX_TEXT_DIM};
    font-family: "Tahoma", "Segoe UI", sans-serif;
    font-size: {FONT_LABEL};
}}
QLabel#film_lbl   {{ font-size: {FONT_LABEL}; font-weight: bold; }}
QLabel#mm_lbl     {{ font-size: {FONT_LABEL}; }}
QLabel#status_lbl {{ font-size: {FONT_LABEL}; min-width: 100px; }}
QLabel#version_lbl {{ color: #606060; font-size: {FONT_SMALL}; }}

/* ── section stretch labels ───────────────────────────── */
QLabel#stretch_lbl {{
    color: transparent;       /* invisible but takes up space */
    background: transparent;
    font-size: 1pt;
}}

/* ── checkbox ─────────────────────────────────────────── */
QCheckBox {{ color: {MX_TEXT}; font-size: {FONT_MAIN}; spacing: 5px; }}
QCheckBox::indicator {{
    width: 13px; height: 13px;
    background-color: {MX_BG_INPUT}; border: 1px solid {MX_BORDER}; border-radius: 1px;
}}
QCheckBox::indicator:checked {{ background-color: #5a8aaa; border-color: {MX_BORDER_HI}; }}
QCheckBox:hover {{ color: {MX_TEXT}; }}

/* ── menus ────────────────────────────────────────────── */
QMenu {{
    background-color: #323232; color: {MX_TEXT};
    border: 1px solid {MX_BORDER};
    font-family: "Tahoma","Segoe UI",sans-serif; font-size: {FONT_MAIN}; padding: 2px 0;
}}
QMenu::item {{ padding: 5px 22px 5px 10px; }}
QMenu::item:selected {{ background-color: {MX_SEL_BG}; color: #ffffff; }}
QMenu::item:disabled {{ color: #606060; }}
QMenu::separator {{ height: 1px; background: {MX_SEP}; margin: 2px 6px; }}

/* ── mini icon buttons (presets, lock, ×2, ½, setup…) ─── */
QToolButton#mini_btn, QToolButton#mini_del {{
    background-color: #464646; border: 1px solid {MX_BORDER}; border-radius: 2px; padding: 0;
}}
QToolButton#mini_btn:hover {{ background-color: {MX_BG_BTN_HO}; border-color: {MX_BORDER_HI}; }}
QToolButton#mini_btn:pressed {{ background-color: {MX_BG_BTN_PR}; }}
QToolButton#mini_btn:checked {{ background-color: #24404a; border-color: #3f8a9a; }}
QToolButton#mini_del:hover {{ background-color: #583030; border-color: #884444; }}
QToolButton#mini_btn::menu-indicator {{ image: none; width: 0; }}

/* ── split action buttons (OPEN ▾ / SAVE ▾) ───────────── */
QToolButton#action_btn {{
    background-color: #484848; color: {MX_TEXT};
    border: 1px solid {MX_BORDER}; border-radius: 1px;
    padding: 0px 18px 0px 10px; height: {H}px; font-size: {FONT_MAIN};
}}
QToolButton#action_btn:hover {{ background-color: {MX_BG_BTN_HO}; border-color: {MX_BORDER_HI}; }}
QToolButton#action_btn:pressed {{ background-color: {MX_BG_BTN_PR}; }}
QToolButton#action_btn::menu-button {{
    width: 14px; border-left: 1px solid {MX_BORDER}; background: transparent;
}}
QToolButton#action_btn::menu-button:hover {{ background-color: #5c5c5c; }}
QToolButton#action_btn::menu-arrow {{ image: url({_icon_url("arrow_down")}); width: 9px; height: 9px; }}

/* ── GET highlighted: open file belongs to another shot/task ── */
QPushButton#action_btn[attention="true"] {{
    color: #f0c060; border-color: #a07a2a; background-color: #4a4232;
}}

/* ── FPS clickeable ───────────────────────────────────── */
QToolButton#fps_btn {{
    background: transparent; border: 1px solid transparent; border-radius: 2px;
    color: {MX_TEXT_DIM}; font-weight: bold; font-size: {FONT_MAIN}; padding: 0px;
}}
QToolButton#fps_btn:hover {{ border-color: {MX_BORDER}; color: {MX_TEXT}; background-color: #444444; }}
QToolButton#fps_btn::menu-indicator {{ image: none; width: 0; }}

/* ── aspect ratio readout ─────────────────────────────── */
QLabel#aspect_lbl {{ color: #7d8f96; font-size: {FONT_SMALL}; }}

/* ── tooltip ──────────────────────────────────────────── */
QToolTip {{
    background-color: #2a2a2a; color: {MX_TEXT};
    border: 1px solid {MX_BORDER};
    font-family: "Tahoma","Segoe UI",sans-serif; font-size: {FONT_LABEL}; padding: 3px 7px;
}}
"""


# ── SVG icons ─────────────────────────────────────────────────────────────────
def _svg_overscan(base, accent):
    return f"""<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
  <rect x="4" y="4" width="16" height="16" fill="none" stroke="{base}" stroke-width="1.4" rx="0.5"/>
  <line x1="0.5" y1="0.5" x2="4"  y2="4"   stroke="{accent}" stroke-width="1.5"/>
  <line x1="23.5" y1="0.5" x2="20" y2="4"  stroke="{accent}" stroke-width="1.5"/>
  <line x1="0.5" y1="23.5" x2="4"  y2="20" stroke="{accent}" stroke-width="1.5"/>
  <line x1="23.5" y1="23.5" x2="20" y2="20" stroke="{accent}" stroke-width="1.5"/>
  <polyline points="0.5,0.5 4,0.5"   stroke="{accent}" stroke-width="1.5" fill="none"/>
  <polyline points="0.5,0.5 0.5,4"   stroke="{accent}" stroke-width="1.5" fill="none"/>
  <polyline points="23.5,0.5 20,0.5"  stroke="{accent}" stroke-width="1.5" fill="none"/>
  <polyline points="23.5,0.5 23.5,4"  stroke="{accent}" stroke-width="1.5" fill="none"/>
  <polyline points="0.5,23.5 4,23.5"  stroke="{accent}" stroke-width="1.5" fill="none"/>
  <polyline points="0.5,23.5 0.5,20"  stroke="{accent}" stroke-width="1.5" fill="none"/>
  <polyline points="23.5,23.5 20,23.5" stroke="{accent}" stroke-width="1.5" fill="none"/>
  <polyline points="23.5,23.5 23.5,20" stroke="{accent}" stroke-width="1.5" fill="none"/>
</svg>"""

def _svg_imgplane(base, accent):
    return f"""<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
  <rect x="1" y="2.5" width="22" height="16" fill="none" stroke="{base}" stroke-width="1.4" rx="0.5"/>
  <line x1="1"  y1="18.5" x2="7"   y2="18.5" stroke="{base}" stroke-width="1.3"/>
  <line x1="17" y1="18.5" x2="23"  y2="18.5" stroke="{base}" stroke-width="1.3"/>
  <line x1="9"  y1="18.5" x2="9"   y2="22"   stroke="{base}" stroke-width="1.3"/>
  <line x1="15" y1="18.5" x2="15"  y2="22"   stroke="{base}" stroke-width="1.3"/>
  <line x1="7"  y1="22"   x2="17"  y2="22"   stroke="{base}" stroke-width="1.3"/>
  <circle cx="7" cy="8" r="2.2" fill="{accent}"/>
  <polyline points="2,16.5 7,12 10,14 14,9 22,16.5" fill="none" stroke="{base}" stroke-width="1.3"/>
</svg>"""

def _svg_remback(base, accent):
    return f"""<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
  <polygon points="4,19 9,5 20,5 15,19" fill="none" stroke="{base}" stroke-width="1.4"/>
  <polygon points="4,19 9,5 12,5 7,19"  fill="{accent}" opacity="0.65"/>
  <line x1="2" y1="21.5" x2="22" y2="21.5" stroke="{base}" stroke-width="1.6"/>
</svg>"""

def _svg_textures(base, accent):
    return f"""<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
  <rect x="1" y="1" width="22" height="22" fill="none" stroke="{base}" stroke-width="1.3" rx="0.5"/>
  <rect x="1"  y="1"  width="11" height="11" fill="{base}"   opacity="0.70"/>
  <rect x="12" y="12" width="11" height="11" fill="{base}"   opacity="0.70"/>
  <rect x="12" y="1"  width="11" height="11" fill="{accent}" opacity="0.35"/>
  <rect x="1"  y="12" width="11" height="11" fill="{accent}" opacity="0.35"/>
</svg>"""

def _svg_bakecam(base, accent):
    return f"""<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
  <rect x="1" y="4" width="14" height="11" rx="1.2" fill="none" stroke="{base}" stroke-width="1.4"/>
  <polyline points="15,7 23,4 23,15 15,12" fill="none" stroke="{base}" stroke-width="1.3"/>
  <circle cx="6" cy="9.5" r="2.5" fill="none" stroke="{base}" stroke-width="1.2"/>
  <circle cx="3"  cy="21" r="1.5" fill="{accent}"/>
  <circle cx="12" cy="21" r="1.5" fill="{accent}"/>
  <circle cx="21" cy="21" r="1.5" fill="{accent}"/>
  <path d="M3,21 C6,16.5 9,25 12,21 C15,16.5 18,25 21,21"
        fill="none" stroke="{base}" stroke-width="1.1" opacity="0.85"/>
</svg>"""

def _svg_library(base, accent):
    return f"""<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
  <rect x="1"  y="1"  width="10" height="10" rx="1" fill="none" stroke="{base}" stroke-width="1.2"/>
  <rect x="13" y="1"  width="10" height="10" rx="1" fill="none" stroke="{base}" stroke-width="1.2"/>
  <rect x="1"  y="13" width="10" height="10" rx="1" fill="none" stroke="{base}" stroke-width="1.2"/>
  <rect x="13" y="13" width="10" height="10" rx="1" fill="none" stroke="{base}" stroke-width="1.2"/>
  <rect x="2.5" y="2.5" width="7" height="7" rx="0.5" fill="{accent}" opacity="0.55"/>
  <rect x="14.5" y="2.5"  width="7" height="7" rx="0.5" fill="{base}" opacity="0.30"/>
  <rect x="2.5"  y="14.5" width="7" height="7" rx="0.5" fill="{base}" opacity="0.30"/>
  <rect x="14.5" y="14.5" width="7" height="7" rx="0.5" fill="{base}" opacity="0.30"/>
</svg>"""

def _svg_snap(base, accent):
    """Snapshot camera — body + lens + little flash."""
    return f"""<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
  <rect x="2" y="6" width="20" height="14" rx="2" fill="none" stroke="{base}" stroke-width="1.4"/>
  <path d="M8,6 L9.5,3 L14.5,3 L16,6" fill="none" stroke="{base}" stroke-width="1.3"/>
  <circle cx="12" cy="13" r="4" fill="none" stroke="{base}" stroke-width="1.3"/>
  <circle cx="12" cy="13" r="2" fill="{accent}" opacity="0.7"/>
  <circle cx="18.5" cy="9" r="1.2" fill="{accent}" opacity="0.9"/>
</svg>"""


# ── Mini icons (16×16 viewBox) for small buttons — replace the S/L/D/H letters ──
def _mi(body, c):
    return (f'<svg viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg" fill="none" '
            f'stroke="{c}" stroke-width="1.55" stroke-linecap="round" stroke-linejoin="round">{body}</svg>')

MINI_ICONS = {
    "save":   '<path d="M3 2.5h8l2.5 2.5v8.5h-10.5z"/><path d="M5.5 2.5v3.5h5v-3.5"/><rect x="5" y="9" width="6" height="4.5"/>',
    "list":   '<path d="M5.5 4h8M5.5 8h8M5.5 12h8"/><circle cx="2.6" cy="4" r=".6"/><circle cx="2.6" cy="8" r=".6"/><circle cx="2.6" cy="12" r=".6"/>',
    "trash":  '<path d="M2.5 4.5h11M6 4.5v-2h4v2M4 4.5l.7 9h6.6l.7-9M6.7 7v4.5M9.3 7v4.5"/>',
    "lock":   '<rect x="3.5" y="7" width="9" height="6.5" rx="1"/><path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2"/>',
    "unlock": '<rect x="3.5" y="7" width="9" height="6.5" rx="1"/><path d="M5.5 7V5a2.5 2.5 0 0 1 4.8-1"/>',
    "x2":     '<path d="M2.5 5l4 6M6.5 5l-4 6"/><path d="M9 6.2c.3-1 1.1-1.5 2-1.5 1.2 0 2 .8 2 1.8 0 1.6-2.5 2.6-4 4.5h4.2"/>',
    "half":   '<path d="M3 4.5v4M2 5.5l1-1"/><path d="M12 3L4 13"/><path d="M9.2 9.6c.2-.7.8-1.1 1.6-1.1.9 0 1.5.6 1.5 1.3 0 1.2-1.9 1.9-3.1 3.2h3.3"/>',
    "gear":   '<circle cx="8" cy="8" r="2"/><path d="M6.9 1.8h2.2l.4 1.8 1.2.7 1.8-.6 1.1 1.9-1.4 1.2v1.4l1.4 1.2-1.1 1.9-1.8-.6-1.2.7-.4 1.8H6.9l-.4-1.8-1.2-.7-1.8.6-1.1-1.9 1.4-1.2V7.3L1.4 6.1l1.1-1.9 1.8.6 1.2-.7z"/>',
    "folder": '<path d="M1.8 4.2v8.3h12.4V5.5H7.6L6.2 3.5H2.5z"/>',
    "plus":   '<path d="M8 3v10M3 8h10"/>',
    "chevron":'<path d="M4.5 6.5L8 10l3.5-3.5"/>',
}

def _mini_icon(name, color=None, color_hover=None, size=16):
    """Crisp (2x) QIcon for small buttons; Normal / Active(hover) / On(checked) states."""
    icon = QtGui.QIcon()
    for mode, col in ((QtGui.QIcon.Normal, color or IC_BASE),
                      (QtGui.QIcon.Active, color_hover or IC_HOVER),
                      (QtGui.QIcon.Disabled, "#5a5a5a")):
        pm = _svg_to_pixmap(_mi(MINI_ICONS[name], col), size * 2)
        pm.setDevicePixelRatio(2.0)
        icon.addPixmap(pm, mode, QtGui.QIcon.Off)
    return icon

def _mini_btn(icon, tooltip, obj="mini_btn", checkable=False):
    b = QtWidgets.QToolButton()
    b.setObjectName(obj)
    b.setIcon(icon if isinstance(icon, QtGui.QIcon) else _mini_icon(icon))
    b.setIconSize(QtCore.QSize(16, 16))
    b.setFixedSize(24, H)
    b.setToolTip(tooltip)
    b.setCheckable(checkable)
    b.setAutoRaise(False)
    b.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
    return b

def _svg_to_pixmap(svg_str, size=ICON_SZ):
    renderer = QtSvg.QSvgRenderer(QtCore.QByteArray(svg_str.encode()))
    pix = QtGui.QPixmap(size, size)
    pix.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(pix)
    renderer.render(painter)
    painter.end()
    return pix


def _svg_to_pixmap_rect(svg_str, w, h):
    """Render an SVG to a QPixmap of arbitrary size."""
    renderer = QtSvg.QSvgRenderer(QtCore.QByteArray(svg_str.encode()))
    pix = QtGui.QPixmap(w, h)
    pix.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(pix)
    renderer.render(painter)
    painter.end()
    return pix


def _svg_x2(color):
    """×2 icon — multiplication sign + a large, clear number 2."""
    return f"""<svg viewBox="0 0 34 22" xmlns="http://www.w3.org/2000/svg">
  <line x1="3" y1="5"  x2="10" y2="14" stroke="{color}" stroke-width="1.8" stroke-linecap="round"/>
  <line x1="10" y1="5" x2="3"  y2="14" stroke="{color}" stroke-width="1.8" stroke-linecap="round"/>
  <path d="M17,6 L24,6 Q27,6 27,9 Q27,12 22,14 L17,17 L27,17"
        fill="none" stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
</svg>"""


def _svg_div2(color):
    """/2 icon — slash + number 2."""
    return f"""<svg viewBox="0 0 34 22" xmlns="http://www.w3.org/2000/svg">
  <line x1="10" y1="17" x2="17" y2="5" stroke="{color}" stroke-width="1.8" stroke-linecap="round"/>
  <path d="M21,6 L28,6 Q31,6 31,9 Q31,12 26,14 L21,17 L31,17"
        fill="none" stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
</svg>"""


class SvgLabelButton(QtWidgets.QPushButton):
    """Small button with a rectangular (non-square) SVG icon, for X2 / /2."""
    def __init__(self, svg_fn, w, h, tooltip="", parent=None):
        super().__init__(parent)
        self._svg_fn  = svg_fn
        self._hovered = False
        self.setFixedSize(w, h)
        self.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.setToolTip(tooltip)
        self.setFlat(True)
        self._pix_normal = _svg_to_pixmap_rect(svg_fn(IC_BASE),  w, h)
        self._pix_hover  = _svg_to_pixmap_rect(svg_fn(IC_HOVER), w, h)

    def enterEvent(self, e): self._hovered = True;  self.update(); super().enterEvent(e)
    def leaveEvent(self, e): self._hovered = False; self.update(); super().leaveEvent(e)

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        bg = MX_BG_BTN_HO if self._hovered else "#484848"
        p.fillRect(self.rect(), QtGui.QColor(bg))
        if self._hovered:
            pen = QtGui.QPen(QtGui.QColor(MX_BORDER)); pen.setWidth(1)
            p.setPen(pen)
            p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        pix = self._pix_hover if self._hovered else self._pix_normal
        p.drawPixmap(0, 0, pix)
        p.end()


# ── IconToolButton — square, icon only, no text overlay ───────────────────────
class IconToolButton(QtWidgets.QPushButton):
    def __init__(self, svg_fn, bg=MX_BG, bg_hover=MX_BG_BTN_HO,
                 base_color=IC_BASE, accent_color=IC_ACCENT, parent=None):
        super().__init__(parent)
        self._svg_fn       = svg_fn
        self._bg           = bg
        self._bg_hover     = bg_hover
        self._hovered      = False

        self.setFixedSize(TOOL_SZ, TOOL_SZ)
        self.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        # No setFlat — we use our own paintEvent
        self.setFlat(True)

        self._pix_normal = _svg_to_pixmap(svg_fn(base_color, accent_color))
        self._pix_hover  = _svg_to_pixmap(svg_fn(IC_HOVER,   accent_color))

    def enterEvent(self, e): self._hovered = True;  self.update(); super().enterEvent(e)
    def leaveEvent(self, e): self._hovered = False; self.update(); super().leaveEvent(e)

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.fillRect(self.rect(), QtGui.QColor(self._bg_hover if self._hovered else self._bg))
        if self._hovered:
            pen = QtGui.QPen(QtGui.QColor(MX_BORDER)); pen.setWidth(1)
            p.setPen(pen)
            p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        pix = self._pix_hover if self._hovered else self._pix_normal
        ix  = (TOOL_SZ - ICON_SZ) // 2
        iy  = (TOOL_SZ - ICON_SZ) // 2
        p.drawPixmap(ix, iy, pix)
        p.end()



# ── Viewport BG Color presets ─────────────────────────────────────────────────
VP_COLOR_PRESETS_DEFAULT = [
    {"name": "Original",      "hex": "#383838"},
    {"name": "Default Gray",  "hex": "#484848"},
    {"name": "Dark Studio",   "hex": "#1e1e20"},
    {"name": "Deep Black",    "hex": "#0a0a0a"},
    {"name": "Soft Charcoal", "hex": "#32343a"},
    {"name": "Pure White",    "hex": "#f5f5f5"},
    {"name": "Blue Slate",    "hex": "#192840"},
    {"name": "Cinema Black",  "hex": "#050505"},
]
VP_COLOR_CFG_KEY = "vp_color_presets"

def _get_vp_color_presets():
    """Read presets from pipeline_config.ini, or return the defaults."""
    cfg = load_pipeline_cfg()
    raw = cfg.get(VP_COLOR_CFG_KEY)
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            pass
    return list(VP_COLOR_PRESETS_DEFAULT)

def _save_vp_color_presets(presets):
    """Save presets to pipeline_config.ini."""
    cfg = load_pipeline_cfg()
    cfg[VP_COLOR_CFG_KEY] = json.dumps(presets)
    save_pipeline_cfg(cfg)

def _hex_to_maxpoint3(hex_color):
    """Convert #rrggbb to a normalized (0-1) Point3 for SetUIColor."""
    h = hex_color.lstrip("#")
    r = int(h[0:2], 16) / 255.0
    g = int(h[2:4], 16) / 255.0
    b = int(h[4:6], 16) / 255.0
    return r, g, b

def _get_current_vp_hex():
    """Read the current viewport color from Max and return #rrggbb.
    Solid: index 41. Gradient: bottom (the most visually representative color)."""
    try:
        is_solid = rt.viewport.IsSolidBackgroundColorMode()
        if is_solid:
            p3 = rt.GetUIColor(41)
        else:
            p3 = rt.colorMan.getColor(rt.Name("ViewportGradientBackgroundBottom"))
        r = int(p3.x * 255)
        g = int(p3.y * 255)
        b = int(p3.z * 255)
        return "#{:02x}{:02x}{:02x}".format(r, g, b)
    except Exception:
        return "#383838"

def _is_solid_mode():
    """True if the active viewport is in solid mode."""
    try:
        return bool(rt.viewport.IsSolidBackgroundColorMode())
    except Exception:
        return True

def _restore_vp_originals(orig_hex, orig_grad_top, orig_grad_bot):
    """Restore exactly the colors that were set before the manager was opened."""
    try:
        r, g, b = _hex_to_maxpoint3(orig_hex)
        rt.execute(f"SetUIColor 41 (point3 {r:.6f} {g:.6f} {b:.6f})")
        ht = orig_grad_top.lstrip("#")
        hb = orig_grad_bot.lstrip("#")
        r1,g1,b1 = int(ht[0:2],16)/255, int(ht[2:4],16)/255, int(ht[4:6],16)/255
        r2,g2,b2 = int(hb[0:2],16)/255, int(hb[2:4],16)/255, int(hb[4:6],16)/255
        rt.execute(f"colorMan.setColor #ViewportGradientBackgroundTop (point3 {r1:.6f} {g1:.6f} {b1:.6f})")
        rt.execute(f"colorMan.setColor #ViewportGradientBackgroundBottom (point3 {r2:.6f} {g2:.6f} {b2:.6f})")
        rt.execute("colorMan.repaintUI #repaintAll")
        rt.execute("max views redraw")
    except Exception as e:
        print(f"[STM Restore] {e}")

def _apply_vp_color(hex_color):
    """Apply a color to the viewport background via MAXScript.
    Keeps the original 3ds Max proportions:
      solid = chosen color
      bottom = color + 21/255  (lighter, like 77 vs 56)
      top    = color - 30/255  (darker, like 26 vs 56)
    """
    try:
        r, g, b = _hex_to_maxpoint3(hex_color)
        OFFSET_BOT =  21 / 255.0   # +21 levels like the Max default
        OFFSET_TOP = -30 / 255.0   # -30 levels like the Max default
        rb = min(1.0, max(0.0, r + OFFSET_BOT))
        gb = min(1.0, max(0.0, g + OFFSET_BOT))
        bb = min(1.0, max(0.0, b + OFFSET_BOT))
        rt_ = min(1.0, max(0.0, r + OFFSET_TOP))
        gt_ = min(1.0, max(0.0, g + OFFSET_TOP))
        bt_ = min(1.0, max(0.0, b + OFFSET_TOP))
        rt.execute(f"SetUIColor 41 (point3 {r:.6f} {g:.6f} {b:.6f})")
        rt.execute(f"colorMan.setColor #ViewportGradientBackgroundTop (point3 {rt_:.6f} {gt_:.6f} {bt_:.6f})")
        rt.execute(f"colorMan.setColor #ViewportGradientBackgroundBottom (point3 {rb:.6f} {gb:.6f} {bb:.6f})")
        rt.execute("colorMan.repaintUI #repaintAll")
        rt.execute("max views redraw")
    except Exception as e:
        print(f"[STM VP Color] {e}")


class ViewportColorButton(QtWidgets.QPushButton):
    """
    Square TOOL_SZ x TOOL_SZ button showing the current viewport color.
    Clicking opens a menu with presets + custom option + add/delete.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        # "Original" is always the known 3ds Max default
        # solid=56,56,56 | gradient top=26,26,26 | gradient bottom=77,77,77
        self._orig_hex      = "#383838"   # 56,56,56
        self._orig_grad_top = "#1a1a1a"   # 26,26,26
        self._orig_grad_bot = "#4d4d4d"   # 77,77,77
        # Start with the original color — updated to the real color after 300ms
        self._cur_hex       = self._orig_hex
        self._hovered   = False

        self.setFixedSize(TOOL_SZ, TOOL_SZ)
        self.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.setToolTip("Viewport Background Color\nClick to change — resets on 3ds Max restart")
        self.setFlat(True)
        self.clicked.connect(self._show_menu)

    def set_color(self, hex_color):
        self._cur_hex = hex_color
        self.update()

    def enterEvent(self, e): self._hovered = True;  self.update(); super().enterEvent(e)
    def leaveEvent(self, e): self._hovered = False; self.update(); super().leaveEvent(e)

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)

        # button background: current viewport color
        col = QtGui.QColor(self._cur_hex)
        p.fillRect(self.rect(), col)

        # border — brighter on hover
        border_col = QtGui.QColor(MX_BORDER_HI if self._hovered else MX_BORDER)
        pen = QtGui.QPen(border_col)
        pen.setWidth(1)
        p.setPen(pen)
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))

        # dropdown triangle in the bottom-right corner
        arrow_col = QtGui.QColor(255, 255, 255, 160) if col.lightness() < 128 else QtGui.QColor(0, 0, 0, 120)
        p.setBrush(arrow_col)
        p.setPen(QtCore.Qt.NoPen)
        sz = self.width()
        tri = QtGui.QPolygon([
            QtCore.QPoint(sz - 2,  sz - 8),
            QtCore.QPoint(sz - 8,  sz - 2),
            QtCore.QPoint(sz - 2,  sz - 2),
        ])
        p.drawPolygon(tri)

        # small centered "BG" label
        lbl_col = QtGui.QColor(255, 255, 255, 200) if col.lightness() < 128 else QtGui.QColor(0, 0, 0, 160)
        p.setPen(lbl_col)
        f = p.font(); f.setPointSize(7); f.setFamily("Tahoma"); p.setFont(f)
        p.drawText(self.rect(), QtCore.Qt.AlignCenter, "BG")
        p.end()

    def _restore_on_close(self):
        """Called when the dock closes — restores the original colors."""
        _restore_vp_originals(self._orig_hex, self._orig_grad_top, self._orig_grad_bot)

    def _show_menu(self):
        presets = _get_vp_color_presets()
        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: #2a2a2a;
                color: {MX_TEXT};
                border: 1px solid {MX_BORDER};
                font-size: {FONT_MAIN};
            }}
            QMenu::item {{ padding: 4px 28px 4px 8px; }}
            QMenu::item:selected {{ background-color: {MX_SEL_BG}; }}
            QMenu::separator {{ height: 1px; background: {MX_SEP}; margin: 3px 0; }}
        """)

        # — Presets with color swatch via QWidgetAction ───────────────────
        menu.setStyleSheet(menu.styleSheet() + "QMenu::item { padding-left: 8px; }")
        for i, preset in enumerate(presets):
            hex_c  = preset["hex"]
            name   = preset["name"]
            # Custom widget: swatch + label with padding
            wa = QtWidgets.QWidgetAction(menu)
            row = QtWidgets.QWidget()
            row.setStyleSheet("background: transparent;")
            hl  = QtWidgets.QHBoxLayout(row)
            hl.setContentsMargins(8, 3, 12, 3)
            hl.setSpacing(8)
            swatch = QtWidgets.QLabel()
            swatch.setFixedSize(14, 14)
            swatch.setStyleSheet(
                f"background-color: {hex_c}; border: 1px solid {MX_BORDER};"
                " border-radius: 1px;")
            lbl = QtWidgets.QLabel(name)
            lbl.setStyleSheet(f"color: {MX_TEXT}; font-size: {FONT_MAIN}; background: transparent;")
            hl.addWidget(swatch)
            hl.addWidget(lbl)
            hl.addStretch()
            wa.setDefaultWidget(row)
            wa.setData(("apply", i))
            # Hover effect
            row._wa = wa
            row._hex = hex_c
            row._idx = i
            menu.addAction(wa)

        menu.addSeparator()

        # — Custom color —
        act_custom = menu.addAction("Custom color…")
        act_custom.setData(("custom", -1))

        menu.addSeparator()

        # — Add current as preset —
        act_add = menu.addAction("Add current as preset…")
        act_add.setData(("add", -1))

        # — Delete preset —
        act_del = menu.addAction("Delete a preset…")
        act_del.setData(("delete", -1))

        menu.addSeparator()

        # — Restore original —
        act_restore = menu.addAction("Restore original")
        act_restore.setData(("restore", -1))

        action = menu.exec(self.mapToGlobal(QtCore.QPoint(0, self.height())))
        if action is None:
            return

        kind, idx = action.data()

        if kind == "apply":
            hex_c = presets[idx]["hex"]
            _apply_vp_color(hex_c)
            self.set_color(hex_c)

        elif kind == "custom":
            initial  = QtGui.QColor(self._cur_hex)
            prev_hex = self._cur_hex          # keep it for cancel
            dlg = QtWidgets.QColorDialog(initial, self)
            dlg.setWindowTitle("Viewport Background Color")
            dlg.setOption(QtWidgets.QColorDialog.NoButtons, False)
            # Real-time preview
            def _on_color_changing(col):
                if col.isValid():
                    _apply_vp_color(col.name())
                    self.set_color(col.name())
            dlg.currentColorChanged.connect(_on_color_changing)
            if dlg.exec() == QtWidgets.QDialog.Accepted:
                col = dlg.currentColor()
                if col.isValid():
                    hex_c = col.name()
                    _apply_vp_color(hex_c)
                    self.set_color(hex_c)
            else:
                # Cancel — restore the previous color
                _apply_vp_color(prev_hex)
                self.set_color(prev_hex)

        elif kind == "add":
            name, ok = QtWidgets.QInputDialog.getText(
                self, "Save preset", "Preset name:", text=f"Custom {self._cur_hex}")
            if ok and name.strip():
                presets.append({"name": name.strip(), "hex": self._cur_hex})
                _save_vp_color_presets(presets)

        elif kind == "delete":
            names = [p["name"] for p in presets]
            chosen, ok = QtWidgets.QInputDialog.getItem(
                self, "Delete preset", "Select preset to delete:", names, 0, False)
            if ok and chosen:
                presets = [p for p in presets if p["name"] != chosen]
                _save_vp_color_presets(presets)

        elif kind == "restore":
            _restore_vp_originals(self._orig_hex, self._orig_grad_top, self._orig_grad_bot)
            self.set_color(self._orig_hex)


class LibraryIconButton(IconToolButton):
    def __init__(self, parent=None):
        super().__init__(
            svg_fn       = _svg_library,
            bg           = LIB_BG,
            bg_hover     = LIB_BG_HO,
            base_color   = LIB_TEXT,
            accent_color = IC_ACCENT,
            parent       = parent,
        )

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.fillRect(self.rect(), QtGui.QColor(LIB_BG_HO if self._hovered else LIB_BG))
        pen = QtGui.QPen(QtGui.QColor(MX_BORDER_HI if self._hovered else LIB_BORDER))
        pen.setWidth(1)
        p.setPen(pen)
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        pix = self._pix_hover if self._hovered else self._pix_normal
        if self._hovered:
            pix = _svg_to_pixmap(_svg_library(LIB_TEXT_HO, IC_ACCENT))
        ix = (TOOL_SZ - ICON_SZ) // 2
        iy = (TOOL_SZ - ICON_SZ) // 2
        p.drawPixmap(ix, iy, pix)
        p.end()


# ── Full-height section separator ────────────────────────────────────────────
def _section_sep(layout):
    layout.addSpacing(10)
    line = QtWidgets.QFrame()
    line.setFrameShape(QtWidgets.QFrame.VLine)
    line.setFixedWidth(1)
    line.setStyleSheet(f"background: {MX_SEP}; border: none;")
    layout.addWidget(line)
    layout.addSpacing(10)

def _lbl(text):
    return QtWidgets.QLabel(text)

def _lbl_mm():
    l = QtWidgets.QLabel("mm"); l.setObjectName("mm_lbl"); return l

def _stretch(layout):
    """Add an invisible widget that absorbs the leftover space."""
    spacer = QtWidgets.QWidget()
    spacer.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
    spacer.setStyleSheet("background: transparent;")
    layout.addWidget(spacer)


# ── State helpers ─────────────────────────────────────────────────────────────
def load_state():
    if os.path.exists(INI_PATH):
        try:
            with open(INI_PATH, "r") as f: return json.load(f)
        except: return {}
    return {}

def save_state(data):
    try:
        os.makedirs(PIPE_DIR, exist_ok=True)
        cur = load_state(); cur.update(data)
        with open(INI_PATH, "w") as f: json.dump(cur, f, indent=2)
    except: pass

def get_project_root():
    try:
        path  = os.path.normpath(str(rt.pathConfig.getCurrentProjectFolder()))
        parts = path.split(os.sep)
        prefix = _cfg().get("project_prefix", "VFX-")
        for i in range(len(parts)-1, -1, -1):
            if parts[i].startswith(prefix): return os.sep.join(parts[:i+1])
        return path
    except: return ""

def get_pipeline_base():
    """Return the directory that contains the VFX-xxx projects.
    Tries the Max project folder first;
    if no prefix is found, falls back to the config's root_drive."""
    cfg    = _cfg()
    prefix = cfg.get("project_prefix", "VFX-")
    try:
        path  = os.path.normpath(str(rt.pathConfig.getCurrentProjectFolder()))
        parts = path.split(os.sep)
        for i, p in enumerate(parts):
            if p.startswith(prefix):
                base = os.sep.join(parts[:i])
                # On Windows "T:" without a slash lists the drive's cwd, not the root
                if base.endswith(":"):
                    base = base + os.sep
                return base
    except: pass
    # Direct fallback to the configured root_drive
    drive = cfg.get("root_drive", "T:").rstrip(os.sep)
    return drive + os.sep

def safe_listdir(path):
    try: return [d for d in os.listdir(path) if os.path.isdir(os.path.join(path, d))]
    except: return []

def next_version_folder(base_dir, prefix):
    existing = [d for d in os.listdir(base_dir) if d.startswith(prefix)] if os.path.isdir(base_dir) else []
    versions = []
    for d in existing:
        m = re.search(r'_v(\d+)$', d)
        if m: versions.append(int(m.group(1)))
    next_v = (max(versions) + 1) if versions else 1
    return f"{prefix}_v{next_v:03d}"


def capture_viewport_to_file(out_path):
    """
    Capture the active 3ds Max viewport to a PNG file.
    Same approach as StudioLibraryMAX — three fallback methods.
    Confirmed working in MAX 2025.
    """
    out_fwd = out_path.replace("\\", "/")
    captured = False

    # Method A: gw.getViewportDib() + .filename + save — confirmed MAX 2025
    if not captured:
        try:
            mxs = (f'( local img = gw.getViewportDib() ; '
                   f'img.filename = "{out_fwd}" ; save img )')
            rt.execute(mxs)
            if os.path.exists(out_path): captured = True
        except Exception as e:
            print(f"[snap A] {e}")

    # Method B: pymxs direct
    if not captured:
        try:
            img = rt.gw.getViewportDib()
            if img is not None:
                img.filename = out_path
                rt.save(img)
                if os.path.exists(out_path): captured = True
        except Exception as e:
            print(f"[snap B] {e}")

    # Method C: grabView()
    if not captured:
        try:
            mxs = f'( local b = grabView() ; b.filename = "{out_fwd}" ; save b )'
            rt.execute(mxs)
            if os.path.exists(out_path): captured = True
        except Exception as e:
            print(f"[snap C] {e}")

    return captured


# ── Main UI ───────────────────────────────────────────────────────────────────
class StudioToolbar(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.state = load_state()
        if "res_presets"  not in self.state: self.state["res_presets"]  = []
        if "film_presets" not in self.state: self.state["film_presets"] = []
        self._current_source = "Global"
        self._current_obj    = None
        self._build_ui()
        self._connect_signals()

        self.sync_timer = QtCore.QTimer(self)
        self.sync_timer.timeout.connect(self._master_sync)
        self.sync_timer.start(500)

        rt.STM_GlobalRefresh = self._on_file_opened
        rt.callbacks.removeScripts(id=rt.Name("Pipe3DSync"))   # legacy id (pre-2.5.36)
        rt.callbacks.removeScripts(id=rt.Name("STM_Sync"))
        rt.callbacks.addScript(rt.Name("filePostOpen"),
            "if STM_GlobalRefresh != undefined do STM_GlobalRefresh()",
            id=rt.Name("STM_Sync"))
        # Sync res/film immediately, populate pipeline after short delay
        QtCore.QTimer.singleShot(100, self._master_sync)
        QtCore.QTimer.singleShot(300, self._populate_projects)

    def _build_ui(self):
        self.setStyleSheet(STYLE)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Row widget with horizontal layout — takes all available width
        row_w = QtWidgets.QWidget()
        row_w.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        L = QtWidgets.QHBoxLayout(row_w)
        L.setContentsMargins(14, 0, 14, 0)
        L.setSpacing(2)

        outer.addStretch(1)
        outer.addWidget(row_w)
        outer.addStretch(1)

        # ── SECTION: TOOLS ───────────────────────────────────────────────────
        # "TOOLS" button that opens a QMenu with the scripts in PATH_TOOLS_DIR
        self.btn_tools_menu = QtWidgets.QPushButton("TOOLS ▾")
        self.btn_tools_menu.setObjectName("tools_menu_btn")
        self.btn_tools_menu.setFixedHeight(16)
        self.btn_tools_menu.setStyleSheet(f"""
            QPushButton#tools_menu_btn {{
                color: {MX_TEXT_DIM}; font-size: {FONT_LABEL}; font-weight: bold;
                background: transparent; border: none; padding: 0px 2px;
                text-align: left;
            }}
            QPushButton#tools_menu_btn:hover {{
                color: {MX_TEXT};
            }}
            QPushButton#tools_menu_btn:pressed {{
                color: #c8a84a;
            }}
        """)
        self.btn_tools_menu.clicked.connect(self._open_tools_menu)
        L.addWidget(self.btn_tools_menu)
        L.addSpacing(4)

        self.btn_overscan  = IconToolButton(_svg_overscan,  accent_color=IC_ACCENT)
        self.btn_img_plane = IconToolButton(_svg_imgplane,  accent_color=IC_ACCENT2)
        self.btn_rem_back  = IconToolButton(_svg_remback,   accent_color=IC_ACCENT)
        self.btn_textures  = IconToolButton(_svg_textures,  accent_color=IC_ACCENT)
        self.btn_bake_cam  = IconToolButton(_svg_bakecam,   accent_color=IC_ACCENT)
        self.btn_library   = LibraryIconButton()

        self.btn_overscan.setToolTip("Overscan\nAdjusts camera overscan — adds bleed area outside the render frame")
        self.btn_img_plane.setToolTip("Image Plane\nCreates a reference image plane inside the active viewport")
        self.btn_rem_back.setToolTip("Remove Background\nRemoves/hides the environment background from the scene")
        self.btn_textures.setToolTip("Show Textures\nToggles texture display in the viewport (on/off)")
        self.btn_bake_cam.setToolTip("Bake Camera\nSelect an Alembic camera — bakes its transform and FOV into a native Free Camera")
        self.btn_library.setToolTip("Studio Library MAX\nOpens the pose/animation library manager")

        for b in [self.btn_overscan, self.btn_img_plane, self.btn_rem_back,
                  self.btn_textures, self.btn_bake_cam]:
            L.addWidget(b)
            L.addSpacing(3)
        L.addSpacing(4)
        L.addWidget(self.btn_library)

        # Stretch after tools — absorbs leftover space in the TOOLS section
        _stretch(L)

        # ── SECTION: RESOLUTION ───────────────────────────────────────────────
        _section_sep(L)

        lbl_res = QtWidgets.QLabel("RESOLUTION")
        lbl_res.setStyleSheet(f"color:{MX_TEXT_DIM}; font-size:{FONT_LABEL}; font-weight:bold; background:transparent;")
        L.addWidget(lbl_res); L.addSpacing(5)

        self.res_w = QtWidgets.QSpinBox()
        self.res_w.setRange(1,32000); self.res_w.setFixedWidth(82); self.res_w.setFixedHeight(H)
        self.res_w.setToolTip("Render Width (pixels)")
        self.res_w.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)

        _x = QtWidgets.QLabel("×"); _x.setAlignment(QtCore.Qt.AlignCenter); _x.setFixedWidth(10)

        self.res_h = QtWidgets.QSpinBox()
        self.res_h.setRange(1,32000); self.res_h.setFixedWidth(82); self.res_h.setFixedHeight(H)
        self.res_h.setToolTip("Render Height (pixels)")
        self.res_h.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)

        self.res_lock_btn = _mini_btn("unlock", "Lock aspect ratio — keeps W:H proportion when either value changes",
                                      checkable=True)
        self._ic_lock, self._ic_unlock = _mini_icon("lock", "#4ec9c9", "#7fe0e0"), _mini_icon("unlock")

        self.res_x2_btn = _mini_btn("x2",   "Double the resolution (W and H × 2, always even)")
        self.res_d2_btn = _mini_btn("half", "Halve the resolution (W and H ÷ 2, always even)")

        self.res_aspect = QtWidgets.QLabel("1.78")
        self.res_aspect.setObjectName("aspect_lbl")
        self.res_aspect.setFixedWidth(38); self.res_aspect.setAlignment(QtCore.Qt.AlignCenter)
        self.res_aspect.setToolTip("Aspect ratio (W ÷ H)")

        self.res_note = QtWidgets.QLineEdit()
        self.res_note.setObjectName("note_field"); self.res_note.setPlaceholderText("preset label…")
        self.res_note.setFixedWidth(198); self.res_note.setFixedHeight(H)
        self.res_note.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.res_note.setToolTip("Resolution preset label — click the arrow to pick a preset")
        # Preset list as an arrow INSIDE the field (was a separate L button)
        self.res_list_act = self.res_note.addAction(_mini_icon("chevron"), QtWidgets.QLineEdit.TrailingPosition)
        self.res_list_act.setToolTip("Saved + standard resolution presets")

        self.res_s = _mini_btn("save",  "Save resolution preset (uses the label)")
        self.res_d = _mini_btn("trash", "Delete current resolution preset", obj="mini_del")

        for w in [self.res_w, _x, self.res_h]: L.addWidget(w)
        L.addSpacing(2)
        L.addWidget(self.res_aspect)
        L.addSpacing(2)
        L.addWidget(self.res_lock_btn)
        L.addSpacing(2)
        L.addWidget(self.res_x2_btn)
        L.addWidget(self.res_d2_btn)
        L.addSpacing(6)
        for w in [self.res_note, self.res_s, self.res_d]: L.addWidget(w)
        L.addSpacing(0)

        # Stretch after RESOLUTION — FILM size is its own section
        _stretch(L)

        # ── SECTION: FILM ────────────────────────────────────────────────
        _section_sep(L)

        self.film_lbl = QtWidgets.QLabel("FILM (Standard)"); self.film_lbl.setObjectName("film_lbl")
        self.film_lbl.setStyleSheet(f"color:{MX_TEXT_DIM}; font-size:{FONT_LABEL}; font-weight:bold; background:transparent;")
        self.film_lbl.setFixedWidth(150)
        L.addWidget(self.film_lbl); L.addSpacing(10)

        self.film_spin = QtWidgets.QDoubleSpinBox()
        self.film_spin.setRange(0.01,1000.0); self.film_spin.setDecimals(2)
        self.film_spin.setFixedWidth(80); self.film_spin.setFixedHeight(H)
        self.film_spin.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.film_spin.setToolTip("Film/aperture width value")

        _mm = _lbl_mm(); _mm.setFixedWidth(34); _mm.setAlignment(QtCore.Qt.AlignCenter)

        self.film_note = QtWidgets.QLineEdit()
        self.film_note.setObjectName("note_field"); self.film_note.setPlaceholderText("camera / lens label…")
        self.film_note.setFixedWidth(270); self.film_note.setFixedHeight(H)
        self.film_note.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.film_note.setToolTip("Film size preset label — click the arrow for saved presets and camera sensors")
        self.film_list_act = self.film_note.addAction(_mini_icon("chevron"), QtWidgets.QLineEdit.TrailingPosition)
        self.film_list_act.setToolTip("Saved presets + camera sensor widths")

        self.film_s = _mini_btn("save",  "Save film size preset (uses the label)")
        self.film_d = _mini_btn("trash", "Delete current film size preset", obj="mini_del")

        L.addWidget(self.film_spin); L.addWidget(_mm)
        for w in [self.film_note, self.film_s, self.film_d]: L.addWidget(w)

        # Stretch after FILM
        _stretch(L)

        # ── SECTION: FPS ──────────────────────────────────────────────────────
        _section_sep(L)

        self.fps_lbl = QtWidgets.QToolButton()
        self.fps_lbl.setObjectName("fps_btn")
        self.fps_lbl.setText("— FPS")
        self.fps_lbl.setFixedSize(72, H)
        self.fps_lbl.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.fps_lbl.setToolTip("Scene frame rate — click to change")
        self.fps_lbl.clicked.connect(self._show_fps_menu)
        L.addWidget(self.fps_lbl)

        # small inner separator
        L.addSpacing(8)
        _inner = QtWidgets.QFrame()
        _inner.setFrameShape(QtWidgets.QFrame.VLine)
        _inner.setFixedWidth(1)
        _inner.setStyleSheet(f"background: {MX_SEP}; border: none;")
        L.addWidget(_inner)
        L.addSpacing(8)

        lbl_unit = QtWidgets.QLabel("UNIT")
        lbl_unit.setStyleSheet(f"color:{MX_TEXT_DIM}; font-size:{FONT_LABEL}; font-weight:bold; background:transparent;")
        L.addWidget(lbl_unit); L.addSpacing(8)

        self.unit_lbl = QtWidgets.QLabel("—")
        self.unit_lbl.setObjectName("unit_val_lbl")
        self.unit_lbl.setStyleSheet(f"color:{MX_TEXT_DIM}; font-size:{FONT_MAIN}; background:transparent;")
        self.unit_lbl.setFixedWidth(110)   # fixed width — "Kilometers" is the longest
        self.unit_lbl.setToolTip("Current scene system unit (read-only)")
        L.addWidget(self.unit_lbl)

        # Stretch after FPS/UNIT
        _stretch(L)

        # ── SECTION: PIPELINE ─────────────────────────────────────────────────
        _section_sep(L)

        lbl_pipe = QtWidgets.QLabel("PIPELINE")
        lbl_pipe.setStyleSheet(f"color:{MX_TEXT_DIM}; font-size:{FONT_LABEL}; font-weight:bold; background:transparent;")
        L.addWidget(lbl_pipe); L.addSpacing(5)

        self.project_cb = QtWidgets.QComboBox()
        self.project_cb.setFixedWidth(110); self.project_cb.setFixedHeight(H)
        self.project_cb.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.project_cb.setToolTip("Active project")

        self.sequence_cb = QtWidgets.QComboBox()
        self.sequence_cb.setFixedWidth(120); self.sequence_cb.setFixedHeight(H)
        self.sequence_cb.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.sequence_cb.setToolTip("Sequence folder")

        self.shot_cb = QtWidgets.QComboBox()
        self.shot_cb.setFixedWidth(274); self.shot_cb.setFixedHeight(H)
        self.shot_cb.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.shot_cb.setToolTip("Shot")

        self.task_cb = QtWidgets.QComboBox()
        self.task_cb.setFixedWidth(160); self.task_cb.setFixedHeight(H)
        self.task_cb.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.task_cb.setToolTip("Task / department folder (e.g. 5_matchmove)")

        self.add_btn = _mini_btn("plus", "Create a new task folder for the selected shot")
        self.folder_btn = _mini_btn("folder", "Open shot / task folders in Explorer")

        for w in [self.project_cb, self.sequence_cb, self.shot_cb, self.task_cb]:
            L.addWidget(w); L.addSpacing(2)
        L.addWidget(self.add_btn)
        L.addSpacing(2)
        L.addWidget(self.folder_btn)

        # Stretch after PIPELINE
        _stretch(L)

        # ── SECTION: ACTIONS ─────────────────────────────────────────────────
        _section_sep(L)

        # Snap button — between the two boxes, original icon size
        self.btn_snap = IconToolButton(_svg_snap, accent_color=IC_ACCENT2)
        self.btn_snap.setFixedSize(TOOL_SZ, TOOL_SZ)
        self.btn_snap.setToolTip("Viewport Snapshot\nCaptures the active viewport and saves a JPG to the current task's review folder\nRight-click: open snapshots folder")
        self.btn_snap.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.btn_snap.customContextMenuRequested.connect(self._snap_context_menu)
        L.addWidget(self.btn_snap)
        L.addSpacing(4)

        self.btn_vp_color = ViewportColorButton()
        self.btn_vp_color.setToolTip("Viewport Background Color\nClick to change — resets on 3ds Max restart")
        L.addWidget(self.btn_vp_color)
        # The BG button starts at the Max default (56,56,56)
        # and only updates when the user picks a color
        L.addSpacing(8)

        def _split_btn(text, tip):
            b = QtWidgets.QToolButton()
            b.setObjectName("action_btn"); b.setText(text); b.setFixedHeight(H)
            b.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
            b.setPopupMode(QtWidgets.QToolButton.MenuButtonPopup)
            b.setToolTip(tip)
            m = QtWidgets.QMenu(b); b.setMenu(m)
            return b, m

        self.open_btn, self._open_menu = _split_btn(
            "OPEN", "OPEN — browse .max scenes in the task folder\n▾ recent versions of this task")
        self._open_menu.aboutToShow.connect(self._fill_open_menu)
        self.save_scene_btn, self._save_menu = _split_btn(
            "SAVE", "SAVE — Save dialog in the task folder, next version pre-filled\n▾ save next version directly")
        self._save_menu.aboutToShow.connect(self._fill_save_menu)

        self.get_btn = QtWidgets.QPushButton("GET")
        self.get_btn.setObjectName("action_btn"); self.get_btn.setFixedHeight(H)
        self.get_btn.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.get_btn.setToolTip("GET — fills Project / Sequence / Shot / Task from the open file's folder")

        self.set_path_btn = QtWidgets.QPushButton("PATHS")
        self.set_path_btn.setObjectName("action_btn"); self.set_path_btn.setFixedHeight(H)
        self.set_path_btn.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.set_path_btn.setToolTip("Set project paths (scenes, images, preview, renderoutput) from selected shot/task")

        self.set_save_btn = QtWidgets.QPushButton("SET RENDER")
        self.set_save_btn.setObjectName("action_btn"); self.set_save_btn.setFixedHeight(H)
        self.set_save_btn.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.set_save_btn.setToolTip("Set Render Output — sets the render filename to the selected shot's publish folder")

        self.shotname_chk = QtWidgets.QCheckBox("SHOT NAME")
        self.shotname_chk.setFixedHeight(H)
        self.shotname_chk.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.shotname_chk.setToolTip(
            "SET RENDER naming\n"
            "  ON  → render named after the dropdowns:  shot_task_v###\n"
            "  OFF → render named after the open .max file\n"
            "The version always comes from the .max file.\n"
            "Use ON to render several shots from the same .max.")
        self.shotname_chk.setChecked(bool(load_state().get("render_shot_name", False)))
        self.shotname_chk.toggled.connect(lambda on: save_state({"render_shot_name": bool(on)}))

        self.reset_btn = QtWidgets.QPushButton("RESET")
        self.reset_btn.setObjectName("reset_btn"); self.reset_btn.setFixedHeight(H)
        self.reset_btn.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.reset_btn.setToolTip("Reset all project paths back to 3ds Max defaults")

        for b in [self.open_btn, self.save_scene_btn, self.get_btn, self.set_path_btn, self.set_save_btn]:
            L.addWidget(b); L.addSpacing(6)
        L.addSpacing(6)
        L.addWidget(self.shotname_chk)
        L.addSpacing(10)
        L.addWidget(self.reset_btn)

        # ── STATUS ────────────────────────────────────────────────────────────
        _section_sep(L)

        self.status_lbl  = QtWidgets.QLabel("Ready")
        self.status_lbl.setTextFormat(QtCore.Qt.RichText)
        self.status_lbl.setObjectName("status_lbl")
        self.status_lbl.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.status_lbl.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.status_lbl.setToolTip("Last action — click for history")
        self.status_lbl.installEventFilter(self)
        self._status_log = []

        L.addWidget(self.status_lbl)
        L.addSpacing(8)

        self.setup_btn = _mini_btn("gear", "Pipeline Setup — configure drive, prefix, tasks and folder names")
        L.addWidget(self.setup_btn)

    # ── signals ───────────────────────────────────────────────────────────────
    def _connect_signals(self):
        self.btn_overscan.clicked.connect(lambda: self._run_smart_script(PATH_OVERSCAN))
        self.btn_img_plane.clicked.connect(lambda: self._run_smart_script(PATH_IMAGE_PLANE))
        self.btn_rem_back.clicked.connect(lambda: self._run_smart_script(PATH_REMOVE_BACK))
        self.btn_textures.clicked.connect(lambda: self._run_smart_script(PATH_TEXTURES))
        self.btn_bake_cam.clicked.connect(lambda: self._run_smart_script(PATH_BAKE_CAM))
        self.btn_library.clicked.connect(lambda: self._run_smart_script(PATH_LIBRARY))
        self.btn_snap.clicked.connect(self._capture_viewport)
        self.res_w.valueChanged.connect(self._on_res_w_change)
        self.res_h.valueChanged.connect(self._on_res_h_change)
        self.res_lock_btn.toggled.connect(self._on_lock_toggled)
        self.res_x2_btn.clicked.connect(self._res_multiply_2)
        self.res_d2_btn.clicked.connect(self._res_divide_2)
        self.res_s.clicked.connect(self._manual_save_res)
        self.res_list_act.triggered.connect(self._show_res_menu)
        self.res_d.clicked.connect(self._delete_res_preset)
        self.film_spin.valueChanged.connect(self._on_film_ui_change)
        self.film_spin.editingFinished.connect(self._write_film_to_max)
        self.film_s.clicked.connect(self._manual_save_film)
        self.film_list_act.triggered.connect(self._show_film_menu)
        self.film_d.clicked.connect(self._delete_film_preset)
        self.get_btn.clicked.connect(self._get_pipeline_from_path)
        self.project_cb.currentTextChanged.connect(self._on_project_changed)
        self.sequence_cb.currentTextChanged.connect(self._populate_shots)
        self.shot_cb.currentTextChanged.connect(self._refresh_tasks)
        self.add_btn.clicked.connect(self.show_task_menu)
        self.folder_btn.clicked.connect(self._show_folder_menu)
        self.open_btn.clicked.connect(self.open_scene_dialog)
        self.save_scene_btn.clicked.connect(self.save_scene_dialog)
        self.set_path_btn.clicked.connect(self.set_paths_only)
        self.set_save_btn.clicked.connect(self.set_save_only)
        self.reset_btn.clicked.connect(self.confirm_and_reset_paths)
        self.setup_btn.clicked.connect(self._open_setup)
        self.film_spin.installEventFilter(self)

    # ── status flash ─────────────────────────────────────────────────────────
    def _set_status(self, text, color=None, detail=None):
        """Show the result of the last action. `detail` (e.g. the full path)
        goes into the tooltip and the history (click the status)."""
        color = color or MX_TEXT_DIM
        self._status_log.append((datetime.now().strftime("%H:%M:%S"), text, color, detail or ""))
        del self._status_log[:-25]
        self._status_seq = getattr(self, "_status_seq", 0) + 1
        seq = self._status_seq

        def paint(dot, txt_col):
            self.status_lbl.setText(f'<span style="color:{dot}">●</span>&nbsp;'
                                    f'<span style="color:{txt_col}">{text}</span>')
        paint(color, color)
        self.status_lbl.setToolTip((detail + "\n\n" if detail else "") + "Click for history")
        self.status_lbl.setStyleSheet(f"font-size:{FONT_LABEL}; min-width:110px; background:transparent;")
        # After 2.2 s the text turns gray again; the dot keeps the result color
        QtCore.QTimer.singleShot(2200, lambda: seq == self._status_seq and paint(color, MX_TEXT_DIM))

    # ── tools dropdown menu ───────────────────────────────────────────────────
    @staticmethod
    def _tool_label(fname):
        """STM_CarRig.ms → 'Car Rig'"""
        label = os.path.splitext(fname)[0]
        label = re.sub(r'^STM_', '', label)
        label = re.sub(r'([a-z])([A-Z])', r'\1 \2', label)
        return label.replace('_', ' ').strip()

    @staticmethod
    def _tool_description(path, max_lines=4):
        """Read the script header and return its description for the tooltip.
        Looks for a DESCRIPTION/Description: block, else the first line with text."""
        try:
            raw = open(path, "rb").read(4000)
            try:    head = raw.decode("utf-8")
            except UnicodeDecodeError: head = raw.decode("cp1252", "replace")
        except Exception:
            return ""
        lines = []
        for l in head.splitlines()[:60]:
            l = re.sub(r'^\s*(--|#|/\*|\*/|\*|"""|\'\'\')\s?', '', l).rstrip()
            l = l.replace('*/', '').replace('"""', '').strip()
            if re.fullmatch(r'[=\-─━_*#~ ]*', l): l = ""      # separators
            if re.search(r'-\*-\s*coding', l): l = ""          # .py encoding header
            lines.append(l)
        desc = []
        for i, l in enumerate(lines):
            m = re.match(r'(?i)^description\s*:?\s*(.*)$', l)
            if m:
                if m.group(1): desc.append(m.group(1))
                for nxt in lines[i+1:]:
                    if not nxt or re.match(r'^[A-Z][A-Z /&]{3,}$', nxt): break   # end of block
                    desc.append(nxt)
                    if nxt.endswith(".") or len(desc) >= max_lines: break   # first sentence
                break
        if not desc:
            desc = [next((l for l in lines if l), "")]
        elif not desc[-1].endswith("."):
            desc[-1] += " …"
        return "\n".join(desc)

    def _fill_tools_menu(self, menu, folder):
        """Add the folder's scripts to the menu; each subfolder is a submenu. Returns the count."""
        try:
            entries = sorted(os.listdir(folder), key=str.lower)
        except Exception:
            return 0
        count = 0
        for d in entries:
            sub = os.path.join(folder, d)
            if os.path.isdir(sub) and not d.startswith(("_", ".")):
                sm = menu.addMenu(self._tool_label(d))
                sm.setToolTipsVisible(True)
                n = self._fill_tools_menu(sm, sub)
                if n == 0: menu.removeAction(sm.menuAction())
                count += n
        for f in entries:
            full = os.path.join(folder, f)
            if (os.path.isfile(full) and f.lower().endswith((".ms", ".mse", ".py"))
                    and not f.startswith(("_", "."))):
                act = menu.addAction(self._tool_label(f))
                tip = self._tool_description(full)
                act.setToolTip(f"{tip}\n\n{f}" if tip else f)
                act.triggered.connect(lambda checked=False, p=full: self._run_smart_script(p))
                count += 1
        return count

    def _open_tools_menu(self):
        tools_dir = PATH_TOOLS_DIR
        menu = QtWidgets.QMenu(self)
        menu.setToolTipsVisible(True)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: #2d2d2d; color: {MX_TEXT};
                border: 1px solid #555; font-size: 9pt;
            }}
            QMenu::item {{ padding: 5px 18px 5px 10px; }}
            QMenu::item:selected {{ background-color: #3a3a3a; color: white; }}
            QMenu::item:disabled {{ color: #777; }}
            QMenu::separator {{ height: 1px; background: #444; margin: 2px 0; }}
        """)

        if not os.path.isdir(tools_dir):
            menu.addAction(f"Folder not found: {tools_dir}").setEnabled(False)
        else:
            if self._fill_tools_menu(menu, tools_dir) == 0:
                menu.addAction("No scripts found").setEnabled(False)
            menu.addSeparator()
            act = menu.addAction("Open tools folder…")
            act.setToolTip(tools_dir)
            act.triggered.connect(lambda: os.startfile(tools_dir))

        # Open the menu right below the button
        menu.exec(self.btn_tools_menu.mapToGlobal(
            QtCore.QPoint(0, self.btn_tools_menu.height())))

    # ── current selection / pipeline paths ───────────────────────────────────
    def _sel(self):
        """(project, seq, shot, task) from the dropdowns; shot is the full folder name."""
        idx = self.shot_cb.currentIndex()
        return (self.project_cb.currentText(), self.sequence_cb.currentText(),
                self.shot_cb.itemData(idx) if idx >= 0 else None, self.task_cb.currentText())

    def _shot_dir(self):
        project, seq, shot, _ = self._sel()
        if not all([project, seq, shot]): return None
        return os.path.join(get_pipeline_base(), f"{_cfg()['project_prefix']}{project}", seq, shot)

    def _task_dir(self, sub=None):
        shot_dir, task = self._shot_dir(), self._sel()[3]
        if not shot_dir or not task: return None
        d = os.path.join(shot_dir, "3D", task)
        return os.path.join(d, sub) if sub else d

    def _snapshot_dir(self):
        cfg = _cfg()
        d = self._task_dir(cfg.get("thumb_subfolder", cfg.get("sub_review", "2_review")))
        sub = cfg.get("thumb_subdir", "").strip()
        return os.path.join(d, sub) if d and sub else d

    @staticmethod
    def _open_in_explorer(path):
        try:
            os.startfile(path)
        except Exception as e:
            print(f"[STM] open folder: {e}")

    def _show_folder_menu(self):
        cfg = _cfg()
        m = QtWidgets.QMenu(self)
        entries = [("Shot", self._shot_dir()), ("Task", self._task_dir())]
        entries += [(f"   {sub}", self._task_dir(sub)) for sub in get_subfolders()]
        snap = self._snapshot_dir()
        if snap and snap not in [e[1] for e in entries]:
            entries.append(("   Snapshots", snap))
        for label, path in entries:
            a = m.addAction(label)
            ok = bool(path) and os.path.isdir(path)
            a.setEnabled(ok)
            if path: a.setToolTip(path)
            a.triggered.connect(lambda c=False, p=path: self._open_in_explorer(p))
        m.setToolTipsVisible(True)
        m.exec(self._menu_below(self.folder_btn))

    def _snap_context_menu(self, pos):
        d = self._snapshot_dir()
        m = QtWidgets.QMenu(self)
        a = m.addAction("Open snapshots folder")
        a.setEnabled(bool(d) and os.path.isdir(d))
        a.triggered.connect(lambda: self._open_in_explorer(d))
        m.exec(self.btn_snap.mapToGlobal(pos))

    # ── FPS ──────────────────────────────────────────────────────────────────
    def _show_fps_menu(self):
        m = QtWidgets.QMenu(self)
        try: cur = int(rt.frameRate)
        except Exception: cur = None
        for fps in (24, 25, 30, 48, 50, 60):
            a = m.addAction(f"{fps} fps"); a.setCheckable(True); a.setChecked(fps == cur)
            a.triggered.connect(lambda c=False, f=fps: self._set_fps(f))
        m.exec(self._menu_below(self.fps_lbl))

    def _set_fps(self, fps):
        try:
            rt.frameRate = fps
            self._set_status(f"{fps} fps", "#70aa70")
        except Exception as e:
            self._set_status("FPS Error", "#e06060"); print(f"[STM] fps: {e}")

    # ── OPEN ▾ / SAVE ▾ ──────────────────────────────────────────────────────
    def _fill_open_menu(self):
        m = self._open_menu; m.clear()
        scene_dir = self._task_dir(_cfg()["sub_projects"])
        files = []
        if scene_dir and os.path.isdir(scene_dir):
            files = sorted((f for f in os.listdir(scene_dir) if f.lower().endswith(".max")),
                           key=lambda f: os.path.getmtime(os.path.join(scene_dir, f)), reverse=True)
        if not files:
            m.addAction("No scenes in this task yet").setEnabled(False); return
        self._menu_header(m, "Recent in this task")
        current = str(rt.maxFileName)
        for f in files[:12]:
            full = os.path.join(scene_dir, f)
            when = datetime.fromtimestamp(os.path.getmtime(full)).strftime("%d %b %H:%M")
            a = m.addAction(f"{f}      {when}")
            if f == current: a.setCheckable(True); a.setChecked(True)
            a.triggered.connect(lambda c=False, p=full: self._load_scene(p))

    def _load_scene(self, path):
        try:
            if hasattr(rt, "checkForSave") and rt.checkForSave() is False:
                return                               # the user cancelled "save changes?"
            rt.loadMaxFile(path, useFileUnits=True, quiet=False)
            self._set_status("File loaded", "#70aa70")
        except Exception as e:
            self._set_status("Open Error", "#e06060"); print(f"[STM] open: {e}")

    def _next_scene_path(self):
        """Path of the next version: <task>/<projects>/<shot>_<task>_v###.max"""
        _, _, shot, task = self._sel()
        scene_dir = self._task_dir(_cfg()["sub_projects"])
        if not scene_dir: return None
        task_clean = task.split("_", 1)[-1] if "_" in task else task
        base_name  = f"{shot}_{task_clean}"
        rx = re.compile(r'^' + re.escape(base_name) + r'_v(\d+)\.max$', re.IGNORECASE)
        max_ver = 0
        if os.path.isdir(scene_dir):
            for f in os.listdir(scene_dir):
                mm = rx.match(f)
                if mm: max_ver = max(max_ver, int(mm.group(1)))
        return os.path.join(scene_dir, f"{base_name}_v{max_ver + 1:03d}.max")

    def _fill_save_menu(self):
        m = self._save_menu; m.clear()
        nxt = self._next_scene_path()
        if not nxt:
            m.addAction("Select a task first").setEnabled(False); return
        a = m.addAction(f"Save next version now  →  {os.path.basename(nxt)}")
        a.triggered.connect(self._quick_save_next)

    def _quick_save_next(self):
        nxt = self._next_scene_path()
        if not nxt: return
        try:
            os.makedirs(os.path.dirname(nxt), exist_ok=True)
            rt.saveMaxFile(nxt)
            ver = re.search(r'_v(\d+)\.max$', nxt).group(1)
            self._set_status(f"Saved v{ver}", "#70aa70", nxt)
        except Exception as e:
            self._set_status("Save Error", "#e06060"); print(f"[STM] save: {e}")

    # ── status history ───────────────────────────────────────────────────────
    def _show_status_log(self):
        m = QtWidgets.QMenu(self)
        if not self._status_log:
            m.addAction("No actions yet").setEnabled(False)
        for t, text, col, detail in reversed(self._status_log):
            pm = QtGui.QPixmap(8, 8); pm.fill(QtGui.QColor(col))
            a = m.addAction(QtGui.QIcon(pm), f"{t}   {text}")
            if detail:
                a.setToolTip(f"{detail}\nClick to copy")
                a.triggered.connect(lambda c=False, d=detail: QtWidgets.QApplication.clipboard().setText(d))
        m.setToolTipsVisible(True)
        m.exec(self._menu_below(self.status_lbl))

    # ── GET highlighted when the file is in another shot/task ────────────────
    def _update_get_attention(self):
        try:
            info = self._parse_pipeline_path(rt.maxFilePath) if str(rt.maxFilePath) else None
        except Exception:
            info = None
        want = False
        if info:
            project, seq, shot, task = self._sel()
            here = (info["project"], info["seq"], info["shot"], info["task"] or task)
            want = tuple(str(x or "").lower() for x in here) != \
                   tuple(str(x or "").lower() for x in (project, seq, shot, task))
        if bool(self.get_btn.property("attention")) != want:
            self.get_btn.setProperty("attention", want)
            self.get_btn.style().unpolish(self.get_btn); self.get_btn.style().polish(self.get_btn)
            base = "GET — fills Project / Sequence / Shot / Task from the open file's folder"
            self.get_btn.setToolTip(base + ("\n\n⚠ The open file is in a different shot/task than the dropdowns"
                                            if want else ""))

    # ── script runner ─────────────────────────────────────────────────────────
    def _run_smart_script(self, path):
        if not os.path.exists(path):
            self._set_status("Not found", "#e06060"); return
        ext = os.path.splitext(path)[1].lower()
        try:
            if ext == ".ms":
                rt.fileIn(path); self._set_status("Loaded", "#70aa70")
            elif ext == ".py":
                raw = open(path, "rb").read()
                try:    src = raw.decode("utf-8")
                except UnicodeDecodeError: src = raw.decode("cp1252")
                ctx = {"__name__": "__main__", "__file__": path, "rt": rt, "os": os}
                exec(compile(src, path, "exec"), ctx)
                # Keep the namespace alive: parentless top-level windows
                # (e.g. StudioLibrary: window = ...) would be destroyed by GC
                if not hasattr(self, "_script_ctx"): self._script_ctx = {}
                self._script_ctx[path] = ctx
                self._set_status("Loaded", "#70aa70")
        except Exception as e:
            import traceback
            self._set_status("Error", "#e06060"); print(f"STM Error in {os.path.basename(path)}:")
            traceback.print_exc()

    def eventFilter(self, obj, event):
        if obj is getattr(self, "status_lbl", None) and event.type() == QtCore.QEvent.MouseButtonPress:
            self._show_status_log(); return True
        if obj is self.film_spin:
            if event.type() == QtCore.QEvent.FocusIn:  self.sync_timer.stop()
            elif event.type() == QtCore.QEvent.FocusOut: self.sync_timer.start(500)
        return super().eventFilter(obj, event)

    # ── res ───────────────────────────────────────────────────────────────────
    def _res_set(self, w, h):
        """Apply W and H atomically, always even numbers, no loops."""
        w = w if w % 2 == 0 else w - 1
        h = h if h % 2 == 0 else h - 1
        w = max(2, w); h = max(2, h)
        self._syncing_from_max = True
        self.res_w.blockSignals(True); self.res_h.blockSignals(True)
        self.res_w.setValue(w); self.res_h.setValue(h)
        self.res_w.blockSignals(False); self.res_h.blockSignals(False)
        self._syncing_from_max = False
        if self.res_lock_btn.isChecked():
            self._lock_ratio = w / h if h else 1.0
        self._write_res_to_max()
        self.res_note.setText(self._res_label(w, h))

    def _res_label(self, w, h):
        """Name of the matching saved preset; else the standard one; else empty."""
        m = next((p for p in self.state.get("res_presets", []) if p['w'] == w and p['h'] == h), None)
        if m: return m.get('n', "")
        return next((n for n, bw, bh in BUILTIN_RES if (bw, bh) == (w, h)), "")

    def _film_label(self, v):
        m = next((p for p in self.state.get("film_presets", []) if abs(p['v'] - v) < 0.001), None)
        if m: return m.get('n', "")
        return next((n for n, bv in BUILTIN_FILM if abs(bv - v) < 0.001), "")

    def _update_aspect(self):
        w, h = self.res_w.value(), self.res_h.value()
        txt = f"{w / h:.2f}" if h else "—"
        if self.res_aspect.text() != txt: self.res_aspect.setText(txt)

    def _res_multiply_2(self):
        self._res_set(self.res_w.value() * 2, self.res_h.value() * 2)

    def _res_divide_2(self):
        self._res_set(self.res_w.value() // 2, self.res_h.value() // 2)

    def _on_lock_toggled(self, locked):
        self.res_lock_btn.setIcon(self._ic_lock if locked else self._ic_unlock)
        if locked:
            h = self.res_h.value()
            self._lock_ratio = self.res_w.value() / h if h else 1.0

    def _on_res_w_change(self):
        if self.res_w.signalsBlocked() or getattr(self, '_res_updating', False) or getattr(self, '_syncing_from_max', False): return
        if self.res_lock_btn.isChecked() and getattr(self, '_lock_ratio', None):
            self._res_updating = True
            new_h = max(1, round(self.res_w.value() / self._lock_ratio))
            self.res_h.blockSignals(True)
            self.res_h.setValue(new_h)
            self.res_h.blockSignals(False)
            self._res_updating = False
        self._on_res_ui_change()

    def _on_res_h_change(self):
        if self.res_h.signalsBlocked() or getattr(self, '_res_updating', False) or getattr(self, '_syncing_from_max', False): return
        if self.res_lock_btn.isChecked() and getattr(self, '_lock_ratio', None):
            self._res_updating = True
            new_w = max(1, round(self.res_h.value() * self._lock_ratio))
            self.res_w.blockSignals(True)
            self.res_w.setValue(new_w)
            self.res_w.blockSignals(False)
            self._res_updating = False
        self._on_res_ui_change()

    def _on_res_ui_change(self):
        self._update_aspect()
        if self.res_w.signalsBlocked(): return
        self._write_res_to_max()
        self.res_note.setText(self._res_label(self.res_w.value(), self.res_h.value()))

    def _manual_save_res(self):
        w,h,n = self.res_w.value(), self.res_h.value(), self.res_note.text()
        pl = self.state.get("res_presets",[]); ex = next((p for p in pl if p['w']==w and p['h']==h), None)
        if ex: ex['n']=n
        else: pl.insert(0,{"w":w,"h":h,"n":n})
        self.state["res_presets"] = pl[:30]; save_state({"res_presets": self.state["res_presets"]}); self._set_status("Saved")

    def _delete_res_preset(self):
        w,h = self.res_w.value(), self.res_h.value()
        pl  = self.state.get("res_presets",[])
        match = next((p for p in pl if p['w']==w and p['h']==h), None)
        if not match: return
        label = f"{w} × {h}   {match.get('n','')}"
        if QtWidgets.QMessageBox.question(self, "Delete Preset",
                f"Delete resolution preset:\n{label}?",
                QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel) != QtWidgets.QMessageBox.Ok:
            return
        nl = [p for p in pl if not(p['w']==w and p['h']==h)]
        self.state["res_presets"]=nl; save_state({"res_presets":nl})
        self.res_note.clear(); self._set_status("Deleted")

    @staticmethod
    def _menu_header(m, text):
        """Section header in a menu. addSection() depends on the Windows style
        and sometimes skips the text; a disabled action looks the same everywhere."""
        if m.actions(): m.addSeparator()
        a = m.addAction(text.upper()); a.setEnabled(False)
        f = a.font(); f.setPointSizeF(7.5); f.setBold(True); a.setFont(f)
        return a

    def _menu_below(self, widget):
        return widget.mapToGlobal(QtCore.QPoint(0, widget.height()))

    def _show_res_menu(self):
        m = QtWidgets.QMenu(self); presets = self.state.get("res_presets",[])
        cur = (self.res_w.value(), self.res_h.value())
        self._menu_header(m, "Saved")
        if presets:
            for p in presets:
                a = m.addAction(f"{p['w']} × {p['h']}    {p['n']}")
                a.setCheckable(True); a.setChecked((p['w'], p['h']) == cur)
                a.triggered.connect(lambda c=False, x=p: self._apply_res(x))
        else: m.addAction("(none yet — type a label and press Save)").setEnabled(False)
        self._menu_header(m, "Standard")
        for name, w, h in BUILTIN_RES:
            a = m.addAction(f"{w} × {h}    {name}")
            a.setCheckable(True); a.setChecked((w, h) == cur)
            a.triggered.connect(lambda c=False, x={"w": w, "h": h, "n": name}: self._apply_res(x))
        m.exec(self._menu_below(self.res_note))

    def _apply_res(self, p):
        # Block both signals to apply W and H in one go without cascading
        self.res_w.blockSignals(True)
        self.res_h.blockSignals(True)
        self.res_w.setValue(p['w'])
        self.res_h.setValue(p['h'])
        self.res_w.blockSignals(False)
        self.res_h.blockSignals(False)
        self.res_note.setText(p.get('n', ""))
        self._update_aspect()
        # If the lock is on, update the ratio to the new preset
        if self.res_lock_btn.isChecked():
            self._lock_ratio = p['w'] / p['h'] if p['h'] else 1.0
        self._write_res_to_max()

    # ── film ──────────────────────────────────────────────────────────────────
    def _on_film_ui_change(self):
        if self.film_spin.signalsBlocked(): return
        self.film_note.setText(self._film_label(self.film_spin.value()))

    def _manual_save_film(self):
        v,n = self.film_spin.value(), self.film_note.text()
        pl = self.state.get("film_presets",[]); ex = next((p for p in pl if abs(p['v']-v)<0.001), None)
        if ex: ex['n']=n
        else: pl.insert(0,{"v":v,"n":n})
        self.state["film_presets"] = pl[:30]; save_state({"film_presets": self.state["film_presets"]}); self._set_status("Saved")

    def _delete_film_preset(self):
        v  = self.film_spin.value()
        pl = self.state.get("film_presets",[])
        match = next((p for p in pl if abs(p['v']-v)<0.001), None)
        if not match: return
        label = f"{v} mm   {match.get('n','')}"
        if QtWidgets.QMessageBox.question(self, "Delete Preset",
                f"Delete film size preset:\n{label}?",
                QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel) != QtWidgets.QMessageBox.Ok:
            return
        nl = [p for p in pl if abs(p['v']-v)>0.001]
        self.state["film_presets"]=nl; save_state({"film_presets":nl})
        self.film_note.clear(); self._set_status("Deleted")

    def _show_film_menu(self):
        m = QtWidgets.QMenu(self); presets = self.state.get("film_presets",[])
        cur = self.film_spin.value()
        self._menu_header(m, "Saved")
        if presets:
            for p in presets:
                a = m.addAction(f"{p['v']:.2f} mm    {p['n']}")
                a.setCheckable(True); a.setChecked(abs(p['v'] - cur) < 0.001)
                a.triggered.connect(lambda c=False, x=p: self._apply_film(x))
        else: m.addAction("(none yet — type a label and press Save)").setEnabled(False)
        self._menu_header(m, "Camera sensors (width)")
        for name, v in BUILTIN_FILM:
            a = m.addAction(f"{v:.2f} mm    {name}")
            a.setCheckable(True); a.setChecked(abs(v - cur) < 0.001)
            a.triggered.connect(lambda c=False, x={"v": v, "n": name}: self._apply_film(x))
        m.exec(self._menu_below(self.film_note))

    def _apply_film(self, p):
        self.film_spin.setValue(p['v']); self.film_note.setText(p.get('n',"")); self._write_film_to_max()

    # ── pipeline — original logic transplanted 100% ──────────────────────────
    def _on_project_changed(self, project_name):
        """On project change, update the Max root and handle the 3D folder."""
        if not project_name: return
        cfg          = _cfg()
        base         = get_pipeline_base()
        base_project = os.path.join(base, f"{cfg['project_prefix']}{project_name}")
        path_3d      = os.path.join(base_project, "3D")
        if not os.path.exists(path_3d):
            res = QtWidgets.QMessageBox.question(self, "Create Structure",
                f"Folder '3D' not found in {project_name}.\nDo you want to create it?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
            if res == QtWidgets.QMessageBox.Yes:
                os.makedirs(path_3d, exist_ok=True)
        if os.path.exists(path_3d):
            rt.pathConfig.setCurrentProjectFolder(path_3d)
        self._populate_sequences()

    def _populate_projects(self):
        self.project_cb.blockSignals(True)
        self.project_cb.clear()
        cfg          = _cfg()
        prefix       = cfg.get("project_prefix", "VFX-")
        base         = get_pipeline_base()

        # Current project name if one is loaded
        current_project_name = ""
        current_root = get_project_root()
        if current_root:
            parts = current_root.split(os.sep)
            for part in reversed(parts):
                if part.startswith(prefix):
                    current_project_name = part.replace(prefix, "")
                    break

        for d in safe_listdir(base):
            if d.startswith(prefix) and os.path.isdir(os.path.join(base, d)):
                self.project_cb.addItem(d.replace(prefix, ""))

        initial = self.state.get("project", current_project_name)
        if initial: self.project_cb.setCurrentText(initial)
        self.project_cb.blockSignals(False)
        # Fire the chain only once with the final project
        self._on_project_changed(self.project_cb.currentText())

    def _populate_sequences(self):
        self.sequence_cb.blockSignals(True)
        self.sequence_cb.clear()
        project = self.project_cb.currentText()
        cfg     = _cfg()
        if not project:
            self.sequence_cb.blockSignals(False); self._populate_shots(); return
        proj_path = os.path.join(get_pipeline_base(), f"{cfg['project_prefix']}{project}")
        exclude   = get_seq_exclude()
        for d in safe_listdir(proj_path):
            if d.upper() in exclude: continue
            if d and d[0].isdigit() and os.path.isdir(os.path.join(proj_path, d)):
                self.sequence_cb.addItem(d)
        if "sequence" in self.state: self.sequence_cb.setCurrentText(self.state["sequence"])
        self.sequence_cb.blockSignals(False)
        self._populate_shots()

    def _populate_shots(self):
        self.shot_cb.blockSignals(True)
        self.shot_cb.clear()
        project = self.project_cb.currentText()
        seq     = self.sequence_cb.currentText()
        cfg     = _cfg()
        if not all([project, seq]):
            self.shot_cb.blockSignals(False); self._refresh_tasks(); return
        seq_path = os.path.join(get_pipeline_base(), f"{cfg['project_prefix']}{project}", seq)
        for d in safe_listdir(seq_path):
            if os.path.isdir(os.path.join(seq_path, d)) and d.startswith(f"{project}_"):
                self.shot_cb.addItem(d, d)
        if "shot" in self.state:
            for i in range(self.shot_cb.count()):
                if self.state["shot"] == self.shot_cb.itemData(i):
                    self.shot_cb.setCurrentIndex(i); break
        self.shot_cb.blockSignals(False)
        self._refresh_tasks()

    def _refresh_tasks(self):
        self.task_cb.clear()
        project   = self.project_cb.currentText()
        seq       = self.sequence_cb.currentText()
        idx       = self.shot_cb.currentIndex()
        shot_full = self.shot_cb.itemData(idx) if idx >= 0 else None
        cfg       = _cfg()
        if project and seq and shot_full:
            base3d = os.path.join(get_pipeline_base(), f"{cfg['project_prefix']}{project}", seq, shot_full, "3D")
            if os.path.isdir(base3d):
                self.task_cb.addItems([d for d in safe_listdir(base3d) if os.path.isdir(os.path.join(base3d, d))])
        if "task" in self.state and self.task_cb.count() > 0:
            self.task_cb.setCurrentText(self.state["task"])

    @staticmethod
    def _parse_pipeline_path(folder):
        """...\\VFX-XXX\\seq\\shot\\3D\\task\\... → dict(project, seq, shot, task) or None."""
        prefix = _cfg()["project_prefix"]
        parts  = [p for p in str(folder).replace("/", "\\").split("\\") if p]
        idx = next((i for i, p in enumerate(parts) if p.startswith(prefix)), None)
        if idx is None or len(parts) <= idx + 2: return None
        return {
            "project": parts[idx][len(prefix):],
            "seq":     parts[idx + 1],
            "shot":    parts[idx + 2],
            # Windows is case-insensitive: "3D" == "3d"
            "task":    parts[idx + 4] if len(parts) > idx + 4 and parts[idx + 3].lower() == "3d" else "",
        }

    def _get_pipeline_from_path(self):
        """GET: read rt.maxFilePath and set the 4 dropdowns."""
        try:
            info = self._parse_pipeline_path(rt.maxFilePath)
            if info is None: return
            project, seq, shot, task = info["project"], info["seq"], info["shot"], info["task"]
            if self.project_cb.findText(project) < 0:
                self._set_status("Project not listed", "#e06060"); return
            self.project_cb.setCurrentText(project)
            self.sequence_cb.setCurrentText(seq)
            for i in range(self.shot_cb.count()):
                if shot == self.shot_cb.itemData(i):
                    self.shot_cb.setCurrentIndex(i); break
            if task: self.task_cb.setCurrentText(task)
            self._set_status("GET OK", "#70aa70")
        except Exception as e:
            self._set_status("GET Error", "#e06060")
            print(f"STM GET error: {e}")

    # ── project paths ─────────────────────────────────────────────────────────
    # Max does NOT store Project Paths inside the .max (they belong to the session / .mxp).
    # Set Paths also stores them in the rootNode AppData, and on file open
    # (_on_file_opened) they are re-applied. Only affects files where Set Paths was used.
    _PATH_KEYS = ("scene", "image", "preview", "renderoutput", "import", "export")

    @staticmethod
    def _apply_path_dirs(dirs):
        for key in StudioToolbar._PATH_KEYS:
            if key in dirs:
                try: rt.pathConfig.setDir(rt.name(key), dirs[key])
                except Exception as e: print(f"[STM Paths] {key}: {e}")

    def set_paths_only(self):
        try:
            project = self.project_cb.currentText()
            seq     = self.sequence_cb.currentText()
            idx     = self.shot_cb.currentIndex()
            shot    = self.shot_cb.itemData(idx) if idx >= 0 else None
            task    = self.task_cb.currentText()
            if not all([project, seq, shot, task]): return
            cfg     = _cfg()
            sub_p   = cfg["sub_projects"]
            sub_r   = cfg["sub_review"]
            sub_pub = cfg["sub_publish"]
            task_rel = f"..\\{seq}\\{shot}\\3D\\{task}"
            dirs = {
                "scene":        f"{task_rel}\\{sub_p}",
                "image":        f"{task_rel}\\{sub_p}\\textures",
                "preview":      f"{task_rel}\\{sub_r}",
                "renderoutput": f"{task_rel}\\{sub_pub}",
                "export":       f"{task_rel}\\{sub_pub}",   # export → publish (same as render)
            }
            # import path — only if the task has an "import" folder
            if "import" in get_task_projects_subs(task):
                dirs["import"] = f"{task_rel}\\{sub_p}\\import"
            self._apply_path_dirs(dirs)

            # Store inside the .max to restore them when the file is reopened
            project_folder = os.path.join(get_pipeline_base(), f"{cfg['project_prefix']}{project}", "3D")
            try:
                rt.setAppData(rt.rootNode, STM_APPDATA_PATHS, json.dumps({
                    "project": project, "seq": seq, "shot": shot, "task": task,
                    "project_folder": project_folder, "dirs": dirs}))
            except Exception as e:
                print(f"[STM Paths] store in file: {e}")

            save_state({"project": project, "sequence": seq, "shot": shot, "task": task})
            self._set_status("Paths set", "#70aa70", self._task_dir())
        except Exception as e:
            self._set_status("PATH Error", "#e06060"); print(e)

    def _restore_paths_from_file(self):
        """If the open .max has paths stored by Set Paths, re-apply them.
        Only if the file is still in the same project/seq/shot/task they were saved for:
        if it was copied or Saved As to another shot, they are ignored.
        Returns "restored", "skipped" or None (no stored paths)."""
        try:
            raw = rt.getAppData(rt.rootNode, STM_APPDATA_PATHS)
            if not raw: return None
            data = json.loads(str(raw))

            stored = {k: data.get(k) for k in ("project", "seq", "shot", "task")}
            if not all(stored.values()):
                # v2.5.39 marker (no shot/task): infer them from the stored scene path
                rel = data.get("dirs", {}).get("scene", "")
                bits = [b for b in rel.split("\\") if b and b != ".."]
                pf_bits = [b for b in data.get("project_folder", "").replace("/", "\\").split("\\") if b]
                proj = pf_bits[-2] if len(pf_bits) >= 2 else ""      # T:\VFX-MOR\3D → VFX-MOR
                prefix = _cfg()["project_prefix"]
                if len(bits) >= 4 and bits[2].lower() == "3d" and proj.startswith(prefix):
                    stored = {"project": proj[len(prefix):], "seq": bits[0],
                              "shot": bits[1], "task": bits[3]}
            here = self._parse_pipeline_path(rt.maxFilePath) or {}
            # project/seq/shot must always match; task only if the file
            # is inside a task folder. Case-insensitive comparison (Windows).
            keys = ["project", "seq", "shot"] + (["task"] if here.get("task") else [])
            same = lambda k: str(stored.get(k) or "").lower() == str(here.get(k) or "").lower()
            if not here or not all(same(k) for k in keys):
                print(f"[STM Paths] skipped — saved for {stored}, file is in {here or 'a non-pipeline folder'}")
                return "skipped"

            proj = data.get("project_folder", "")
            if proj and os.path.isdir(proj):
                rt.pathConfig.setCurrentProjectFolder(proj)
            self._apply_path_dirs(data.get("dirs", {}))
            return "restored"
        except Exception as e:
            print(f"[STM Paths] restore: {e}")
            return None

    def _on_file_opened(self):
        """filePostOpen callback: GET the dropdowns + restore paths stored in the file."""
        self._get_pipeline_from_path()
        result = self._restore_paths_from_file()
        if result == "restored":
            self._set_status("Paths restored", "#70aa70")
        elif result == "skipped":
            self._set_status("Paths skipped", "#d4a017")

    def set_save_only(self):
        try:
            project = self.project_cb.currentText()
            seq     = self.sequence_cb.currentText()
            idx     = self.shot_cb.currentIndex()
            shot    = self.shot_cb.itemData(idx) if idx >= 0 else None
            task    = self.task_cb.currentText()
            if not all([project, seq, shot, task]): return
            cfg          = _cfg()
            publish_base = os.path.join(get_pipeline_base(), f"{cfg['project_prefix']}{project}",
                                        seq, shot, "3D", task, cfg["sub_publish"])
            task_clean  = task.split("_", 1)[-1] if "_" in task else task
            current_max = str(rt.maxFileName)
            raw_name    = os.path.splitext(current_max)[0] if current_max else ""

            # Base name without _vXXX: dropdowns (SHOT NAME) or the open Max file
            if self.shotname_chk.isChecked() or not raw_name:
                prefix = f"{shot}_{task_clean}"
            else:
                m = re.match(r'^(.+?)(_v\d+)?$', raw_name)
                prefix = m.group(1) if m else raw_name

            # Version: always the one from the open Max file
            mv_file = re.search(r'_v(\d+)$', raw_name)
            file_ver, pad = (int(mv_file.group(1)), len(mv_file.group(1))) if mv_file else (1, 3)
            folder_name = f"{prefix}_v{file_ver:0{pad}d}"

            # If that version already has renders, ask instead of silently overwriting
            target = os.path.join(publish_base, folder_name)
            if os.path.isdir(target) and any(os.scandir(target)):
                box = QtWidgets.QMessageBox(self)
                box.setWindowTitle("Set Render")
                box.setText(f"{folder_name} already has renders.")
                box.setInformativeText("Overwrite them, or render to the next free version?")
                b_over = box.addButton("Overwrite", QtWidgets.QMessageBox.DestructiveRole)
                b_new  = box.addButton("New version", QtWidgets.QMessageBox.AcceptRole)
                box.addButton(QtWidgets.QMessageBox.Cancel)
                box.setDefaultButton(b_new)
                box.exec()
                if box.clickedButton() is b_new:
                    rx = re.compile(r'^' + re.escape(prefix) + r'_v(\d+)$', re.IGNORECASE)
                    used = [int(m.group(1)) for d in os.listdir(publish_base) if (m := rx.match(d))]
                    folder_name = f"{prefix}_v{max(used + [file_ver]) + 1:0{pad}d}"
                elif box.clickedButton() is not b_over:
                    self._set_status("Cancelled"); return

            pub_dir  = os.path.join(publish_base, folder_name)
            exr_name = f"{folder_name}{cfg.get('render_sep', '_')}.exr"
            os.makedirs(pub_dir, exist_ok=True)
            rt.rendSaveFile       = True
            rt.rendOutputFilename = os.path.join(pub_dir, exr_name)
            extra = self._set_renderer_outputs(pub_dir, folder_name, cfg.get('render_sep', '_'))
            self._set_status("Render set" + (f" +{extra}" if extra else ""), "#70aa70",
                             os.path.join(pub_dir, exr_name))
        except Exception as e:
            self._set_status("SET RENDER Error", "#e06060"); print(e)

    def _set_renderer_outputs(self, pub_dir, base, sep):
        """Point the outputs the renderer writes on its own to publish.
        Only updates paths of outputs ALREADY enabled — never turns anything on.
        Returns how many extra outputs were updated (for the status)."""
        done = []
        r = rt.renderers.current
        rclass = str(rt.classOf(r)).lower()

        # Max Render Elements (V-Ray, Corona, Scanline, Arnold legacy…)
        try:
            mgr = rt.maxOps.GetCurRenderElementMgr()
            for i in range(mgr.NumRenderElements()):
                el = mgr.GetRenderElement(i)
                if not el.enabled: continue
                el_name = re.sub(r'[\\/:*?"<>|\s]+', '_', str(el.elementName)).strip("_")
                mgr.SetRenderElementFilename(i, os.path.join(pub_dir, f"{base}_{el_name}{sep}.exr"))
                done.append(f"elem:{el_name}")
        except Exception as e:
            print(f"[STM Render] elements: {e}")

        # V-Ray VFB: Raw image file and Separate render channels
        if "v_ray" in rclass or "vray" in rclass:
            try:
                if getattr(r, "output_saveRawFile", False):
                    r.output_rawFileName = os.path.join(pub_dir, f"{base}{sep}.exr")
                    done.append("vray:raw")
                if getattr(r, "output_splitgbuffer", False):
                    r.output_splitfilename = os.path.join(pub_dir, f"{base}{sep}.exr")
                    done.append("vray:split")
            except Exception as e:
                print(f"[STM Render] V-Ray: {e}")

        # Arnold: AOV Manager output folder
        if "arnold" in rclass:
            try:
                aov = r.AOVManager
                if aov is not None and hasattr(aov, "outputPath"):
                    aov.outputPath = pub_dir
                    done.append("arnold:aov")
            except Exception as e:
                print(f"[STM Render] Arnold: {e}")

        if done: print(f"[STM Render] {rclass} → {pub_dir}  ({', '.join(done)})")
        return len(done)

    def open_scene_dialog(self):
        project  = self.project_cb.currentText()
        seq      = self.sequence_cb.currentText()
        idx      = self.shot_cb.currentIndex()
        shot     = self.shot_cb.itemData(idx) if idx >= 0 else None
        task     = self.task_cb.currentText()
        if not all([project, seq, shot, task]):
            self._set_status("Select Task first", "#e06060"); return
        cfg       = _cfg()
        root      = get_project_root()
        scene_dir = os.path.join(get_pipeline_base(), f"{cfg['project_prefix']}{project}",
                                 seq, shot, "3D", task, cfg["sub_projects"]).replace("\\", "/")
        if not os.path.exists(scene_dir):
            QtWidgets.QMessageBox.warning(self, "Path Error", f"Folder not found:\n{scene_dir}"); return
        f = rt.getOpenFileName(caption="Open Max Scene", filename=scene_dir + "/", types="3ds Max(*.max)|*.max")
        if f:
            self._load_scene(f)

    def save_scene_dialog(self):
        """Open the Max Save dialog in the task folder with the versioned name ready."""
        project = self.project_cb.currentText()
        seq     = self.sequence_cb.currentText()
        idx     = self.shot_cb.currentIndex()
        shot    = self.shot_cb.itemData(idx) if idx >= 0 else None
        task    = self.task_cb.currentText()
        if not all([project, seq, shot, task]):
            self._set_status("Select Task first", "#e06060"); return
        cfg       = _cfg()
        scene_dir = os.path.join(get_pipeline_base(), f"{cfg['project_prefix']}{project}",
                                 seq, shot, "3D", task, cfg["sub_projects"])
        os.makedirs(scene_dir, exist_ok=True)
        # Compute versioned name: find the latest existing _vXXX
        task_clean = task.split("_", 1)[-1] if "_" in task else task
        base_name  = f"{shot}_{task_clean}"
        rx         = re.compile(r'^' + re.escape(base_name) + r'_v(\d+)\.max$', re.IGNORECASE)
        max_ver    = 0
        for f in os.listdir(scene_dir):
            m = rx.match(f)
            if m: max_ver = max(max_ver, int(m.group(1)))
        next_ver   = max_ver + 1
        filename   = f"{base_name}_v{next_ver:03d}.max"
        full_path  = os.path.join(scene_dir, filename).replace(os.sep, "/")
        # Open the Max Save dialog with the name ready — the user clicks Save
        f = rt.getSaveFileName(
            caption="Save Max Scene",
            filename=full_path,
            types="3ds Max(*.max)|*.max"
        )
        if f:
            rt.saveMaxFile(f)
            self._set_status("Saved", "#70aa70", f)

    def show_task_menu(self):
        project  = self.project_cb.currentText()
        seq      = self.sequence_cb.currentText()
        idx      = self.shot_cb.currentIndex()
        shot     = self.shot_cb.itemData(idx) if idx >= 0 else None
        if not all([project, seq, shot]): return
        cfg       = _cfg()
        root      = get_project_root()
        base_path = os.path.join(get_pipeline_base(), f"{cfg['project_prefix']}{project}", seq, shot, "3D")
        os.makedirs(base_path, exist_ok=True)
        existing  = safe_listdir(base_path)
        menu      = QtWidgets.QMenu(self)
        for t in get_tasks_template():
            if t not in existing:
                act = menu.addAction(t)
                act.triggered.connect(lambda checked=False, tt=t, bp=base_path: self._create_task_folder(bp, tt))
        menu.exec(QtGui.QCursor.pos())

    def _create_task_folder(self, base_path, task):
        task_path    = os.path.join(base_path, task)
        subs         = get_subfolders()
        proj_sub     = subs[0] if subs else "1_projects"
        proj_subs    = get_task_projects_subs(task)

        # Create subfolders inside projects/ for this specific task
        for ps in proj_subs:
            os.makedirs(os.path.join(task_path, proj_sub, ps), exist_ok=True)
        # If there were none, still create the projects/ folder
        if not proj_subs:
            os.makedirs(os.path.join(task_path, proj_sub), exist_ok=True)

        # Create the other subfolders (review, publish, extras)
        for sub in subs[1:]:
            os.makedirs(os.path.join(task_path, sub), exist_ok=True)

        self._refresh_tasks()
        self.task_cb.setCurrentText(task)

    def confirm_and_reset_paths(self):
        if QtWidgets.QMessageBox.warning(self, "Reset Paths",
                "Reset all project paths back to 3ds Max defaults?",
                QtWidgets.QMessageBox.Ok|QtWidgets.QMessageBox.Cancel) == QtWidgets.QMessageBox.Ok:
            rt.pathConfig.setDir(rt.name('scene'),        ".\\scenes")
            rt.pathConfig.setDir(rt.name('image'),        ".\\sceneassets\\images")
            rt.pathConfig.setDir(rt.name('preview'),      ".\\previews")
            rt.pathConfig.setDir(rt.name('renderoutput'), ".\\renderoutput")
            try: rt.pathConfig.setDir(rt.name('import'), ".\\import")
            except: pass
            try: rt.pathConfig.setDir(rt.name('export'), ".\\export")
            except: pass
            rt.rendOutputFilename = ""; rt.rendSaveFile = False
            try: rt.deleteAppData(rt.rootNode, STM_APPDATA_PATHS)   # the file stops restoring paths
            except: pass
            self._set_status("Reset")

    def _write_res_to_max(self):
        rt.renderWidth, rt.renderHeight = self.res_w.value(), self.res_h.value()

    def _write_film_to_max(self):
        val = self.film_spin.value()
        try:
            if   self._current_source == "Standard": rt.SetRendApertureWidth(val)
            elif self._current_source == "VRayCam" and self._current_obj: self._current_obj.film_width    = val
            elif self._current_source == "PhysCam" and self._current_obj: self._current_obj.film_width_mm = val
        except: pass

    def _master_sync(self):
        try:
            if not self.res_w.hasFocus() and not self.res_h.hasFocus():
                mw, mh = int(rt.renderWidth), int(rt.renderHeight)
                if self.res_w.value() != mw or self.res_h.value() != mh:
                    self._syncing_from_max = True
                    self.res_w.blockSignals(True); self.res_h.blockSignals(True)
                    self.res_w.setValue(mw); self.res_h.setValue(mh)
                    self.res_w.blockSignals(False); self.res_h.blockSignals(False)
                    self._syncing_from_max = False
                    # Update only the note, without writing back to Max
                    self.res_note.setText(self._res_label(mw, mh))
            self._update_aspect()
            self._update_get_attention()
            val,source,color = None,"Standard", MX_TEXT_DIM
            sel = rt.selection
            if len(sel)==1:
                obj = sel[0]
                if   hasattr(obj,'film_width') and not hasattr(obj,'film_width_mm'):
                    val,source,color = obj.film_width,    "VRayCam", "#d4a017"
                elif hasattr(obj,'film_width_mm'):
                    val,source,color = obj.film_width_mm, "PhysCam", "#4ec9c9"
            if val is None: val = rt.GetRendApertureWidth()
            if val is not None and not self.film_spin.hasFocus():
                if abs(self.film_spin.value()-float(val))>0.001:
                    self.film_spin.blockSignals(True); self.film_spin.setValue(float(val)); self.film_spin.blockSignals(False)
                    self._on_film_ui_change()
            self.film_lbl.setText(f"FILM ({source})")
            self.film_lbl.setStyleSheet(f"color:{color}; font-size:{FONT_LABEL}; font-weight:bold; background:transparent;")
            self._current_source = source
            self._current_obj    = sel[0] if len(sel)==1 else None
            # FPS — read-only from rt.frameRate
            try:
                fps = rt.frameRate
                fps_str = str(int(fps)) if fps == int(fps) else f"{fps:.2f}"
                self.fps_lbl.setText(f"{fps_str} FPS")
            except: self.fps_lbl.setText("— FPS")
            try:
                # rt.units.SystemType returns a Name such as #centimeters, #meters, etc.
                unit_name = str(rt.units.SystemType)   # e.g. "#centimeters"
                unit_clean = unit_name.lstrip("#").capitalize()
                self.unit_lbl.setText(f"({unit_clean})")
            except: self.unit_lbl.setText("—")
            # Two-way project folder sync — if Max changes the folder, update the dropdown
            try:
                cur_root = get_project_root()
                if cur_root:
                    cfg    = _cfg()
                    prefix = cfg.get("project_prefix", "VFX-")
                    parts  = cur_root.split(os.sep)
                    for part in reversed(parts):
                        if part.startswith(prefix):
                            proj_name = part.replace(prefix, "")
                            if proj_name and self.project_cb.currentText() != proj_name:
                                idx = self.project_cb.findText(proj_name)
                                if idx >= 0:
                                    self.project_cb.blockSignals(True)
                                    self.project_cb.setCurrentIndex(idx)
                                    self.project_cb.blockSignals(False)
                                    self._populate_sequences()
                            break
            except: pass
        except: pass

    def _sync_vp_color_btn(self):
        """Read the real viewport color and update the BG button."""
        try:
            hex_c = _get_current_vp_hex()
            if hex_c not in ("#ffffff", "#000000"):
                self.btn_vp_color.set_color(hex_c)
        except: pass

    def _open_setup(self):
        dlg = PipelineSetupDialog(parent=self)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            self._populate_projects()
            self._set_status("Config saved", "#70aa70")

    def _capture_viewport(self):
        """Capture the active viewport and save it to the active task's configured folder."""
        try:
            project = self.project_cb.currentText()
            seq     = self.sequence_cb.currentText()
            idx     = self.shot_cb.currentIndex()
            shot    = self.shot_cb.itemData(idx) if idx >= 0 else None
            task    = self.task_cb.currentText()

            if not all([project, seq, shot, task]):
                self._set_status("Select Task first", "#e06060")
                return

            cfg         = _cfg()
            root        = get_project_root()
            thumb_sub   = cfg.get("thumb_subfolder", cfg.get("sub_review", "2_review"))
            thumb_subdir = cfg.get("thumb_subdir", "").strip()
            thumb_dir   = os.path.join(get_pipeline_base(),
                                       f"{cfg['project_prefix']}{project}",
                                       seq, shot, "3D", task, thumb_sub)
            if thumb_subdir:
                thumb_dir = os.path.join(thumb_dir, thumb_subdir)
            os.makedirs(thumb_dir, exist_ok=True)

            # ── Name: configurable parts + incremental vNNN ──────────────────
            max_name   = os.path.splitext(str(rt.maxFileName))[0] if str(rt.maxFileName) else shot
            task_clean = task.split("_", 1)[-1] if "_" in task else task

            # Config flags
            def _bool(v, default):
                if isinstance(v, bool): return v
                return str(v).lower() != "false" if default else str(v).lower() == "true"

            inc_maxfile = _bool(cfg.get("snap_inc_maxfile", True),  True)
            inc_shot    = _bool(cfg.get("snap_inc_shot",    False), False)
            inc_task    = _bool(cfg.get("snap_inc_task",    False), False)
            inc_camera  = _bool(cfg.get("snap_inc_camera",  True),  True)

            # Get camera/view name
            view_name = "viewport"
            if inc_camera:
                try:
                    cam_obj = rt.viewport.getCamera()
                    if cam_obj is not None and str(cam_obj) != "undefined":
                        view_name = str(cam_obj.name)
                    else:
                        vtype = str(rt.viewport.getType())
                        _vmap = {
                            "view_persp_user": "persp", "view_persp": "persp",
                            "view_top": "top", "view_bottom": "bottom",
                            "view_front": "front", "view_back": "back",
                            "view_left": "left", "view_right": "right",
                            "view_ortho": "ortho", "view_iso_user": "iso",
                        }
                        vkey = vtype.lstrip("#").lower()
                        view_name = _vmap.get(vkey, vkey.replace("view_", ""))
                except: pass
                view_name = re.sub(r'[\\/:*?"<>|\[\]\(\)@\s]+', '_', view_name).strip("_")

            # Assemble the name parts
            parts = []
            if inc_maxfile: parts.append(max_name)
            if inc_shot:    parts.append(shot)
            if inc_task:    parts.append(task_clean)
            if inc_camera:  parts.append(view_name)
            if not parts:   parts.append("snapshot")

            base = "_".join(parts)

            # Find the highest existing vNNN for this base in the target folder
            rx    = re.compile(r'^' + re.escape(base) + r'_v(\d+)\.jpg$', re.IGNORECASE)
            max_v = 0
            for f in (os.listdir(thumb_dir) if os.path.isdir(thumb_dir) else []):
                m = rx.match(f)
                if m: max_v = max(max_v, int(m.group(1)))
            version  = max_v + 1
            filename = f"{base}_v{version:03d}.jpg"
            out_path = os.path.join(thumb_dir, filename)

            ok = capture_viewport_to_file(out_path)

            if ok and os.path.exists(out_path):
                self._set_status("Snap OK", "#70aa70", out_path)
                print(f"[Snap] {out_path}")
            else:
                self._set_status("Snap failed", "#e06060")

        except Exception as e:
            self._set_status("Snap error", "#e06060")
            print(f"STM Snap error: {e}")

    def cleanup(self):
        """Stop polling and remove the Max callback. Called when the dock closes;
        without this the timer kept running with the toolbar closed and the
        filePostOpen callback pointed at a dead widget."""
        try: self.sync_timer.stop()
        except: pass
        try: rt.callbacks.removeScripts(id=rt.Name("STM_Sync"))
        except: pass
        try: rt.STM_GlobalRefresh = None
        except: pass

    def _load_current_max_settings(self):
        """Only syncs res/film/fps/unit — does NOT touch the pipeline."""
        try: self._master_sync()
        except: pass


# ── Pipeline Setup Dialog ─────────────────────────────────────────────────────
class PipelineSetupDialog(QtWidgets.QDialog):
    """
    Pipeline setup dialog.
    - Saves active config to  ~/.studio-toolbar/pipeline_config.ini
    - Saves presets to        ~/.studio-toolbar/pipeline_presets.json
    """

    PRESETS_PATH = os.path.join(PIPE_DIR, "pipeline_presets.json")

    DIALOG_STYLE = f"""
        QDialog {{ background-color: #2b2b2b; color: {MX_TEXT}; font-family: "Segoe UI", "Tahoma", sans-serif; font-size: 9pt; }}
        QWidget#page, QWidget#footer {{ background: transparent; }}
        QLabel {{ color: #9a9a9a; font-size: 8.5pt; background: transparent; }}
        QLabel#page_title {{ color: #e6e6e6; font-size: 13pt; font-weight: 600; }}
        QLabel#page_sub   {{ color: #8a8a8a; font-size: 8.5pt; }}
        QLabel#field_lbl  {{ color: #b0b0b0; font-size: 8.5pt; }}
        QLabel#hint       {{ color: #6f6f6f; font-size: 8pt; }}
        QLabel#card_title {{ color: #c8c8c8; font-size: 9pt; font-weight: 600; }}
        QLabel#tree {{
            background: #1f1f1f; border: 1px solid #3c3c3c; border-radius: 4px;
            color: #b8b8b8; font-family: "Consolas", "Cascadia Mono", monospace; font-size: 8.5pt; padding: 10px 12px;
        }}
        QLabel#preview {{ color: #7fb6c9; font-family: "Consolas", monospace; font-size: 8.5pt; }}
        QFrame#card {{ background: #313131; border: 1px solid #3d3d3d; border-radius: 5px; }}

        QListWidget#nav {{
            background: #242424; border: none; border-right: 1px solid #3a3a3a; outline: none;
            font-size: 9.5pt; padding-top: 10px;
        }}
        QListWidget#nav::item {{ color: #a8a8a8; padding: 9px 16px; border-left: 3px solid transparent; }}
        QListWidget#nav::item:hover {{ background: #2e2e2e; color: #dddddd; }}
        QListWidget#nav::item:selected {{ background: #333a3e; color: #ffffff; border-left: 3px solid #4ec9c9; }}

        QLineEdit, QListWidget, QComboBox {{
            background-color: #1f1f1f; color: {MX_TEXT}; border: 1px solid #4a4a4a; border-radius: 3px;
            padding: 4px 7px; font-size: 9pt; selection-background-color: #3f6f80;
        }}
        QListWidget {{ padding: 3px; }}
        QListWidget::item {{ padding: 4px 6px; border-radius: 2px; }}
        QListWidget::item:selected {{ background: #3a5560; color: #ffffff; }}
        QListWidget::item:hover {{ background: #2a2a2a; }}
        QLineEdit:focus, QListWidget:focus, QComboBox:focus {{ border-color: #4ec9c9; }}
        QComboBox::drop-down {{ border: none; width: 20px; }}
        QComboBox::down-arrow {{ image: url({_icon_url("arrow_down")}); width: 11px; height: 11px; margin-right: 4px; }}
        QComboBox QAbstractItemView {{ background-color: #1f1f1f; color: {MX_TEXT}; border: 1px solid #4a4a4a;
                                       selection-background-color: #3a5560; outline: none; }}
        QCheckBox {{ color: #c8c8c8; spacing: 6px; }}
        QCheckBox::indicator {{ width: 14px; height: 14px; background: #1f1f1f; border: 1px solid #555; border-radius: 3px; }}
        QCheckBox::indicator:checked {{ background: #3f8a9a; border-color: #4ec9c9; }}

        QPushButton {{
            background-color: #3a3a3a; color: {MX_TEXT}; border: 1px solid #505050; border-radius: 3px;
            padding: 5px 14px; font-size: 9pt;
        }}
        QPushButton:hover {{ background-color: #474747; border-color: #6a6a6a; }}
        QPushButton:pressed {{ background-color: #252525; }}
        QPushButton#ok_btn {{ background-color: #2f5560; color: #ffffff; border-color: #4ec9c9; font-weight: 600; padding: 6px 20px; }}
        QPushButton#ok_btn:hover {{ background-color: #386673; }}
        QPushButton#flat_btn {{ background: transparent; border-color: transparent; color: #a8a8a8; }}
        QPushButton#flat_btn:hover {{ background: #3a3a3a; border-color: #505050; color: #e0e0e0; }}
        QToolButton#mini_btn, QToolButton#mini_del {{
            background-color: #3a3a3a; border: 1px solid #505050; border-radius: 3px; padding: 0;
        }}
        QToolButton#mini_btn:hover {{ background-color: #484848; border-color: #6a6a6a; }}
        QToolButton#mini_del:hover {{ background-color: #583030; border-color: #884444; }}
        QWidget#footer {{ border-top: 1px solid #3a3a3a; }}
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Pipeline Setup  —  Studio Toolbar for MAX  v{VERSION}")
        self.setMinimumWidth(560)
        self.setStyleSheet(self.DIALOG_STYLE)
        self.cfg = load_pipeline_cfg()
        self._build()
        # Install an event filter on every QLineEdit in the dialog
        # so Enter doesn't close or reset the dialog
        for child in self.findChildren(QtWidgets.QLineEdit):
            child.installEventFilter(self)

    def eventFilter(self, obj, event):
        """Swallow Enter/Return in QLineEdit — don't propagate to the dialog."""
        if isinstance(obj, QtWidgets.QLineEdit):
            if event.type() == QtCore.QEvent.KeyPress:
                if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
                    obj.clearFocus()
                    return True
        return super().eventFilter(obj, event)

    # ── helpers ───────────────────────────────────────────────────────────────
    def _load_presets(self):
        if os.path.exists(self.PRESETS_PATH):
            try:
                with open(self.PRESETS_PATH, "r") as f:
                    return json.load(f)
            except: pass
        return {}

    def _save_presets(self, presets):
        try:
            os.makedirs(PIPE_DIR, exist_ok=True)
            with open(self.PRESETS_PATH, "w") as f:
                json.dump(presets, f, indent=2)
        except: pass

    # Sentinel to tell "never configured" from "configured as empty"
    _PSUB_UNCONFIGURED = object()

    def _on_psub_task_changed(self, task_name):
        """Store the current list in the mapping, load the selected task's list."""
        # Save the previous task's state before switching
        if hasattr(self, '_psub_last_task') and self._psub_last_task:
            items = [self.psub_list.item(i).text().strip()
                     for i in range(self.psub_list.count()) if self.psub_list.item(i).text().strip()]
            # Always save, even an empty list — so we remember everything was deleted
            self._psub_mapping[self._psub_last_task] = items

        self._psub_last_task = task_name
        self.psub_list.clear()

        if task_name in self._psub_mapping:
            # Task already configured — load what it has (may be an empty list)
            for s in self._psub_mapping[task_name]:
                self.psub_list.addItem(s)
        else:
            # Task never touched — load the default and store it in the mapping now
            default = ["textures"]
            self._psub_mapping[task_name] = default
            for s in default:
                self.psub_list.addItem(s)

    def _sync_psub_task_combo(self):
        """Update the tasks combo in the psub section when the task list changes."""
        current = self.psub_task_cb.currentText()
        tasks = [self.task_list.item(i).text().strip()
                 for i in range(self.task_list.count()) if self.task_list.item(i).text().strip()]
        self.psub_task_cb.blockSignals(True)
        self.psub_task_cb.clear()
        for t in tasks: self.psub_task_cb.addItem(t)
        if current in tasks: self.psub_task_cb.setCurrentText(current)
        self.psub_task_cb.blockSignals(False)

    def _current_form_data(self):
        """Collect the current form values as a dict."""
        # Flush current psub task before collecting
        if hasattr(self, '_psub_last_task') and self._psub_last_task:
            items = [self.psub_list.item(i).text().strip()
                     for i in range(self.psub_list.count()) if self.psub_list.item(i).text().strip()]
            # Always save, including an empty list
            self._psub_mapping[self._psub_last_task] = items

        tasks = [self.task_list.item(i).text().strip()
                 for i in range(self.task_list.count()) if self.task_list.item(i).text().strip()]
        subs  = [self.sub_list.item(i).text().strip()
                 for i in range(self.sub_list.count()) if self.sub_list.item(i).text().strip()]
        return {
            "root_drive":          self.ed_drive.text().strip().rstrip("\\"),
            "project_prefix":      self.ed_prefix.text().strip(),
            "seq_exclude":         self.ed_exclude.text().strip(),
            "tasks":               ",".join(tasks),
            "sub_projects":        subs[0] if len(subs) > 0 else "1_projects",
            "sub_review":          subs[1] if len(subs) > 1 else "2_review",
            "sub_publish":         subs[2] if len(subs) > 2 else "3_publish",
            "extra_subs":          ",".join(subs[3:]) if len(subs) > 3 else "",
            "task_projects_subs":  json.dumps(self._psub_mapping) if self._psub_mapping else "",
            "thumb_subfolder":     self.thumb_sub_cb.currentText(),
            "thumb_subdir":        self.ed_thumb_subdir.text().strip(),
            "snap_inc_maxfile":    self.chk_snap_maxfile.isChecked(),
            "snap_inc_shot":       self.chk_snap_shot.isChecked(),
            "snap_inc_task":       self.chk_snap_task.isChecked(),
            "snap_inc_camera":     self.chk_snap_camera.isChecked(),
            "render_sep":          "_" if self.render_sep_cb.currentIndex() == 0 else ".",
        }

    def _apply_cfg_to_form(self, cfg):
        """Load a config dict into all the form widgets."""
        self.ed_drive.setText(cfg.get("root_drive", "T:"))
        self.ed_prefix.setText(cfg.get("project_prefix", "VFX-"))
        self.ed_exclude.setText(cfg.get("seq_exclude", "3D,SOURCE,FOOTAGE"))

        self.task_list.clear()
        tasks = [t.strip() for t in cfg.get("tasks", "").split(",") if t.strip()]
        for t in tasks: self.task_list.addItem(t)
        self._sync_psub_task_combo()

        self.sub_list.clear()
        subs = []
        for key in ["sub_projects", "sub_review", "sub_publish"]:
            v = cfg.get(key, "").strip()
            if v: subs.append(v)
        for v in [v.strip() for v in cfg.get("extra_subs", "").split(",") if v.strip()]:
            subs.append(v)
        for s in subs: self.sub_list.addItem(s)

        # Reload psub mapping
        self._psub_mapping = {}
        raw = cfg.get("task_projects_subs", "")
        if raw:
            try: self._psub_mapping = json.loads(raw)
            except: pass
        self._psub_last_task = None
        if self.psub_task_cb.count() > 0:
            self._on_psub_task_changed(self.psub_task_cb.currentText())

        # Restore thumb subfolder selection
        self._refresh_thumb_sub_combo()
        thumb = cfg.get("thumb_subfolder", "")
        if thumb:
            idx = self.thumb_sub_cb.findText(thumb)
            if idx >= 0: self.thumb_sub_cb.setCurrentIndex(idx)
        self.ed_thumb_subdir.setText(cfg.get("thumb_subdir", ""))
        self.chk_snap_maxfile.setChecked( cfg.get("snap_inc_maxfile", True)  if isinstance(cfg.get("snap_inc_maxfile", True),  bool) else str(cfg.get("snap_inc_maxfile", "true")).lower()  != "false")
        self.chk_snap_shot.setChecked(    cfg.get("snap_inc_shot",    False) if isinstance(cfg.get("snap_inc_shot",    False), bool) else str(cfg.get("snap_inc_shot",    "false")).lower() == "true")
        self.chk_snap_task.setChecked(    cfg.get("snap_inc_task",    False) if isinstance(cfg.get("snap_inc_task",    False), bool) else str(cfg.get("snap_inc_task",    "false")).lower() == "true")
        self.chk_snap_camera.setChecked(  cfg.get("snap_inc_camera",  True)  if isinstance(cfg.get("snap_inc_camera",  True),  bool) else str(cfg.get("snap_inc_camera",  "true")).lower()  != "false")
        self._update_snap_preview()

    # ── build ─────────────────────────────────────────────────────────────────
    # Layout: section sidebar + stacked pages + footer with presets and buttons.
    # Widget names (ed_drive, task_list, sub_list, psub_*, thumb_*, chk_snap_*,
    # render_sep_cb, preset_cb, ed_preset_name) are kept: the save logic is unchanged.

    def _page(self, title, subtitle):
        w = QtWidgets.QWidget(); w.setObjectName("page")
        v = QtWidgets.QVBoxLayout(w); v.setContentsMargins(26, 22, 26, 18); v.setSpacing(12)
        t = QtWidgets.QLabel(title); t.setObjectName("page_title")
        st = QtWidgets.QLabel(subtitle); st.setObjectName("page_sub"); st.setWordWrap(True)
        v.addWidget(t); v.addWidget(st); v.addSpacing(6)
        return w, v

    @staticmethod
    def _card(title=None):
        f = QtWidgets.QFrame(); f.setObjectName("card")
        v = QtWidgets.QVBoxLayout(f); v.setContentsMargins(14, 12, 14, 12); v.setSpacing(8)
        if title:
            t = QtWidgets.QLabel(title); t.setObjectName("card_title"); v.addWidget(t)
        return f, v

    @staticmethod
    def _field(text):
        l = QtWidgets.QLabel(text); l.setObjectName("field_lbl"); return l

    @staticmethod
    def _hint(text):
        l = QtWidgets.QLabel(text); l.setObjectName("hint"); l.setWordWrap(True); return l

    def _list_editor(self, listw, line_edit, placeholder, label):
        """List + [new name][+][delete] row with icons."""
        box = QtWidgets.QVBoxLayout(); box.setSpacing(6)
        listw.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        listw.itemDoubleClicked.connect(self._rename_item)
        box.addWidget(listw, 1)
        row = QtWidgets.QHBoxLayout(); row.setSpacing(4)
        line_edit.setPlaceholderText(placeholder)
        line_edit.setMinimumWidth(130)
        add = _mini_btn("plus", f"Add {label}"); add.setFixedSize(30, 28)
        dele = _mini_btn("trash", f"Delete selected {label}", obj="mini_del"); dele.setFixedSize(30, 28)
        add.clicked.connect(lambda: self._add_item(listw, line_edit))
        line_edit.returnPressed.connect(lambda: self._add_item(listw, line_edit))
        dele.clicked.connect(lambda: self._del_item(listw, label))
        row.addWidget(line_edit, 1); row.addWidget(add); row.addWidget(dele)
        box.addLayout(row)
        return box

    def _build(self):
        outer = QtWidgets.QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)
        body = QtWidgets.QHBoxLayout(); body.setContentsMargins(0, 0, 0, 0); body.setSpacing(0)
        outer.addLayout(body, 1)

        self.nav = QtWidgets.QListWidget(); self.nav.setObjectName("nav"); self.nav.setFixedWidth(170)
        self.pages = QtWidgets.QStackedWidget()
        body.addWidget(self.nav); body.addWidget(self.pages, 1)
        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex)

        subs = []
        for key in ["sub_projects", "sub_review", "sub_publish"]:
            v = self.cfg.get(key, "").strip()
            if v: subs.append(v)
        subs += [v.strip() for v in self.cfg.get("extra_subs", "").split(",") if v.strip()]
        tasks = [t.strip() for t in self.cfg.get("tasks", "").split(",") if t.strip()]

        # ── PAGE 1: PROJECT ──────────────────────────────────────────────────
        pg, v = self._page("Project", "Where your projects live and how the toolbar recognises them.")
        card, c = self._card()
        form = QtWidgets.QGridLayout(); form.setHorizontalSpacing(12); form.setVerticalSpacing(10)
        self.ed_drive  = QtWidgets.QLineEdit(self.cfg.get("root_drive", "T:"))
        self.ed_drive.setToolTip("Root drive or path where projects live  (e.g.  T:  or  //server/projects)")
        browse = QtWidgets.QPushButton("Browse…"); browse.setObjectName("flat_btn")
        browse.clicked.connect(self._browse_root)
        self.ed_prefix = QtWidgets.QLineEdit(self.cfg.get("project_prefix", "VFX-"))
        self.ed_prefix.setToolTip("Prefix that identifies project folders  (e.g.  VFX-  → folders named  VFX-MOR…)")
        self.ed_prefix.setMaximumWidth(160)
        self.ed_exclude = QtWidgets.QLineEdit(self.cfg.get("seq_exclude", "3D,SOURCE,FOOTAGE"))
        self.ed_exclude.setToolTip("e.g.  3D,SOURCE,FOOTAGE,AUDIO,RENDER")
        form.addWidget(self._field("Root path"), 0, 0); form.addWidget(self.ed_drive, 0, 1); form.addWidget(browse, 0, 2)
        form.addWidget(self._field("Project prefix"), 1, 0); form.addWidget(self.ed_prefix, 1, 1, 1, 2, QtCore.Qt.AlignLeft)
        form.addWidget(self._field("Not sequences"), 2, 0); form.addWidget(self.ed_exclude, 2, 1, 1, 2)
        form.addWidget(self._hint("Folders inside a project that should not be listed as sequences — comma-separated, case-insensitive."),
                       3, 1, 1, 2)
        form.setColumnStretch(1, 1)
        c.addLayout(form)
        v.addWidget(card)
        self._proj_preview = QtWidgets.QLabel(); self._proj_preview.setObjectName("preview")
        self._proj_found = QtWidgets.QLabel(); self._proj_found.setWordWrap(True)
        v.addWidget(self._hint("Project folders look like:")); v.addWidget(self._proj_preview)
        v.addSpacing(4); v.addWidget(self._proj_found)
        v.addStretch()
        self._add_page("Project", pg)

        # ── PAGE 2: TASKS ────────────────────────────────────────────────────
        pg, v = self._page("Tasks",
            "Department folders created with the  +  button. Select a task to choose the subfolders "
            "created inside its scenes folder.")
        row = QtWidgets.QHBoxLayout(); row.setSpacing(14)
        card, c = self._card("Task folders")
        self.task_list = QtWidgets.QListWidget()
        for t in tasks: self.task_list.addItem(t)
        self.ed_new_task = QtWidgets.QLineEdit()
        c.addLayout(self._list_editor(self.task_list, self.ed_new_task, "new task…", "task"), 1)
        c.addWidget(self._hint("Drag to reorder · double-click to rename"))
        row.addWidget(card, 1)

        card, c = self._card()
        self._psub_title = QtWidgets.QLabel(); self._psub_title.setObjectName("card_title")
        c.addWidget(self._psub_title)
        # hidden combo: driven by the task list selection (used by the psub logic)
        self.psub_task_cb = QtWidgets.QComboBox(); self.psub_task_cb.setVisible(False)
        for t in tasks: self.psub_task_cb.addItem(t)
        self.psub_list = QtWidgets.QListWidget()
        self.psub_list.setToolTip("Subfolders to create inside this task's scenes folder")
        self.ed_new_psub = QtWidgets.QLineEdit()
        c.addLayout(self._list_editor(self.psub_list, self.ed_new_psub, "new subfolder…", "subfolder"), 1)
        c.addWidget(self._hint("Tasks you never touch get  textures/  by default."))
        row.addWidget(card, 1)
        v.addLayout(row, 1)
        self._add_page("Tasks", pg)

        self.task_list.model().rowsInserted.connect(self._sync_psub_task_combo)
        self.task_list.model().rowsRemoved.connect(self._sync_psub_task_combo)
        self.task_list.currentTextChanged.connect(self._on_task_selected)

        self._psub_mapping = {}
        raw = self.cfg.get("task_projects_subs", "")
        if raw:
            try: self._psub_mapping = json.loads(raw)
            except: pass
        self.psub_task_cb.currentTextChanged.connect(self._on_psub_task_changed)
        if self.psub_task_cb.count() > 0:
            self._on_psub_task_changed(self.psub_task_cb.currentText())

        # ── PAGE 3: FOLDERS ──────────────────────────────────────────────────
        pg, v = self._page("Folders",
            "Subfolders created inside every task. The first three have fixed roles; extras are optional.")
        row = QtWidgets.QHBoxLayout(); row.setSpacing(14)
        card, c = self._card("Task subfolders")
        self.sub_list = QtWidgets.QListWidget()
        for s_ in subs: self.sub_list.addItem(s_)
        self.ed_new_sub = QtWidgets.QLineEdit()
        c.addLayout(self._list_editor(self.sub_list, self.ed_new_sub, "new subfolder…", "subfolder"), 1)
        c.addWidget(self._hint("1st = scenes · 2nd = review · 3rd = publish (renders)"))
        card.setMinimumWidth(240)
        row.addWidget(card, 1)
        card, c = self._card("Resulting structure")
        self._tree_lbl = QtWidgets.QLabel(); self._tree_lbl.setObjectName("tree")
        self._tree_lbl.setAlignment(QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft)
        self._tree_lbl.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        c.addWidget(self._tree_lbl, 1)
        row.addWidget(card, 1)
        v.addLayout(row, 1)
        self._add_page("Folders", pg)
        self.sub_list.model().rowsInserted.connect(self._refresh_thumb_sub_combo)
        self.sub_list.model().rowsRemoved.connect(self._refresh_thumb_sub_combo)

        # ── PAGE 4: OUTPUT (snapshots + render) ──────────────────────────────
        pg, v = self._page("Output", "Where viewport snapshots go, how they are named, and how render frames are numbered.")
        card, c = self._card("Viewport snapshots")
        grid = QtWidgets.QGridLayout(); grid.setHorizontalSpacing(12); grid.setVerticalSpacing(10)
        self.thumb_sub_cb = QtWidgets.QComboBox(); self.thumb_sub_cb.setMinimumWidth(180)
        self.thumb_sub_cb.setToolTip("Which task subfolder receives the snapshots")
        for s_ in subs: self.thumb_sub_cb.addItem(s_)
        saved_thumb = self.cfg.get("thumb_subfolder", subs[1] if len(subs) > 1 else "")
        if saved_thumb:
            i = self.thumb_sub_cb.findText(saved_thumb)
            if i >= 0: self.thumb_sub_cb.setCurrentIndex(i)
        self.ed_thumb_subdir = QtWidgets.QLineEdit(self.cfg.get("thumb_subdir", ""))
        self.ed_thumb_subdir.setPlaceholderText("optional — e.g.  captures")
        self.ed_thumb_subdir.setToolTip("If set, snapshots go into  task / subfolder / <this>  —  created automatically")
        grid.addWidget(self._field("Save into"), 0, 0); grid.addWidget(self.thumb_sub_cb, 0, 1, QtCore.Qt.AlignLeft)
        grid.addWidget(self._field("Inside folder"), 1, 0); grid.addWidget(self.ed_thumb_subdir, 1, 1)
        chk_row = QtWidgets.QHBoxLayout(); chk_row.setSpacing(16)
        self.chk_snap_maxfile = QtWidgets.QCheckBox("Max filename")
        self.chk_snap_shot    = QtWidgets.QCheckBox("Shot")
        self.chk_snap_task    = QtWidgets.QCheckBox("Task")
        self.chk_snap_camera  = QtWidgets.QCheckBox("Camera / view")
        def _b(key, default):
            val = self.cfg.get(key, default)
            return val if isinstance(val, bool) else (str(val).lower() != "false" if default else str(val).lower() == "true")
        self.chk_snap_maxfile.setChecked(_b("snap_inc_maxfile", True))
        self.chk_snap_shot.setChecked(_b("snap_inc_shot", False))
        self.chk_snap_task.setChecked(_b("snap_inc_task", False))
        self.chk_snap_camera.setChecked(_b("snap_inc_camera", True))
        for chk in [self.chk_snap_maxfile, self.chk_snap_shot, self.chk_snap_task, self.chk_snap_camera]:
            chk_row.addWidget(chk); chk.toggled.connect(self._update_snap_preview)
        chk_row.addStretch()
        grid.addWidget(self._field("Name parts"), 2, 0); grid.addLayout(chk_row, 2, 1)
        self._snap_preview_lbl = QtWidgets.QLabel(); self._snap_preview_lbl.setObjectName("preview")
        grid.addWidget(self._field("Example"), 3, 0); grid.addWidget(self._snap_preview_lbl, 3, 1)
        grid.setColumnStretch(1, 1)
        c.addLayout(grid)
        v.addWidget(card)

        card, c = self._card("Render frames")
        rr = QtWidgets.QHBoxLayout(); rr.setSpacing(12)
        self.render_sep_cb = QtWidgets.QComboBox()
        self.render_sep_cb.addItems(["Underscore   shot_v001_0001.exr", "Dot   shot_v001.0001.exr"])
        self.render_sep_cb.setCurrentIndex(0 if self.cfg.get("render_sep", "_") == "_" else 1)
        rr.addWidget(self._field("Frame separator")); rr.addWidget(self.render_sep_cb); rr.addStretch()
        c.addLayout(rr)
        v.addWidget(card)
        v.addStretch()
        self._add_page("Output", pg)
        self._update_snap_preview()

        # ── FOOTER: presets + buttons ────────────────────────────────────────
        footer = QtWidgets.QWidget(); footer.setObjectName("footer")
        fl = QtWidgets.QHBoxLayout(footer); fl.setContentsMargins(16, 12, 16, 12); fl.setSpacing(6)
        fl.addWidget(self._field("Preset"))
        self.preset_cb = QtWidgets.QComboBox(); self.preset_cb.setMinimumWidth(180)
        self.preset_cb.setToolTip("Saved pipeline configurations")
        self._refresh_preset_combo()
        self.ed_preset_name = QtWidgets.QLineEdit(); self.ed_preset_name.setVisible(False)
        btn_load = QtWidgets.QPushButton("Load"); btn_load.setObjectName("flat_btn")
        btn_load.setToolTip("Load the selected preset into this dialog (applied when you press Save & Apply)")
        btn_save = QtWidgets.QPushButton("Save as…"); btn_save.setObjectName("flat_btn")
        btn_save.setToolTip("Save the current settings as a named preset")
        btn_del = _mini_btn("trash", "Delete the selected preset", obj="mini_del"); btn_del.setFixedSize(28, 26)
        btn_load.clicked.connect(self._load_preset)
        btn_save.clicked.connect(self._save_preset_as)
        btn_del.clicked.connect(self._delete_preset)
        for w in (self.preset_cb, btn_load, btn_save, btn_del): fl.addWidget(w)
        fl.addStretch()
        cfg_link = QtWidgets.QPushButton("Config folder"); cfg_link.setObjectName("flat_btn")
        cfg_link.setToolTip(f"{PIPELINE_CFG}\n{self.PRESETS_PATH}")
        cfg_link.clicked.connect(lambda: StudioToolbar._open_in_explorer(PIPE_DIR))
        fl.addWidget(cfg_link); fl.addSpacing(10)
        btn_cancel = QtWidgets.QPushButton("Cancel")
        btn_ok     = QtWidgets.QPushButton("Save && Apply"); btn_ok.setObjectName("ok_btn")
        for btn in (btn_cancel, btn_ok, btn_load, btn_save, cfg_link):
            btn.setAutoDefault(False); btn.setDefault(False)
        btn_cancel.clicked.connect(self.reject)
        btn_ok.clicked.connect(self._save_and_accept)
        fl.addWidget(btn_cancel); fl.addWidget(btn_ok)
        outer.addWidget(footer)

        # live previews
        for ed in (self.ed_drive, self.ed_prefix):
            ed.textChanged.connect(self._update_previews)
        for lw in (self.sub_list, self.psub_list, self.task_list):
            m = lw.model()
            for sig in (m.rowsInserted, m.rowsRemoved, m.rowsMoved, m.dataChanged):
                sig.connect(self._update_previews)
        self.ed_thumb_subdir.textChanged.connect(self._update_previews)
        self.thumb_sub_cb.currentTextChanged.connect(self._update_previews)
        self.render_sep_cb.currentIndexChanged.connect(self._update_previews)

        if self.task_list.count(): self.task_list.setCurrentRow(len(tasks) - 1)
        self.nav.setCurrentRow(0)
        self._update_previews()

        # Never squash text: each button/label keeps at least the width of its text
        # (with Max's real font), and the dialog never shrinks below its content.
        for w in [x for cls in (QtWidgets.QPushButton, QtWidgets.QLabel, QtWidgets.QCheckBox)
                  for x in self.findChildren(cls)]:
            if isinstance(w, QtWidgets.QLabel) and (w.wordWrap() or w.objectName() in ("tree", "preview")):
                continue
            w.ensurePolished()
            w.setMinimumWidth(w.sizeHint().width())
        self.preset_cb.setMinimumWidth(max(150, self.preset_cb.minimumWidth()))
        self.preset_cb.setMaximumWidth(260)
        outer.setSizeConstraint(QtWidgets.QLayout.SetMinimumSize)
        self.setMinimumSize(0, 0)
        self.resize(max(860, self.minimumSizeHint().width()), max(600, self.minimumSizeHint().height()))

    def _add_page(self, name, widget):
        self.nav.addItem(name); self.pages.addWidget(widget)

    def _browse_root(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Projects root", self.ed_drive.text() or "")
        if d: self.ed_drive.setText(os.path.normpath(d))

    def _on_task_selected(self, task):
        """The task list selection controls which subfolders are edited on the right."""
        if task and self.psub_task_cb.findText(task) >= 0:
            self.psub_task_cb.setCurrentText(task)
        self._psub_title.setText(f"Inside  {task or '—'} / {self._list_items(self.sub_list)[0] if self.sub_list.count() else 'scenes'}" if hasattr(self, "sub_list")
                                 else f"Inside  {task or '—'}")
        self._update_previews()

    @staticmethod
    def _list_items(listw):
        return [listw.item(i).text().strip() for i in range(listw.count()) if listw.item(i).text().strip()]

    def _update_previews(self, *a):
        if not hasattr(self, "_tree_lbl"): return
        prefix = self.ed_prefix.text().strip() or "VFX-"
        root   = (self.ed_drive.text().strip().rstrip("\\/") or "T:")
        self._proj_preview.setText(f"{root}\\{prefix}MYPROJECT\\")
        scan_root = root + os.sep if root.endswith(":") else root
        if not os.path.isdir(scan_root):
            self._proj_found.setText("⚠  Root path not found on this machine")
            self._proj_found.setStyleSheet("color: #e07a6a;")
        else:
            found = sorted(d[len(prefix):] for d in safe_listdir(scan_root) if d.startswith(prefix))
            if found:
                more = f"  +{len(found) - 10} more" if len(found) > 10 else ""
                self._proj_found.setText(f"✓  {len(found)} project{'s' if len(found) != 1 else ''} found:  "
                                         + ",  ".join(found[:10]) + more)
                self._proj_found.setStyleSheet("color: #78b878;")
            else:
                self._proj_found.setText(f"No folders starting with  “{prefix}”  in this root")
                self._proj_found.setStyleSheet("color: #d4a017;")
        subs  = self._list_items(self.sub_list) or ["1_projects"]
        task  = self.task_list.currentItem().text() if self.task_list.currentItem() else (self._list_items(self.task_list) or ["task"])[0]
        psubs = self._list_items(self.psub_list) if self.psub_task_cb.currentText() == task else \
                self._psub_mapping.get(task, ["textures"])
        roles = {0: "scenes", 1: "review", 2: "renders"}
        snap_sub = self.thumb_sub_cb.currentText()
        lines = [f"{root}\\{prefix}PROJ\\", "  101\\  PROJ_101_010\\  3D\\", f"    {task}\\"]
        for i, sb in enumerate(subs):
            tag = roles.get(i, "")
            if sb == snap_sub: tag = (tag + " · snapshots").strip(" ·")
            lines.append(f"      {sb}\\".ljust(30) + (f"← {tag}" if tag else ""))
            if i == 0:
                for ps in psubs: lines.append(f"        {ps}\\")
            if sb == snap_sub and self.ed_thumb_subdir.text().strip():
                lines.append(f"        {self.ed_thumb_subdir.text().strip()}\\")
        self._tree_lbl.setText("\n".join(lines))
        if hasattr(self, "_psub_title") and task:
            self._psub_title.setText(f"Inside  {task} \u203a {subs[0]}")

    def _save_preset_as(self):
        cur = self.preset_cb.currentText()
        name, ok = QtWidgets.QInputDialog.getText(self, "Save preset", "Preset name:",
                                                  text="" if cur == "(no presets saved)" else cur)
        if ok and name.strip():
            self.ed_preset_name.setText(name.strip())
            self._save_preset()

    # ── list helpers ──────────────────────────────────────────────────────────
    def _add_item(self, listw, line_edit):
        txt = line_edit.text().strip()
        if txt:
            listw.addItem(txt)
            line_edit.clear()

    def _del_item(self, listw, label):
        row = listw.currentRow()
        if row >= 0:
            item = listw.item(row)
            if QtWidgets.QMessageBox.question(self, f"Delete {label}",
                    f"Remove  '{item.text()}'?",
                    QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel) == QtWidgets.QMessageBox.Ok:
                listw.takeItem(row)

    def _rename_item(self, item):
        new_name, ok = QtWidgets.QInputDialog.getText(
            self, "Rename", "New name:", text=item.text())
        if ok and new_name.strip():
            item.setText(new_name.strip())

    # ── preset helpers ────────────────────────────────────────────────────────
    def _refresh_thumb_sub_combo(self):
        """Repopulate the snapshot destination combo with the current subfolders."""
        if not hasattr(self, 'thumb_sub_cb'): return
        current = self.thumb_sub_cb.currentText()
        self.thumb_sub_cb.clear()
        subs = [self.sub_list.item(i).text().strip()
                for i in range(self.sub_list.count()) if self.sub_list.item(i).text().strip()]
        for s in subs:
            self.thumb_sub_cb.addItem(s)
        saved = self.cfg.get("thumb_subfolder", "")
        target = current or saved
        if target:
            idx = self.thumb_sub_cb.findText(target)
            if idx >= 0: self.thumb_sub_cb.setCurrentIndex(idx)

    def _refresh_preset_combo(self):
        self.preset_cb.clear()
        presets = self._load_presets()
        if presets:
            for name in sorted(presets.keys()):
                self.preset_cb.addItem(name)
        else:
            self.preset_cb.addItem("(no presets saved)")

    def _update_snap_preview(self):
        """Update the snapshot name preview label."""
        parts = []
        if self.chk_snap_maxfile.isChecked():  parts.append("maxfile")
        if self.chk_snap_shot.isChecked():     parts.append("shot")
        if self.chk_snap_task.isChecked():     parts.append("task")
        if self.chk_snap_camera.isChecked():   parts.append("Camera001")
        if not parts: parts.append("snapshot")
        self._snap_preview_lbl.setText(f"{'_'.join(parts)}_v001.jpg")

    def _load_preset(self):
        name = self.preset_cb.currentText()
        if not name or name == "(no presets saved)": return
        presets = self._load_presets()
        if name in presets:
            self._apply_cfg_to_form(presets[name])

    def _save_preset(self):
        name = self.ed_preset_name.text().strip()
        if not name:
            QtWidgets.QMessageBox.warning(self, "Preset Name", "Enter a name for the preset.")
            return
        presets = self._load_presets()
        if name in presets:
            if QtWidgets.QMessageBox.question(self, "Overwrite Preset",
                    f"Preset  '{name}'  already exists. Overwrite?",
                    QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel) != QtWidgets.QMessageBox.Ok:
                return
        presets[name] = self._current_form_data()
        self._save_presets(presets)
        self.ed_preset_name.clear()
        self._refresh_preset_combo()
        # Select the newly saved preset
        idx = self.preset_cb.findText(name)
        if idx >= 0: self.preset_cb.setCurrentIndex(idx)

    def _delete_preset(self):
        name = self.preset_cb.currentText()
        if not name or name == "(no presets saved)": return
        if QtWidgets.QMessageBox.question(self, "Delete Preset",
                f"Delete preset  '{name}'?",
                QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel) == QtWidgets.QMessageBox.Ok:
            presets = self._load_presets()
            presets.pop(name, None)
            self._save_presets(presets)
            self._refresh_preset_combo()

    # ── save ──────────────────────────────────────────────────────────────────
    def _save_and_accept(self):
        tasks = [self.task_list.item(i).text().strip()
                 for i in range(self.task_list.count()) if self.task_list.item(i).text().strip()]
        if not tasks:
            QtWidgets.QMessageBox.warning(self, "Validation", "At least one task is required.")
            return
        subs = [self.sub_list.item(i).text().strip()
                for i in range(self.sub_list.count()) if self.sub_list.item(i).text().strip()]
        if not subs:
            QtWidgets.QMessageBox.warning(self, "Validation", "At least one subfolder is required.")
            return
        # Merge with the existing config: the dialog doesn't know every key
        # (e.g. the BG button's vp_color_presets) and used to wipe them on save.
        data = load_pipeline_cfg()
        data.update(self._current_form_data())
        save_pipeline_cfg(data)
        self.accept()


# ── Dock ─────────────────────────────────────────────────────────────────────
class STMDock(QtWidgets.QDockWidget):
    """Dock that is destroyed when closed (X) and cleans up the toolbar timer/callbacks."""
    def closeEvent(self, event):
        w = self.widget()
        if w is not None and hasattr(w, "cleanup"):
            w.cleanup()
        super().closeEvent(event)

def show_studio_toolbar():
    main  = GetQMaxMainWindow()
    title = f"Studio Toolbar for MAX  v{VERSION}"
    # Close any previous instance (current or legacy) so the toolbar isn't duplicated
    for child in main.findChildren(QtWidgets.QDockWidget):
        if (child.objectName() in ("STM_ToolbarDock", "Pipe3DShotManagerDock")
                or child.windowTitle().startswith(("Studio Toolbar for MAX", "Pipe3D Shot Manager"))):
            w = child.widget()
            if w is not None and hasattr(w, "cleanup"):
                try: w.cleanup()
                except: pass
            child.close()
            child.deleteLater()
    dock = STMDock(title, main)
    dock.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
    dock.setObjectName("STM_ToolbarDock")
    dock.setFeatures(
        QtWidgets.QDockWidget.DockWidgetMovable   |
        QtWidgets.QDockWidget.DockWidgetFloatable |
        QtWidgets.QDockWidget.DockWidgetClosable  |
        # Vertical title on the left: still the drag handle,
        # but doesn't eat a full-height horizontal strip.
        QtWidgets.QDockWidget.DockWidgetVerticalTitleBar
    )
    dock.setToolTip(f"Studio Toolbar for MAX  v{VERSION} — drag this handle to move / float")
    mgr = StudioToolbar(parent=main)
    dock.setWidget(mgr)
    mgr.setFixedHeight(TOOL_SZ + 8)
    dock.setStyleSheet(f"""
        QDockWidget {{
            color: {MX_TEXT_DIM};
            font-family: "Tahoma", "Segoe UI", sans-serif;
            font-size: 8pt;
        }}
        QDockWidget::title {{
            background: #303030;
            border-right: 1px solid {MX_SEP};
            padding: 4px 1px;
            text-align: center;
        }}
        QDockWidget::close-button, QDockWidget::float-button {{
            background: transparent; border: none; padding: 0px; icon-size: 10px;
        }}
        QDockWidget::close-button:hover, QDockWidget::float-button:hover {{ background: #505050; }}
    """)
    # Top corners to the top area — the dock spans the full width edge to edge
    main.setCorner(QtCore.Qt.TopLeftCorner,  QtCore.Qt.TopDockWidgetArea)
    main.setCorner(QtCore.Qt.TopRightCorner, QtCore.Qt.TopDockWidgetArea)
    main.addDockWidget(QtCore.Qt.TopDockWidgetArea, dock)

    # Allow re-docking: when the dock becomes top-level (floating)
    # and the user drags it back, Qt handles it with DockWidgetMovable.
    # The issue is setFixedHeight — floating needs free height, docking makes it fixed again.
    def _on_top_level_changed(floating):
        if floating:
            mgr.setMinimumHeight(0)
            mgr.setMaximumHeight(16777215)  # QWIDGETSIZE_MAX
        else:
            mgr.setFixedHeight(TOOL_SZ + 8)
            main.addDockWidget(QtCore.Qt.TopDockWidgetArea, dock)

    dock.topLevelChanged.connect(_on_top_level_changed)
    dock.show()


if __name__ == "__main__":
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    show_studio_toolbar()
