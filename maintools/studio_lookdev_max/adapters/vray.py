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
        return light

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

    def setup_ref_node(self, node, cast_shadows=False):
        super(VRayAdapter, self).setup_ref_node(node, cast_shadows)
        # Keep the references out of the asset's reflections / GI.
        # These are the user props the "V-Ray object properties" dialog writes.
        rt.setUserProp(node, "VRay_GI_VisibleToReflections", "false")
        rt.setUserProp(node, "VRay_GI_VisibleToRefractions", "false")
        rt.setUserProp(node, "VRay_GI_Generate", "false")
