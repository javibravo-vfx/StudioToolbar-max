"""
Render engine adapters for the Lookdev Rig (3ds Max).

Each engine implements ONLY four things:
    create_dome(hdri_path, intensity, name)  -> light node carrying the HDRI
    mtl_chrome(name)                         -> perfect mirror material
    mtl_flat(name, rgb)                      -> pure diffuse material (18% grey, chart patches)
    mtl_shadow_catcher(name)                 -> matte that only shows shadows (optional)
    setup_ref_node(node, cast_shadows)       -> visibility of balls / chart

Everything else (camera, layout, turntable) is shared and lives in builder.py and the
DCC-agnostic core (T:\\.studio-toolbar\\shared\\python\\studio_lookdev\\core.py).

Adding an engine (Redshift, Octane, Corona...):
    1. Create adapters/<engine>.py with a class that inherits RenderAdapter.
    2. Decorate it with @register and fill class_tokens with text that appears in
       classOf(renderers.current) for that engine.
    3. Import it in adapters/__init__.py.
"""

import pymxs

rt = pymxs.runtime

REGISTRY = {}


def register(cls):
    REGISTRY[cls.name] = cls
    return cls


class UnsupportedRenderer(Exception):
    pass


# ---------------------------------------------------------------------------
# Safe helpers: property names change between plugin versions, so nothing is
# assumed — every property is probed and the missing ones are logged.
# ---------------------------------------------------------------------------

def is_undefined(v):
    return v is None or v == rt.undefined


def max_class(*names):
    """First MAXScript class that exists, from a list of candidates."""
    for n in names:
        try:
            c = getattr(rt, n)
        except AttributeError:
            continue
        if not is_undefined(c):
            return c
    return None


def set_prop(obj, prop, value, log=None):
    try:
        if rt.isProperty(obj, prop):
            rt.setProperty(obj, prop, value)
            return True
    except Exception as exc:  # noqa: BLE001
        if log is not None:
            log.append("  ! %s.%s: %s" % (rt.classOf(obj), prop, exc))
        return False
    if log is not None:
        log.append("  - %s has no .%s" % (rt.classOf(obj), prop))
    return False


def set_first(obj, props, value, log=None):
    """Sets the first property of the list that exists. Returns the one used."""
    for p in props:
        try:
            if rt.isProperty(obj, p):
                rt.setProperty(obj, p, value)
                return p
        except Exception:  # noqa: BLE001
            continue
    if log is not None:
        log.append("  - %s: none of %s" % (rt.classOf(obj), list(props)))
    return None


def color(rgb):
    """Linear 0-1 rgb (working space) -> Max Color (0-255 scale, linear)."""
    return rt.Color(rgb[0] * 255.0, rgb[1] * 255.0, rgb[2] * 255.0)


def dump_props(obj):
    """Debug: prints an object's properties in the Listener."""
    print("%s:" % rt.classOf(obj))
    for n in rt.getPropNames(obj):
        print("   .%s" % n)


class RenderAdapter(object):
    name = "base"
    label = "Base"
    class_tokens = ()       # lowercase text found in classOf(renderers.current)
    implemented = True      # False = stub: detected, but it won't build

    def __init__(self):
        self.log = []

    # --- per engine ----------------------------------------------------------

    def create_dome(self, hdri_path, intensity, name):
        raise NotImplementedError

    def mtl_chrome(self, name):
        raise NotImplementedError

    def mtl_flat(self, name, rgb):
        raise NotImplementedError

    def mtl_shadow_catcher(self, name):
        """Optional: engines without it simply build the rig with no ground."""
        raise NotImplementedError("%s: no shadow catcher material" % self.label)

    # --- shared, can be overridden -------------------------------------------

    def setup_ref_node(self, node, cast_shadows=False):
        node.castShadows = bool(cast_shadows)
        node.receiveShadows = True

    def check(self):
        """Checks the engine's classes are loaded. Raises if something is missing."""
        return True

    # --- live dome controls (generic; override when an engine differs) --------

    TEXMAP_PROPS = ("texmap", "color_texmap", "shader")
    FILENAME_PROPS = ("HDRIMapName", "filename", "fileName")
    INTENSITY_PROPS = ("multiplier", "intensity")

    def dome_texmap(self, node):
        for p in self.TEXMAP_PROPS:
            if rt.isProperty(node, p):
                tex = rt.getProperty(node, p)
                if not is_undefined(tex):
                    return tex
        return None

    def set_dome_hdri(self, node, path):
        tex = self.dome_texmap(node)
        if tex is None:
            self.log.append("  - %s: dome has no texture slot" % self.label)
            return False
        return set_first(tex, self.FILENAME_PROPS, path, self.log) is not None

    def set_dome_intensity(self, node, value):
        return set_first(node, self.INTENSITY_PROPS, float(value), self.log) is not None

    def set_dome_background(self, node, visible):
        """Dome visible to camera (background) or not (alpha for comp)."""
        self.log.append("  - %s: background toggle not supported" % self.label)
        return False

    def after_build(self, rig):
        """
        Optional hook at the end of the build. `rig` is the dict builder.build() returns.
        e.g. Octane: wire the dome node (a Dummy) rotation to the environment rotation.
        """
        return None


def detect():
    """Adapter for the active renderer."""
    cls_name = str(rt.classOf(rt.renderers.current)).lower()
    for adapter_cls in REGISTRY.values():
        if any(tok in cls_name for tok in adapter_cls.class_tokens):
            if not adapter_cls.implemented:
                raise UnsupportedRenderer(
                    "%s detected, but its adapter is not implemented yet." % adapter_cls.label)
            adapter = adapter_cls()
            adapter.check()
            return adapter
    raise UnsupportedRenderer(
        "Unsupported renderer: %s. Supported: %s"
        % (rt.classOf(rt.renderers.current),
           ", ".join(c.label for c in REGISTRY.values() if c.implemented)))
