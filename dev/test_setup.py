import sys, os, json
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = sys.argv[1]; sys.argv = ['x', SRC, '/dev/null']
exec(open(os.path.join(HERE, 'render_toolbar.py')).read().replace('pix.save(OUT)', 'pass').replace('print("saved"', '0 and print("saved"'))
from PySide6 import QtWidgets
fails = []
def check(n, c, info=""):
    print(("PASS " if c else "FAIL ") + n + (f"  [{info}]" if info else "")); c or fails.append(n)
class Box(QtWidgets.QMessageBox):
    @staticmethod
    def question(*a, **k): return QtWidgets.QMessageBox.Ok
    @staticmethod
    def warning(*a, **k): return QtWidgets.QMessageBox.Ok
QtWidgets.QMessageBox = Box
class Inp(QtWidgets.QInputDialog):
    @staticmethod
    def getText(*a, **k): return ("Studio A", True)
QtWidgets.QInputDialog = Inp

# BG colour presets live in the same config file
stm._save_vp_color_presets([{"name": "Mine", "hex": "#123456"}])
D = stm.PipelineSetupDialog
dlg = D(parent=dock.widget()); dlg.show(); app.processEvents()
check("4 pages", dlg.nav.count() == 4 and dlg.pages.count() == 4)
check("projects detected", "2 projects" in dlg._proj_found.text(), dlg._proj_found.text())
dlg.ed_drive.setText("/nope/x"); app.processEvents()
check("missing root warned", "not found" in dlg._proj_found.text())
dlg.ed_drive.setText(ROOT)

# per-task subfolders follow task selection
items = lambda lw: [lw.item(i).text() for i in range(lw.count())]
dlg.task_list.setCurrentRow(7); app.processEvents()
check("lighting psubs", items(dlg.psub_list) == ["textures", "cache", "import"], str(items(dlg.psub_list)))
dlg.ed_new_psub.setText("hdri"); dlg._add_item(dlg.psub_list, dlg.ed_new_psub)
dlg.task_list.setCurrentRow(0); app.processEvents()
check("matchmove psubs", items(dlg.psub_list) == ["footage", "textures"], str(items(dlg.psub_list)))
dlg.task_list.setCurrentRow(7); app.processEvents()
check("edit kept when switching back", "hdri" in items(dlg.psub_list), str(items(dlg.psub_list)))
check("tree preview shows task + psub", "8_lighting" in dlg._tree_lbl.text() and "hdri" in dlg._tree_lbl.text())

# add task, subfolder → combos sync
dlg.ed_new_task.setText("9_comp"); dlg._add_item(dlg.task_list, dlg.ed_new_task)
check("psub combo synced", dlg.psub_task_cb.findText("9_comp") >= 0)
dlg.ed_new_sub.setText("4_dailies"); dlg._add_item(dlg.sub_list, dlg.ed_new_sub)
check("snapshot combo synced", dlg.thumb_sub_cb.findText("4_dailies") >= 0)

# snapshot preview
dlg.chk_snap_shot.setChecked(True)
check("snap preview", dlg._snap_preview_lbl.text() == "maxfile_shot_Camera001_v001.jpg", dlg._snap_preview_lbl.text())

# preset save / load
dlg._save_preset_as()
check("preset saved", dlg.preset_cb.findText("Studio A") >= 0)

# save & apply keeps BG presets
dlg.render_sep_cb.setCurrentIndex(1)
dlg._save_and_accept()
cfg = stm.load_pipeline_cfg()
check("config saved", cfg["render_sep"] == "." and "9_comp" in cfg["tasks"] and cfg["extra_subs"] == "4_dailies")
check("hdri in mapping", "hdri" in json.loads(cfg["task_projects_subs"])["8_lighting"])
check("BG colour presets survive Save & Apply", stm._get_vp_color_presets()[0]["name"] == "Mine",
      str(stm._get_vp_color_presets()[:1]))

# reopen → values loaded, preset load restores
dlg2 = D(parent=dock.widget()); app.processEvents()
check("reopen shows saved tasks", "9_comp" in items(dlg2.task_list))
dlg2.task_list.clear(); dlg2.preset_cb.setCurrentText("Studio A"); dlg2._load_preset()
check("preset load restores tasks", "9_comp" in items(dlg2.task_list), str(items(dlg2.task_list)))
print("\n%d failures" % len(fails), fails)
