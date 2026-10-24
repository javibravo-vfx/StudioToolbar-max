"""
Lookdev Rig for 3ds Max — rig construction.

From the Python Listener:
    from studio_lookdev_max import builder
    builder.build("studio_softbox_4k")            # on the current selection
    builder.set_clay(True)                        # grey override on the asset
    builder.remove_rig()

Hierarchy it creates (layer LOOKDEV_RIG, every node prefixed LKD_):

    LKD_root  (Dummy at the asset centre; spins during the "object" pass)
     |- LKD_cam                (Free camera: framed automatically, or a copy of the
     |   |                      camera selected with the asset)
     |   |- LKD_chrome         (chrome ball, fixed size on screen)
     |   |- LKD_grey18         (18% grey ball)
     |   '- LKD_chart_board    (procedural 24-patch ColorChecker)
     |- LKD_dome               (dome light with the HDRI; spins only during the "HDRI" pass)
     '- LKD_shadow_catcher     (ground plane under the asset that only shows shadows)
    LKD_store (hidden Dummy: remembers the asset and its materials while clay is on)

The asset is never modified, except:
  - two user props with the HDRI / preset used;
  - clay mode: its materials are swapped for a grey one and stored on LKD_store,
    and put back when clay is turned off or the rig is deleted.
"""

import math
import os
import sys

import pymxs

rt = pymxs.runtime

_SHARED = os.path.join(os.environ.get("STUDIO_TOOLBAR_ROOT", r"T:\.studio-toolbar"),
                       "shared", "python")
if _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)

from studio_lookdev import core          # noqa: E402
from . import adapters                    # noqa: E402
from .adapters.base import is_undefined, set_prop   # noqa: E402

P = core.RIG_PREFIX
UP_AXIS = "Z"
STORE_NAME = P + "store"
CLAY_MTL_NAME = P + "mtl_clay"

# Custom attribute on LKD_store. Lives in the .max file, so a scene saved with clay on
# can still restore the original materials in a later session.
_MS_DEFS = r"""
global LKD_ClayStoreCA = attributes LKD_ClayStore attribID:#(0x4c4b4431, 0x436c6179)
(
    parameters main
    (
        assets    type:#nodeTab     tabSizeVariable:true
        clayNodes type:#nodeTab     tabSizeVariable:true
        clayMtls  type:#materialTab tabSizeVariable:true
        clayHad   type:#boolTab     tabSizeVariable:true
    )
)
global LKD_setAssets
fn LKD_setAssets store arr = ( store.assets = arr; arr.count )
global LKD_clayApply
fn LKD_clayApply store clay =
(
    if store.clayNodes.count > 0 do return 0
    local n = 0
    for a in store.assets where isValidNode a do
    (
        local had = (a.material != undefined)
        append store.clayNodes a
        append store.clayHad had
        append store.clayMtls (if had then a.material else clay)
        a.material = clay
        n += 1
    )
    n
)
global LKD_clayRestore
fn LKD_clayRestore store =
(
    local n = 0
    for i = 1 to store.clayNodes.count do
    (
        local a = store.clayNodes[i]
        if isValidNode a do
        (
            a.material = if store.clayHad[i] then store.clayMtls[i] else undefined
            n += 1
        )
    )
    store.clayNodes = #()
    store.clayMtls = #()
    store.clayHad = #()
    n
)
"""


def _ensure_ms_defs():
    rt.execute(_MS_DEFS)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _p3(v):
    return rt.Point3(float(v[0]), float(v[1]), float(v[2]))


def _v3(p):
    return (float(p.x), float(p.y), float(p.z))


def _cam_matrix(frame, pos=None):
    """Matrix with the camera orientation at `pos` (rows = X, Y, Z axes, position)."""
    return rt.Matrix3(_p3(frame.x_axis), _p3(frame.y_axis), _p3(frame.z_axis),
                      _p3(pos if pos is not None else frame.position))


def _is_rig(node):
    return str(node.name).startswith(P)


def rig_nodes():
    return [n for n in rt.objects if _is_rig(n)]


def _store():
    n = rt.getNodeByName(STORE_NAME)
    return None if is_undefined(n) else n


def remove_rig():
    """Puts the asset materials back (if clay is on) and deletes every LKD_ node."""
    set_clay(False)
    for n in rig_nodes():
        if rt.isValidNode(n):
            rt.delete(n)


def _layer():
    lyr = rt.LayerManager.getLayerFromName(core.RIG_LAYER)
    if is_undefined(lyr):
        lyr = rt.LayerManager.newLayerFromName(core.RIG_LAYER)
    return lyr


def _bounds(nodes):
    inf = float("inf")
    lo, hi = [inf, inf, inf], [-inf, -inf, -inf]
    for n in nodes:
        bb = rt.nodeGetBoundingBox(n, rt.Matrix3(1))
        a, b = bb[0], bb[1]
        for i, (va, vb) in enumerate(((a.x, b.x), (a.y, b.y), (a.z, b.z))):
            lo[i] = min(lo[i], va, vb)
            hi[i] = max(hi[i], va, vb)
    return tuple(lo), tuple(hi)


def _render_aspect():
    return (float(rt.renderWidth) / float(rt.renderHeight)) * float(rt.renderPixelAspect)


def _resolve_hdri(hdri):
    if isinstance(hdri, core.HDRI):
        return hdri
    if os.path.isfile(str(hdri)):
        name = os.path.splitext(os.path.basename(hdri))[0]
        return core.find_hdri(name, os.path.dirname(hdri)) or core.HDRI(name, hdri)
    found = core.find_hdri(str(hdri))
    if not found:
        raise ValueError("HDRI not found in the library: %s" % hdri)
    return found


def _ms_str(s):
    return '"%s"' % str(s).replace("\\", "\\\\").replace('"', '\\"')


def _set_z_rotation(node_name, degrees):
    rt.execute('(getNodeByName %s).rotation.controller.Z_Rotation = %f'
               % (_ms_str(node_name), degrees))


def _split_selection(nodes):
    """(geometry, user camera or None) from the selection, ignoring rig nodes."""
    geo, cams = [], []
    for n in nodes:
        if _is_rig(n):
            continue
        sc = rt.superClassOf(n)
        if sc == rt.GeometryClass:
            geo.append(n)
        elif sc == rt.camera:
            cams.append(n)
    return geo, (cams[0] if cams else None)


def _frame_from_camera(cam, bmin, bmax, aspect):
    """Frame matching an existing camera (any type: Free, Physical, V-Ray...)."""
    rt.viewport.setCamera(cam)                     # viewport FOV = camera FOV for every type
    hfov = math.radians(float(rt.getViewFOV()))
    tm = cam.transform
    return core.camera_frame_from_existing(
        _v3(tm.row4), _v3(tm.row1), _v3(tm.row2), _v3(tm.row3), hfov, aspect, bmin, bmax)


def _animate_turntable(root_name, dome_name, timing, hdri_offset):
    """
    Object pass: the root (camera + refs + dome + ground) orbits 360° -> the asset turns
    under fixed light. HDRI pass: the root holds still and only the dome spins 360°.
    Linear keys; the user's default tangent type is restored afterwards.
    """
    s, oe, he = timing.start, timing.object_end, timing.hdri_end
    a = 360.0 * timing.object_sign
    ms = """
(
    local root = getNodeByName {root}
    local dome = getNodeByName {dome}
    local tIn, tOut
    maxOps.getDefaultTangentType &tIn &tOut
    maxOps.setDefaultTangentType #linear #linear writeInCfgFile:false
    with animate on
    (
        at time {s}  root.rotation.controller.Z_Rotation = 0.0
        at time {oe} root.rotation.controller.Z_Rotation = {a}
        at time {oe} dome.rotation.controller.Z_Rotation = {off}
        at time {he} dome.rotation.controller.Z_Rotation = {off_end}
    )
    maxOps.setDefaultTangentType tIn tOut writeInCfgFile:false
    animationRange = interval {s} {he_last}
    rendTimeType = 2
)
""".format(root=_ms_str(root_name), dome=_ms_str(dome_name),
           s=s, oe=oe, he=he, he_last=he - 1, a=a,
           off=hdri_offset, off_end=hdri_offset + 360.0)
    rt.execute(ms)


# ---------------------------------------------------------------------------
# Clay override
# ---------------------------------------------------------------------------

def clay_is_on():
    st = _store()
    if st is None:
        return False
    _ensure_ms_defs()
    try:
        return int(st.clayNodes.count) > 0
    except Exception:  # noqa: BLE001  (store without the attribute)
        return False


def set_clay(on, albedo=None):
    """
    Clay ON: the asset's materials are stored on LKD_store and replaced by a grey
    diffuse (albedo from the preset, 0.18 by default). The rig refs are not touched.
    Clay OFF: original materials go back. Returns the number of objects changed.
    Material edits made on the asset while clay is on are discarded when it is restored.
    """
    st = _store()
    if st is None:
        if on:
            raise RuntimeError("Build the rig first.")
        return 0
    _ensure_ms_defs()
    if not on:
        with pymxs.undo(True, "Lookdev clay off"):
            return int(rt.LKD_clayRestore(st))
    if clay_is_on():
        return 0
    adapter = adapters.detect()
    pname = rt.getUserProp(st, core.USER_PROP_PRESET)
    preset = core.load_preset("turntable_default" if is_undefined(pname) else str(pname))
    value = float(albedo if albedo is not None else preset["clay"].get("albedo", 0.18))
    with pymxs.undo(True, "Lookdev clay on"):
        clay = adapter.mtl_flat(CLAY_MTL_NAME, core.grey(value, preset["working_space"]))
        return int(rt.LKD_clayApply(st, clay))


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build(hdri, preset_name="turntable_default", nodes=None, set_viewport=True,
          overrides=None):
    """
    Builds (or rebuilds) the lookdev rig around `nodes` (default: selection).

    If a camera is selected together with the asset, the rig uses its framing: LKD_cam is
    a copy of it (same transform and FOV) so the turntable never touches the original.

    hdri: library name, path to an .exr/.hdr, or core.HDRI.
    overrides: dict merged over the preset for this build only,
               e.g. {"turntable": {"enabled": False}, "ground": {"shadow_catcher": False}}.
    Returns a dict with the created nodes and the log of properties that could not be set.
    """
    src = list(nodes) if nodes is not None else list(rt.selection)
    geo, user_cam = _split_selection(src)
    if not geo:
        raise ValueError("Select at least one geometry object (not part of the rig).")

    hdri = _resolve_hdri(hdri)
    preset = core.merge(core.load_preset(preset_name), overrides)
    adapter = adapters.detect()
    ws = preset["working_space"]
    aspect = _render_aspect()

    bmin, bmax = _bounds(geo)
    if user_cam is not None:
        frame = _frame_from_camera(user_cam, bmin, bmax, aspect)
    else:
        frame = core.camera_frame(bmin, bmax, preset, aspect, up_axis=UP_AXIS)
    layout = core.reference_layout(frame, preset)
    cast_shadows = bool(preset["refs"].get("cast_shadows", False))

    rig = {"adapter": adapter.name, "hdri": hdri.name, "preset": preset["_name"],
           "camera_source": str(user_cam.name) if user_cam is not None else None,
           "nodes": [], "refs": [], "warnings": []}

    with pymxs.undo(True, "Lookdev Rig"):
        remove_rig()
        _ensure_ms_defs()
        lyr = _layer()

        def keep(node):
            lyr.addNode(node)
            rig["nodes"].append(node)
            return node

        # Store: remembers the asset (and its materials while clay is on)
        store = keep(rt.Dummy())
        store.name = STORE_NAME
        store.boxsize = _p3((frame.radius * 0.05,) * 3)
        rt.custAttributes.add(store, rt.LKD_ClayStoreCA)
        rt.LKD_setAssets(store, geo)
        rt.setUserProp(store, core.USER_PROP_PRESET, preset["_name"])
        store.isHidden = True

        # Root at the asset centre
        root = keep(rt.Dummy())
        root.name = P + "root"
        root.boxsize = _p3((frame.radius * 0.25,) * 3)
        root.position = _p3(frame.target)

        # Camera (automatic framing, or a copy of the selected camera)
        cam = keep(rt.Freecamera())
        cam.name = P + "cam"
        set_prop(cam, "fovType", 1)                 # horizontal FOV
        cam.fov = math.degrees(frame.hfov)
        cam.transform = _cam_matrix(frame)
        cam.parent = root

        # Dome
        intensity = hdri.intensity * float(preset["light"].get("intensity", 1.0))
        dome = keep(adapter.create_dome(hdri.path, intensity, P + "dome"))
        dome.position = _p3(frame.target)
        dome.parent = root

        # Shadow catcher (orbits with the rig: ground and light stay fixed to the camera,
        # exactly like a real object turning on a turntable)
        if preset["ground"].get("shadow_catcher", True):
            try:
                mtl_ground = adapter.mtl_shadow_catcher(P + "mtl_shadow_catcher")
            except NotImplementedError as exc:
                rig["warnings"].append("No shadow catcher: %s" % exc)
            else:
                g = core.ground_plane(bmin, bmax, preset, up_axis=UP_AXIS)
                ground = keep(rt.Plane())
                ground.name = P + "shadow_catcher"
                ground.width = ground.length = g["size"]
                ground.widthsegs = ground.lengthsegs = 1
                ground.position = _p3(g["pos"])
                ground.material = mtl_ground
                ground.castShadows = False
                ground.receiveShadows = True
                ground.parent = root
                rig["ground"] = ground

        # Shared materials
        mtl_chrome = adapter.mtl_chrome(P + "mtl_chrome")
        mtl_grey = adapter.mtl_flat(P + "mtl_grey18", core.grey18(ws))
        mtl_board = adapter.mtl_flat(P + "mtl_chart_board", (0.03, 0.03, 0.03))

        # References
        for item in layout:
            kind = item["kind"]
            cpos = item["pos"]
            if kind in core.BALL_KINDS:
                ball = keep(rt.Sphere())
                ball.name = P + kind
                ball.radius = item["radius"]
                ball.segs = 64
                ball.transform = _cam_matrix(frame, frame.to_world(cpos))
                ball.material = mtl_chrome if kind == "chrome" else mtl_grey
                adapter.setup_ref_node(ball, cast_shadows)
                ball.parent = cam
                rig["refs"].append(ball)

            elif kind == "colorchecker":
                w, h = item["size"]
                lay = core.colorchecker_layout(w, h)
                board = keep(rt.Plane())
                board.name = P + "chart_board"
                board.width, board.length = w, h
                board.widthsegs = board.lengthsegs = 1
                board.transform = _cam_matrix(frame, frame.to_world(cpos))
                board.material = mtl_board
                adapter.setup_ref_node(board, cast_shadows)

                eps = h * 0.003                       # patches just in front of the board
                for p in core.colorchecker_patches(ws):
                    cx, cy = lay["cells"][(p["row"], p["col"])]
                    ppos = frame.to_world((cpos[0] + cx, cpos[1] + cy, cpos[2] + eps))
                    patch = keep(rt.Plane())
                    patch.name = "%schart_%02d_%s" % (P, p["id"], p["name"])
                    patch.width = patch.length = lay["patch"]
                    patch.widthsegs = patch.lengthsegs = 1
                    patch.transform = _cam_matrix(frame, ppos)
                    patch.material = adapter.mtl_flat(P + "mtl_cc_" + p["name"], p["rgb"])
                    adapter.setup_ref_node(patch, cast_shadows)
                    patch.parent = board
                board.parent = cam
                rig["refs"].append(board)

        # HDRI rotation + turntable
        _set_z_rotation(dome.name, hdri.rotation_offset)
        if preset["turntable"].get("enabled", True):
            timing = core.turntable_timing(preset)
            _animate_turntable(root.name, dome.name, timing, hdri.rotation_offset)
            rig["render_range"] = timing.render_range

        # Tag the asset so the same setup can be rebuilt in another DCC
        for n in geo:
            rt.setUserProp(n, core.USER_PROP_HDRI, hdri.name)
            rt.setUserProp(n, core.USER_PROP_PRESET, preset["_name"])

        rig.update({"root": root, "camera": cam, "dome": dome, "store": store,
                    "frame": frame})
        adapter.after_build(rig)

    if preset["clay"].get("enabled", False):
        rig["clay"] = set_clay(True)

    if set_viewport:
        rt.viewport.setCamera(cam)
        rt.redrawViews()

    rig["log"] = list(adapter.log)
    if adapter.log or rig["warnings"]:
        print("[Lookdev Rig] %s:" % adapter.label)
        for line in rig["warnings"] + adapter.log:
            print(line)
    return rig


def stored_settings(node):
    """(hdri, preset) stored on an asset by a previous build, or (None, None)."""
    h = rt.getUserProp(node, core.USER_PROP_HDRI)
    p = rt.getUserProp(node, core.USER_PROP_PRESET)
    return (None if is_undefined(h) else str(h), None if is_undefined(p) else str(p))
