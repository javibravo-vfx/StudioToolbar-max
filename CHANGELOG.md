# Changelog — Studio Toolbar for 3ds Max

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
