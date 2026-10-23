# -*- coding: utf-8 -*-
"""
Lookdev Rig launcher — run by the Lookdev button of the Studio Toolbar.

Builds a lookdev / turntable setup around the selection: camera framed to the asset,
chrome ball, 18% grey ball, procedural ColorChecker and a dome light with an HDRI from the
shared library. V-Ray and Arnold supported; Redshift / Octane adapters are stubs.

Code:   maintools/studio_lookdev_max/        (Max side: builder, UI, engine adapters)
Shared: T:\\.studio-toolbar\\shared\\         (read by every DCC toolbar)
          lookdev\\hdri\\      HDRIs (+ optional .json sidecar and .jpg thumbnail)
          lookdev\\presets\\   framing / refs / turntable presets
          lookdev\\reference\\ ColorChecker values
          python\\studio_lookdev\\core.py   DCC-agnostic math
Override the root with the STUDIO_TOOLBAR_ROOT environment variable.
"""

import os
import sys

from pymxs import runtime as rt

_ROOT = os.environ.get("STUDIO_TOOLBAR_ROOT", r"T:\.studio-toolbar")
_HERE = os.path.dirname(os.path.abspath(__file__))
_SHARED = os.path.join(_ROOT, "shared", "python")


def _launch():
    for p in (_HERE, _SHARED):
        if p not in sys.path:
            sys.path.insert(0, p)

    if not os.path.isfile(os.path.join(_SHARED, "studio_lookdev", "core.py")):
        rt.messageBox("Lookdev Rig: shared library not found.\n\n"
                      "Expected:\n%s\\studio_lookdev\\core.py\n\n"
                      "Copy the 'shared' folder to %s." % (_SHARED, _ROOT),
                      title="Lookdev Rig")
        return None

    import studio_lookdev_max
    # Pick up script updates on the studio drive without restarting Max,
    # but only when the dialog is not open (keeps a live window intact).
    ui_mod = sys.modules.get("studio_lookdev_max.ui")
    dlg = getattr(ui_mod, "_INSTANCE", None) if ui_mod else None
    try:
        open_now = dlg is not None and dlg.isVisible()
    except RuntimeError:
        open_now = False
    if not open_now:
        for name in sorted([m for m in sys.modules
                            if m == "studio_lookdev" or m.startswith("studio_lookdev.")
                            or m.startswith("studio_lookdev_max")], key=len, reverse=True):
            sys.modules.pop(name, None)
        import studio_lookdev_max  # noqa: F811
    return studio_lookdev_max.show()


window = _launch()
