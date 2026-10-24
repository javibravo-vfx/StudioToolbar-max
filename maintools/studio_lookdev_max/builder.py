"""
Lookdev Rig for 3ds Max — rig construction.

From the Python Listener:
    from studio_lookdev_max import builder
    builder.build("studio_softbox_4k")            # on the current selection
    builder.set_clay(True)                        # grey override on the asset
    builder.set_hdri("exterior_overcast_8k")      # live: swap / rotate / expose the dome
    builder.set_rotation(90); builder.set_exposure(-0.5)
    builder.remove_rig()

Hierarchy it creates (layer LOOKDEV_RIG, every node prefixed LKD_):

    LKD_root  (Dummy at the asset centre; spins during the "object" pass)
     |- LKD_cam                (Free camera: framed automatically, or a copy of the
     |   |                      camera selected with the asset)
     |   |- LKD_chrome         (chrome ball, fixed size on screen)
     |   |- LKD_grey18         (18% grey ball)
     |   '- LKD_chart_board    (procedural 24-patch ColorChecker)
     |- LKD_hdri_spin          (Dummy; spins 360° during the "HDRI" pass)
     |   '- LKD_dome           (dome light with the HDRI; its own Z rotation = HDRI offset,
     |                          so the offset can be changed live without re-keying)
     '- LKD_shadow_catcher     (ground plane under the asset that only shows shadows)
    LKD_store (hidden Dummy: remembers the asset and its materials while clay is on)

The asset is never modified, except:
  - two user props with the HDRI / preset used;
  - clay mode: its materials are swapped for a grey one and stored on LKD_store,
    and put back when clay is turned off or the rig is deleted.
"""

import json
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
DOME_NAME = P + "dome"
SPIN_NAME = P + "hdri_spin"
CLAY_MTL_NAME = P + "mtl_clay"

# HDRI state kept as user props on LKD_store (survives save / reopen)
UP_ROT = "lookdev_rotation"            # absolute HDRI rotation, degrees
UP_EV = "lookdev_exposure"             # EV on top of the base intensity
UP_BASE = "lookdev_base_intensity"     # sidecar intensity * preset light intensity
UP_BG = "lookdev_bg_visible"
UP_BG_COLOR = "lookdev_bg_color"       # linear r,g,b used when the dome is hidden
UP_PREV_ENV = "lookdev_prev_env"       # scene background before the rig changed it
UP_REFS = "lookdev_refs"               # JSON: items / corner / chart currently built
UP_DIST = "lookdev_distance"           # lens -> asset distance (keeps ref size on rebuild)
UP_RADIUS = "lookdev_radius"
REF_NAMES = (P + "chrome", P + "grey18", P + "chart_board")

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
    _restore_environment()
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


def _animate_turntable(root_name, spin_name, timing):
    """
    Object pass: the root (camera + refs + dome + ground) orbits 360° -> the asset turns
    under fixed light. HDRI pass: the root holds still and only LKD_hdri_spin turns 360°.
    Linear keys; the user's default tangent type is restored afterwards.
    """
    s, oe, he = timing.start, timing.object_end, timing.hdri_end
    a = 360.0 * timing.object_sign
    ms = """
(
    local root = getNodeByName {root}
    local spin = getNodeByName {spin}
    local tIn, tOut
    maxOps.getDefaultTangentType &tIn &tOut
    maxOps.setDefaultTangentType #linear #linear writeInCfgFile:false
    with animate on
    (
        at time {s}  root.rotation.controller.Z_Rotation = 0.0
        at time {oe} root.rotation.controller.Z_Rotation = {a}
        at time {oe} spin.rotation.controller.Z_Rotation = 0.0
        at time {he} spin.rotation.controller.Z_Rotation = 360.0
    )
    maxOps.setDefaultTangentType tIn tOut writeInCfgFile:false
    animationRange = interval {s} {he_last}
    rendTimeType = 2
)
""".format(root=_ms_str(root_name), spin=_ms_str(spin_name),
           s=s, oe=oe, he=he, he_last=he - 1, a=a)
    rt.execute(ms)


# ---------------------------------------------------------------------------
# Live HDRI controls (no rebuild)
# ---------------------------------------------------------------------------

def _node(name):
    n = rt.getNodeByName(name)
    return None if is_undefined(n) else n


def _prop_float(node, key, default):
    v = rt.getUserProp(node, key)
    if is_undefined(v):
        return default
    try:
        return float(str(v))
    except ValueError:
        return default


def _require_rig():
    st, dome = _store(), _node(DOME_NAME)
    if st is None or dome is None:
        raise RuntimeError("Build the rig first.")
    return st, dome


def hdri_state():
    """Current dome state, or None when there is no rig:
    {hdri, rotation, exposure, base_intensity, bg_visible}."""
    st, dome = _store(), _node(DOME_NAME)
    if st is None or dome is None:
        return None
    h = rt.getUserProp(st, core.USER_PROP_HDRI)
    return {
        "hdri": None if is_undefined(h) else str(h),
        "rotation": _prop_float(st, UP_ROT, 0.0),
        "exposure": _prop_float(st, UP_EV, 0.0),
        "base_intensity": _prop_float(st, UP_BASE, 1.0),
        "bg_visible": _prop_float(st, UP_BG, 1.0) > 0.5,
    }


def set_rotation(degrees):
    """Absolute HDRI rotation (the turntable spin is added on top)."""
    st, dome = _require_rig()
    _set_z_rotation(dome.name, float(degrees))
    rt.setUserProp(st, UP_ROT, float(degrees))


def set_exposure(ev):
    st, dome = _require_rig()
    base = _prop_float(st, UP_BASE, 1.0)
    adapters.detect().set_dome_intensity(dome, base * (2.0 ** float(ev)))
    rt.setUserProp(st, UP_EV, float(ev))


def set_background_visible(visible, color=None):
    """Dome visible to camera, or hidden with a flat background colour (linear rgb)."""
    st, dome = _require_rig()
    adapters.detect().set_dome_background(dome, bool(visible))
    rt.setUserProp(st, UP_BG, 1 if visible else 0)
    if color is not None:
        rt.setUserProp(st, UP_BG_COLOR, ",".join("%.6f" % v for v in color[:3]))
    if visible:
        _restore_environment()
    else:
        _apply_background_color(st, background_color())


def set_hdri(hdri, keep_adjustments=False):
    """
    Swaps the dome texture without rebuilding. By default the new HDRI starts from its own
    sidecar defaults (rotation offset, intensity) and EV 0.
    Returns the resolved core.HDRI.
    """
    st, dome = _require_rig()
    hdri = _resolve_hdri(hdri)
    adapter = adapters.detect()
    adapter.set_dome_hdri(dome, hdri.path)
    pname = rt.getUserProp(st, core.USER_PROP_PRESET)
    preset = core.load_preset("turntable_default" if is_undefined(pname) else str(pname))
    base = hdri.intensity * float(preset["light"].get("intensity", 1.0))
    rt.setUserProp(st, UP_BASE, base)
    rt.setUserProp(st, core.USER_PROP_HDRI, hdri.name)
    if keep_adjustments:
        set_exposure(_prop_float(st, UP_EV, 0.0))
    else:
        set_rotation(hdri.rotation_offset)
        set_exposure(0.0)
    for a in (st.assets if hasattr(st, "assets") else []):
        if rt.isValidNode(a):
            rt.setUserProp(a, core.USER_PROP_HDRI, hdri.name)
    return hdri


def save_hdri_defaults():
    """
    Writes the current rotation and intensity into the HDRI sidecar, so every toolbar
    (Max, Houdini, Blender, Maya) starts from them. EV is folded into the intensity.
    """
    st, _dome = _require_rig()
    state = hdri_state()
    hdri = _resolve_hdri(state["hdri"])
    intensity = hdri.intensity * (2.0 ** state["exposure"])
    core.save_sidecar(hdri.path, {"rotation_offset_deg": round(state["rotation"], 3),
                                  "intensity": round(intensity, 5)})
    pname = rt.getUserProp(st, core.USER_PROP_PRESET)
    preset = core.load_preset("turntable_default" if is_undefined(pname) else str(pname))
    rt.setUserProp(st, UP_BASE, intensity * float(preset["light"].get("intensity", 1.0)))
    rt.setUserProp(st, UP_EV, 0.0)
    return {"rotation_offset_deg": state["rotation"], "intensity": intensity}


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

# ---------------------------------------------------------------------------
# References (balls + chart)
# ---------------------------------------------------------------------------

def _refs_settings(preset):
    r = preset["refs"]
    return {"items": [i for i in r.get("items", []) if i in core.REF_ITEMS],
            "corner": r.get("corner", "bottom_right"),
            "chart": r.get("chart", core.DEFAULT_CHART)}


def _build_refs(adapter, frame, preset, cam, keep):
    """Creates the enabled references in the chosen corner, packed from the corner inwards."""
    ws = preset["working_space"]
    r = preset["refs"]
    cast_shadows = bool(r.get("cast_shadows", False))
    chart = None
    if "colorchecker" in r.get("items", []):
        chart = core.load_chart(r.get("chart") or core.DEFAULT_CHART, ws)
    aspect = (chart["cols"] / float(chart["rows"])) if chart else 1.5
    layout = core.reference_layout(frame, preset, chart_aspect=aspect)
    nodes = []
    mtl_chrome = mtl_grey = None
    for item in layout:
        kind, cpos = item["kind"], item["pos"]
        if kind in core.BALL_KINDS:
            if kind == "chrome":
                mtl_chrome = mtl_chrome or adapter.mtl_chrome(P + "mtl_chrome")
            else:
                mtl_grey = mtl_grey or adapter.mtl_flat(P + "mtl_grey18", core.grey18(ws))
            ball = keep(rt.Sphere())
            ball.name = P + kind
            ball.radius = item["radius"]
            ball.segs = 64
            ball.transform = _cam_matrix(frame, frame.to_world(cpos))
            ball.material = mtl_chrome if kind == "chrome" else mtl_grey
            adapter.setup_ref_node(ball, cast_shadows)
            ball.parent = cam
            nodes.append(ball)
        elif kind == "colorchecker" and chart:
            w, h = item["size"]
            lay = core.colorchecker_layout(w, h, rows=chart["rows"], cols=chart["cols"])
            board = keep(rt.Plane())
            board.name = P + "chart_board"
            board.width, board.length = w, h
            board.widthsegs = board.lengthsegs = 1
            board.transform = _cam_matrix(frame, frame.to_world(cpos))
            board.material = adapter.mtl_flat(P + "mtl_chart_board", (0.03, 0.03, 0.03))
            adapter.setup_ref_node(board, cast_shadows)
            rt.setUserProp(board, "lookdev_chart", chart["id"])
            eps = h * 0.003                       # patches just in front of the board
            for p in chart["patches"]:
                cell = lay["cells"].get((p["row"], p["col"]))
                if cell is None:
                    continue
                ppos = frame.to_world((cpos[0] + cell[0], cpos[1] + cell[1], cpos[2] + eps))
                patch = keep(rt.Plane())
                patch.name = "%schart_%02d_%s" % (P, p["id"], p["name"])
                patch.width = patch.length = lay["patch"]
                patch.widthsegs = patch.lengthsegs = 1
                patch.transform = _cam_matrix(frame, ppos)
                patch.material = adapter.mtl_flat(P + "mtl_cc_" + p["name"], p["rgb"])
                adapter.setup_ref_node(patch, cast_shadows)
                patch.parent = board
            board.parent = cam
            nodes.append(board)
    return nodes


def refs_state():
    """{items, corner, chart} of the built rig, or None."""
    st = _store()
    if st is None:
        return None
    raw = rt.getUserProp(st, UP_REFS)
    try:
        return json.loads(str(raw)) if not is_undefined(raw) else None
    except ValueError:
        return None


def update_refs(items=None, corner=None, chart=None):
    """
    Rebuilds only the balls / chart on the existing rig (no full rebuild): toggle each
    reference, move them to another corner or swap the chart. Missing items are packed
    towards the corner automatically.
    """
    st, _dome = _require_rig()
    cam = _node(P + "cam")
    if cam is None:
        raise RuntimeError("Rig camera missing — rebuild the rig.")
    pname = rt.getUserProp(st, core.USER_PROP_PRESET)
    preset = core.load_preset("turntable_default" if is_undefined(pname) else str(pname))
    cur = refs_state() or _refs_settings(preset)
    if items is not None:
        cur["items"] = [i for i in core.REF_ITEMS if i in items]   # canonical order
    if corner is not None:
        cur["corner"] = corner
    if chart is not None:
        cur["chart"] = chart
    preset = core.merge(preset, {"refs": cur})

    # frame from the camera as it is now (refs are placed in camera space, so the current
    # turntable frame does not matter)
    tm = cam.transform
    hfov = math.radians(float(cam.fov))
    frame = core.CameraFrame(_v3(tm.row4), core._norm(_v3(tm.row1)), core._norm(_v3(tm.row2)),
                             core._norm(_v3(tm.row3)), _v3(tm.row4),
                             _prop_float(st, UP_DIST, 100.0), hfov,
                             core.vfov_from_hfov(hfov, _render_aspect()),
                             _prop_float(st, UP_RADIUS, 10.0))
    adapter = adapters.detect()
    with pymxs.undo(True, "Lookdev references"):
        for n in rig_nodes():
            name = str(n.name)
            if rt.isValidNode(n) and (name in REF_NAMES or name.startswith(P + "chart_")):
                rt.delete(n)
        lyr = _layer()

        def keep(node):
            lyr.addNode(node)
            return node

        nodes = _build_refs(adapter, frame, preset, cam, keep)
        rt.setUserProp(st, UP_REFS, json.dumps(cur))
    rt.redrawViews()
    return {"refs": nodes, "settings": cur, "log": list(adapter.log)}


# ---------------------------------------------------------------------------
# Background colour when the dome is hidden
# ---------------------------------------------------------------------------

def _restore_environment():
    st = _store()
    if st is None:
        return
    raw = rt.getUserProp(st, UP_PREV_ENV)
    if is_undefined(raw) or not str(raw):
        return
    try:
        prev = json.loads(str(raw))
        rt.backgroundColor = rt.Color(*prev["color"])
        rt.useEnvironmentMap = bool(prev["use_map"])
    except Exception:  # noqa: BLE001
        pass
    rt.setUserProp(st, UP_PREV_ENV, "")


def _apply_background_color(st, rgb):
    raw = rt.getUserProp(st, UP_PREV_ENV)
    if is_undefined(raw) or not str(raw):          # remember the scene setting once
        c = rt.backgroundColor
        rt.setUserProp(st, UP_PREV_ENV, json.dumps(
            {"color": [float(c.r), float(c.g), float(c.b)],
             "use_map": bool(rt.useEnvironmentMap)}))
    rt.backgroundColor = rt.Color(rgb[0] * 255.0, rgb[1] * 255.0, rgb[2] * 255.0)
    rt.useEnvironmentMap = False                  # an environment map would cover the colour


def background_color():
    """Linear rgb used behind the asset when the dome is hidden."""
    st = _store()
    default = (0.18, 0.18, 0.18)
    if st is None:
        return default
    raw = rt.getUserProp(st, UP_BG_COLOR)
    try:
        return tuple(float(v) for v in str(raw).split(","))[:3] if not is_undefined(raw) else default
    except ValueError:
        return default


def set_background_color(rgb):
    """Colour (linear, working space) seen in the render when the dome is hidden."""
    st, _dome = _require_rig()
    rt.setUserProp(st, UP_BG_COLOR, ",".join("%.6f" % v for v in rgb[:3]))
    if not hdri_state()["bg_visible"]:
        _apply_background_color(st, rgb)


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

        # HDRI spin pivot + dome
        spin = keep(rt.Dummy())
        spin.name = SPIN_NAME
        spin.boxsize = _p3((frame.radius * 0.15,) * 3)
        spin.position = _p3(frame.target)
        spin.parent = root
        intensity = hdri.intensity * float(preset["light"].get("intensity", 1.0))
        dome = keep(adapter.create_dome(hdri.path, intensity, DOME_NAME))
        dome.position = _p3(frame.target)
        dome.parent = spin

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

        # References (balls + chart), parented to the camera
        rt.setUserProp(store, UP_DIST, frame.distance)
        rt.setUserProp(store, UP_RADIUS, frame.radius)
        rig["refs"] = _build_refs(adapter, frame, preset, cam, keep)
        rt.setUserProp(store, UP_REFS, json.dumps(_refs_settings(preset)))

        # HDRI rotation + turntable
        _set_z_rotation(dome.name, hdri.rotation_offset)
        rt.setUserProp(store, core.USER_PROP_HDRI, hdri.name)
        rt.setUserProp(store, UP_ROT, hdri.rotation_offset)
        rt.setUserProp(store, UP_EV, 0.0)
        rt.setUserProp(store, UP_BASE, intensity)
        rt.setUserProp(store, UP_BG, 1)
        if preset["turntable"].get("enabled", True):
            timing = core.turntable_timing(preset)
            _animate_turntable(root.name, spin.name, timing)
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
