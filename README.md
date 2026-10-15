# Studio Toolbar for 3ds Max

A dockable pipeline toolbar for **3ds Max** built with Python / PySide6.  
Designed for VFX studios — manages resolution, film size, FPS, pipeline navigation, and shot actions from a single persistent dock.

![Studio Toolbar](docs/screenshot.png)

---

## Features

| Section | What it does |
|---|---|
| **Tools** | Quick-launch buttons: Overscan, Image Plane, Remove Background, Show Textures, Bake Camera, Studio Library — plus a **TOOLS ▾** menu that lists every script in `tools/` (subfolders become submenus) |
| **Resolution** | W×H spinners, live aspect ratio, aspect lock, ×2 / ½. Preset list (arrow inside the label field) with your saved presets and standard formats (HD, UHD, DCI 2K/4K, Scope, square, vertical…) |
| **Film gate** | Reads/writes aperture for Standard, V-Ray and Physical cameras. Preset list includes common cinema sensor widths (ARRI Alexa 35 / Mini / Mini LF, RED V-Raptor / Komodo, Sony Venice 2, Blackmagic, Super 35…) |
| **FPS / Units** | Live sync; click FPS to switch frame rate |
| **Pipeline** | Project → Sequence → Shot → Task dropdowns from the filesystem, **+** to create task folders, folder button to open shot / task / subfolders in Explorer |
| **Viewport Snapshot** | Saves a `.jpg` of the active viewport — configurable filename parts and destination. Right-click opens the snapshots folder |
| **Actions** | **OPEN ▾** (browse, or pick a recent version of the task) · **SAVE ▾** (dialog, or save next version in one click) · **GET** (reads shot/task from the open file — glows amber when the dropdowns don't match the open file) · **PATHS** (project paths, stored in the .max and restored on open) · **SET RENDER** (publish output incl. render elements / V-Ray / Arnold; asks before overwriting) · **RESET** |
| **Status** | Coloured result of the last action; click for a history with full paths (click an entry to copy) |
| **Setup** | Full pipeline config dialog with preset save/load |

---

## Requirements

- **3ds Max 2024+** (PySide6)
- **pymxs** + **qtmax** (bundled with Max)
- Python 3.x (bundled with Max)

---

## Installation

1. Copy this repo to your studio's shared drive, e.g.:
   ```
   T:\.studio-toolbar\max\
   ```

2. Edit the **USER CONFIG** block at the top of `StudioToolbar-max.py` to match your pipeline:
   ```python
   CFG_ROOT_DRIVE     = "T:"          # where your projects live
   CFG_PROJECT_PREFIX = "VFX-"        # folder prefix, e.g. VFX-MOR
   CFG_TASKS          = [...]          # your department folders
   ```

3. Update the tool paths to point to your copies of the helper scripts:
   ```python
   PATH_OVERSCAN    = r"T:\.studio-toolbar\max\maintools\STM_Overscan.ms"
   PATH_IMAGE_PLANE = r"T:\.studio-toolbar\max\maintools\STM_ImagePlane.ms"
   # etc.
   ```

4. Run from MAXScript:
   ```maxscript
   python.ExecuteFile @"T:\.studio-toolbar\max\StudioToolbar-max.py"
   ```

5. Or add a toolbar button in Max pointing to that MAXScript line.

---

## Folder Structure

```
StudioToolbar-max.py     ← main script (run this)
maintools/               ← MAXScript helpers called by toolbar buttons
  STM_Overscan.ms
  STM_ImagePlane.ms
  STM_RemoveBack.ms
  STM_ShowTextures.ms
  STM_BakeAlembic.ms
  STM_StudioLibraryMAX.py
tools/                   ← optional extra tools
  STM_CarRig.ms
  STM_SuperAttach.ms
docs/                    ← screenshots and documentation
```

---

## Pipeline Config

On first run the toolbar creates `~/.studio-toolbar/` with three files:

| File | Purpose |
|---|---|
| `pipeline_state.ini` | Saves last used resolution/film presets and pipeline state |
| `pipeline_config.ini` | Active pipeline config (written by the Setup ⚙ dialog) |
| `pipeline_presets.json` | Named pipeline presets you save from the Setup dialog |

The **Setup dialog** (⚙ button at the right of the toolbar) lets you configure everything without editing the script — and save/load named presets for different projects or studios.

---

## Expected Folder Structure on Disk

```
T:/
  VFX-MOR/
    101/
      010/
        3D/
          8_lighting/
            1_projects/
            2_review/
            3_publish/
```

---

## Viewport Snapshot

The camera icon button captures the active viewport and saves a `.jpg` to the configured task subfolder.

Filename format is configurable via the Setup dialog — you can toggle which parts are included:
- ☑ Max filename
- ☐ Shot name  
- ☐ Task
- ☑ Camera / view name

Example: `MOR_010_0010_lighting_v003_A_cam_001_v001.jpg`

---

## Version

Current: **v2.5.35**  
See [CHANGELOG.md](CHANGELOG.md) for history.

---

## Author

**Javi Bravo** — VFX / Motion Graphics  
