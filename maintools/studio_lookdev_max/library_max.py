"""
HDRI library maintenance from 3ds Max: image I/O for studio_lookdev.library.

    from studio_lookdev_max import library_max
    report = library_max.refresh()          # thumbnails + blurred backgrounds (+ .tx)

Reads HDRIs with Max's own bitmap loaders (no extra dependencies), writes thumbnails
with Qt, the blurred background as EXR with Max. Generated files live in
shared/lookdev/hdri/_cache/ and are used by every DCC toolbar.
"""

import glob
import os

import pymxs

try:
    from PySide6 import QtGui
except ImportError:  # Max 2024 and older
    from PySide2 import QtGui

from .builder import core
from studio_lookdev import library

rt = pymxs.runtime


def _pixels(bmp, y, w):
    try:
        return rt.getPixels(bmp, rt.Point2(0, y), w, linear=True)
    except Exception:  # noqa: BLE001  (older Max without linear:)
        return rt.getPixels(bmp, rt.Point2(0, y), w)


def read_linear(path, w, h):
    """HDRI resampled to w x h, as flat linear floats (1.0 = white)."""
    src = rt.openBitMap(path)
    if src is None or src == rt.undefined:
        raise IOError("Max could not open %s" % path)
    small = rt.bitmap(w, h, hdr=True)
    try:
        rt.copy(src, small)
        out = []
        for y in range(h):
            for c in _pixels(small, y, w):
                out.extend((c.r / 255.0, c.g / 255.0, c.b / 255.0))
        return out
    finally:
        rt.close(src)
        rt.close(small)


def write_jpg(path, rgb8, w, h):
    img = QtGui.QImage(rgb8, w, h, w * 3, QtGui.QImage.Format_RGB888)
    if not img.copy().save(path, "JPG", 90):
        raise IOError("could not write %s" % path)


def write_exr(path, rgb, w, h):
    bmp = rt.bitmap(w, h, hdr=True, filename=path)
    try:
        for y in range(h):
            row = [rt.Color(rgb[i] * 255.0, rgb[i + 1] * 255.0, rgb[i + 2] * 255.0)
                   for i in range((y * w) * 3, (y * w + w) * 3, 3)]
            try:
                rt.setPixels(bmp, rt.Point2(0, y), row, linear=True)
            except Exception:  # noqa: BLE001
                rt.setPixels(bmp, rt.Point2(0, y), row)
        rt.save(bmp)
    finally:
        rt.close(bmp)


def maketx_dirs():
    """Folders where MAXtoA usually ships maketx.exe."""
    try:
        root = str(rt.getDir(rt.Name("maxroot")))
    except Exception:  # noqa: BLE001
        return []
    return glob.glob(os.path.join(root, "Plugins", "MAXtoA*")) + \
        glob.glob(os.path.join(root, "Plugins", "MAXtoA*", "bin"))


def find_maketx():
    return library.find_maketx(maketx_dirs())


def pending(want_tx=False, force=False):
    return library.pending_jobs(core.HDRI_DIR, want_tx=want_tx, force=force)


def refresh(make_tx=False, force=False, progress=None):
    """Generates missing / stale thumbnails and backgrounds (and .tx when asked and found)."""
    maketx = find_maketx() if make_tx else None
    return library.refresh(read_linear, write_jpg, write_exr, folder=core.HDRI_DIR,
                           maketx=maketx, force=force, progress=progress)
