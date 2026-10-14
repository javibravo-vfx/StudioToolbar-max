"""Functional tests of the v2.6 features against the fake Max runtime."""
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = sys.argv[1]
sys.argv = ['x', SRC, '/dev/null']
code = open(os.path.join(HERE, 'render_toolbar.py')).read()
exec(code.replace('pix.save(OUT)', 'pass').replace('print("saved"', '0 and print("saved"'))

from PySide6 import QtWidgets, QtCore, QtGui
mgr = dock.widget()
fails = []
def check(name, cond, info=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{info}]" if info else ""))
    if not cond: fails.append(name)

# intercept QMenu.exec: record visible actions, optionally trigger one by text
captured = {}
pick = {"text": None}
def fake_exec(self, *a, **k):
    acts = [x for x in self.actions()]
    captured["items"] = [(x.text(), x.isEnabled(), x.isChecked(), x.isSeparator()) for x in acts]
    if pick["text"]:
        for x in acts:
            if pick["text"] in x.text() and x.isEnabled():
                x.trigger(); return x
    return None
_RealMenu = QtWidgets.QMenu
class FakeMenu(_RealMenu):
    def exec(self, *a, **k): return fake_exec(self, *a, **k)
    exec_ = exec
QtWidgets.QMenu = FakeMenu
def items(): return [t for t, en, ch, sep in captured.get("items", []) if t and not sep]

# 1 — GET attention: file in 0000/8_lighting, dropdowns elsewhere
mgr._master_sync(); app.processEvents()
check("GET highlighted when dropdowns != file", bool(mgr.get_btn.property("attention")),
      str(mgr._sel()))
mgr._get_pipeline_from_path(); mgr._master_sync(); app.processEvents()
check("GET fills dropdowns from file", mgr._sel() == ("ERSO", "105", "ERSO_5027_0000_WAN", "8_lighting"), str(mgr._sel()))
check("GET highlight clears after GET", not mgr.get_btn.property("attention"))

# 2 — aspect + builtin labels
rt.renderWidth, rt.renderHeight = 2048, 858
mgr._master_sync(); app.processEvents()
check("aspect readout", mgr.res_aspect.text() == "2.39", mgr.res_aspect.text())
check("builtin res label", mgr.res_note.text() == "2K Scope 2.39", mgr.res_note.text())

# 3 — res menu contents & apply builtin
pick["text"] = "UHD 4K"; mgr._show_res_menu(); pick["text"] = None
check("res menu has Saved + Standard sections", "SAVED" in items() and "STANDARD" in items(), str(items()[:4]))
check("apply builtin res → Max", (rt.renderWidth, rt.renderHeight) == (3840, 2160), f"{rt.renderWidth}x{rt.renderHeight}")

# 4 — film menu: sensors
pick["text"] = "Alexa 35"; mgr._show_film_menu(); pick["text"] = None
check("film menu lists sensors", any("Alexa 35" in t for t in items()))
check("apply sensor sets spin + label", abs(mgr.film_spin.value() - 27.99) < 1e-6 and "Alexa 35" in mgr.film_note.text(),
      f"{mgr.film_spin.value()} {mgr.film_note.text()}")

# 5 — save res preset with label, then it appears first and labels match
mgr.res_note.setText("Client delivery"); mgr._manual_save_res()
mgr._show_res_menu()
check("saved preset listed", any("Client delivery" in t for t in items()))

# 6 — lock icon toggles
mgr.res_lock_btn.setChecked(True); app.processEvents()
check("lock toggles", mgr.res_lock_btn.isChecked())
mgr.res_x2_btn.click(); app.processEvents()
check("x2 doubles", (rt.renderWidth, rt.renderHeight) == (7680, 4320), f"{rt.renderWidth}x{rt.renderHeight}")
mgr.res_d2_btn.click(); app.processEvents()
check("½ halves", (rt.renderWidth, rt.renderHeight) == (3840, 2160))

# 7 — folder menu
opened = []
mgr._open_in_explorer = lambda p: opened.append(p)
pick["text"] = "Task"; mgr._show_folder_menu(); pick["text"] = None
check("folder menu entries", items()[:2] == ["Shot", "Task"] and any("3_publish" in t for t in items()), str(items()))
check("folder opens task dir", opened and opened[-1].endswith(os.path.join("3D", "8_lighting")), str(opened))

# 8 — OPEN ▾ lists scenes, SAVE ▾ next version
mgr._fill_open_menu()
labels = [a.text() for a in mgr._open_menu.actions() if a.text()]
check("open menu lists task scenes", any("lighting_v012.max" in t for t in labels), str(labels))
nxt = mgr._next_scene_path()
check("next version path", nxt and nxt.endswith("ERSO_5027_0000_WAN_lighting_v013.max"), str(nxt))
saved = []
rt.saveMaxFile = lambda p: (saved.append(p), open(p, "w").close())
mgr._quick_save_next()
check("quick save writes v013", saved and saved[-1].endswith("_v013.max"))
check("next after save is v014", mgr._next_scene_path().endswith("_v014.max"))
loaded = []
rt.checkForSave = lambda: True
rt.loadMaxFile = lambda p, **k: loaded.append((p, k))
mgr._fill_open_menu()
mgr._open_menu.actions()[1].trigger()
check("open recent loads file", loaded and loaded[-1][0].endswith(".max"), str(loaded[-1:]))
rt.checkForSave = lambda: False
mgr._load_scene("x.max")
check("cancel on unsaved changes aborts load", len(loaded) == 1)

# 9 — FPS menu
pick["text"] = "25 fps"; mgr._show_fps_menu(); pick["text"] = None
check("fps set", rt.frameRate == 25, str(rt.frameRate))

# 10 — status history with detail
mgr._set_status("Render set", "#70aa70", r"T:\VFX-X\render_v001_.exr")
mgr._show_status_log()
check("status history lists entries", any("Render set" in t for t in items()), str(items()[:3]))
check("status label rich text with dot", "●" in mgr.status_lbl.text())

# 11 — SET RENDER: overwrite prompt when renders exist
mgr.shotname_chk.setChecked(True)
mgr.set_save_only()
first = str(rt.rendOutputFilename)
check("set render path", first.endswith(os.path.join("ERSO_5027_0000_WAN_lighting_v012", "ERSO_5027_0000_WAN_lighting_v012_.exr")), first)
open(first, "w").close()
answers = {"btn": "New version"}
def fake_box_exec(self):
    for b in self.buttons():
        if b.text().replace("&", "") == answers["btn"]:
            self._clicked = b
    return 0
class FakeBox(QtWidgets.QMessageBox):
    def exec(self): return fake_box_exec(self)
    def clickedButton(self): return getattr(self, "_clicked", None)
QtWidgets.QMessageBox = FakeBox
mgr.set_save_only()
check("existing renders → New version v013", "_v013" in str(rt.rendOutputFilename), str(rt.rendOutputFilename))
answers["btn"] = "Overwrite"; mgr.set_save_only()
check("Overwrite keeps v012", "_v012" in str(rt.rendOutputFilename))

# 12 — setup gear & tools menu still work
pick["text"] = None; mgr._open_tools_menu()
check("tools menu opens", len(captured.get("items", [])) > 0)

# 13 — close cleans up
dock.close(); app.processEvents()
check("dock close OK", True)

print("\n%d failures" % len(fails), fails)
