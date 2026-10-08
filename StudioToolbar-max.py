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

VERSION = "2.5.38"

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
PIPE_DIR     = os.path.expanduser("~\\.studio-toolbar")
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
    """Carga pipeline_config.ini (merge con defaults). Cacheado: solo relee
    el archivo si cambió en disco — _master_sync lo consulta cada 500 ms."""
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
    _CFG_CACHE["data"] = None   # forzar relectura

def _cfg():
    """Shortcut para obtener la config activa."""
    return load_pipeline_cfg()

# Derivados de config — se recalculan en runtime desde _cfg()
def get_tasks_template():
    return [t.strip() for t in _cfg()["tasks"].split(",") if t.strip()]

def get_subfolders():
    """Devuelve lista ordenada de todas las subcarpetas de task."""
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
    Devuelve la lista de subcarpetas a crear dentro de projects/ para una task.
    Si la task no tiene config específica, devuelve ["textures"] por default.
    """
    raw = _cfg().get("task_projects_subs", "")
    if raw:
        try:
            mapping = json.loads(raw)
            if task_name in mapping:
                return mapping[task_name]
        except: pass
    return ["textures"]

# Mantener compatibilidad con código que usa las constantes directamente
TASKS_TEMPLATE      = ["1_matchmove","2_model","3_retopo","4_rigging","5_shaders","6_animation","7_fx","8_lighting"]
SUBFOLDERS_TEMPLATE = {"projects":"1_projects","review":"2_review","publish":"3_publish"}

# ── Paleta ────────────────────────────────────────────────────────────────────
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
IC_ACCENT2 = "#d4b44a"   # amarillo
IC_HOVER   = "#ffffff"

LIB_BG     = "#1e1e1e"
LIB_BG_HO  = "#2a2a2a"
LIB_BORDER = "#484848"
LIB_TEXT   = "#aaaaaa"
LIB_TEXT_HO= "#d8d8d8"

FONT_MAIN  = "9pt"
FONT_LABEL = "8.5pt"
FONT_SMALL = "8pt"

# Dimensiones tool buttons — cuadrados, iconos grandes
TOOL_SZ = 40     # ancho y alto del botón
ICON_SZ = 28     # tamaño del SVG
H       = 22     # altura estándar de inputs/combos/botones normales

# ── Stylesheet ────────────────────────────────────────────────────────────────
STYLE = f"""
QWidget {{
    background-color: {MX_BG};
    color: {MX_TEXT};
    font-family: "Tahoma", "Segoe UI", sans-serif;
    font-size: {FONT_MAIN};
}}

/* ── inputs — NUNCA se estiran, siempre fixed ────────── */
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
QComboBox::down-arrow {{
    width:0; height:0;
    border-left:4px solid transparent; border-right:4px solid transparent;
    border-top:5px solid {MX_TEXT_DIM}; margin-right:4px;
}}
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
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    width:0; height:0;
    border-left:3px solid transparent; border-right:3px solid transparent;
    border-bottom:4px solid {MX_TEXT_DIM};
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    width:0; height:0;
    border-left:3px solid transparent; border-right:3px solid transparent;
    border-top:4px solid {MX_TEXT_DIM};
}}

/* ── botón base — fixed, no stretch ─────────────────── */
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

/* ── reset — tint rojizo sutil ────────────────────────── */
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
    color: transparent;       /* invisible pero ocupa espacio */
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
    """Cámara de snapshot — cuerpo + lente + destellito."""
    return f"""<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
  <rect x="2" y="6" width="20" height="14" rx="2" fill="none" stroke="{base}" stroke-width="1.4"/>
  <path d="M8,6 L9.5,3 L14.5,3 L16,6" fill="none" stroke="{base}" stroke-width="1.3"/>
  <circle cx="12" cy="13" r="4" fill="none" stroke="{base}" stroke-width="1.3"/>
  <circle cx="12" cy="13" r="2" fill="{accent}" opacity="0.7"/>
  <circle cx="18.5" cy="9" r="1.2" fill="{accent}" opacity="0.9"/>
</svg>"""


def _svg_to_pixmap(svg_str, size=ICON_SZ):
    renderer = QtSvg.QSvgRenderer(QtCore.QByteArray(svg_str.encode()))
    pix = QtGui.QPixmap(size, size)
    pix.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(pix)
    renderer.render(painter)
    painter.end()
    return pix


def _svg_to_pixmap_rect(svg_str, w, h):
    """Renderiza SVG a un QPixmap de dimensiones arbitrarias."""
    renderer = QtSvg.QSvgRenderer(QtCore.QByteArray(svg_str.encode()))
    pix = QtGui.QPixmap(w, h)
    pix.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(pix)
    renderer.render(painter)
    painter.end()
    return pix


def _svg_x2(color):
    """Icono ×2 — símbolo de multiplicación + número 2 grande y claro."""
    return f"""<svg viewBox="0 0 34 22" xmlns="http://www.w3.org/2000/svg">
  <line x1="3" y1="5"  x2="10" y2="14" stroke="{color}" stroke-width="1.8" stroke-linecap="round"/>
  <line x1="10" y1="5" x2="3"  y2="14" stroke="{color}" stroke-width="1.8" stroke-linecap="round"/>
  <path d="M17,6 L24,6 Q27,6 27,9 Q27,12 22,14 L17,17 L27,17"
        fill="none" stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
</svg>"""


def _svg_div2(color):
    """Icono /2 — barra diagonal + número 2."""
    return f"""<svg viewBox="0 0 34 22" xmlns="http://www.w3.org/2000/svg">
  <line x1="10" y1="17" x2="17" y2="5" stroke="{color}" stroke-width="1.8" stroke-linecap="round"/>
  <path d="M21,6 L28,6 Q31,6 31,9 Q31,12 26,14 L21,17 L31,17"
        fill="none" stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
</svg>"""


class SvgLabelButton(QtWidgets.QPushButton):
    """Botón pequeño con icono SVG rectangular (no cuadrado), para X2 / /2."""
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


# ── IconToolButton — cuadrado, solo icono, sin overlay de texto ───────────────
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
        # Sin setFlat — usamos paintEvent propio
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
    """Lee presets desde pipeline_config.ini, o devuelve los defaults."""
    cfg = load_pipeline_cfg()
    raw = cfg.get(VP_COLOR_CFG_KEY)
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            pass
    return list(VP_COLOR_PRESETS_DEFAULT)

def _save_vp_color_presets(presets):
    """Guarda presets en pipeline_config.ini."""
    cfg = load_pipeline_cfg()
    cfg[VP_COLOR_CFG_KEY] = json.dumps(presets)
    save_pipeline_cfg(cfg)

def _hex_to_maxpoint3(hex_color):
    """Convierte #rrggbb a Point3 normalizado (0-1) para SetUIColor."""
    h = hex_color.lstrip("#")
    r = int(h[0:2], 16) / 255.0
    g = int(h[2:4], 16) / 255.0
    b = int(h[4:6], 16) / 255.0
    return r, g, b

def _get_current_vp_hex():
    """Lee el color actual del viewport desde Max y devuelve #rrggbb.
    Solid: índice 41. Gradient: bottom (el color más representativo visualmente)."""
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
    """True si el viewport activo está en modo solid."""
    try:
        return bool(rt.viewport.IsSolidBackgroundColorMode())
    except Exception:
        return True

def _restore_vp_originals(orig_hex, orig_grad_top, orig_grad_bot):
    """Restaura exactamente los colores que había antes de abrir el manager."""
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
    """Aplica un color al viewport background via MAXScript.
    Mantiene la proporcion original de 3ds Max:
      solid = color elegido
      bottom = color + 21/255  (mas claro, como 77 respecto a 56)
      top    = color - 30/255  (mas oscuro, como 26 respecto a 56)
    """
    try:
        r, g, b = _hex_to_maxpoint3(hex_color)
        OFFSET_BOT =  21 / 255.0   # +21 niveles como el default de Max
        OFFSET_TOP = -30 / 255.0   # -30 niveles como el default de Max
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
    Botón cuadrado TOOL_SZ x TOOL_SZ que muestra el color actual del viewport.
    Al hacer click despliega un menú con presets + opción custom + add/delete.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        # "Original" siempre es el default conocido de 3ds Max
        # solid=56,56,56 | gradient top=26,26,26 | gradient bottom=77,77,77
        self._orig_hex      = "#383838"   # 56,56,56
        self._orig_grad_top = "#1a1a1a"   # 26,26,26
        self._orig_grad_bot = "#4d4d4d"   # 77,77,77
        # Iniciar con el color original — se actualiza al color real tras 300ms
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

        # fondo del botón: color actual del viewport
        col = QtGui.QColor(self._cur_hex)
        p.fillRect(self.rect(), col)

        # borde — más brillante en hover
        border_col = QtGui.QColor(MX_BORDER_HI if self._hovered else MX_BORDER)
        pen = QtGui.QPen(border_col)
        pen.setWidth(1)
        p.setPen(pen)
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))

        # triángulo dropdown en esquina inferior derecha
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

        # pequeño label "BG" centrado
        lbl_col = QtGui.QColor(255, 255, 255, 200) if col.lightness() < 128 else QtGui.QColor(0, 0, 0, 160)
        p.setPen(lbl_col)
        f = p.font(); f.setPointSize(7); f.setFamily("Tahoma"); p.setFont(f)
        p.drawText(self.rect(), QtCore.Qt.AlignCenter, "BG")
        p.end()

    def _restore_on_close(self):
        """Llamado al cerrar el dock — restaura los colores originales."""
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

        # — Presets con swatch de color via QWidgetAction ─────────────────
        menu.setStyleSheet(menu.styleSheet() + "QMenu::item { padding-left: 8px; }")
        for i, preset in enumerate(presets):
            hex_c  = preset["hex"]
            name   = preset["name"]
            # Widget personalizado: swatch + label con aire
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
            prev_hex = self._cur_hex          # guardamos para cancelar
            dlg = QtWidgets.QColorDialog(initial, self)
            dlg.setWindowTitle("Viewport Background Color")
            dlg.setOption(QtWidgets.QColorDialog.NoButtons, False)
            # Preview en tiempo real
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
                # Cancel — restaurar el color previo
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


# ── Separador de sección full-height ─────────────────────────────────────────
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
    """Agrega un widget invisible que absorbe el espacio sobrante."""
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
    """Devuelve el directorio que contiene los proyectos VFX-xxx.
    Primero intenta desde el project folder de Max,
    si no encuentra prefix usa root_drive del config como fallback."""
    cfg    = _cfg()
    prefix = cfg.get("project_prefix", "VFX-")
    try:
        path  = os.path.normpath(str(rt.pathConfig.getCurrentProjectFolder()))
        parts = path.split(os.sep)
        for i, p in enumerate(parts):
            if p.startswith(prefix):
                base = os.sep.join(parts[:i])
                # En Windows "T:" sin barra lista el cwd del drive, no la raiz
                if base.endswith(":"):
                    base = base + os.sep
                return base
    except: pass
    # Fallback directo al root_drive configurado
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
    Captura el viewport activo de 3ds Max a un archivo PNG.
    Idéntico al método del StudioLibraryMAX — tres métodos de fallback.
    Confirmado funcional en MAX 2025.
    """
    out_fwd = out_path.replace("\\", "/")
    captured = False

    # Método A: gw.getViewportDib() + .filename + save — confirmado MAX 2025
    if not captured:
        try:
            mxs = (f'( local img = gw.getViewportDib() ; '
                   f'img.filename = "{out_fwd}" ; save img )')
            rt.execute(mxs)
            if os.path.exists(out_path): captured = True
        except Exception as e:
            print(f"[snap A] {e}")

    # Método B: pymxs directo
    if not captured:
        try:
            img = rt.gw.getViewportDib()
            if img is not None:
                img.filename = out_path
                rt.save(img)
                if os.path.exists(out_path): captured = True
        except Exception as e:
            print(f"[snap B] {e}")

    # Método C: grabView()
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

        rt.STM_GlobalRefresh = self._get_pipeline_from_path
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

        # Row widget con layout horizontal — ocupa todo el ancho disponible
        row_w = QtWidgets.QWidget()
        row_w.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        L = QtWidgets.QHBoxLayout(row_w)
        L.setContentsMargins(14, 0, 14, 0)
        L.setSpacing(2)

        outer.addStretch(1)
        outer.addWidget(row_w)
        outer.addStretch(1)

        # ── SECTION: TOOLS ───────────────────────────────────────────────────
        # Botón "TOOLS" que abre un QMenu con los scripts de PATH_TOOLS_DIR
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
        self.btn_bake_cam.setToolTip("Bake Camera\nBakes the active camera animation to an Alembic (.abc) cache")
        self.btn_library.setToolTip("Studio Library MAX\nOpens the pose/animation library manager")

        for b in [self.btn_overscan, self.btn_img_plane, self.btn_rem_back,
                  self.btn_textures, self.btn_bake_cam]:
            L.addWidget(b)
            L.addSpacing(3)
        L.addSpacing(4)
        L.addWidget(self.btn_library)

        # Stretch después de tools — absorbe espacio sobrante de la sección TOOLS
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

        self.res_lock_btn = QtWidgets.QPushButton("🔓")
        self.res_lock_btn.setObjectName("save_btn")
        self.res_lock_btn.setFixedHeight(H); self.res_lock_btn.setFixedWidth(24)
        self.res_lock_btn.setCheckable(True)
        self.res_lock_btn.setToolTip("Lock aspect ratio — keeps W:H proportion when either value changes")
        self.res_lock_btn.setStyleSheet(f"""
            QPushButton {{ background-color: #484848; color: {MX_TEXT_DIM}; border: 1px solid {MX_BORDER};
                          border-radius: 1px; font-size: 9pt; padding: 0; }}
            QPushButton:checked {{ background-color: #2a3a4a; color: #4ec9c9; border-color: #4a7a9a; }}
            QPushButton:hover {{ background-color: {MX_BG_BTN_HO}; border-color: {MX_BORDER_HI}; }}
        """)

        self.res_x2_btn = QtWidgets.QPushButton("D")
        self.res_x2_btn.setObjectName("save_btn")
        self.res_x2_btn.setFixedHeight(H); self.res_x2_btn.setFixedWidth(20)
        self.res_x2_btn.setToolTip("Double the resolution (W and H × 2, always even)")

        self.res_d2_btn = QtWidgets.QPushButton("H")
        self.res_d2_btn.setObjectName("save_btn")
        self.res_d2_btn.setFixedHeight(H); self.res_d2_btn.setFixedWidth(20)
        self.res_d2_btn.setToolTip("Halve the resolution (W and H ÷ 2, always even)")

        self.res_note = QtWidgets.QLineEdit()
        self.res_note.setObjectName("note_field"); self.res_note.setPlaceholderText("preset label…")
        self.res_note.setFixedWidth(216); self.res_note.setFixedHeight(H)
        self.res_note.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.res_note.setToolTip("Resolution preset label")

        self.res_s = QtWidgets.QPushButton("S"); self.res_s.setObjectName("save_btn"); self.res_s.setFixedHeight(H); self.res_s.setFixedWidth(20); self.res_s.setToolTip("Save resolution preset")
        self.res_l = QtWidgets.QPushButton("L"); self.res_l.setObjectName("load_btn"); self.res_l.setFixedHeight(H); self.res_l.setFixedWidth(20); self.res_l.setToolTip("Load resolution preset from list")
        self.res_d = QtWidgets.QPushButton("D"); self.res_d.setObjectName("del_btn");  self.res_d.setFixedHeight(H); self.res_d.setFixedWidth(20); self.res_d.setToolTip("Delete current resolution preset")

        for w in [self.res_w, _x, self.res_h]: L.addWidget(w)
        L.addSpacing(4)
        L.addWidget(self.res_lock_btn)
        L.addSpacing(2)
        L.addWidget(self.res_x2_btn)
        L.addWidget(self.res_d2_btn)
        L.addSpacing(4)
        for w in [self.res_note, self.res_s, self.res_l, self.res_d]: L.addWidget(w)

        # Stretch después de RESOLUTION — FILM size es su propia sección
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

        _mm = _lbl_mm(); _mm.setFixedWidth(36); _mm.setContentsMargins(6, 0, 8, 0)

        self.film_note = QtWidgets.QLineEdit()
        self.film_note.setObjectName("note_field"); self.film_note.setPlaceholderText("camera / lens label…")
        self.film_note.setFixedWidth(297); self.film_note.setFixedHeight(H)
        self.film_note.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.film_note.setToolTip("Film size preset label (e.g. camera name or lens)")

        self.film_s = QtWidgets.QPushButton("S"); self.film_s.setObjectName("save_btn"); self.film_s.setFixedHeight(H); self.film_s.setFixedWidth(20); self.film_s.setToolTip("Save film size preset")
        self.film_l = QtWidgets.QPushButton("L"); self.film_l.setObjectName("load_btn"); self.film_l.setFixedHeight(H); self.film_l.setFixedWidth(20); self.film_l.setToolTip("Load film size preset from list")
        self.film_d = QtWidgets.QPushButton("D"); self.film_d.setObjectName("del_btn");  self.film_d.setFixedHeight(H); self.film_d.setFixedWidth(20); self.film_d.setToolTip("Delete current film size preset")

        L.addWidget(self.film_spin); L.addWidget(_mm)
        for w in [self.film_note, self.film_s, self.film_l, self.film_d]: L.addWidget(w)

        # Stretch después de FILM
        _stretch(L)

        # ── SECTION: FPS ──────────────────────────────────────────────────────
        _section_sep(L)

        self.fps_lbl = QtWidgets.QLabel("— FPS")
        self.fps_lbl.setObjectName("fps_val_lbl")
        self.fps_lbl.setStyleSheet(f"color:{MX_TEXT_DIM}; font-size:{FONT_MAIN}; font-weight:bold; background:transparent;")
        self.fps_lbl.setFixedWidth(62)
        self.fps_lbl.setToolTip("Current scene frame rate (read-only)")
        L.addWidget(self.fps_lbl)

        # mini separador interno
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
        self.unit_lbl.setFixedWidth(110)   # ancho fijo — "Kilometers" es la más larga
        self.unit_lbl.setToolTip("Current scene system unit (read-only)")
        L.addWidget(self.unit_lbl)

        # Stretch después de FPS/UNIT
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
        self.shot_cb.setFixedWidth(340); self.shot_cb.setFixedHeight(H)   # mucho más ancho
        self.shot_cb.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.shot_cb.setToolTip("Shot")

        self.task_cb = QtWidgets.QComboBox()
        self.task_cb.setFixedWidth(160); self.task_cb.setFixedHeight(H)
        self.task_cb.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.task_cb.setToolTip("Task / department folder (e.g. 5_matchmove)")

        self.add_btn = QtWidgets.QPushButton("+")
        self.add_btn.setObjectName("add_btn"); self.add_btn.setFixedHeight(H); self.add_btn.setFixedWidth(20)
        self.add_btn.setToolTip("Create a new task folder for the selected shot")

        for w in [self.project_cb, self.sequence_cb, self.shot_cb, self.task_cb]:
            L.addWidget(w); L.addSpacing(2)
        L.addWidget(self.add_btn)

        # Stretch después de PIPELINE
        _stretch(L)

        # ── SECTION: ACTIONS ─────────────────────────────────────────────────
        _section_sep(L)

        # Snap button — entre los dos boxes, tamaño icono original
        self.btn_snap = IconToolButton(_svg_snap, accent_color=IC_ACCENT2)
        self.btn_snap.setFixedSize(TOOL_SZ, TOOL_SZ)
        self.btn_snap.setToolTip("Viewport Snapshot\nCaptures the active viewport and saves a JPG to the current task's review folder")
        L.addWidget(self.btn_snap)
        L.addSpacing(4)

        self.btn_vp_color = ViewportColorButton()
        self.btn_vp_color.setToolTip("Viewport Background Color\nClick to change — resets on 3ds Max restart")
        L.addWidget(self.btn_vp_color)
        # El botón BG arranca en el default de Max (56,56,56)
        # y se actualiza solo cuando el usuario elige un color
        L.addSpacing(8)

        self.open_btn = QtWidgets.QPushButton("OPEN")
        self.open_btn.setObjectName("action_btn"); self.open_btn.setFixedHeight(H)
        self.open_btn.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.open_btn.setToolTip("Open a .max scene file from the selected shot/task folder")

        self.save_scene_btn = QtWidgets.QPushButton("SAVE")
        self.save_scene_btn.setObjectName("action_btn"); self.save_scene_btn.setFixedHeight(H)
        self.save_scene_btn.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.save_scene_btn.setToolTip("Save Scene — opens Save dialog in the task folder with versioned filename ready")

        self.get_btn = QtWidgets.QPushButton("GET")
        self.get_btn.setObjectName("action_btn"); self.get_btn.setFixedHeight(H)
        self.get_btn.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.get_btn.setToolTip("Read current render settings and path config from 3ds Max")

        self.set_path_btn = QtWidgets.QPushButton("PATHS")
        self.set_path_btn.setObjectName("action_btn"); self.set_path_btn.setFixedHeight(H)
        self.set_path_btn.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.set_path_btn.setToolTip("Set project paths (scenes, images, preview, renderoutput) from selected shot/task")

        self.set_save_btn = QtWidgets.QPushButton("SET RENDER")
        self.set_save_btn.setObjectName("action_btn"); self.set_save_btn.setFixedHeight(H)
        self.set_save_btn.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.set_save_btn.setToolTip("Set Render Output — sets the render filename to the selected shot's publish folder")

        self.auto_chk = QtWidgets.QCheckBox("AUTO")
        self.auto_chk.setFixedHeight(H)
        self.auto_chk.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.auto_chk.setToolTip("AUTO — uses dropdown name (shot_task_v001) instead of current Max filename")

        self.inc_chk = QtWidgets.QCheckBox("INC")
        self.inc_chk.setFixedHeight(H)
        self.inc_chk.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.inc_chk.setToolTip("INC — auto-increments version number (v001 → v002…)")

        self.reset_btn = QtWidgets.QPushButton("RESET")
        self.reset_btn.setObjectName("reset_btn"); self.reset_btn.setFixedHeight(H)
        self.reset_btn.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.reset_btn.setToolTip("Reset all project paths back to 3ds Max defaults")

        for b in [self.open_btn, self.save_scene_btn, self.get_btn, self.set_path_btn, self.set_save_btn]:
            L.addWidget(b); L.addSpacing(6)
        L.addSpacing(6)
        L.addWidget(self.auto_chk)
        L.addSpacing(4)
        L.addWidget(self.inc_chk)
        L.addSpacing(10)
        L.addWidget(self.reset_btn)

        # ── STATUS ────────────────────────────────────────────────────────────
        _section_sep(L)

        self.status_lbl  = QtWidgets.QLabel("Ready")
        self.status_lbl.setObjectName("status_lbl")
        self.status_lbl.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)

        L.addWidget(self.status_lbl)
        L.addSpacing(8)

        self.setup_btn = QtWidgets.QPushButton("⚙")
        self.setup_btn.setObjectName("save_btn")
        self.setup_btn.setFixedHeight(H); self.setup_btn.setFixedWidth(22)
        self.setup_btn.setToolTip("Pipeline Setup — configure drive, prefix, tasks and folder names")
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
        self.res_l.clicked.connect(self._show_res_menu)
        self.res_d.clicked.connect(self._delete_res_preset)
        self.film_spin.valueChanged.connect(self._on_film_ui_change)
        self.film_spin.editingFinished.connect(self._write_film_to_max)
        self.film_s.clicked.connect(self._manual_save_film)
        self.film_l.clicked.connect(self._show_film_menu)
        self.film_d.clicked.connect(self._delete_film_preset)
        self.get_btn.clicked.connect(self._get_pipeline_from_path)
        self.project_cb.currentTextChanged.connect(self._on_project_changed)
        self.sequence_cb.currentTextChanged.connect(self._populate_shots)
        self.shot_cb.currentTextChanged.connect(self._refresh_tasks)
        self.add_btn.clicked.connect(self.show_task_menu)
        self.open_btn.clicked.connect(self.open_scene_dialog)
        self.save_scene_btn.clicked.connect(self.save_scene_dialog)
        self.set_path_btn.clicked.connect(self.set_paths_only)
        self.set_save_btn.clicked.connect(self.set_save_only)
        self.reset_btn.clicked.connect(self.confirm_and_reset_paths)
        self.setup_btn.clicked.connect(self._open_setup)
        self.film_spin.installEventFilter(self)

    # ── status flash ─────────────────────────────────────────────────────────
    def _set_status(self, text, color=None):
        color = color or MX_TEXT_DIM
        self.status_lbl.setText(text)
        self.status_lbl.setStyleSheet(
            f"color:{color}; font-size:{FONT_LABEL}; min-width:100px; background:transparent;")
        QtCore.QTimer.singleShot(2200, lambda: self.status_lbl.setStyleSheet(
            f"color:{MX_TEXT_DIM}; font-size:{FONT_LABEL}; min-width:100px; background:transparent;"))

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
        """Lee el encabezado del script y devuelve su descripción para el tooltip.
        Busca un bloque DESCRIPTION/Description:, si no, la primera línea con texto."""
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
            if re.fullmatch(r'[=\-─━_*#~ ]*', l): l = ""      # separadores
            if re.search(r'-\*-\s*coding', l): l = ""          # cabecera de encoding .py
            lines.append(l)
        desc = []
        for i, l in enumerate(lines):
            m = re.match(r'(?i)^description\s*:?\s*(.*)$', l)
            if m:
                if m.group(1): desc.append(m.group(1))
                for nxt in lines[i+1:]:
                    if not nxt or re.match(r'^[A-Z][A-Z /&]{3,}$', nxt): break   # fin de bloque
                    desc.append(nxt)
                    if nxt.endswith(".") or len(desc) >= max_lines: break   # primera frase
                break
        if not desc:
            desc = [next((l for l in lines if l), "")]
        elif not desc[-1].endswith("."):
            desc[-1] += " …"
        return "\n".join(desc)

    def _fill_tools_menu(self, menu, folder):
        """Agrega scripts de folder al menú; cada subcarpeta es un submenú. Devuelve cantidad."""
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

        # Abrir el menú justo debajo del botón
        menu.exec(self.btn_tools_menu.mapToGlobal(
            QtCore.QPoint(0, self.btn_tools_menu.height())))

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
                # Mantener vivo el namespace: ventanas top-level sin parent
                # (ej. StudioLibrary: window = ...) se destruirían por GC
                if not hasattr(self, "_script_ctx"): self._script_ctx = {}
                self._script_ctx[path] = ctx
                self._set_status("Loaded", "#70aa70")
        except Exception as e:
            import traceback
            self._set_status("Error", "#e06060"); print(f"STM Error in {os.path.basename(path)}:")
            traceback.print_exc()

    def eventFilter(self, obj, event):
        if obj is self.film_spin:
            if event.type() == QtCore.QEvent.FocusIn:  self.sync_timer.stop()
            elif event.type() == QtCore.QEvent.FocusOut: self.sync_timer.start(500)
        return super().eventFilter(obj, event)

    # ── res ───────────────────────────────────────────────────────────────────
    def _res_set(self, w, h):
        """Aplica W y H atómicamente, siempre números pares, sin loops."""
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
        m = next((p for p in self.state.get("res_presets",[]) if p['w']==w and p['h']==h), None)
        self.res_note.setText(m['n'] if m else "")

    def _res_multiply_2(self):
        self._res_set(self.res_w.value() * 2, self.res_h.value() * 2)

    def _res_divide_2(self):
        self._res_set(self.res_w.value() // 2, self.res_h.value() // 2)

    def _on_lock_toggled(self, locked):
        self.res_lock_btn.setText("🔒" if locked else "🔓")
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
        if self.res_w.signalsBlocked(): return
        self._write_res_to_max()
        m = next((p for p in self.state.get("res_presets",[])
                  if p['w']==self.res_w.value() and p['h']==self.res_h.value()), None)
        self.res_note.setText(m['n'] if m else "")

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

    def _show_res_menu(self):
        m = QtWidgets.QMenu(self); presets = self.state.get("res_presets",[])
        if presets:
            for p in presets:
                a = m.addAction(f"{p['w']} × {p['h']}   {p['n']}")
                a.triggered.connect(lambda c=False, x=p: self._apply_res(x))
        else: m.addAction("(no presets saved)").setEnabled(False)
        m.exec(QtGui.QCursor.pos())

    def _apply_res(self, p):
        # Bloquear ambas señales para aplicar W y H de una sola vez sin cascada
        self.res_w.blockSignals(True)
        self.res_h.blockSignals(True)
        self.res_w.setValue(p['w'])
        self.res_h.setValue(p['h'])
        self.res_w.blockSignals(False)
        self.res_h.blockSignals(False)
        self.res_note.setText(p.get('n', ""))
        # Si el lock está activo, actualizar el ratio al nuevo preset
        if self.res_lock_btn.isChecked():
            self._lock_ratio = p['w'] / p['h'] if p['h'] else 1.0
        self._write_res_to_max()

    # ── film ──────────────────────────────────────────────────────────────────
    def _on_film_ui_change(self):
        if self.film_spin.signalsBlocked(): return
        m = next((p for p in self.state.get("film_presets",[])
                  if abs(p['v']-self.film_spin.value())<0.001), None)
        self.film_note.setText(m['n'] if m else "")

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
        if presets:
            for p in presets:
                a = m.addAction(f"{p['v']} mm   {p['n']}")
                a.triggered.connect(lambda c=False, x=p: self._apply_film(x))
        else: m.addAction("(no presets saved)").setEnabled(False)
        m.exec(QtGui.QCursor.pos())

    def _apply_film(self, p):
        self.film_spin.setValue(p['v']); self.film_note.setText(p.get('n',"")); self._write_film_to_max()

    # ── pipeline — lógica original transplantada al 100% ─────────────────────
    def _on_project_changed(self, project_name):
        """Al cambiar proyecto, actualiza el root de Max y gestiona carpeta 3D."""
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

        # Nombre del proyecto actual si hay uno cargado
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
        # Disparar la cadena una sola vez con el proyecto final
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

    def _get_pipeline_from_path(self):
        """GET: lee rt.maxFilePath y setea los 4 dropdowns."""
        try:
            cfg        = _cfg()
            prefix     = cfg["project_prefix"]
            max_folder = str(rt.maxFilePath)
            parts      = [p for p in max_folder.split("\\") if p]
            idx = next((i for i, p in enumerate(parts) if p.startswith(prefix)), None)
            if idx is None or len(parts) <= idx + 2: return
            project = parts[idx].replace(prefix, "")
            seq     = parts[idx + 1]
            shot    = parts[idx + 2]
            task    = parts[idx + 4] if len(parts) > idx + 4 and parts[idx + 3] == "3D" else ""
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
            rel_scenes = f"..\\{seq}\\{shot}\\3D\\{task}\\{sub_p}"
            rt.pathConfig.setDir(rt.name('scene'),        rel_scenes)
            rt.pathConfig.setDir(rt.name('image'),        rel_scenes + "\\textures")
            rt.pathConfig.setDir(rt.name('preview'),      f"..\\{seq}\\{shot}\\3D\\{task}\\{sub_r}")
            rt.pathConfig.setDir(rt.name('renderoutput'), f"..\\{seq}\\{shot}\\3D\\{task}\\{sub_pub}")
            # import path — buscar carpeta "import" en los subfolders del task
            task_subs = get_task_projects_subs(task)
            if "import" in task_subs:
                import_rel = f"..\\{seq}\\{shot}\\3D\\{task}\\{sub_p}\\import"
                try: rt.pathConfig.setDir(rt.name('import'), import_rel)
                except: pass
            # export path → carpeta publish (igual que renderoutput)
            try: rt.pathConfig.setDir(rt.name('export'), f"..\\{seq}\\{shot}\\3D\\{task}\\{sub_pub}")
            except: pass
            save_state({"project": project, "sequence": seq, "shot": shot, "task": task})
            self._set_status("Paths set", "#70aa70")
        except Exception as e:
            self._set_status("PATH Error", "#e06060"); print(e)

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
            use_auto = self.auto_chk.isChecked()
            use_inc  = self.inc_chk.isChecked()
            task_clean  = task.split("_", 1)[-1] if "_" in task else task

            # Prefijo base sin _vXXX (para buscar versiones existentes)
            if use_auto:
                # Desde dropdowns: shot_task
                prefix = f"{shot}_{task_clean}"
            else:
                # Desde el archivo Max actual — extraer prefijo sin _vXXX
                current_max = str(rt.maxFileName)
                raw = os.path.splitext(current_max)[0] if current_max else f"{shot}_{task_clean}"
                m   = re.match(r'^(.+?)(_v\d+)?$', raw)
                prefix = m.group(1) if m else raw

            # Versión del archivo Max abierto — siempre es el punto de partida
            current_max = str(rt.maxFileName)
            raw_name    = os.path.splitext(current_max)[0] if current_max else ""
            mv_file     = re.search(r'_v(\d+)$', raw_name)
            if mv_file:
                file_ver = int(mv_file.group(1))
                pad      = len(mv_file.group(1))
            else:
                file_ver = 1
                pad      = 3

            if use_inc:
                # Con INC: buscar el mayor en disco
                existing = [d for d in (os.listdir(publish_base) if os.path.isdir(publish_base) else [])
                            if re.match(r'^' + re.escape(prefix) + r'_v\d+$', d)]
                max_ver = 0
                for d in existing:
                    mv = re.search(r'_v(\d+)$', d)
                    if mv:
                        n = int(mv.group(1))
                        if n > max_ver:
                            max_ver = n
                            pad     = len(mv.group(1))
                # Usar el mayor entre disco y archivo abierto
                # Si la carpeta del archivo ya existe → incrementar, si no → usar la del archivo
                current_folder = f"{prefix}_v{file_ver:0{pad}d}"
                current_exists = os.path.isdir(os.path.join(publish_base, current_folder))
                if current_exists:
                    next_ver    = max(max_ver, file_ver) + 1
                    folder_name = f"{prefix}_v{next_ver:0{pad}d}"
                else:
                    folder_name = current_folder
            else:
                # Sin INC: usar exactamente la versión del archivo abierto
                folder_name = f"{prefix}_v{file_ver:0{pad}d}"

            pub_dir  = os.path.join(publish_base, folder_name)
            exr_name = f"{folder_name}{cfg.get('render_sep', '_')}.exr"
            os.makedirs(pub_dir, exist_ok=True)
            rt.rendSaveFile       = True
            rt.rendOutputFilename = os.path.join(pub_dir, exr_name)
            extra = self._set_renderer_outputs(pub_dir, folder_name, cfg.get('render_sep', '_'))
            self._set_status("Render set" + (f" +{extra}" if extra else ""), "#70aa70")
        except Exception as e:
            self._set_status("SET RENDER Error", "#e06060"); print(e)

    def _set_renderer_outputs(self, pub_dir, base, sep):
        """Apunta al publish las salidas que el renderer escribe por su cuenta.
        Solo actualiza rutas de salidas YA activas — no prende nada nuevo.
        Devuelve cuántas salidas extra se actualizaron (para el status)."""
        done = []
        r = rt.renderers.current
        rclass = str(rt.classOf(r)).lower()

        # Render Elements de Max (V-Ray, Corona, Scanline, Arnold legacy…)
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

        # V-Ray VFB: Raw image file y Separate render channels
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

        # Arnold: carpeta de salida del AOV Manager
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
            rt.loadMaxFile(f, useFileUnits=True, quiet=False)
            self._set_status("File loaded", "#70aa70")

    def save_scene_dialog(self):
        """Abre el Save dialog de Max en la carpeta del task con nombre versionado listo."""
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
        # Calcular nombre versionado: buscar el último _vXXX existente
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
        # Abrir el Save dialog de Max con el nombre ya listo — el usuario da Save
        f = rt.getSaveFileName(
            caption="Save Max Scene",
            filename=full_path,
            types="3ds Max(*.max)|*.max"
        )
        if f:
            rt.saveMaxFile(f)
            self._set_status("Saved", "#70aa70")

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

        # Crear subcarpetas dentro de projects/ para esta task específica
        for ps in proj_subs:
            os.makedirs(os.path.join(task_path, proj_sub, ps), exist_ok=True)
        # Si no había ninguna, crear igualmente el folder projects/
        if not proj_subs:
            os.makedirs(os.path.join(task_path, proj_sub), exist_ok=True)

        # Crear los demás subfolders (review, publish, extras)
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
            rt.rendOutputFilename = ""; rt.rendSaveFile = False; self._set_status("Reset")

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
                    # Actualizar solo la nota, sin escribir de vuelta a Max
                    m = next((p for p in self.state.get("res_presets",[])
                              if p['w']==mw and p['h']==mh), None)
                    self.res_note.setText(m['n'] if m else "")
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
            # FPS — solo lectura desde rt.frameRate
            try:
                fps = rt.frameRate
                fps_str = str(int(fps)) if fps == int(fps) else f"{fps:.2f}"
                self.fps_lbl.setText(f"{fps_str} FPS")
            except: self.fps_lbl.setText("— FPS")
            try:
                # rt.units.SystemType devuelve un Name como #centimeters, #meters, etc.
                unit_name = str(rt.units.SystemType)   # e.g. "#centimeters"
                unit_clean = unit_name.lstrip("#").capitalize()
                self.unit_lbl.setText(f"({unit_clean})")
            except: self.unit_lbl.setText("—")
            # Sync bidireccional project folder — si Max cambia el folder, actualizar dropdown
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
        """Lee el color real del viewport y actualiza el botón BG."""
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
        """Captura el viewport activo y lo guarda en la carpeta configurada de la task activa."""
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

            # ── Nombre: partes configurables + vNNN incremental ──────────────
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

            # Obtener nombre de cámara/vista
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

            # Ensamblar partes del nombre
            parts = []
            if inc_maxfile: parts.append(max_name)
            if inc_shot:    parts.append(shot)
            if inc_task:    parts.append(task_clean)
            if inc_camera:  parts.append(view_name)
            if not parts:   parts.append("snapshot")

            base = "_".join(parts)

            # Buscar el mayor vNNN existente para este base en la carpeta destino
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
                self._set_status("Snap OK", "#70aa70")
                print(f"[Snap] {out_path}")
            else:
                self._set_status("Snap failed", "#e06060")

        except Exception as e:
            self._set_status("Snap error", "#e06060")
            print(f"STM Snap error: {e}")

    def cleanup(self):
        """Detiene el polling y quita el callback de Max. Se llama al cerrar el dock;
        sin esto el timer seguía corriendo con el toolbar cerrado y el callback
        filePostOpen apuntaba a un widget muerto."""
        try: self.sync_timer.stop()
        except: pass
        try: rt.callbacks.removeScripts(id=rt.Name("STM_Sync"))
        except: pass
        try: rt.STM_GlobalRefresh = None
        except: pass

    def _load_current_max_settings(self):
        """Solo sincroniza res/film/fps/unit — NO toca pipeline."""
        try: self._master_sync()
        except: pass


# ── Pipeline Setup Dialog ─────────────────────────────────────────────────────
class PipelineSetupDialog(QtWidgets.QDialog):
    """
    Diálogo de configuración del pipeline.
    - Guarda config activa en  ~/.studio-toolbar/pipeline_config.ini
    - Guarda presets en        ~/.studio-toolbar/pipeline_presets.json
    """

    PRESETS_PATH = os.path.join(PIPE_DIR, "pipeline_presets.json")

    DIALOG_STYLE = f"""
        QDialog {{
            background-color: #2a2a2a;
            color: #d8d8d8;
            font-family: "Segoe UI", "Tahoma", sans-serif;
            font-size: 9pt;
        }}
        QGroupBox {{
            color: #909090;
            font-size: 8.5pt;
            font-weight: bold;
            border: 1px solid #444;
            border-radius: 3px;
            margin-top: 10px;
            padding-top: 6px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 8px;
            padding: 0 4px;
        }}
        QLabel {{ color: #909090; font-size: 8.5pt; background: transparent; }}
        QLineEdit, QListWidget, QComboBox {{
            background-color: #1e1e1e;
            color: #d8d8d8;
            border: 1px solid #555;
            border-radius: 2px;
            padding: 3px 6px;
            font-size: 9pt;
            selection-background-color: #4a6a8a;
        }}
        QLineEdit:focus, QListWidget:focus, QComboBox:focus {{ border-color: #7a7a7a; }}
        QComboBox::drop-down {{ border: none; width: 18px; }}
        QComboBox::down-arrow {{
            width:0; height:0;
            border-left:4px solid transparent; border-right:4px solid transparent;
            border-top:5px solid #777; margin-right:4px;
        }}
        QComboBox QAbstractItemView {{
            background-color: #1e1e1e; color: #d8d8d8;
            border: 1px solid #555; selection-background-color: #4a6a8a;
        }}
        QPushButton {{
            background-color: #3a3a3a;
            color: #d8d8d8;
            border: 1px solid #555;
            border-radius: 2px;
            padding: 4px 12px;
            font-size: 9pt;
        }}
        QPushButton:hover {{ background-color: #505050; border-color: #7a7a7a; }}
        QPushButton:pressed {{ background-color: #222; }}
        QPushButton#ok_btn {{
            background-color: #2a3a4a; color: #7ab8d8;
            border-color: #4a6a8a; font-weight: bold;
        }}
        QPushButton#ok_btn:hover {{ background-color: #3a5060; }}
        QPushButton#del_item_btn {{
            background-color: #3a2828; color: #cc6060;
            border-color: #6a3a3a; padding: 4px 8px;
        }}
        QPushButton#del_item_btn:hover {{ background-color: #583030; color: #ee7070; }}
        QPushButton#preset_save_btn {{
            background-color: #283828; color: #70aa70;
            border-color: #3a6a3a; padding: 4px 8px;
        }}
        QPushButton#preset_save_btn:hover {{ background-color: #385038; color: #88cc88; }}
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Pipeline Setup  —  Studio Toolbar for MAX  v{VERSION}")
        self.setMinimumWidth(560)
        self.setStyleSheet(self.DIALOG_STYLE)
        self.cfg = load_pipeline_cfg()
        self._build()
        # Instalar event filter en todos los QLineEdit del dialog
        # para que Enter no cierre ni resetee el dialog
        for child in self.findChildren(QtWidgets.QLineEdit):
            child.installEventFilter(self)

    def eventFilter(self, obj, event):
        """Consume Enter/Return en QLineEdit — no propaga al dialog."""
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

    # Sentinel para distinguir "nunca configurado" de "configurado como vacío"
    _PSUB_UNCONFIGURED = object()

    def _on_psub_task_changed(self, task_name):
        """Guarda la lista actual en el mapping, carga la del task seleccionado."""
        # Guardar el estado del task anterior antes de cambiar
        if hasattr(self, '_psub_last_task') and self._psub_last_task:
            items = [self.psub_list.item(i).text().strip()
                     for i in range(self.psub_list.count()) if self.psub_list.item(i).text().strip()]
            # Siempre guardar, aunque sea lista vacía — así se recuerda que se borró todo
            self._psub_mapping[self._psub_last_task] = items

        self._psub_last_task = task_name
        self.psub_list.clear()

        if task_name in self._psub_mapping:
            # Task ya configurada — cargar lo que tiene (puede ser lista vacía)
            for s in self._psub_mapping[task_name]:
                self.psub_list.addItem(s)
        else:
            # Task nunca tocada — cargar default y guardarlo ya en el mapping
            default = ["textures"]
            self._psub_mapping[task_name] = default
            for s in default:
                self.psub_list.addItem(s)

    def _sync_psub_task_combo(self):
        """Actualiza el combo de tasks en la sección psub cuando cambia la task list."""
        current = self.psub_task_cb.currentText()
        tasks = [self.task_list.item(i).text().strip()
                 for i in range(self.task_list.count()) if self.task_list.item(i).text().strip()]
        self.psub_task_cb.blockSignals(True)
        self.psub_task_cb.clear()
        for t in tasks: self.psub_task_cb.addItem(t)
        if current in tasks: self.psub_task_cb.setCurrentText(current)
        self.psub_task_cb.blockSignals(False)

    def _current_form_data(self):
        """Recopila los valores actuales del formulario como dict."""
        # Flush current psub task before collecting
        if hasattr(self, '_psub_last_task') and self._psub_last_task:
            items = [self.psub_list.item(i).text().strip()
                     for i in range(self.psub_list.count()) if self.psub_list.item(i).text().strip()]
            # Guardar siempre, incluyendo lista vacía
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
        """Carga un dict de config en todos los widgets del formulario."""
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
    def _build(self):
        root_layout = QtWidgets.QVBoxLayout(self)
        root_layout.setSpacing(10)
        root_layout.setContentsMargins(14, 14, 14, 14)

        # ── PRESETS BAR ───────────────────────────────────────────────────────
        grp_pre = QtWidgets.QGroupBox("Presets")
        gp = QtWidgets.QHBoxLayout(grp_pre)
        gp.setSpacing(6)

        self.preset_cb = QtWidgets.QComboBox()
        self.preset_cb.setToolTip("Load a saved pipeline configuration preset")
        self._refresh_preset_combo()

        self.ed_preset_name = QtWidgets.QLineEdit()
        self.ed_preset_name.setPlaceholderText("preset name…")
        self.ed_preset_name.setFixedWidth(160)

        btn_load_pre  = QtWidgets.QPushButton("Load")
        btn_save_pre  = QtWidgets.QPushButton("Save")
        btn_save_pre.setObjectName("preset_save_btn")
        btn_del_pre   = QtWidgets.QPushButton("Delete")
        btn_del_pre.setObjectName("del_item_btn")

        btn_load_pre.clicked.connect(self._load_preset)
        btn_save_pre.clicked.connect(self._save_preset)
        btn_del_pre.clicked.connect(self._delete_preset)

        gp.addWidget(self.preset_cb, 1)
        gp.addWidget(btn_load_pre)
        gp.addSpacing(8)
        gp.addWidget(self.ed_preset_name)
        gp.addWidget(btn_save_pre)
        gp.addWidget(btn_del_pre)
        root_layout.addWidget(grp_pre)

        # ── ROOT DRIVE & PREFIX ───────────────────────────────────────────────
        grp_root = QtWidgets.QGroupBox("Project Root")
        g1 = QtWidgets.QFormLayout(grp_root)
        g1.setSpacing(8)
        self.ed_drive  = QtWidgets.QLineEdit(self.cfg.get("root_drive", "T:"))
        self.ed_drive.setToolTip("Root drive or path where projects live  (e.g.  T:  or  //server/projects)")
        self.ed_prefix = QtWidgets.QLineEdit(self.cfg.get("project_prefix", "VFX-"))
        self.ed_prefix.setToolTip("Prefix that identifies project folders  (e.g.  VFX-  → folders named  VFX-MOR…)")
        g1.addRow("Drive / root path:", self.ed_drive)
        g1.addRow("Project prefix:", self.ed_prefix)
        root_layout.addWidget(grp_root)

        # ── EXCLUDED SEQUENCE FOLDERS ─────────────────────────────────────────
        grp_exc = QtWidgets.QGroupBox("Sequence — excluded folder names")
        g2 = QtWidgets.QVBoxLayout(grp_exc)
        g2.setSpacing(6)
        lbl_exc = QtWidgets.QLabel("Folders inside the project that are NOT sequences (comma-separated, case-insensitive):")
        lbl_exc.setWordWrap(True)
        self.ed_exclude = QtWidgets.QLineEdit(self.cfg.get("seq_exclude", "3D,SOURCE,FOOTAGE"))
        self.ed_exclude.setToolTip("e.g.  3D,SOURCE,FOOTAGE,AUDIO,RENDER")
        g2.addWidget(lbl_exc); g2.addWidget(self.ed_exclude)
        root_layout.addWidget(grp_exc)

        # ── TASKS ─────────────────────────────────────────────────────────────
        grp_tasks = QtWidgets.QGroupBox("Task folders (ordered list — drag to reorder, double-click to rename)")
        gt = QtWidgets.QVBoxLayout(grp_tasks); gt.setSpacing(6)
        self.task_list = QtWidgets.QListWidget()
        self.task_list.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        for t in [t.strip() for t in self.cfg.get("tasks","").split(",") if t.strip()]:
            self.task_list.addItem(t)
        self.task_list.setFixedHeight(140)
        self.task_list.itemDoubleClicked.connect(self._rename_item)
        self.task_list.model().rowsInserted.connect(self._sync_psub_task_combo)
        self.task_list.model().rowsRemoved.connect(self._sync_psub_task_combo)
        gt.addWidget(self.task_list)
        task_btn_row = QtWidgets.QHBoxLayout()
        self.ed_new_task = QtWidgets.QLineEdit(); self.ed_new_task.setPlaceholderText("new task name…")
        btn_add_t = QtWidgets.QPushButton("+ Add")
        btn_del_t = QtWidgets.QPushButton("Delete"); btn_del_t.setObjectName("del_item_btn")
        btn_add_t.clicked.connect(lambda: self._add_item(self.task_list, self.ed_new_task))
        btn_del_t.clicked.connect(lambda: self._del_item(self.task_list, "task"))
        task_btn_row.addWidget(self.ed_new_task); task_btn_row.addWidget(btn_add_t); task_btn_row.addWidget(btn_del_t)
        gt.addLayout(task_btn_row)
        root_layout.addWidget(grp_tasks)

        # ── SUBFOLDERS ────────────────────────────────────────────────────────
        grp_sub = QtWidgets.QGroupBox("Task subfolders (ordered — first=scenes, second=review, third=publish, extras optional)")
        gs = QtWidgets.QVBoxLayout(grp_sub); gs.setSpacing(6)
        self.sub_list = QtWidgets.QListWidget()
        self.sub_list.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self.sub_list.setToolTip("Drag to reorder. Double-click to rename. First 3 are scenes/review/publish.")

        # Poblar subcarpetas
        subs = []
        for key in ["sub_projects", "sub_review", "sub_publish"]:
            v = self.cfg.get(key, "").strip()
            if v: subs.append(v)
        for v in [v.strip() for v in self.cfg.get("extra_subs", "").split(",") if v.strip()]:
            subs.append(v)
        for s in subs:
            self.sub_list.addItem(s)
        self.sub_list.setFixedHeight(110)
        self.sub_list.itemDoubleClicked.connect(self._rename_item)
        self.sub_list.model().rowsInserted.connect(self._refresh_thumb_sub_combo)
        self.sub_list.model().rowsRemoved.connect(self._refresh_thumb_sub_combo)
        gs.addWidget(self.sub_list)

        sub_btn_row = QtWidgets.QHBoxLayout()
        self.ed_new_sub = QtWidgets.QLineEdit(); self.ed_new_sub.setPlaceholderText("new subfolder name…")
        btn_add_s = QtWidgets.QPushButton("+ Add")
        btn_del_s = QtWidgets.QPushButton("Delete"); btn_del_s.setObjectName("del_item_btn")
        btn_add_s.clicked.connect(lambda: self._add_item(self.sub_list, self.ed_new_sub))
        btn_del_s.clicked.connect(lambda: self._del_item(self.sub_list, "subfolder"))
        sub_btn_row.addWidget(self.ed_new_sub); sub_btn_row.addWidget(btn_add_s); sub_btn_row.addWidget(btn_del_s)
        gs.addLayout(sub_btn_row)

        root_layout.addWidget(grp_sub)

        # ── PROJECTS SUBFOLDERS PER TASK ──────────────────────────────────────
        grp_psub = QtWidgets.QGroupBox("Subfolders inside  'projects/'  per task")
        gps = QtWidgets.QVBoxLayout(grp_psub); gps.setSpacing(6)

        lbl_psub = QtWidgets.QLabel(
            "Select a task to configure which subfolders get created inside its  projects/  folder.\n"
            "Default for tasks not listed here:  textures")
        lbl_psub.setWordWrap(True)
        gps.addWidget(lbl_psub)

        # Row: task selector + list + buttons
        psub_row = QtWidgets.QHBoxLayout(); psub_row.setSpacing(8)

        # Left: task selector
        left_col = QtWidgets.QVBoxLayout()
        lbl_pick = QtWidgets.QLabel("Task:")
        self.psub_task_cb = QtWidgets.QComboBox()
        self.psub_task_cb.setMinimumWidth(160)
        for t in [t.strip() for t in self.cfg.get("tasks","").split(",") if t.strip()]:
            self.psub_task_cb.addItem(t)
        left_col.addWidget(lbl_pick)
        left_col.addWidget(self.psub_task_cb)
        left_col.addStretch()
        psub_row.addLayout(left_col)

        # Right: subfolder list for selected task
        right_col = QtWidgets.QVBoxLayout()
        self.psub_list = QtWidgets.QListWidget()
        self.psub_list.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self.psub_list.setToolTip("Subfolders to create inside this task's  projects/  folder.\nDrag to reorder, double-click to rename.")
        self.psub_list.setFixedHeight(100)
        self.psub_list.itemDoubleClicked.connect(self._rename_item)
        right_col.addWidget(self.psub_list)

        psub_btn_row = QtWidgets.QHBoxLayout()
        self.ed_new_psub = QtWidgets.QLineEdit(); self.ed_new_psub.setPlaceholderText("subfolder name…")
        btn_add_ps = QtWidgets.QPushButton("+ Add")
        btn_del_ps = QtWidgets.QPushButton("Delete"); btn_del_ps.setObjectName("del_item_btn")
        btn_add_ps.clicked.connect(lambda: self._add_item(self.psub_list, self.ed_new_psub))
        btn_del_ps.clicked.connect(lambda: self._del_item(self.psub_list, "subfolder"))
        psub_btn_row.addWidget(self.ed_new_psub); psub_btn_row.addWidget(btn_add_ps); psub_btn_row.addWidget(btn_del_ps)
        right_col.addLayout(psub_btn_row)
        psub_row.addLayout(right_col)
        gps.addLayout(psub_row)
        root_layout.addWidget(grp_psub)

        # Load/save per-task data when task selection changes
        # Store the mapping in memory while editing
        self._psub_mapping = {}
        raw = self.cfg.get("task_projects_subs", "")
        if raw:
            try: self._psub_mapping = json.loads(raw)
            except: pass

        self.psub_task_cb.currentTextChanged.connect(self._on_psub_task_changed)
        # Trigger initial load
        if self.psub_task_cb.count() > 0:
            self._on_psub_task_changed(self.psub_task_cb.currentText())

        # ── VIEWPORT SNAPSHOT ─────────────────────────────────────────────────
        grp_snap = QtWidgets.QGroupBox("Viewport Snapshot")
        gsnap = QtWidgets.QVBoxLayout(grp_snap); gsnap.setSpacing(8)

        lbl_snap_desc = QtWidgets.QLabel(
            "Destination subfolder and filename options for viewport snapshots.")
        lbl_snap_desc.setWordWrap(True)
        gsnap.addWidget(lbl_snap_desc)

        # Row 1: subfolder selector
        row1 = QtWidgets.QHBoxLayout()
        lbl_dest = QtWidgets.QLabel("Save into:")
        self.thumb_sub_cb = QtWidgets.QComboBox()
        self.thumb_sub_cb.setMinimumWidth(160)
        self.thumb_sub_cb.setToolTip("Which task subfolder receives the snapshots")
        for s in subs:
            self.thumb_sub_cb.addItem(s)
        saved_thumb = self.cfg.get("thumb_subfolder", subs[1] if len(subs) > 1 else "")
        if saved_thumb:
            idx = self.thumb_sub_cb.findText(saved_thumb)
            if idx >= 0: self.thumb_sub_cb.setCurrentIndex(idx)
        row1.addWidget(lbl_dest); row1.addWidget(self.thumb_sub_cb); row1.addStretch()
        gsnap.addLayout(row1)

        # Row 2: optional sub-subfolder
        row2 = QtWidgets.QHBoxLayout()
        lbl_subf = QtWidgets.QLabel("Sub-subfolder (optional):")
        self.ed_thumb_subdir = QtWidgets.QLineEdit()
        self.ed_thumb_subdir.setPlaceholderText("e.g.  captures   (leave empty to save directly in subfolder above)")
        self.ed_thumb_subdir.setText(self.cfg.get("thumb_subdir", ""))
        self.ed_thumb_subdir.setToolTip("If set, snapshots go into  task / subfolder / <this>  —  folder is created automatically")
        row2.addWidget(lbl_subf); row2.addWidget(self.ed_thumb_subdir, 1)
        gsnap.addLayout(row2)

        # Row 3: filename components checkboxes
        lbl_fname = QtWidgets.QLabel("Filename includes:")
        gsnap.addWidget(lbl_fname)

        chk_row = QtWidgets.QHBoxLayout()
        self.chk_snap_maxfile  = QtWidgets.QCheckBox("Max filename")
        self.chk_snap_shot     = QtWidgets.QCheckBox("Shot name")
        self.chk_snap_task     = QtWidgets.QCheckBox("Task")
        self.chk_snap_camera   = QtWidgets.QCheckBox("Camera / view")

        self.chk_snap_maxfile.setChecked(self.cfg.get("snap_inc_maxfile",  True)  if isinstance(self.cfg.get("snap_inc_maxfile",  True),  bool) else self.cfg.get("snap_inc_maxfile",  "true").lower()  != "false")
        self.chk_snap_shot.setChecked(   self.cfg.get("snap_inc_shot",     False) if isinstance(self.cfg.get("snap_inc_shot",     False), bool) else self.cfg.get("snap_inc_shot",     "false").lower() == "true")
        self.chk_snap_task.setChecked(   self.cfg.get("snap_inc_task",     False) if isinstance(self.cfg.get("snap_inc_task",     False), bool) else self.cfg.get("snap_inc_task",     "false").lower() == "true")
        self.chk_snap_camera.setChecked( self.cfg.get("snap_inc_camera",   True)  if isinstance(self.cfg.get("snap_inc_camera",   True),  bool) else self.cfg.get("snap_inc_camera",   "true").lower()  != "false")

        self.chk_snap_maxfile.setToolTip("Include the Max filename in the snapshot name")
        self.chk_snap_shot.setToolTip("Include the shot name")
        self.chk_snap_task.setToolTip("Include the task/department name")
        self.chk_snap_camera.setToolTip("Include the camera or viewport name")

        for chk in [self.chk_snap_maxfile, self.chk_snap_shot, self.chk_snap_task, self.chk_snap_camera]:
            chk_row.addWidget(chk)
        chk_row.addStretch()
        gsnap.addLayout(chk_row)

        lbl_preview = QtWidgets.QLabel("Result:  maxfile_Camera001_v001.jpg")
        lbl_preview.setStyleSheet("color: #555; font-size: 7.5pt; font-style: italic; background: transparent;")
        gsnap.addWidget(lbl_preview)
        self._snap_preview_lbl = lbl_preview

        # Update preview when checkboxes change
        for chk in [self.chk_snap_maxfile, self.chk_snap_shot, self.chk_snap_task, self.chk_snap_camera]:
            chk.toggled.connect(self._update_snap_preview)
        self._update_snap_preview()

        # ── Render filename separator ─────────────────────────────────────
        grp_render = QtWidgets.QGroupBox("Render Output")
        g_render   = QtWidgets.QHBoxLayout(grp_render); g_render.setSpacing(8)
        lbl_sep    = QtWidgets.QLabel("Frame separator:")
        lbl_sep.setStyleSheet("background: transparent;")
        self.render_sep_cb = QtWidgets.QComboBox()
        self.render_sep_cb.addItems(["_  (underscore)  shot_v001_0001.exr",
                                     ".  (dot)         shot_v001.0001.exr"])
        cur_sep = self.cfg.get("render_sep", "_")
        self.render_sep_cb.setCurrentIndex(0 if cur_sep == "_" else 1)
        self.render_sep_cb.setFixedHeight(H)
        g_render.addWidget(lbl_sep)
        g_render.addWidget(self.render_sep_cb, 1)
        root_layout.addWidget(grp_render)

        root_layout.addWidget(grp_snap)

        # ── INI PATH INFO ─────────────────────────────────────────────────────
        lbl_path = QtWidgets.QLabel(f"Config:  {PIPELINE_CFG}     Presets:  {self.PRESETS_PATH}")
        lbl_path.setStyleSheet("color: #555; font-size: 7.5pt; background: transparent;")
        root_layout.addWidget(lbl_path)

        # ── OK / CANCEL ───────────────────────────────────────────────────────
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch()
        btn_cancel = QtWidgets.QPushButton("Cancel")
        btn_ok     = QtWidgets.QPushButton("Save && Apply")
        btn_ok.setObjectName("ok_btn")
        btn_cancel.setAutoDefault(False); btn_cancel.setDefault(False)
        btn_ok.setAutoDefault(False);     btn_ok.setDefault(False)
        btn_cancel.clicked.connect(self.reject)
        btn_ok.clicked.connect(self._save_and_accept)
        btn_row.addWidget(btn_cancel); btn_row.addSpacing(8); btn_row.addWidget(btn_ok)
        root_layout.addLayout(btn_row)

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
        """Repuebla el combo de snapshot destination con los subfolders actuales."""
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
        """Actualiza el label de preview del nombre del snapshot."""
        parts = []
        if self.chk_snap_maxfile.isChecked():  parts.append("maxfile")
        if self.chk_snap_shot.isChecked():     parts.append("shot")
        if self.chk_snap_task.isChecked():     parts.append("task")
        if self.chk_snap_camera.isChecked():   parts.append("Camera001")
        if not parts: parts.append("snapshot")
        self._snap_preview_lbl.setText(f"Result:  {'_'.join(parts)}_v001.jpg")

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
        # Seleccionar el preset recién guardado
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
        data = self._current_form_data()
        save_pipeline_cfg(data)
        self.accept()


# ── Dock ─────────────────────────────────────────────────────────────────────
class STMDock(QtWidgets.QDockWidget):
    """Dock que se destruye al cerrarlo (X) y limpia timer/callbacks del toolbar."""
    def closeEvent(self, event):
        w = self.widget()
        if w is not None and hasattr(w, "cleanup"):
            w.cleanup()
        super().closeEvent(event)

def show_studio_toolbar():
    main  = GetQMaxMainWindow()
    title = f"Studio Toolbar for MAX  v{VERSION}"
    # Cerrar cualquier instancia previa (actual o legacy) para no duplicar el toolbar
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
        QtWidgets.QDockWidget.DockWidgetClosable
    )
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
            background: #333333;
            border-bottom: 1px solid {MX_SEP};
            padding-left: 6px;
            padding-top: 1px;
        }}
    """)
    # Esquinas superiores al área top — dock ocupa todo el ancho de punta a punta
    main.setCorner(QtCore.Qt.TopLeftCorner,  QtCore.Qt.TopDockWidgetArea)
    main.setCorner(QtCore.Qt.TopRightCorner, QtCore.Qt.TopDockWidgetArea)
    main.addDockWidget(QtCore.Qt.TopDockWidgetArea, dock)

    # Permitir re-dockeo: cuando el dock vuelve a ser top-level (flotante)
    # y el usuario lo arrastra de vuelta, Qt lo maneja solo con DockWidgetMovable.
    # El problema es setFixedHeight — al flotar necesita altura libre, al dockear vuelve fija.
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
