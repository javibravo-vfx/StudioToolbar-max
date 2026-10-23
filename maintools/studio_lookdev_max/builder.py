"""
Lookdev Rig for 3ds Max — rig construction.

From the Python Listener:
    from studio_lookdev_max import builder
    builder.build("studio_softbox_4k")            # on the current selection
    builder.remove_rig()

Hierarchy it creates (layer LOOKDEV_RIG, every node prefixed LKD_):

    LKD_root  (Dummy at the asset centre; spins during the "object" pass)
     |- LKD_cam                (Free camera framing the bounding sphere)
     |   |- LKD_chrome         (chrome ball, fixed size on screen)
     |   |- LKD_grey18         (18% grey ball)
     |   '- LKD_chart_board    (procedural 24-patch ColorChecker)
     '- LKD_dome               (dome light with the HDRI; spins only during the "HDRI" pass)

The asset itself is never modified (apart from two user props with the HDRI/preset used).
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _p3(v):
    return rt.Point3(float(v[0]), float(v[1]), float(v[2]))


def _cam_matrix(frame, pos=None):
    """Matrix with the camera orientation at `pos` (rows = X, Y, Z axes, position)."""
    return rt.Matrix3(_p3(frame.x_axis), _p3(frame.y_axis), _p3(frame.z_axis),
                      _p3(pos if pos is not None else frame.position))


def _is_rig(node):
    return str(node.name).startswith(P)


def rig_nodes():
    return [n for n in rt.objects if _is_rig(n)]


def remove_rig():
    """Deletes the whole rig (only nodes prefixed LKD_)."""
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


def _animate_turntable(root_name, dome_name, timing, hdri_offset):
    """
    Object pass: the root (camera + refs + dome) orbits 360° -> the asset turns under fixed light.
    HDRI pass: the root holds still and only the dome spins 360°.
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
# Build
# ---------------------------------------------------------------------------

def build(hdri, preset_name="turntable_default", nodes=None, set_viewport=True,
          overrides=None):
    """
    Builds (or rebuilds) the lookdev rig around `nodes` (default: selection).

    hdri: library name, path to an .exr/.hdr, or core.HDRI.
    overrides: dict merged over the preset for this build only,
               e.g. {"turntable": {"enabled": False}}.
    Returns a dict with the created nodes and the log of properties that could not be set.
    """
    src = list(nodes) if nodes is not None else list(rt.selection)
    geo = [n for n in src if not _is_rig(n) and rt.superClassOf(n) == rt.GeometryClass]
    if not geo:
        raise ValueError("Select at least one geometry object (not part of the rig).")

    hdri = _resolve_hdri(hdri)
    preset = core.load_preset(preset_name)
    if overrides:
        preset = core._deep_merge(preset, overrides)
    adapter = adapters.detect()
    ws = preset["working_space"]

    bmin, bmax = _bounds(geo)
    frame = core.camera_frame(bmin, bmax, preset, _render_aspect(), up_axis=UP_AXIS)
    layout = core.reference_layout(frame, preset)
    cast_shadows = bool(preset["refs"].get("cast_shadows", False))

    rig = {"adapter": adapter.name, "hdri": hdri.name, "preset": preset["_name"],
           "nodes": [], "refs": []}

    with pymxs.undo(True, "Lookdev Rig"):
        remove_rig()
        lyr = _layer()

        def keep(node):
            lyr.addNode(node)
            rig["nodes"].append(node)
            return node

        # Root at the asset centre
        root = keep(rt.Dummy())
        root.name = P + "root"
        root.boxsize = _p3((frame.radius * 0.25,) * 3)
        root.position = _p3(frame.target)

        # Camera
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

        rig.update({"root": root, "camera": cam, "dome": dome, "frame": frame})
        adapter.after_build(rig)

    if set_viewport:
        rt.viewport.setCamera(cam)
        rt.redrawViews()

    rig["log"] = list(adapter.log)
    if adapter.log:
        print("[Lookdev Rig] Properties not applied (%s):" % adapter.label)
        for line in adapter.log:
            print(line)
    return rig


def stored_settings(node):
    """(hdri, preset) stored on an asset by a previous build, or (None, None)."""
    h = rt.getUserProp(node, core.USER_PROP_HDRI)
    p = rt.getUserProp(node, core.USER_PROP_PRESET)
    return (None if is_undefined(h) else str(h), None if is_undefined(p) else str(p))
