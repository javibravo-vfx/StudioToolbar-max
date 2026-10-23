"""Offscreen harness: fakes pymxs/qtmax, builds the toolbar with real Qt and saves a PNG.
Usage: QT_QPA_PLATFORM=offscreen python render_toolbar.py <toolbar.py> <out.png> [width] [--menu tools|res|...]
"""
import sys, os, types, tempfile, importlib.util

SRC, OUT = sys.argv[1], sys.argv[2]
WIDTH = int(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3].isdigit() else 3840

# ── fake pipeline on disk ────────────────────────────────────────────────────
ROOT = tempfile.mkdtemp(prefix="stm_")
shot_dir = os.path.join(ROOT, "VFX-ERSO", "105", "ERSO_5027_0000_WAN", "3D")
for t in ("5_animation", "8_lighting"):
    for sub in ("1_projects", "2_review", "3_publish"):
        os.makedirs(os.path.join(shot_dir, t, sub), exist_ok=True)
os.makedirs(os.path.join(ROOT, "VFX-ERSO", "105", "ERSO_5027_0010_WAN", "3D"), exist_ok=True)
os.makedirs(os.path.join(ROOT, "VFX-ERSO", "3D"), exist_ok=True)
os.makedirs(os.path.join(ROOT, "VFX-MOR", "101", "MOR_1001A_930", "3D"), exist_ok=True)
os.makedirs(os.path.join(ROOT, "VFX-MOR", "3D"), exist_ok=True)
open(os.path.join(shot_dir, "8_lighting", "1_projects", "ERSO_5027_0000_WAN_lighting_v012.max"), "w").close()
HOME = tempfile.mkdtemp(prefix="home_"); os.environ["HOME"] = HOME; os.environ["USERPROFILE"] = HOME

# ── fake pymxs runtime ───────────────────────────────────────────────────────
class Any:
    """Permissive stand-in: any attribute/call returns another Any (falsy-ish)."""
    def __init__(self, name="any"): self._n = name
    def __getattr__(self, k): return Any(k)
    def __call__(self, *a, **k): return None
    def __bool__(self): return False
    def __iter__(self): return iter([])
    def __len__(self): return 0
    def __str__(self): return "undefined"

class Runtime(Any):
    def __init__(self):
        super().__init__("rt")
        self.renderWidth, self.renderHeight = 1920, 1080
        self.frameRate = 24
        self.maxFilePath = shot_dir + "/8_lighting/1_projects/"
        self.maxFileName = "ERSO_5027_0000_WAN_lighting_v012.max"
        self.selection = []
        self.rendOutputFilename = ""
        self.rendSaveFile = False
        self._appdata = {}
        self.units = types.SimpleNamespace(SystemType="#centimeters")
        self.pathConfig = types.SimpleNamespace(
            getCurrentProjectFolder=lambda: os.path.join(ROOT, "VFX-ERSO", "3D"),
            setCurrentProjectFolder=lambda p: None, setDir=lambda k, v: None, getDir=lambda k: "")
        self.callbacks = types.SimpleNamespace(addScript=lambda *a, **k: None, removeScripts=lambda *a, **k: None)
        self.viewport = types.SimpleNamespace(getCamera=lambda: None, getType=lambda: "#view_persp_user",
                                              EnableSolidBackgroundColorMode=lambda *a: None)
        self.rootNode = object()
    def GetRendApertureWidth(self): return 36.0
    def SetRendApertureWidth(self, v): pass
    def Name(self, s): return s
    def name(self, s): return s
    def getAppData(self, n, i): return self._appdata.get(i)
    def setAppData(self, n, i, v): self._appdata[i] = v
    def deleteAppData(self, n, i): self._appdata.pop(i, None)
    def execute(self, s): return None
    def classOf(self, x): return "Default_Scanline_Renderer"

rt = Runtime()
import contextlib
pymxs = types.ModuleType("pymxs"); pymxs.runtime = rt; sys.modules["pymxs"] = pymxs
pymxs.UNDO_LABELS = []
@contextlib.contextmanager
def _undo(on, label=""):
    pymxs.UNDO_LABELS.append(label); yield
pymxs.undo = _undo
pymxs.animate = lambda *a: contextlib.nullcontext()
pymxs.attime = lambda *a: contextlib.nullcontext()

from PySide6 import QtWidgets, QtCore, QtGui
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
app.setFont(QtGui.QFont("DejaVu Sans", 9))
MAIN = QtWidgets.QMainWindow(); MAIN.resize(WIDTH, 220)
MAIN.setStyleSheet("QMainWindow { background: #444444; }")
central = QtWidgets.QLabel("  3ds Max viewport"); central.setStyleSheet("background:#5a5a5a; color:#888;")
MAIN.setCentralWidget(central)
qtmax = types.ModuleType("qtmax"); qtmax.GetQMaxMainWindow = lambda: MAIN; sys.modules["qtmax"] = qtmax

# pipeline config pointing at the fake drive
spec = importlib.util.spec_from_file_location("stm", SRC)
stm = importlib.util.module_from_spec(spec)
sys.modules["stm"] = stm
spec.loader.exec_module(stm)
cfg = stm.load_pipeline_cfg(); cfg["root_drive"] = ROOT; stm.save_pipeline_cfg(cfg)

fn = getattr(stm, "show_studio_toolbar")
fn()
MAIN.show()
for _ in range(30):
    app.processEvents(); QtCore.QThread.msleep(30)
QtCore.QTimer.singleShot(0, lambda: None)
for _ in range(20):
    app.processEvents(); QtCore.QThread.msleep(30)

dock = MAIN.findChild(QtWidgets.QDockWidget)
pix = dock.grab()
pix.save(OUT)
print("saved", OUT, pix.width(), pix.height())
# expose for menu-rendering callers
if "--hold" in sys.argv:
    import code; code.interact(local=dict(globals()))
