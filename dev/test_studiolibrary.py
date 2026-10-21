"""StudioLibrary MAX — tests against a simulated 3ds Max scene (real parent/child behaviour).

    QT_QPA_PLATFORM=offscreen python dev/test_studiolibrary.py maintools/STM_StudioLibraryMAX.py

Builds the real UI, saves a pose of linked objects, scrambles them and applies the pose
through the UI, like an artist would. Also unit-tests the matrix maths and helpers.
"""
import sys, os, types, math, random, tempfile, contextlib, json, importlib.util

SRC = sys.argv[1]
os.environ["HOME"] = os.environ["USERPROFILE"] = tempfile.mkdtemp(prefix="slhome_")

# ── fake Max ─────────────────────────────────────────────────────────────────
class P3:
    def __init__(s, x, y, z): s.x, s.y, s.z = float(x), float(y), float(z)
    def __add__(s, o): return P3(s.x + o.x, s.y + o.y, s.z + o.z)

class Q:
    def __init__(s, x=0, y=0, z=0, w=1): s.x, s.y, s.z, s.w = x, y, z, w

class M3:
    def __init__(s, r1, r2, r3, r4): s.row1, s.row2, s.row3, s.row4 = r1, r2, r3, r4
    def flat(s): return [s.row1.x, s.row1.y, s.row1.z, s.row2.x, s.row2.y, s.row2.z,
                         s.row3.x, s.row3.y, s.row3.z, s.row4.x, s.row4.y, s.row4.z]

def from_flat(m): return M3(P3(*m[0:3]), P3(*m[3:6]), P3(*m[6:9]), P3(*m[9:12]))

def mul(a, b):
    out = []
    for i in range(3):
        r = a[i * 3:i * 3 + 3]
        out += [sum(r[k] * b[k * 3 + j] for k in range(3)) for j in range(3)]
    t = a[9:12]
    return out + [sum(t[k] * b[k * 3 + j] for k in range(3)) + b[9 + j] for j in range(3)]

SCENE = []
class Node:
    def __init__(s, name, parent=None, local=None):
        s.name, s.parent, s._local = name, parent, local or [1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0]
        SCENE.append(s)
    def world(s): return s._local if s.parent is None else mul(s._local, s.parent.world())
    @property
    def transform(s): return from_flat(s.world())
    @transform.setter
    def transform(s, m):
        w = m.flat()
        s._local = w if s.parent is None else mul(w, STM.m_inv(s.parent.world()))
    @property
    def pos(s): w = s.world(); return P3(*w[9:12])
    @property
    def rotation(s): return Q()
    @property
    def scale(s): return P3(1, 1, 1)

class Sel(list):
    @property
    def count(s): return len(s)

class RT:
    currentTime = 0
    maxFileName = "test_v001.max"
    def __init__(s): s.selection = Sel()
    def Point3(s, *a): return P3(*a)
    def Matrix3(s, *a): return M3(*a)
    def Quat(s, *a): return Q(*a)
    def getNodeByName(s, name, all=False):
        hits = [n for n in SCENE if n.name.lower() == name.lower()]
        return hits if all else (hits[0] if hits else None)
    def suspendEditing(s): pass
    def resumeEditing(s): pass
    def redrawViews(s): pass
    def execute(s, code): return 12.0
    def clearSelection(s): s.selection = Sel()
    def select(s, nodes): s.selection = Sel(nodes)

rt = RT()
UNDO_LABELS = []
@contextlib.contextmanager
def _undo(on, label=""):
    UNDO_LABELS.append(label); yield
pymxs = types.ModuleType("pymxs")
pymxs.runtime = rt
pymxs.undo = _undo
pymxs.animate = lambda *a: contextlib.nullcontext()
pymxs.attime = lambda *a: contextlib.nullcontext()
sys.modules["pymxs"] = pymxs

from PySide6 import QtWidgets, QtCore, QtGui
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
spec = importlib.util.spec_from_file_location("stm_lib", SRC)
STM = importlib.util.module_from_spec(spec)
spec.loader.exec_module(STM)

fails = []
def check(name, cond, info=""):
    print(("PASS " if cond else "FAIL ") + name + (f"   [{info}]" if info else ""))
    if not cond: fails.append(name)

def rot_z(deg, t=(0, 0, 0)):
    c, n = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return [c, n, 0, -n, c, 0, 0, 0, 1, *t]

# ── unit: maths & helpers ────────────────────────────────────────────────────
random.seed(3)
ok = all(STM.m_close(STM.m_mul(a, STM.m_inv(a)), STM.IDENTITY_M, 1e-6)
         for a in ([random.uniform(-3, 3) for _ in range(12)] for _ in range(100)))
check("m_inv: 100 random affine matrices", ok)
check("validate_name rejects / : ?", all(STM.validate_name(n) for n in ("a/b", "x:y", "w?", "  ", "CON")))
check("validate_name accepts normal names", not STM.validate_name("Hand_Closed v2"))
d = {"metadata": {"contains": "A,B"}, "nodes": [{"name": "A", "parent": None}, {"name": "B", "parent": "A"}]}
STM.rename_nodes_in_pose_data(d, {"A": "Z"})
check("rename updates names, parents and contains",
      d["nodes"][0]["name"] == "Z" and d["nodes"][1]["parent"] == "Z" and d["metadata"]["contains"] == "Z,B")

# ── end to end through the UI ────────────────────────────────────────────────
lib = tempfile.mkdtemp(prefix="sllib_")
os.makedirs(os.path.join(lib, "PROJ", "Poses"))
ui = STM.StudioLibraryMaxUI()
ui._load_library(lib, os.path.join(lib, "PROJ"))
ui.current_folder_path = os.path.join(lib, "PROJ", "Poses")

hips  = Node("Hips",  None,  rot_z(0,  (0, 0, 100)))
spine = Node("Spine", hips,  rot_z(10, (0, 0, 20)))
arm   = Node("Arm_L", spine, rot_z(30, (15, 0, 10)))
hand  = Node("Hand_L", arm,  rot_z(5,  (12, 0, 0)))
target = {n.name: n.world() for n in SCENE}

rt.selection = Sel([hand, arm, spine, hips])          # children selected FIRST
ui.show_new_pose_form()
ui.new_pose_name.setText("Wave")
ui.save_new_pose()
pose_dir = os.path.join(ui.current_folder_path, "Wave.pose")
data = json.load(open(os.path.join(pose_dir, "pose_data.json")))
check("pose saved with format 2 (world/local/parent)",
      data["metadata"].get("format") == 2 and all("world" in n and "local" in n for n in data["nodes"]))
check("metadata count/frame", data["metadata"]["count"] == 4 and data["metadata"]["frame"] == 12.0)

def scramble():
    hips._local  = rot_z(60, (40, -20, 100))
    spine._local = rot_z(-25, (0, 0, 30))
    arm._local   = rot_z(90, (5, 5, 5))
    hand._local  = rot_z(-40, (20, 0, 0))

def matches(): return all(STM.m_close(n.world(), target[n.name]) for n in (hips, spine, arm, hand))

it = ui.items_view.item(0); ui.items_view.setCurrentItem(it); ui.on_pose_selected(it)
for space in (False, True):
    ui.opt_world.setChecked(space)
    scramble()
    rt.selection = Sel([hand, arm, spine, hips])
    UNDO_LABELS.clear()
    ui.apply_selected_pose()
    check(f"ONE paste restores linked hierarchy (world space={space})", matches(),
          ui.status_bar.currentMessage())
    check("apply is one undo step", UNDO_LABELS == ["STM Apply Pose"], str(UNDO_LABELS))

# Partial selection → only those objects
ui.opt_world.setChecked(False)
scramble(); hand_before = hand._local[:]
rt.selection = Sel([hips, spine])
ui.apply_selected_pose()
check("partial selection: only selected objects get the pose",
      STM.m_close(hips.world(), target["Hips"]) and hand._local == hand_before,
      ui.status_bar.currentMessage())
check("status says 'selected only'", "selected only" in ui.status_bar.currentMessage())

# Options remembered
ui.opt_world.setChecked(True); ui.filter_s.setChecked(False)
check("options persisted", STM.load_options()["world"] and not STM.load_options()["s"])
ui.filter_s.setChecked(True); ui.opt_world.setChecked(False)

# Select objects
rt.selection = Sel()
ui.select_pose_objects([it])
check("Select Objects selects the pose's objects", {n.name for n in rt.selection} == set(target))

# Old format-1 pose still applies (component path), parents first
old = {"metadata": {"name": "Old"}, "nodes": [
    {"name": "Arm_L", "position": [1, 2, 3], "rotation": [0, 0, 0, 1], "scale": [1, 1, 1]}]}
calls = []
orig = STM.apply_node_components
STM.apply_node_components = lambda node, *a, **k: calls.append(node.name)
r = STM.apply_pose(old["nodes"], selection=[])
STM.apply_node_components = orig
check("format-1 poses use the legacy component path", calls == ["Arm_L"] and r["applied"] == 1)

# Comment debounce
ui.on_pose_selected(it)
writes = []
orig_save = ui._save_comment
ui._save_comment = lambda: writes.append(1)
ui._comment_timer.timeout.disconnect(); ui._comment_timer.timeout.connect(ui._save_comment)
for ch in "hello":
    ui.comment_info.insertPlainText(ch)
check("comment not written on every keystroke", len(writes) == 0 and ui._comment_timer.isActive())

# Invalid pose name → nothing created
ui.show_new_pose_form(); ui.new_pose_name.setText("bad/name")
class Box(QtWidgets.QMessageBox):
    @staticmethod
    def warning(*a, **k): return 0
QtWidgets.QMessageBox = Box
rt.selection = Sel([hips])
ui.save_new_pose()
check("invalid name: no folder created", not any("bad" in n for n in os.listdir(ui.current_folder_path)))

# ── window position, last folder/pose, single window ─────────────────────────
win1 = STM.show_studio_library()
win1.resize(700, 500); win1.move(60, 40); app.processEvents()
saved_size = (win1.width(), win1.height())          # clamped by the window's minimum size
pose_item = win1.items_view.item(0) if win1.items_view.count() else None
fi = win1._find_folder_item(os.path.join(lib, "PROJ", "Poses"))
win1.sidebar.setCurrentItem(fi); win1.on_folder_selected(fi, 0)
it2 = win1.items_view.item(0); win1.items_view.setCurrentItem(it2); win1.on_pose_selected(it2)
app.processEvents(); win1.close(); app.processEvents()
ws = STM.load_window_state()
check("close saves geometry + folder + pose",
      bool(ws["geometry"]) and ws["folder"].endswith("Poses") and ws["pose"] == "Wave.pose", str({k: v[:20] for k, v in ws.items()}))
again = STM.show_studio_library()
check("reopening reuses the same window (no duplicates)", again is win1)
win1.close(); win1.deleteLater(); app.processEvents()
for w in QtWidgets.QApplication.topLevelWidgets():
    if w.objectName() == "StudioLibMax": w.setObjectName("old"); w.close()
win2 = STM.StudioLibraryMaxUI(); win2.show(); app.processEvents()
check("new window restores size (±4 px: restored pose panel can raise the min height)",
      abs(win2.width() - saved_size[0]) <= 4 and abs(win2.height() - saved_size[1]) <= 4, f"{win2.width()}x{win2.height()} vs {saved_size}")
check("new window restores last folder", (win2.current_folder_path or "").endswith("Poses"), str(win2.current_folder_path))
check("new window restores last pose", (win2.current_pose_path or "").endswith("Wave.pose"), str(win2.current_pose_path))
win2.move(-9000, -9000); win2._ensure_on_screen()
scr = QtGui.QGuiApplication.primaryScreen().availableGeometry()
check("off-screen position is brought back on screen", scr.intersects(win2.frameGeometry()))

print(f"\n{len(fails)} failures", fails)
