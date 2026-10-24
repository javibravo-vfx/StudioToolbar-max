"""Arnold (MAXtoA) adapter for the Lookdev Rig."""

from .base import RenderAdapter, register, rt, max_class, set_prop, set_first, color

# Arnold_Light shape enum in MAXtoA:
# 0 point, 1 distant, 2 spot, 3 quad, 4 disk, 5 cylinder, 6 skydome, 7 photometric, 8 mesh
ARNOLD_SKYDOME = 6


@register
class ArnoldAdapter(RenderAdapter):
    name = "arnold"
    label = "Arnold"
    class_tokens = ("arnold",)

    def check(self):
        if max_class("Arnold_Light") is None:
            raise RuntimeError("Arnold is active but Arnold_Light was not found.")
        if max_class("ai_standard_surface") is None:
            raise RuntimeError("Arnold is active but ai_standard_surface was not found.")

    def _hdri_map(self, path, name):
        ai_image = max_class("ai_image")
        if ai_image is not None:
            tex = ai_image()
            set_first(tex, ("filename", "fileName"), path, self.log)
        else:
            tex = rt.Bitmaptexture()
            tex.filename = path
            tex.coords.mappingType = 1     # Environ
            tex.coords.mapping = 0         # Spherical Environment
        tex.name = name + "_map"
        return tex

    def create_dome(self, hdri_path, intensity, name):
        light = rt.Arnold_Light()
        light.name = name
        set_first(light, ("shapeType", "shape_type", "type"), ARNOLD_SKYDOME, self.log)
        tex = self._hdri_map(hdri_path, name)
        set_first(light, ("texmap", "color_texmap", "shader"), tex, self.log)
        set_first(light, ("texmapOn", "texmap_on", "use_texmap", "useTexmap"), True, self.log)
        set_first(light, ("useColor", "use_color"), False, self.log)
        set_prop(light, "intensity", float(intensity), self.log)
        set_prop(light, "exposure", 0.0, self.log)
        set_first(light, ("camera", "visible_camera", "camera_visibility"), 1.0, self.log)
        return light

    def make_camera_only(self, node):
        set_first(node, ("camera", "visible_camera", "camera_visibility"), 1.0, self.log)
        for p in ("diffuse", "specular", "sss", "indirect", "volume", "transmission"):
            set_first(node, (p, p + "_visibility", "visible_" + p), 0.0, self.log)

    def set_dome_background(self, node, visible):
        return set_first(node, ("camera", "visible_camera", "camera_visibility"),
                         1.0 if visible else 0.0, self.log) is not None

    def mtl_chrome(self, name):
        m = rt.ai_standard_surface()
        m.name = name
        set_prop(m, "base", 1.0, self.log)
        set_prop(m, "base_color", rt.Color(255, 255, 255), self.log)
        set_prop(m, "metalness", 1.0, self.log)
        set_prop(m, "specular", 1.0, self.log)
        set_prop(m, "specular_color", rt.Color(255, 255, 255), self.log)
        set_prop(m, "specular_roughness", 0.0, self.log)
        return m

    def mtl_flat(self, name, rgb):
        m = rt.ai_standard_surface()
        m.name = name
        set_prop(m, "base", 1.0, self.log)
        set_prop(m, "base_color", color(rgb), self.log)
        set_prop(m, "diffuse_roughness", 0.0, self.log)
        set_prop(m, "metalness", 0.0, self.log)
        set_prop(m, "specular", 0.0, self.log)                   # pure diffuse
        return m

    def mtl_shadow_catcher(self, name):
        cls = max_class("ai_shadow_matte")
        if cls is None:
            raise NotImplementedError("Arnold: ai_shadow_matte not found")
        m = cls()
        m.name = name
        set_prop(m, "shadow_opacity", 1.0, self.log)
        return m

    def setup_ref_node(self, node, cast_shadows=False):
        super(ArnoldAdapter, self).setup_ref_node(node, cast_shadows)
        # Per-ray visibility lives in the node's Arnold Properties (MAXtoA).
        # Left manual for now; castShadows already keeps shadows off the asset.
