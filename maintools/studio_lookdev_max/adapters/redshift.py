"""
Redshift adapter — STUB.

To enable:
  1. implemented = True
  2. create_dome: rt.RS_Dome_Light() with the HDRI texture (check property names with dump_props).
  3. mtl_chrome / mtl_flat: rt.RS_Standard_Material() (metalness 1 / roughness 0 for chrome;
     base_color + refl_weight 0 for diffuse).
"""

from .base import RenderAdapter, register


@register
class RedshiftAdapter(RenderAdapter):
    name = "redshift"
    label = "Redshift"
    class_tokens = ("redshift",)
    implemented = False

    def create_dome(self, hdri_path, intensity, name):
        raise NotImplementedError("Redshift: pending")

    def mtl_chrome(self, name):
        raise NotImplementedError("Redshift: pending")

    def mtl_flat(self, name, rgb):
        raise NotImplementedError("Redshift: pending")
