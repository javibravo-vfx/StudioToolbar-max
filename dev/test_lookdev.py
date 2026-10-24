"""
Offline test of the Lookdev Rig (maintools/studio_lookdev_max) with a fake pymxs.

    python dev/test_lookdev.py <path to the shared folder>

e.g. python dev/test_lookdev.py "T:\\.studio-toolbar\\shared"

The fake runtime models just enough of 3ds Max (nodes, materials, user props, layers,
bounding boxes, the clay store) to run build / clay / remove end to end with the V-Ray
and Arnold adapters. It checks the rig logic, not how the engines render.
"""

import math
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SHARED = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, "..", "shared"))
os.environ["STUDIO_TOOLBAR_ROOT"] = os.path.dirname(SHARED)

fails = []


def check(name, cond, info=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{info}]" if info else ""))
    if not cond:
        fails.append(name)


# ── fake runtime ────────────────────────────────────────────────────────────
class _Undef:
    def __repr__(self): return "undefined"


UNDEF = _Undef()


class Point3:
    def __init__(self, x, y, z): self.x, self.y, self.z = float(x), float(y), float(z)


class Matrix3:
    def __init__(self, *rows):
        if len(rows) == 1:
            rows = (Point3(1, 0, 0), Point3(0, 1, 0), Point3(0, 0, 1), Point3(0, 0, 0))
        self.row1, self.row2, self.row3, self.row4 = rows


class Color:
    def __init__(self, r, g, b): self.r, self.g, self.b = r, g, b


class MaxObj:
    """Material / texture with a fixed property list (anything else 'does not exist')."""
    PROPS = ()

    def __init__(self, **kw):
        self.name = ""
        for k, v in kw.items(): setattr(self, k, v)


def _mtl_class(cls_name, props):
    return type(cls_name, (MaxObj,), {"PROPS": tuple(props)})


SCENE = []
GEO, CAM, LIGHT, HELPER = "GeometryClass", "camera", "light", "helper"


class Node:
    SUPER = GEO

    def __init__(self, **kw):
        self.name, self.parent, self.material = "", None, UNDEF
        self.castShadows = self.receiveShadows = True
        self.isHidden = False
        self.transform = Matrix3(1)
        self.userprops = {}
        self.bbox = ((0, 0, 0), (0, 0, 0))
        for k, v in kw.items(): setattr(self, k, v)
        SCENE.append(self)

    @property
    def position(self): return self.transform.row4

    @position.setter
    def position(self, p): self.transform.row4 = p


def _node_class(cls_name, sup, extra=()):
    return type(cls_name, (Node,), {"SUPER": sup, "PROPS": tuple(extra)})


rt = types.SimpleNamespace()
rt.undefined = UNDEF
rt.Point3, rt.Matrix3, rt.Color = Point3, Matrix3, Color
rt.GeometryClass, rt.camera = GEO, CAM
rt.Dummy = _node_class("Dummy", HELPER, ("boxsize",))
rt.Freecamera = _node_class("Freecamera", CAM, ("fov", "fovType"))
rt.Physcam = _node_class("Physical", CAM, ("fov",))
rt.Sphere = _node_class("Sphere", GEO, ("radius", "segs"))
rt.Plane = _node_class("Plane", GEO, ("width", "length", "widthsegs", "lengthsegs"))
rt.Box = _node_class("Box", GEO)
rt.VRayLight = _node_class("VRayLight", LIGHT, ("type", "dome_spherical", "texmap", "texmap_on",
                                                "multiplier", "invisible", "texmap_locktolight",
                                                "affect_diffuse", "affect_specular",
                                                "affect_reflections"))
rt.Arnold_Light = _node_class("Arnold_Light", LIGHT, ("shapeType", "texmap", "texmapOn",
                                                      "useColor", "intensity", "exposure", "camera",
                                                      "diffuse", "specular", "sss", "indirect",
                                                      "volume", "transmission"))
rt.VRayBitmap = _mtl_class("VRayBitmap", ("HDRIMapName", "mapType", "horizontalRotation"))
rt.VRayMtl = _mtl_class("VRayMtl", ("diffuse", "reflection", "reflection_glossiness",
                                    "reflection_fresnel", "reflection_metalness", "diffuse_roughness"))
rt.VRayMtlWrapper = _mtl_class("VRayMtlWrapper", ("baseMtl", "matte_surface", "alpha_contribution",
                                                  "matte_shadows", "matte_shadowsAffectAlpha", "generateGI"))
rt.ai_standard_surface = _mtl_class("ai_standard_surface", ("base", "base_color", "metalness", "specular",
                                                            "specular_color", "specular_roughness",
                                                            "diffuse_roughness"))
rt.ai_image = _mtl_class("ai_image", ("filename",))
rt.ai_shadow_matte = _mtl_class("ai_shadow_matte", ("shadow_opacity",))
rt.LKD_ClayStoreCA = "LKD_ClayStoreCA"

rt.renderWidth, rt.renderHeight, rt.renderPixelAspect = 1920, 1080, 1.0
rt.backgroundColor = Color(10, 20, 30)
rt.useEnvironmentMap = True
rt.selection = []
rt.objects = SCENE
VIEW = {"cam": None}


class _Renderer: pass


def _renderer(name): r = _Renderer(); r.cls = name; return r


rt.renderers = types.SimpleNamespace(current=_renderer("V_Ray_7__update_1"))
rt.classOf = lambda o: getattr(o, "cls", type(o).__name__)
rt.superClassOf = lambda n: n.SUPER
rt.isProperty = lambda o, p: p in getattr(o, "PROPS", ())
rt.setProperty = setattr
rt.getProperty = getattr
rt.getPropNames = lambda o: list(getattr(o, "PROPS", ()))
rt.isValidNode = lambda n: isinstance(n, Node) and n in SCENE
rt.delete = lambda n: SCENE.remove(n)
rt.setUserProp = lambda n, k, v: n.userprops.__setitem__(k, v)
rt.getUserProp = lambda n, k: n.userprops.get(k, UNDEF)
rt.getNodeByName = lambda name: next((n for n in SCENE if n.name == name), UNDEF)
rt.nodeGetBoundingBox = lambda n, m: (Point3(*n.bbox[0]), Point3(*n.bbox[1]))
rt.redrawViews = lambda: None
rt.getViewFOV = lambda: VIEW["cam"].fov
rt.viewport = types.SimpleNamespace(setCamera=lambda c: VIEW.__setitem__("cam", c))
EXECUTED = []
rt.execute = lambda code: EXECUTED.append(code)


class _Layer:
    PROPS = ("isFrozen", "showFrozenInGray", "current")

    def __init__(self):
        self.nodes, self.isFrozen, self.showFrozenInGray, self.current = [], False, True, False

    def addNode(self, n): self.nodes.append(n)


LAYERS = {"0": _Layer()}


def _del_layer(name):
    lyr = LAYERS.get(name)
    if lyr is None or lyr.current or any(n in SCENE for n in lyr.nodes):
        return False
    del LAYERS[name]
    return True


rt.LayerManager = types.SimpleNamespace(
    getLayerFromName=lambda n: LAYERS.get(n, UNDEF),
    newLayerFromName=lambda n: LAYERS.setdefault(n, _Layer()),
    getLayer=lambda i: LAYERS["0"],
    deleteLayerByName=_del_layer)
rt.custAttributes = types.SimpleNamespace()


def _set_assets(store, arr): store.assets = list(arr); return len(arr)


def _clay_apply(store, clay):
    if store.clayNodes: return 0
    n = 0
    for a in store.assets:
        if not rt.isValidNode(a): continue
        had = a.material is not UNDEF
        store.clayNodes.append(a); store.clayHad.append(had)
        store.clayMtls.append(a.material if had else clay)
        a.material = clay; n += 1
    return n


def _clay_restore(store):
    n = 0
    for a, had, m in zip(store.clayNodes, store.clayHad, store.clayMtls):
        if rt.isValidNode(a):
            a.material = m if had else UNDEF; n += 1
    store.clayNodes, store.clayMtls, store.clayHad = [], [], []
    return n


rt.LKD_setAssets, rt.LKD_clayApply, rt.LKD_clayRestore = _set_assets, _clay_apply, _clay_restore


# Custom attribute tabs: MAXScript arrays expose .count
class _Tab(list):
    @property
    def count(self): return len(self)


rt.custAttributes.add = lambda node, ca: node.__dict__.update(
    assets=_Tab(), clayNodes=_Tab(), clayMtls=_Tab(), clayHad=_Tab())
_orig_apply, _orig_restore = _clay_apply, _clay_restore


def _apply(store, clay):
    n = _orig_apply(store, clay); store.clayNodes = _Tab(store.clayNodes); return n


def _restore(store):
    n = _orig_restore(store); store.clayNodes = _Tab(); return n


rt.LKD_clayApply, rt.LKD_clayRestore = _apply, _restore


class _Undo:
    def __init__(self, *a): pass
    def __enter__(self): return self
    def __exit__(self, *a): return False


pymxs = types.ModuleType("pymxs")
pymxs.runtime = rt
pymxs.undo = _Undo
sys.modules["pymxs"] = pymxs

sys.path.insert(0, os.path.join(REPO, "maintools"))
sys.path.insert(0, os.path.join(SHARED, "python"))

# ── HDRI library in a temp folder ────────────────────────────────────────────
import tempfile, json  # noqa: E401,E402
tmp = tempfile.mkdtemp()
os.environ["STUDIO_LOOKDEV_DIR"] = os.path.join(tmp, "lookdev")
import shutil  # noqa: E402
shutil.copytree(os.path.join(SHARED, "lookdev"), os.environ["STUDIO_LOOKDEV_DIR"])
hdri_dir = os.path.join(os.environ["STUDIO_LOOKDEV_DIR"], "hdri")
open(os.path.join(hdri_dir, "studio_a.exr"), "wb").close()
json.dump({"rotation_offset_deg": 45, "intensity": 2.0}, open(os.path.join(hdri_dir, "studio_a.json"), "w"))
open(os.path.join(hdri_dir, "exterior_b.hdr"), "wb").close()
json.dump({"rotation_offset_deg": -30, "intensity": 0.5, "tags": ["sun"]},
          open(os.path.join(hdri_dir, "exterior_b.json"), "w"))

from studio_lookdev_max import builder  # noqa: E402
from studio_lookdev import core  # noqa: E402

# ── scene ────────────────────────────────────────────────────────────────────
asset = rt.Box(name="chair_geo", bbox=((-50, -40, 0), (50, 40, 120)))
asset_mtl = rt.VRayMtl(name="chair_mtl")
asset.material = asset_mtl
legs = rt.Box(name="chair_legs", bbox=((-50, -40, 0), (50, 40, 10)))   # no material
rt.selection = [asset, legs]

# 1. automatic camera, V-Ray
rig = builder.build("studio_a")
names = {n.name for n in SCENE}
check("build: root, cam, dome, store, shadow catcher",
      {"LKD_root", "LKD_cam", "LKD_dome", "LKD_store", "LKD_shadow_catcher"} <= names, sorted(names)[:8])
check("build: chrome, grey, chart + 24 patches",
      {"LKD_chrome", "LKD_grey18", "LKD_chart_board"} <= names
      and sum(1 for n in names if n.startswith("LKD_chart_")) == 25)
check("build: no warnings / missing props", not rig["warnings"] and not rig["log"], rig["log"][:3])
dome = rt.getNodeByName("LKD_dome")
check("dome: V-Ray dome with HDRI", dome.type == 1 and dome.texmap.HDRIMapName.endswith("studio_a.exr"))
check("dome: sidecar intensity", dome.multiplier == 2.0)
check("dome: V-Ray texture locked to icon (rotates with the node)", dome.texmap_locktolight is True)
ground = rt.getNodeByName("LKD_shadow_catcher")
check("ground: at the asset base", abs(ground.position.z - 0.0) < 1e-6, ground.position.z)
check("ground: V-Ray matte wrapper, no shadow cast",
      type(ground.material).__name__ == "VRayMtlWrapper" and ground.material.matte_surface
      and ground.material.alpha_contribution == -1.0 and not ground.castShadows)
check("ground: orbits with the rig", ground.parent is rt.getNodeByName("LKD_root"))
spin = rt.getNodeByName("LKD_hdri_spin")
check("dome under the HDRI spin pivot", dome.parent is spin and spin.parent is rt.getNodeByName("LKD_root"))
check("turntable spins the pivot, not the dome",
      any('spin.rotation.controller.Z_Rotation = -360.0' in c for c in EXECUTED)
      and not any('dome.rotation' in c for c in EXECUTED if 'with animate' in c))
check("refs parented to the camera",
      all(rt.getNodeByName(n).parent is rt.getNodeByName("LKD_cam")
          for n in ("LKD_chrome", "LKD_grey18", "LKD_chart_board")))
store = rt.getNodeByName("LKD_store")
check("store: hidden, remembers the asset", store.isHidden and list(store.assets) == [asset, legs])
check("turntable keyed with HDRI offset", any("Z_Rotation = 45.0" in c for c in EXECUTED))
check("asset untouched (material)", asset.material is asset_mtl)
check("rig on layer LOOKDEV_RIG", len(LAYERS["LOOKDEV_RIG"].nodes) == len(rig["nodes"]))
check("layer frozen, shown in colour", LAYERS["LOOKDEV_RIG"].isFrozen
      and all(getattr(n, "showFrozenInGray", True) is False for n in rig["nodes"]))

# 1b. live HDRI controls
st = builder.hdri_state()
check("live: state after build", st and st["hdri"] == "studio_a" and st["rotation"] == 45
      and st["exposure"] == 0 and st["bg_visible"], st)
EXECUTED.clear()
builder.set_rotation(90)
check("live: rotation on the dome, no rebuild",
      any('"LKD_dome").rotation.controller.Z_Rotation = 90.0' in c for c in EXECUTED)
      and builder.hdri_state()["rotation"] == 90 and rt.getNodeByName("LKD_dome") is dome)
builder.set_exposure(1.0)
check("live: +1 EV doubles intensity", abs(dome.multiplier - 4.0) < 1e-9, dome.multiplier)
builder.set_background_visible(False)
check("live: background off -> V-Ray dome invisible", dome.invisible is True
      and builder.hdri_state()["bg_visible"] is False)
builder.set_background_visible(True)
h = builder.set_hdri("exterior_b")
check("live: swap HDRI keeps the dome node", rt.getNodeByName("LKD_dome") is dome
      and dome.texmap.HDRIMapName.endswith("exterior_b.hdr"))
st = builder.hdri_state()
check("live: swap resets to the new sidecar", st["rotation"] == -30 and st["exposure"] == 0
      and abs(dome.multiplier - 0.5) < 1e-9, (st, dome.multiplier))
check("live: asset tag follows the swap", asset.userprops[core.USER_PROP_HDRI] == "exterior_b")
builder.set_rotation(12.5)
builder.set_exposure(-1.0)
saved = builder.save_hdri_defaults()
side = json.load(open(os.path.join(hdri_dir, "exterior_b.json")))
check("save default: sidecar rotation + intensity, other fields kept",
      side["rotation_offset_deg"] == 12.5 and abs(side["intensity"] - 0.25) < 1e-9
      and side["tags"] == ["sun"], side)
check("save default: EV folded (light unchanged)", builder.hdri_state()["exposure"] == 0
      and abs(dome.multiplier - 0.25) < 1e-9)
builder.set_hdri("studio_a")

# 1c. references: toggle, corner, chart swap — live, rig kept
cam = rt.getNodeByName("LKD_cam")
root_before = rt.getNodeByName("LKD_root")


def _cam_local(n):
    """Position of n in camera space (x right, y up)."""
    d = [n.transform.row4.x - cam.transform.row4.x, n.transform.row4.y - cam.transform.row4.y,
         n.transform.row4.z - cam.transform.row4.z]
    ax = cam.transform.row1; ay = cam.transform.row2
    return (d[0] * ax.x + d[1] * ax.y + d[2] * ax.z, d[0] * ay.x + d[1] * ay.y + d[2] * ay.z)


chrome_x0 = _cam_local(rt.getNodeByName("LKD_chrome"))[0]
r = builder.update_refs(items=["chrome", "colorchecker"])
check("refs: grey removed, rest of the rig kept",
      rt.getNodeByName("LKD_grey18") is UNDEF and rt.getNodeByName("LKD_root") is root_before
      and rt.getNodeByName("LKD_chart_board") is not UNDEF)
check("refs: chart packs into the freed slot",
      _cam_local(rt.getNodeByName("LKD_chart_board"))[0] > 0
      and abs(_cam_local(rt.getNodeByName("LKD_chrome"))[0] - chrome_x0) < 1e-6)
builder.update_refs(corner="top_left")
cx, cy = _cam_local(rt.getNodeByName("LKD_chrome"))
check("refs: top-left corner", cx < 0 and cy > 0, (cx, cy))
check("refs: state remembered", builder.refs_state() == {"items": ["chrome", "colorchecker"],
                                                         "corner": "top_left",
                                                         "chart": "colorchecker24"})
shutil.copy(os.path.join(os.environ["STUDIO_LOOKDEV_DIR"], "reference", "_TEMPLATE_chart.json"),
            os.path.join(os.environ["STUDIO_LOOKDEV_DIR"], "reference", "test_chart6.json"))
check("charts: listed from reference/", "test_chart6" in core.list_charts()
      and "_TEMPLATE_chart" not in core.list_charts())
builder.update_refs(chart="test_chart6")
patches = [n for n in SCENE if n.name.startswith("LKD_chart_") and n.name != "LKD_chart_board"]
board = rt.getNodeByName("LKD_chart_board")
check("charts: swap to a 3x2 chart (6 patches, 1.5:1 board)", len(patches) == 6
      and abs(board.width / board.length - 1.5) < 1e-6, (len(patches), board.width / board.length))
builder.update_refs(items=[], corner="bottom_right", chart="colorchecker24")
check("refs: all off", not any(n.name in ("LKD_chrome", "LKD_grey18", "LKD_chart_board") for n in SCENE))
builder.update_refs(items=["chrome", "grey18", "colorchecker"])
check("refs: all back (24 patches)", sum(1 for n in SCENE if n.name.startswith("LKD_chart_")) == 25)

# 1d. background colour when the dome is hidden
builder.set_background_visible(False, color=(0.5, 0.25, 0.0))
check("bg colour: scene background set, env map off",
      abs(rt.backgroundColor.r - 127.5) < 1e-6 and rt.useEnvironmentMap is False)
builder.set_background_color((0.0, 0.0, 1.0))
check("bg colour: live change while hidden", rt.backgroundColor.b == 255.0)
builder.set_background_visible(True)
check("bg colour: scene background restored when the dome is visible again",
      rt.backgroundColor.r == 10 and rt.useEnvironmentMap is True)
builder.set_background_visible(False)
builder.remove_rig()
check("bg colour: delete rig restores the scene background",
      rt.backgroundColor.b == 30 and rt.useEnvironmentMap is True)
rig = builder.build("studio_a")
dome = rt.getNodeByName("LKD_dome")

# 1e. background modes
try:
    builder.set_background_mode("blur"); ok = False
except RuntimeError as e:
    ok = "Refresh library" in str(e)
check("bg mode: blur needs Refresh library first", ok)
os.makedirs(core.cache_dir(hdri_dir), exist_ok=True)
for n in ("studio_a", "exterior_b"):
    open(core.bg_cache_path(os.path.join(hdri_dir, n + ".exr")), "wb").close()
EXECUTED.clear()
builder.set_background_mode("blur")
bgd = rt.getNodeByName("LKD_dome_bg")
check("bg mode: blurred dome, camera only", bgd is not UNDEF and bgd.texmap.HDRIMapName.endswith("studio_a.bg.exr")
      and bgd.affect_diffuse is False and bgd.affect_reflections is False and bgd.invisible is False
      and dome.invisible is True)
check("bg mode: blurred dome follows rig (same pivot, same rotation)",
      bgd.parent is rt.getNodeByName("LKD_hdri_spin")
      and any('"LKD_dome_bg").rotation.controller.Z_Rotation = 45.0' in c for c in EXECUTED))
builder.set_rotation(60); builder.set_exposure(1.0)
check("bg mode: rotation / exposure drive both domes",
      any('"LKD_dome_bg").rotation.controller.Z_Rotation = 60.0' in c for c in EXECUTED)
      and bgd.multiplier == dome.multiplier == 4.0)
builder.set_exposure(0.0)
open(os.path.join(hdri_dir, "nobg_c.exr"), "wb").close()
builder.set_hdri("nobg_c")
check("bg mode: HDRI without blurred copy falls back to HDRI background",
      builder.hdri_state()["bg_mode"] == "hdri" and rt.getNodeByName("LKD_dome_bg") is UNDEF
      and dome.invisible is False)
os.remove(os.path.join(hdri_dir, "nobg_c.exr"))
builder.set_hdri("studio_a")
builder.set_background_mode("color", color=(0.2, 0.2, 0.2))
check("bg mode: colour removes the blurred dome",
      rt.getNodeByName("LKD_dome_bg") is UNDEF and rt.useEnvironmentMap is False)
builder.set_background_mode("hdri")
check("bg mode: back to HDRI restores the scene", rt.useEnvironmentMap is True and dome.invisible is False)
for n in ("studio_a", "exterior_b"):
    os.remove(core.bg_cache_path(os.path.join(hdri_dir, n + ".exr")))

# 2. clay
n = builder.set_clay(True)
check("clay on: both asset nodes", n == 2 and builder.clay_is_on())
check("clay on: grey material", asset.material.name == "LKD_mtl_clay" and legs.material.name == "LKD_mtl_clay")
check("clay on: refs untouched", rt.getNodeByName("LKD_chrome").material.name == "LKD_mtl_chrome")
check("clay on twice: no-op", builder.set_clay(True) == 0)
n = builder.set_clay(False)
check("clay off: original materials back", n == 2 and asset.material is asset_mtl and legs.material is UNDEF)

# 3. rebuild with clay on, then delete restores
builder.set_clay(True)
builder.build("studio_a")
check("rebuild: asset restored before rebuilding", asset.material is asset_mtl)
check("rebuild: single rig", sum(1 for n in SCENE if n.name == "LKD_root") == 1)
builder.set_clay(True)
builder.remove_rig()
check("remove_rig: materials restored", asset.material is asset_mtl and legs.material is UNDEF)
check("remove_rig: no LKD_ nodes left", not any(n.name.startswith("LKD_") for n in SCENE))
check("remove_rig: LOOKDEV_RIG layer deleted", "LOOKDEV_RIG" not in LAYERS)

# 4. selected camera -> copied framing
user_cam = rt.Physcam(name="CAM_approved", fov=30.0)
user_cam.transform = Matrix3(Point3(1, 0, 0), Point3(0, 0, 1), Point3(0, -1, 0), Point3(0, -900, 60))
rt.selection = [asset, user_cam]
rig = builder.build("studio_a", overrides={"turntable": {"enabled": False}})
cam = rt.getNodeByName("LKD_cam")
check("user cam: rig copies its FOV", abs(cam.fov - 30.0) < 1e-6, cam.fov)
check("user cam: rig copies its position", abs(cam.transform.row4.y + 900) < 1e-6)
check("user cam: original untouched", user_cam.parent is None and user_cam.fov == 30.0)
check("user cam: reported", rig["camera_source"] == "CAM_approved")
f = rig["frame"]
check("user cam: distance to asset along view", abs(f.distance - 900.0) < 1e-6, f.distance)
chrome = rt.getNodeByName("LKD_chrome")
dz = chrome.transform.row4.y - (-900)
check("user cam: refs in front of the lens", 0 < dz < 900, dz)
builder.remove_rig()

# 5. options off
rt.selection = [asset]
rig = builder.build("studio_a", overrides={"ground": {"shadow_catcher": False},
                                           "clay": {"enabled": True}})
check("no shadow catcher when disabled", rt.getNodeByName("LKD_shadow_catcher") is UNDEF)
check("clay from preset on build", builder.clay_is_on() and asset.material.name == "LKD_mtl_clay")
builder.remove_rig()

# 6. Arnold
rt.renderers.current = _renderer("Arnold")
rig = builder.build("studio_a")
dome = rt.getNodeByName("LKD_dome")
check("arnold: skydome with ai_image", dome.shapeType == 6 and dome.texmap.filename.endswith("studio_a.exr"))
check("arnold: shadow matte ground",
      type(rt.getNodeByName("LKD_shadow_catcher").material).__name__ == "ai_shadow_matte")
check("arnold: no missing props", not rig["log"], rig["log"][:3])
builder.set_background_visible(False)
check("arnold: background off -> camera visibility 0", dome.camera == 0.0)
builder.set_hdri("exterior_b")
check("arnold: swap HDRI on ai_image", dome.texmap.filename.endswith("exterior_b.hdr"))
builder.remove_rig()

# 7. stub engine
rt.renderers.current = _renderer("Redshift_Renderer")
try:
    builder.build("studio_a"); ok = False
except Exception as e:  # noqa: BLE001
    ok = "not implemented" in str(e)
check("redshift stub: clear error", ok)

# 8. library maintenance (generic part; Max image I/O needs Max)
from studio_lookdev import library  # noqa: E402
jobs = library.pending_jobs(hdri_dir)
check("library: both HDRIs need thumb + bg", len(jobs) == 2 and all(j.thumb and j.bg and not j.tx for j in jobs))
written = []


def _read(path, w, h):
    return [0.5, 0.6, 0.7] * (w * h)


def _jpg(path, data, w, h):
    assert len(data) == w * h * 3
    written.append(path); open(path, "wb").write(b"jpg")


def _exr(path, data, w, h):
    assert len(data) == w * h * 3
    written.append(path); open(path, "wb").write(b"exr")


rep_ = library.refresh(_read, _jpg, _exr, folder=hdri_dir)
check("library: 4 files into _cache", len(written) == 4 and all("_cache" in w for w in written)
      and not rep_.errors, rep_.errors)
check("library: up to date afterwards", not library.pending_jobs(hdri_dir))
hs = {h.name: h for h in core.list_hdris(hdri_dir)}
check("library: list_hdris picks cached thumb + bg",
      hs["studio_a"].thumb.endswith("studio_a.thumb.jpg") and hs["studio_a"].bg.endswith("studio_a.bg.exr"))
open(os.path.join(hdri_dir, "studio_a.jpg"), "wb").close()
check("library: hand-made thumbnail wins and is never regenerated",
      core.find_hdri("studio_a", hdri_dir).thumb.endswith(os.sep + "studio_a.jpg")
      and not any(j.thumb for j in library.pending_jobs(hdri_dir, force=True) if j.hdri.name == "studio_a"))
check("library: cache files are not listed as HDRIs", len(core.list_hdris(hdri_dir)) == 2)
tm = library.tonemap_srgb8([0.18, 0.18, 0.18] * 4)
check("library: tonemap grey stays neutral", tm[0] == tm[1] == tm[2] and 60 < tm[0] < 200, tm[:3])

# 8b. another folder as library (e.g. a collection on the NAS) — never written to
check("ext library: cache on the studio drive (shared/lookdev/_library_cache)",
      core.LIBRARY_CACHE_ROOT == os.path.join(os.environ["STUDIO_LOOKDEV_DIR"], "_library_cache"))
ext = os.path.join(tmp, "nas_hdri")
for sub in ("exterior/day", "exterior/night", "studio", "_skip"):
    os.makedirs(os.path.join(ext, *sub.split("/")), exist_ok=True)
for rel in ("exterior/day/field_4k.exr", "exterior/night/street_8k.hdr", "studio/box.exr",
            "_skip/hidden.exr", "top.exr"):
    open(os.path.join(ext, *rel.split("/")), "wb").close()
before = sorted(os.path.relpath(os.path.join(d, f), ext) for d, _, fs in os.walk(ext) for f in fs)
items = {h.name: h for h in core.list_hdris(ext)}
check("ext library: sub-folders become groups, _folders skipped",
      sorted(items) == ["exterior/day/field_4k", "exterior/night/street_8k", "studio/box", "top"]
      and items["exterior/day/field_4k"].group == "exterior/day" and items["top"].group == "",
      sorted(items))
written = []
library.refresh(_read, _jpg, _exr, folder=ext)
after = sorted(os.path.relpath(os.path.join(d, f), ext) for d, _, fs in os.walk(ext) for f in fs)
check("ext library: previews go to the shared library cache, folder untouched",
      after == before and len(written) == 8 and all(w.startswith(core.LIBRARY_CACHE_ROOT) for w in written))
h = core.list_hdris(ext)[0]
check("ext library: cached thumb + bg picked up", h.thumb and h.bg and h.root == ext)
core.save_sidecar(h.path, {"rotation_offset_deg": 33}, root=h.root)
after2 = sorted(os.path.relpath(os.path.join(d, f), ext) for d, _, fs in os.walk(ext) for f in fs)
check("ext library: 'save default' goes to the cache too",
      after2 == before and core.hdri_from_path(h.path, ext).rotation_offset == 33)
check("ext library: separate caches per folder",
      core.library_cache_dir(ext) != core.library_cache_dir(os.path.join(tmp, "other")))
rt.renderers.current = _renderer("V_Ray_7")
rt.selection = [asset]
builder.build(h)
dome = rt.getNodeByName("LKD_dome")
check("ext library: rig uses the NAS file directly", dome.texmap.HDRIMapName == h.path)
builder.set_rotation(10)
builder.save_hdri_defaults()
check("ext library: save default from the rig resolves the NAS HDRI",
      core.hdri_from_path(h.path, ext).rotation_offset == 10 and sorted(
          os.path.relpath(os.path.join(d, f), ext) for d, _, fs in os.walk(ext) for f in fs) == before)
builder.remove_rig()

# 9. core: same on-screen ref size regardless of asset scale
p = core.load_preset()
sizes = []
for s in (1.0, 100.0):
    fr = core.camera_frame((-s, -s, 0), (s, s, 2 * s), p, 16 / 9)
    it = core.reference_layout(fr, p)[0]
    sizes.append(it["radius"] / (-it["pos"][2] * math.tan(fr.vfov / 2)))
check("core: refs keep screen size at any scale", abs(sizes[0] - sizes[1]) < 1e-9)

if not os.environ.get("LOOKDEV_TEST_KEEP"):
    shutil.rmtree(tmp, ignore_errors=True)
print("\n%d failures" % len(fails), fails)
sys.exit(1 if fails else 0)
