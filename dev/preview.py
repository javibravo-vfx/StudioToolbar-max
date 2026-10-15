import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = sys.argv[1]; sys.argv = ['x', SRC, '/dev/null']
exec(open(os.path.join(HERE, 'render_toolbar.py')).read().replace('pix.save(OUT)', 'pass').replace('print("saved"', '0 and print("saved"'))
from PySide6 import QtWidgets, QtCore, QtGui
mgr = dock.widget()
mgr._get_pipeline_from_path()
rt.renderWidth, rt.renderHeight = 2048, 858
mgr.state["res_presets"] = [{"w": 1920, "h": 1080, "n": "Client HD delivery"}, {"w": 2048, "h": 858, "n": "Scope plates"}]
mgr.state["film_presets"] = [{"v": 24.89, "n": "Plates — Alexa S35"}]
rt.GetRendApertureWidth = lambda: 27.99
for _ in range(3): mgr._master_sync(); app.processEvents()
mgr._set_status("Render set", "#70aa70", "T:/...v012_.exr")
for _ in range(5): app.processEvents()
grabs = {}
_Real = QtWidgets.QMenu
class GrabMenu(_Real):
    def exec(self, *a, **k):
        self.adjustSize(); self.show(); app.processEvents()
        grabs[len(grabs)] = self.grab(); self.hide(); return None
QtWidgets.QMenu = GrabMenu
mgr._show_res_menu(); mgr._show_film_menu(); mgr._show_folder_menu(); mgr._show_fps_menu()
mgr._fill_open_menu(); m = mgr._open_menu; m.adjustSize(); m.show(); app.processEvents(); grabs[len(grabs)] = m.grab(); m.hide()
mgr._fill_save_menu(); m = mgr._save_menu; m.adjustSize(); m.show(); app.processEvents(); grabs[len(grabs)] = m.grab(); m.hide()
dock.grab().save(os.path.join(HERE, "pv_bar.png"))
for k, p in grabs.items(): p.save(os.path.join(HERE, f"pv_menu{k}.png"))
print("menus", len(grabs))
