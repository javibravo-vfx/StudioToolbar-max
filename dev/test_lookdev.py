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
                                                "multiplier", "invisible"))
rt.Arnold_Light = _node_class("Arnold_Light", LIGHT, ("shapeType", "texmap", "texmapOn",
                                                      "useColor", "intensity", "exposure", "camera"))
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
    def __init__(self): self.nodes = []
    def addNode(self, n): self.nodes.append(n)


LAYERS = {}
rt.LayerManager = types.SimpleNamespace(
    getLayerFromName=lambda n: LAYERS.get(n, UNDEF),
    newLayerFromName=lambda n: LAYERS.setdefault(n, _Layer()))
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
ground = rt.getNodeByName("LKD_shadow_catcher")
check("ground: at the asset base", abs(ground.position.z - 0.0) < 1e-6, ground.position.z)
check("ground: V-Ray matte wrapper, no shadow cast",
      type(ground.material).__name__ == "VRayMtlWrapper" and ground.material.matte_surface
      and ground.material.alpha_contribution == -1.0 and not ground.castShadows)
check("ground: orbits with the rig", ground.parent is rt.getNodeByName("LKD_root"))
check("refs parented to the camera",
      all(rt.getNodeByName(n).parent is rt.getNodeByName("LKD_cam")
          for n in ("LKD_chrome", "LKD_grey18", "LKD_chart_board")))
store = rt.getNodeByName("LKD_store")
check("store: hidden, remembers the asset", store.isHidden and list(store.assets) == [asset, legs])
check("turntable keyed with HDRI offset", any("Z_Rotation = 45.0" in c for c in EXECUTED))
check("asset untouched (material)", asset.material is asset_mtl)
check("rig on layer LOOKDEV_RIG", len(LAYERS["LOOKDEV_RIG"].nodes) == len(rig["nodes"]))

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
builder.remove_rig()

# 7. stub engine
rt.renderers.current = _renderer("Redshift_Renderer")
try:
    builder.build("studio_a"); ok = False
except Exception as e:  # noqa: BLE001
    ok = "not implemented" in str(e)
check("redshift stub: clear error", ok)

# 8. core: same on-screen ref size regardless of asset scale
p = core.load_preset()
sizes = []
for s in (1.0, 100.0):
    fr = core.camera_frame((-s, -s, 0), (s, s, 2 * s), p, 16 / 9)
    it = core.reference_layout(fr, p)[0]
    sizes.append(it["radius"] / (-it["pos"][2] * math.tan(fr.vfov / 2)))
check("core: refs keep screen size at any scale", abs(sizes[0] - sizes[1]) < 1e-9)

shutil.rmtree(tmp, ignore_errors=True)
print("\n%d failures" % len(fails), fails)
sys.exit(1 if fails else 0)
