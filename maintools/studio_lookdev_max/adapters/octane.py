"""
Octane adapter — STUB.

To enable:
  1. implemented = True
  2. create_dome: Octane uses the environment (Texture Environment with the HDRI image)
     instead of a light node. Return a Dummy named `name` and set the environment in the
     render settings; in `after_build(rig)` wire the Dummy's Z rotation to the
     environment rotation (float expression / wire) so the HDRI turntable works the same
     as in V-Ray / Arnold.
  3. mtl_chrome / mtl_flat: Universal Material (metallic 1 / roughness 0; pure diffuse).
"""

from .base import RenderAdapter, register


@register
class OctaneAdapter(RenderAdapter):
    name = "octane"
    label = "Octane"
    class_tokens = ("octane",)
    implemented = False

    def create_dome(self, hdri_path, intensity, name):
        raise NotImplementedError("Octane: pending")

    def mtl_chrome(self, name):
        raise NotImplementedError("Octane: pending")

    def mtl_flat(self, name, rgb):
        raise NotImplementedError("Octane: pending")
