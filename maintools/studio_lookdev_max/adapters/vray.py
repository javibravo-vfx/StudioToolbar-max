"""V-Ray (5, 6, 7) adapter for the Lookdev Rig."""

from .base import RenderAdapter, register, rt, max_class, set_prop, set_first, color


@register
class VRayAdapter(RenderAdapter):
    name = "vray"
    label = "V-Ray"
    class_tokens = ("v_ray", "vray")

    def check(self):
        if max_class("VRayLight") is None or max_class("VRayMtl") is None:
            raise RuntimeError("V-Ray is active but VRayLight / VRayMtl were not found.")

    def create_dome(self, hdri_path, intensity, name):
        tex_cls = max_class("VRayBitmap", "VRayHDRI")
        tex = tex_cls()
        tex.name = name + "_map"
        set_first(tex, ("HDRIMapName", "filename"), hdri_path, self.log)
        set_prop(tex, "mapType", 2, self.log)                    # 2 = spherical
        set_prop(tex, "horizontalRotation", 0.0, self.log)       # rotation lives on the node

        light = rt.VRayLight()
        light.name = name
        set_prop(light, "type", 1, self.log)                     # 1 = dome
        set_prop(light, "dome_spherical", True, self.log)
        set_prop(light, "texmap", tex, self.log)
        set_prop(light, "texmap_on", True, self.log)
        set_prop(light, "multiplier", float(intensity), self.log)
        set_prop(light, "invisible", False, self.log)            # background visible to camera
        self._lock_texture_to_icon(light)
        return light

    # Names V-Ray has used for the dome's "Lock texture to icon" option. Without it the
    # HDRI stays fixed in world space and rotating the light (or the turntable) does nothing.
    LOCK_PROPS = ("texmap_locktolight", "dome_locktexture", "lock_texture_to_icon",
                  "lockTextureToIcon", "texmap_lock", "dome_lock_texture")

    def _lock_texture_to_icon(self, light):
        if set_first(light, self.LOCK_PROPS, True) is not None:
            return True
        # Unknown V-Ray build: look for any property that reads like "lock … tex/icon"
        try:
            names = [str(n) for n in rt.getPropNames(light)]
        except Exception:  # noqa: BLE001
            names = []
        for n in names:
            low = n.lower().lstrip("#")
            if "lock" in low and ("tex" in low or "icon" in low):
                if set_prop(light, low, True, self.log):
                    return True
        self.log.append("  ! V-Ray: 'Lock texture to icon' not found — tick it on LKD_dome "
                        "or the HDRI won't rotate")
        return False

    def make_camera_only(self, node):
        for p in ("affect_diffuse", "affect_specular", "affect_reflections"):
            set_prop(node, p, False, self.log)
        set_prop(node, "invisible", False, self.log)
        set_first(node, ("castShadows", "cast_shadows"), False)

    def set_dome_background(self, node, visible):
        return set_prop(node, "invisible", not visible, self.log)

    def mtl_chrome(self, name):
        m = rt.VRayMtl()
        m.name = name
        set_prop(m, "diffuse", rt.Color(0, 0, 0), self.log)
        set_prop(m, "reflection", rt.Color(255, 255, 255), self.log)
        set_prop(m, "reflection_glossiness", 1.0, self.log)
        set_prop(m, "reflection_fresnel", False, self.log)
        set_prop(m, "reflection_metalness", 0.0, self.log)
        return m

    def mtl_flat(self, name, rgb):
        m = rt.VRayMtl()
        m.name = name
        set_prop(m, "diffuse", color(rgb), self.log)
        set_prop(m, "reflection", rt.Color(0, 0, 0), self.log)   # pure diffuse
        set_prop(m, "diffuse_roughness", 0.0, self.log)
        return m

    def mtl_shadow_catcher(self, name):
        if max_class("VRayMtlWrapper") is None:
            raise NotImplementedError("V-Ray: VRayMtlWrapper not found")
        base = rt.VRayMtl()
        base.name = name + "_base"
        set_prop(base, "diffuse", color((0.18, 0.18, 0.18)), self.log)
        set_prop(base, "reflection", rt.Color(0, 0, 0), self.log)
        w = rt.VRayMtlWrapper()
        w.name = name
        set_first(w, ("baseMtl", "base_material"), base, self.log)
        set_first(w, ("matte_surface", "matteSurface"), True, self.log)
        set_first(w, ("alpha_contribution", "alphaContribution"), -1.0, self.log)
        set_first(w, ("matte_shadows", "shadows"), True, self.log)
        set_first(w, ("matte_shadowsAffectAlpha", "shadows_affect_alpha", "affect_alpha"),
                  True, self.log)
        set_first(w, ("generateGI", "generate_GI"), False, self.log)
        return w

    def setup_ref_node(self, node, cast_shadows=False):
        super(VRayAdapter, self).setup_ref_node(node, cast_shadows)
        # Keep the references out of the asset's reflections / GI.
        # These are the user props the "V-Ray object properties" dialog writes.
        rt.setUserProp(node, "VRay_GI_VisibleToReflections", "false")
        rt.setUserProp(node, "VRay_GI_VisibleToRefractions", "false")
        rt.setUserProp(node, "VRay_GI_Generate", "false")
