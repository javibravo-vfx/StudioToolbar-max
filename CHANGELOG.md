# Changelog — Studio Toolbar for 3ds Max

## v2.8.7 — Lookdev Rig 0.7.0
- **Any folder as HDRI library** (top bar): pick a collection (e.g. on the NAS) to try HDRIs without copying them, and switch back to the Studio library. Recent folders are remembered. Sub-folders show as a FOLDERS tree in the sidebar and are searchable
  - Nothing is written into those folders: previews, blurred backgrounds and "Save as HDRI default" go to a local cache (`~/.studio-toolbar/lookdev_cache/`). Only the optional Arnold `.tx` is written next to the source
  - Refresh library asks before processing a big collection; it can be cancelled and resumed
  - The rig stores the HDRI's full path, so live controls and Save default work with any library
- **Right panel tidied:** aligned label / control columns, sections Rig · References · Dome; fixed-height HDRI details (nothing jumps when switching HDRIs), long text elided with full text in the tooltip, wider minimum width (no cut text), value boxes sized to their content and aligned, colour swatch the same height as the Background list
- `dev/test_lookdev.py`: external library checks (84 checks)

## v2.8.6 — Lookdev Rig 0.6.0
- **Delete rig leaves no trace:** the `LOOKDEV_RIG` layer is removed too (after restoring materials and scene background)
- **Rig layer frozen** so it can't be picked by accident, with *Show Frozen in Gray* off — it stays in colour in the viewport. The tool itself still updates it (refs, dome, background)
- **Background mode** (replaces the checkbox): HDRI / **Blurred HDRI** / Colour. Blurred uses the library copy (`_cache/<name>.bg.exr`, made by Refresh library) on a second dome that only the camera sees (`LKD_dome_bg`), so lighting and reflections stay sharp; it follows rotation, exposure, HDRI swaps and the turntable. HDRIs without a blurred copy fall back to HDRI
- **Presets:** shown by label; new **Turntable · clockwise** next to the default (counter-clockwise). The HDRI pass now spins in the same direction as the object pass
- `dev/test_lookdev.py`: 77 checks

## v2.8.5 — Lookdev Rig 0.5.0
- **References, live on the rig:** toggle Chrome / Grey / Chart individually (the rest pack towards the corner), pick the corner (bottom right default, bottom left, top right, top left) and the chart — only the references are rebuilt, the rest of the rig stays
- **Charts are data:** every `*.json` with patches in `shared\lookdev\reference\` shows in the Chart list (every toolbar). Patches can sit anywhere on a rows × cols grid and be given as CIELAB D50 (as X-Rite / Calibrite publish them), 8-bit sRGB or linear. `_TEMPLATE_chart.json` documents the format
- **Background colour when the dome is hidden:** colour swatch next to "Background visible in render" (default 18% grey). Sets the scene background colour (and turns the environment map off while hidden); the original scene background comes back when the dome is visible again or the rig is deleted
- Remembers refs, corner, chart and background colour with the other window settings
- `dev/test_lookdev.py`: 68 checks

## v2.8.4 — Lookdev Rig 0.4.0
- **Fix (V-Ray): the dome didn't rotate.** "Lock texture to icon" is now ticked on `LKD_dome` at build; without it the HDRI stays fixed in world space and neither the Rotation slider nor the HDRI turntable did anything. If a V-Ray build names the option differently, the window says so
- **New layout, Studio Library style** (same palette as StudioLibrary MAX): top bar with search (name / label / tags), renderer badge, Refresh library, Open folder · sidebar with All / Missing preview / tags from the sidecars · thumbnail grid · right panel · status bar
- **Resizable thumbnails:** size slider in the status bar or Ctrl + mouse wheel on the grid (96–512 px); never wider than the grid. Panels resizable with splitters; the preview scales with the right panel
- **Rig options moved to the right panel** (Preset, Turntable, Shadow catcher, Clay, Build / Delete) above the live dome controls
- **Remembers** window position and size, panel sizes, thumbnail size, sidebar filter, preset, last HDRI and rig options (`~/.studio-toolbar/lookdev_rig.ini`); re-centred if that monitor is gone
- Status bar with coloured result dot; click it for the message history. Right-click an HDRI: Build rig / Use on the rig / Show in folder. Double-click a slider resets it

## v2.8.3 — Lookdev Rig 0.3.0
- **Live dome controls** (right panel, act on the built rig without rebuilding): pick another HDRI in the grid and only the dome texture is swapped; Rotation, Exposure (EV) and "Background visible in render" (off = dome still lights, render gets alpha)
- **Save as HDRI default:** writes the current rotation and intensity into the HDRI `.json` sidecar in the shared library, so every toolbar (Max, Houdini, Blender, Maya) starts from them
- **Big preview** of the selected HDRI with its defaults and tags
- **Refresh library:** generates, for every HDRI missing them, a 512×256 auto-exposed thumbnail and a blurred low-res background into `hdri\_cache\` (shared by every DCC). Menu: Missing + Arnold `.tx` (uses MAXtoA's maketx when found), Rebuild all previews. Uses Max's own bitmap loaders, no extra dependencies; hand-made `.jpg` thumbnails next to the HDRI always win
- Rig: dome now sits under `LKD_hdri_spin` (the turntable spins the pivot), so the HDRI rotation can change live without re-keying
- Shared: `studio_lookdev/library.py` (what to regenerate + tonemap / blur math; DCCs only provide image read/write)
- `dev/test_lookdev.py`: live controls, sidecar saving and library checks (55 checks)

## v2.8.2 — Lookdev Rig 0.2.0
- **Shadow catcher:** ground plane under the asset that only shows shadows (V-Ray: VRayMtlWrapper matte with alpha -1; Arnold: ai_shadow_matte). Orbits with the rig so ground and light stay fixed to the camera. Toggle in the dialog or `ground.shadow_catcher` in the preset
- **Use the selected camera:** select a camera together with the asset and the rig takes its framing (`LKD_cam` copies its transform and FOV, so the turntable never moves the original). Works with any camera type; the dialog shows which camera will be used
- **Clay:** live toggle that swaps the asset materials for a grey diffuse (`clay.albedo`, 0.18 default); refs untouched. Originals are stored on the hidden `LKD_store` node (saved with the .max) and come back when clay is turned off, the rig is rebuilt or deleted
- Shared preset gains `ground` and `clay` sections; shared core and data now in English
- `dev/test_lookdev.py`: fake-pymxs end-to-end test of build / clay / remove, selected camera, V-Ray, Arnold and stub engines (35 checks)

## v2.8.1
- **Bake Camera** moved off the bar: now in **TOOLS ▾** (under Show Textures) and in the right-click menu — its slot is used by Lookdev Rig, so the toolbar keeps the v2.7.0 width
- `dev/test_features.py`: Bake Camera menu checks

## v2.8.0
- **New: Lookdev Rig** (TOOLS section, after Bake Camera) — select an asset and build a lookdev / turntable setup around it
  - Camera framed automatically from the asset's bounding sphere (works for any size; uses render aspect)
  - Chrome ball, 18% grey ball and a procedural 24-patch ColorChecker (values converted to ACEScg), parented to the camera at a fixed size on screen
  - Dome light with an HDRI picked from the shared library `T:\.studio-toolbar\shared\lookdev\hdri\` (optional `.json` sidecar for rotation offset / intensity, `.jpg` thumbnail)
  - Turntable without touching the asset: camera + refs + dome orbit together (object pass), then only the dome spins (HDRI pass)
  - Detects the renderer: V-Ray and Arnold implemented; Redshift and Octane adapters registered as stubs
  - Everything lives on layer `LOOKDEV_RIG` with prefix `LKD_`; rebuilding replaces it, **Delete rig** removes it; one Undo step
- Code: `maintools/STM_LookdevRig.py` (launcher) + `maintools/studio_lookdev_max/`; the DCC-agnostic core, presets and HDRIs live in `T:\.studio-toolbar\shared\` so the Houdini / Blender / Maya toolbars read the same data
- `dev/test_features.py`: Lookdev button checks

## v2.7.0
- **New: Paste Cam** (TOOLS section) — creates the camera copied with the Copy button of 3D Camera Pin
  - Reads the clipboard; if it is empty or doesn't contain "Camera Pin", warns and runs nothing
  - Runs the MAXScript inside one Undo record ("Paste Camera Pin" — Ctrl+Z removes the camera)
  - Status shows `Camera pasted: <name>` (full name in the tooltip / history); script errors open a dialog
- **Show Textures** moved off the bar (rarely used): now in **TOOLS ▾** (top item) and in the new right-click menu on the toolbar background (which also opens Pipeline Setup)
- Toolbar width unchanged

## v2.6.6 — StudioLibrary MAX 2.1.1
- StudioLibrary remembers window position/size, last folder and last pose, and reopens exactly there (re-centred if that monitor is gone)
- Opening StudioLibrary again brings the open window to the front instead of creating a second window
- Fix: changing folder kept the previous folder's pose as current (Apply could use it)

## v2.6.5
- Fix: `.mse` (encrypted MAXScript) scripts listed in TOOLS ▾ did nothing when clicked — they now run like `.ms`

## v2.6.4 — StudioLibrary MAX 2.1.0
- **Fix: poses of linked objects needed two pastes.** Poses were applied in selection order in world space, so a child placed before its parent got dragged away when the parent moved. Objects are now applied parents-first — one paste is enough
- Poses store full transforms (world + parent-relative). Default apply is relative to the parent (the pose follows the rig, like Maya's Studio Library); new **World space** option for the exact captured positions. Old poses still apply
- Apply Pose is one Undo step; Key uses pymxs animate / at time instead of generated MAXScript
- If some of the pose's objects are selected, only those receive it (status says "selected only")
- Mirror swaps L/R objects (L/R, Left/Right, Lft/Rgt) when the counterpart exists
- Duplicate object names: the selected one wins
- Thumbnail capture no longer changes display gamma, shading mode or viewport framing; previews stored at max 480 px (grid loads faster)
- Pose/folder names validated; failed saves leave no empty folders
- Comment saved 0.8 s after typing stops (it rewrote the JSON on every key and every time a pose was selected)
- Options remembered between sessions; checked boxes clearly visible; new context-menu **Select Objects**
- Renaming objects in a pose also updates parent references
- `dev/test_studiolibrary.py`: simulated Max scene with real parent/child behaviour (17 tests)

## v2.6.3
- **Install:** `startup/StudioToolbar-max_Start.ms` — copy into a Max `scripts\startup` folder so the toolbar opens with 3ds Max (checks the path and reports in the Listener if the toolbar file is missing). README has the per-user and all-users folders
- **Everything in English:** comments, docstrings and on-screen text of the toolbar and every bundled script (CarRig UI, StudioLibrary messages, MAXScript helpers). Verified with `dev/check_text_only.py`: only comments/strings changed, code identical
  - CarRig: internal identifiers and scene data keys untouched (existing rigs keep working); the viewport label now reads FRONT on newly created rigs
  - StudioLibrary re-saved as UTF-8 (it was cp1252 with a utf-8 header); lost placeholder glyph restored
- `dev/check_text_only.py`: verifies a change touched only comments/strings, and flags single-word strings that could be data keys

## v2.6.2
- Setup dialog: shrinking the window no longer squashes text — buttons and labels keep their text width (with Max's real font) and the dialog stops at its content's minimum size

## v2.6.1
- **Setup dialog redesigned:** sidebar with four pages (Project · Tasks · Folders · Output) instead of one 1280 px column
  - Project: Browse… for the root, live check — lists the projects found or warns if the root doesn't exist
  - Tasks: task list and its scenes-subfolders side by side — select a task to edit its subfolders
  - Folders: live preview of the resulting folder tree, with roles (scenes / review / renders / snapshots)
  - Output: snapshots (destination, name parts, example) and render frame separator
  - Footer: preset combo · Load · Save as… · delete · Config folder · Cancel · Save & Apply
- **Fix:** Save & Apply no longer wipes other settings stored in the same file (custom viewport BG colour presets were reset to defaults)
- Toolbar: FPS no longer truncated ("3…S"), "mm" no longer cut to "mn", bigger and bolder mini icons and spinner arrows, proper gear icon
- Width kept below v2.5 (shot dropdown slightly narrower)

## v2.6.0 — redesign (branch `v2.6`)
**Look**
- Dock title bar is now a vertical handle on the left → toolbar is 16 px shorter (still draggable / floatable)
- Small buttons use crisp SVG icons instead of letters/emoji: save, delete, lock, ×2, ½, +, folder, setup
- Combo / spinner / menu arrows are real chevrons (CSS triangles rendered as "=" bars in Qt)
- Status shows a coloured dot; text fades back to grey, the dot keeps the result colour
- Overall width slightly *narrower* than v2.5 despite the new controls

**Resolution & film gate**
- Preset list opens from an arrow inside the label field (replaces the separate L button)
- Built-in presets under your saved ones: standard resolutions and cinema camera sensor widths
- Label shows the matching preset name automatically (yours first, then built-in)
- Live aspect ratio next to W×H

**Pipeline & actions**
- Folder button: open Shot / Task / task subfolders / snapshots folder in Explorer
- OPEN ▾: recent .max versions of the selected task (asks to save changes first)
- SAVE ▾: save next version in one click (no dialog)
- GET glows amber when the open file belongs to a different shot/task than the dropdowns
- FPS is clickable: 24 / 25 / 30 / 48 / 50 / 60
- Snapshot button: right-click → open snapshots folder
- Status history (click the status): last 25 actions with time and full path; click to copy

## v2.5.42
- **AUTO → SHOT NAME.** Same function, clearer name: when ON, SET RENDER names the render after the dropdowns (`shot_task_v###`) instead of the open .max — for rendering several shots from one scene. State is remembered between sessions
- **INC removed.** The render version is always the .max version. If that version folder already has renders, SET RENDER asks: **Overwrite / New version / Cancel** (New version = next free number) instead of silently overwriting or silently bumping

## v2.5.41
- Fix: stored paths were skipped when the task couldn't be read from the file location (`3D` vs `3d`, or file not inside a task folder). Comparison is now case-insensitive and the task is only required when the file sits inside a task folder; project/seq/shot must always match
- GET also reads the task when the folder is `3d` (lowercase)

## v2.5.40
- Stored project paths are only restored if the file is still in the same project / sequence / shot / task they were saved for. A file copied or saved-as into another shot no longer gets the old shot's paths → status `Paths skipped` (reason printed to the Listener)
- Stamp now records project/seq/shot/task; v2.5.39 stamps are still understood
- GET and the restore check share one path parser (`_parse_pipeline_path`)

## v2.5.39
- **Project paths travel with the .max file.** 3ds Max does not store Project Paths in the scene, so after a reset, reopening a file showed whatever paths the session had.
  - Set Paths now also stores the paths (and the project folder) in the scene's AppData
  - On file open, after GET, stored paths are re-applied automatically → status `Paths restored`
  - Only files where Set Paths was used (and then saved) are affected
  - Toolbar Reset also removes the stored paths from the current scene

## v2.5.38
- **Set Render** now also points renderer-owned outputs to the publish folder (only outputs already enabled — nothing is switched on):
  - Max Render Elements → `<version>_<Element><sep>.exr`
  - V-Ray VFB Raw image file and Separate render channels
  - Arnold AOV Manager output path
  - Status shows `Render set +N` when extra outputs were updated; details printed to the Listener
- **TOOLS ▾** menu:
  - Subfolders inside `tools/` appear as submenus (empty ones hidden; `_` / `.` prefixed ignored)
  - Hover tooltip with the script's description, read from its header
  - `Open tools folder…` entry at the bottom
  - `.mse` (encrypted MAXScript) supported

## v2.5.37
- Fix: closing the toolbar (X) now really destroys it — the 500 ms sync timer and the `filePostOpen` callback no longer keep running / pointing at a dead widget
- Fix: startup no longer fires the project → sequence → shot chain once per list item (could pop "Create 3D folder?" for the wrong project)
- Fix: snapshot and Save Scene versioning match the exact base name (`cam` no longer counts `cam2` versions)
- Fix: GET matches the shot exactly and reports `Project not listed` instead of a false `GET OK`
- Perf: `pipeline_config.ini` cached by file mtime (was parsed from disk twice every 500 ms)
- `.py` tools run as real modules (`compile` + `exec`) with `__file__`, full tracebacks, UTF-8/cp1252 decoding, and their namespace kept alive
- Config read/write errors are printed instead of silently ignored

## v2.5.36
- New: **TOOLS ▾** dropdown — lists every `.ms`/`.py` in `tools/` (scanned on open, no code changes needed to add scripts)
- Fix: re-running the script no longer stacks duplicate toolbars (old dock is now detected and closed)
- Internal rename `Pipe3D` → `STM`: class `StudioToolbar`, `show_studio_toolbar()`, `STM_GlobalRefresh`, callback id `STM_Sync`, dock objectName `STM_ToolbarDock`
  - Legacy `Pipe3DSync` callback and `Pipe3DShotManagerDock` are still cleaned up automatically
  - Note: dock position must be re-arranged once after updating (new objectName)
- All MAXScript tools use the `STM_` prefix; SuperAttach globals namespaced as `STM_SA_*`
- `QMenu.exec_()` → `exec()` (PySide6)

## v2.5.35
- Viewport snapshot filename components configurable via Setup dialog (checkboxes)
- Viewport type names cleaned up: `persp_user` → `persp`, etc.
- Camera name taken directly from `cam_obj.name` (no type prefix, no coordinates)
- Status bar shows `Snap OK` instead of full filename
- Enter key in Setup dialog QLineEdits does `clearFocus()` instead of closing dialog
- Viewport Snapshot section separated into its own QGroupBox in Setup
- Optional sub-subfolder field for snapshot destination (e.g. `captures`)

## v2.5.3
- Fix: `persp_user` mapped to `persp` in viewport type names

## v2.5.2
- Snapshot filename components: 4 checkboxes in Setup (Max filename, Shot, Task, Camera/view)
- Live preview label in Setup showing resulting filename
- Status back to `Snap OK` (no full path)

## v2.5.1
- Camera name from `cam_obj.name` directly — no type prefix, no `@[coords]`

## v2.5.0
- Snapshot filename: cut everything after `@`, clean special chars from camera name

## v2.4.9
- Snapshot filename format: `maxfile_cameraname_vNNN.jpg` (incremental per base+camera)

## v2.4.8
- Enter key in Setup dialog QLineEdits: `clearFocus()` via eventFilter on all children

## v2.4.4 – v2.4.7
- Viewport Snapshot section extracted to its own QGroupBox in Setup dialog
- Optional sub-subfolder field (`thumb_subdir`) — creates folder automatically
- Fix: Enter in QLineEdit no longer closes Setup dialog

## v2.4.3
- Note fields narrowed (res: −28px, film: −14px) so Setup button fits in toolbar

## v2.4.2
- Summary version matching session history

## v2.5.3 (session base)
- All pipeline config keys (`thumb_subfolder`, `thumb_subdir`, `snap_inc_*`) saved to `pipeline_config.ini`
- Compatible with named pipeline presets

---

*Earlier history from v1.0 → v2.4.x available on request.*
