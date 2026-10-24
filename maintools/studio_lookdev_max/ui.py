"""
Lookdev Rig — dialog opened from the Studio Toolbar (Lookdev button).

    from studio_lookdev_max import ui
    ui.show()

Left: HDRI library grid. Right: big preview and live dome controls (rotation, exposure,
background) that act on the built rig without rebuilding it.
"""

import os

import pymxs

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:  # Max 2024 and older
    from PySide2 import QtCore, QtGui, QtWidgets

from . import builder, adapters
from .builder import core

rt = pymxs.runtime

_INSTANCE = None
GRID_THUMB = QtCore.QSize(128, 64)
PREVIEW = QtCore.QSize(300, 150)

STYLE = """
QDialog { background-color: #3c3c3c; color: #d8d8d8;
          font-family: "Tahoma","Segoe UI",sans-serif; font-size: 9pt; }
QLabel { color: #d8d8d8; background: transparent; }
QLabel#dim { color: #8a8a8a; }
QLabel#title { font-weight: bold; }
QLabel#preview { background-color: #262626; border: 1px solid #262626; }
QGroupBox { border: 1px solid #2c2c2c; border-radius: 2px; margin-top: 14px; padding: 6px; }
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 3px; color: #8a8a8a;
                   font-weight: bold; }
QListWidget, QPlainTextEdit { background-color: #2b2b2b; color: #d8d8d8;
          border: 1px solid #262626; }
QListWidget::item { padding: 3px; }
QListWidget::item:selected { background-color: #24404a; color: #ffffff; }
QComboBox, QPushButton, QToolButton {
          background-color: #484848; color: #d8d8d8;
          border: 1px solid #262626; border-radius: 1px; padding: 3px 8px; min-height: 18px; }
QDoubleSpinBox { padding-right: 4px; background-color: #2b2b2b; color: #d8d8d8;
          border: 1px solid #262626; border-radius: 1px; min-height: 18px; }
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
          subcontrol-origin: border; width: 0px; height: 0px; border: none; }
QDoubleSpinBox QLineEdit { color: #d8d8d8; background: transparent;
          selection-background-color: #24404a; }
QPushButton:hover, QComboBox:hover, QToolButton:hover { background-color: #555555;
          border-color: #707070; }
QPushButton:pressed, QToolButton:pressed { background-color: #2f2f2f; }
QPushButton#primary { background-color: #2f5560; border-color: #3f8a9a; color: #ffffff; }
QPushButton#primary:hover { background-color: #3a6a77; }
QPushButton:disabled, QToolButton:disabled, QDoubleSpinBox:disabled { color: #6a6a6a; }
QToolButton::menu-button { border-left: 1px solid #262626; width: 14px; }
QSlider::groove:horizontal { height: 4px; background: #2b2b2b; border-radius: 2px; }
QSlider::handle:horizontal { background: #9a9a9a; width: 10px; margin: -5px 0; border-radius: 2px; }
QSlider::handle:horizontal:disabled { background: #5a5a5a; }
QCheckBox { color: #d8d8d8; }
QMenu { background-color: #323232; color: #d8d8d8; border: 1px solid #262626; }
QMenu::item:selected { background-color: #24404a; }
"""


def _max_main_window():
    try:
        import qtmax
        return qtmax.GetQMaxMainWindow()
    except ImportError:
        return None


def _placeholder(size, text):
    pm = QtGui.QPixmap(size)
    pm.fill(QtGui.QColor(45, 45, 48))
    p = QtGui.QPainter(pm)
    p.setPen(QtGui.QColor(130, 130, 130))
    p.drawText(pm.rect(), QtCore.Qt.AlignCenter | QtCore.Qt.TextWordWrap, text)
    p.end()
    return pm


def _thumb_pixmap(h, size):
    if h.thumb:
        pm = QtGui.QPixmap(h.thumb)
        if not pm.isNull():
            return pm.scaled(size, QtCore.Qt.IgnoreAspectRatio, QtCore.Qt.SmoothTransformation)
    return _placeholder(size, "no preview\nRefresh library")


class _SliderRow(QtWidgets.QWidget):
    """Label + slider + spinbox, kept in sync. Emits valueChanged(float)."""
    valueChanged = QtCore.Signal(float)

    def __init__(self, label, lo, hi, step, decimals, suffix="", parent=None):
        super(_SliderRow, self).__init__(parent)
        self._scale = 10 ** decimals
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lbl = QtWidgets.QLabel(label)
        lbl.setFixedWidth(62)
        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider.setRange(int(lo * self._scale), int(hi * self._scale))
        self.spin = QtWidgets.QDoubleSpinBox()
        self.spin.setRange(lo, hi)
        self.spin.setDecimals(decimals)
        self.spin.setSingleStep(step)
        self.spin.setSuffix(suffix)
        self.spin.setFixedWidth(72)
        self.spin.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self.spin.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        lay.addWidget(lbl)
        lay.addWidget(self.slider, 1)
        lay.addWidget(self.spin)
        self.slider.valueChanged.connect(self._from_slider)
        self.spin.valueChanged.connect(self._from_spin)

    def _from_slider(self, v):
        self.spin.blockSignals(True)
        self.spin.setValue(v / float(self._scale))
        self.spin.blockSignals(False)
        self.valueChanged.emit(v / float(self._scale))

    def _from_spin(self, v):
        self.slider.blockSignals(True)
        self.slider.setValue(int(round(v * self._scale)))
        self.slider.blockSignals(False)
        self.valueChanged.emit(v)

    def value(self):
        return self.spin.value()

    def set_value(self, v):
        for w in (self.slider, self.spin):
            w.blockSignals(True)
        self.spin.setValue(v)
        self.slider.setValue(int(round(v * self._scale)))
        for w in (self.slider, self.spin):
            w.blockSignals(False)


class LookdevRigDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super(LookdevRigDialog, self).__init__(parent or _max_main_window())
        self.setWindowTitle("Lookdev Rig · Studio Toolbar")
        self.setMinimumSize(760, 560)
        self.setStyleSheet(STYLE)
        self._hdris = []
        self._loading = False
        self._build_ui()
        self.refresh()

    # -- UI -----------------------------------------------------------------

    def _build_ui(self):
        lay = QtWidgets.QVBoxLayout(self)

        top = QtWidgets.QHBoxLayout()
        self.lbl_renderer = QtWidgets.QLabel()
        top.addWidget(self.lbl_renderer, 1)
        top.addWidget(QtWidgets.QLabel("Preset:"))
        self.cmb_preset = QtWidgets.QComboBox()
        self.cmb_preset.setMinimumWidth(170)
        top.addWidget(self.cmb_preset)
        lay.addLayout(top)

        mid = QtWidgets.QHBoxLayout()
        self.lst_hdri = QtWidgets.QListWidget()
        self.lst_hdri.setViewMode(QtWidgets.QListView.IconMode)
        self.lst_hdri.setIconSize(GRID_THUMB)
        self.lst_hdri.setResizeMode(QtWidgets.QListView.Adjust)
        self.lst_hdri.setMovement(QtWidgets.QListView.Static)
        self.lst_hdri.setSpacing(4)
        self.lst_hdri.setWordWrap(True)
        self.lst_hdri.currentItemChanged.connect(self.on_hdri_changed)
        self.lst_hdri.itemDoubleClicked.connect(lambda *_: self.on_build())
        mid.addWidget(self.lst_hdri, 1)
        mid.addWidget(self._build_side())
        lay.addLayout(mid, 1)

        opts = QtWidgets.QHBoxLayout()
        self.chk_turntable = QtWidgets.QCheckBox("Turntable")
        self.chk_turntable.setToolTip("Object turn, then HDRI turn (frames from the preset)")
        self.chk_turntable.setChecked(True)
        self.chk_ground = QtWidgets.QCheckBox("Shadow catcher")
        self.chk_ground.setToolTip("Ground plane under the asset that only shows shadows")
        self.chk_ground.setChecked(True)
        self.chk_clay = QtWidgets.QCheckBox("Clay")
        self.chk_clay.setToolTip("Grey override on the asset (refs untouched).\n"
                                 "Turning it off puts the original materials back;\n"
                                 "material edits made while clay is on are discarded.")
        self.chk_clay.toggled.connect(self.on_clay)
        for w in (self.chk_turntable, self.chk_ground, self.chk_clay):
            opts.addWidget(w)
            opts.addSpacing(10)
        opts.addStretch(1)
        self.lbl_camera = QtWidgets.QLabel()
        self.lbl_camera.setObjectName("dim")
        opts.addWidget(self.lbl_camera)
        lay.addLayout(opts)

        btns = QtWidgets.QHBoxLayout()
        b_folder = QtWidgets.QPushButton("Open folder")
        b_folder.setToolTip(core.HDRI_DIR)
        b_folder.clicked.connect(self.on_open_folder)

        self.b_library = QtWidgets.QToolButton()
        self.b_library.setText("Refresh library")
        self.b_library.setToolTip("Generates missing thumbnails and blurred backgrounds\n"
                                  "(shared by every DCC toolbar)")
        self.b_library.setPopupMode(QtWidgets.QToolButton.MenuButtonPopup)
        self.b_library.clicked.connect(lambda: self.on_refresh_library())
        m = QtWidgets.QMenu(self.b_library)
        m.addAction("Missing only", lambda: self.on_refresh_library())
        m.addAction("Missing + Arnold .tx", lambda: self.on_refresh_library(make_tx=True))
        m.addSeparator()
        m.addAction("Rebuild all previews", lambda: self.on_refresh_library(force=True))
        self.b_library.setMenu(m)

        b_remove = QtWidgets.QPushButton("Delete rig")
        b_remove.setToolTip("Deletes every LKD_ node (the asset is untouched)")
        b_remove.clicked.connect(self.on_remove)
        self.b_build = QtWidgets.QPushButton("Build / update rig")
        self.b_build.setObjectName("primary")
        self.b_build.setDefault(True)
        self.b_build.clicked.connect(self.on_build)
        for b in (b_folder, self.b_library, b_remove):
            btns.addWidget(b)
        btns.addStretch(1)
        btns.addWidget(self.b_build)
        lay.addLayout(btns)

        self.txt_log = QtWidgets.QPlainTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setMaximumHeight(80)
        lay.addWidget(self.txt_log)

    def _build_side(self):
        side = QtWidgets.QWidget()
        side.setFixedWidth(PREVIEW.width() + 16)
        v = QtWidgets.QVBoxLayout(side)
        v.setContentsMargins(0, 0, 0, 0)

        self.lbl_preview = QtWidgets.QLabel()
        self.lbl_preview.setObjectName("preview")
        self.lbl_preview.setFixedSize(PREVIEW)
        self.lbl_preview.setAlignment(QtCore.Qt.AlignCenter)
        v.addWidget(self.lbl_preview, 0, QtCore.Qt.AlignHCenter)
        self.lbl_name = QtWidgets.QLabel()
        self.lbl_name.setObjectName("title")
        v.addWidget(self.lbl_name)
        self.lbl_info = QtWidgets.QLabel()
        self.lbl_info.setObjectName("dim")
        self.lbl_info.setWordWrap(True)
        v.addWidget(self.lbl_info)

        box = QtWidgets.QGroupBox("DOME · LIVE")
        b = QtWidgets.QVBoxLayout(box)
        self.row_rot = _SliderRow("Rotation", -180.0, 180.0, 1.0, 1, "°")
        self.row_rot.setToolTip("HDRI rotation; the turntable spin is added on top")
        self.row_rot.valueChanged.connect(self.on_rotation)
        self.row_ev = _SliderRow("Exposure", -5.0, 5.0, 0.1, 2, " EV")
        self.row_ev.setToolTip("Dome intensity in stops over the HDRI default")
        self.row_ev.valueChanged.connect(self.on_exposure)
        self.chk_bg = QtWidgets.QCheckBox("Background visible in render")
        self.chk_bg.setToolTip("Off: the dome still lights the asset, the render gets alpha")
        self.chk_bg.toggled.connect(self.on_background)
        self.b_save_default = QtWidgets.QPushButton("Save as HDRI default")
        self.b_save_default.setToolTip("Writes rotation and intensity to the HDRI .json sidecar\n"
                                       "— every toolbar (Max, Houdini, Blender, Maya) starts there")
        self.b_save_default.clicked.connect(self.on_save_default)
        self.lbl_live = QtWidgets.QLabel()
        self.lbl_live.setObjectName("dim")
        for w in (self.row_rot, self.row_ev, self.chk_bg, self.b_save_default, self.lbl_live):
            b.addWidget(w)
        v.addWidget(box)
        v.addStretch(1)
        return side

    # -- data ---------------------------------------------------------------

    def refresh(self):
        self._loading = True
        try:
            try:
                a = adapters.detect()
                self.lbl_renderer.setText("Renderer: <b>%s</b>" % a.label)
                self.b_build.setEnabled(True)
            except Exception as exc:  # noqa: BLE001
                self.lbl_renderer.setText("<span style='color:#e06060'>%s</span>" % exc)
                self.b_build.setEnabled(False)

            current = self.cmb_preset.currentText()
            self.cmb_preset.clear()
            names = list(core.list_presets().keys()) or ["turntable_default"]
            self.cmb_preset.addItems(names)
            if current in names:
                self.cmb_preset.setCurrentText(current)

            self.lst_hdri.clear()
            self._hdris = core.list_hdris()
            for h in self._hdris:
                it = QtWidgets.QListWidgetItem(QtGui.QIcon(_thumb_pixmap(h, GRID_THUMB)), h.label)
                it.setData(QtCore.Qt.UserRole, h.name)
                it.setToolTip(h.path)
                self.lst_hdri.addItem(it)
            if not self._hdris:
                self._log("No HDRIs in %s" % core.HDRI_DIR)
            missing = sum(1 for h in self._hdris if not h.thumb)
            if missing:
                self._log("%d HDRI(s) without preview — Refresh library" % missing)

            self._select_stored()
            self._sync_clay()
            self._update_camera_label()
            self._sync_live()
        finally:
            self._loading = False
        self._show_preview(self._current_hdri())

    def _current_hdri(self):
        item = self.lst_hdri.currentItem()
        if not item:
            return None
        name = item.data(QtCore.Qt.UserRole)
        return next((h for h in self._hdris if h.name == name), None)

    def _show_preview(self, h):
        if h is None:
            self.lbl_preview.setPixmap(_placeholder(PREVIEW, "No HDRI"))
            self.lbl_name.setText("")
            self.lbl_info.setText("")
            return
        self.lbl_preview.setPixmap(_thumb_pixmap(h, PREVIEW))
        self.lbl_name.setText(h.label)
        bits = []
        if h.meta.get("tags"):
            bits.append(", ".join(h.meta["tags"]))
        bits.append("default rot %.1f° · intensity %.2f" % (h.rotation_offset, h.intensity))
        if h.bg:
            bits.append("blurred bg ready")
        self.lbl_info.setText("\n".join(bits))

    def _sync_live(self):
        """Live controls follow the built rig; disabled when there is none."""
        state = builder.hdri_state()
        on = state is not None
        for w in (self.row_rot, self.row_ev, self.chk_bg, self.b_save_default):
            w.setEnabled(on)
        if on:
            self.row_rot.set_value(state["rotation"])
            self.row_ev.set_value(state["exposure"])
            self.chk_bg.blockSignals(True)
            self.chk_bg.setChecked(state["bg_visible"])
            self.chk_bg.blockSignals(False)
            self.lbl_live.setText("Acting on the rig · %s" % state["hdri"])
        else:
            self.lbl_live.setText("Build the rig to adjust the dome live")

    def _update_camera_label(self):
        _geo, cam = builder._split_selection(list(rt.selection))
        if cam is not None:
            self.lbl_camera.setText("Camera: copy of %s" % cam.name)
            self.lbl_camera.setToolTip("A camera is selected with the asset: the rig uses its framing")
        else:
            self.lbl_camera.setText("Camera: automatic framing")
            self.lbl_camera.setToolTip("Select a camera together with the asset to use its framing")

    def _sync_clay(self):
        self.chk_clay.blockSignals(True)
        try:
            self.chk_clay.setChecked(builder.clay_is_on())
        except Exception:  # noqa: BLE001
            self.chk_clay.setChecked(False)
        self.chk_clay.blockSignals(False)

    def _select_stored(self):
        """Preselect the rig's HDRI, else the one stored on the selected asset."""
        state = builder.hdri_state()
        hdri = state["hdri"] if state else None
        preset = None
        sel = list(rt.selection)
        if sel and hdri is None:
            hdri, preset = builder.stored_settings(sel[0])
        if preset:
            self.cmb_preset.setCurrentText(preset)
        if self.cmb_preset.currentText():
            p = core.load_preset(self.cmb_preset.currentText())
            self.chk_ground.setChecked(bool(p["ground"].get("shadow_catcher", True)))
        for i in range(self.lst_hdri.count()):
            if self.lst_hdri.item(i).data(QtCore.Qt.UserRole) == hdri:
                self.lst_hdri.setCurrentRow(i)
                return
        if self.lst_hdri.count():
            self.lst_hdri.setCurrentRow(0)

    def _log(self, msg):
        self.txt_log.appendPlainText(msg)

    # -- actions ------------------------------------------------------------

    def on_hdri_changed(self, *_):
        h = self._current_hdri()
        self._show_preview(h)
        if self._loading or h is None or builder.hdri_state() is None:
            return
        if builder.hdri_state()["hdri"] == h.name:
            return
        try:
            builder.set_hdri(h)
        except Exception as exc:  # noqa: BLE001
            self._log("HDRI: %s" % exc)
            return
        rt.redrawViews()
        self._sync_live()
        self._log("Dome → %s" % h.label)

    def on_rotation(self, value):
        try:
            builder.set_rotation(value)
            rt.redrawViews()
        except Exception as exc:  # noqa: BLE001
            self._log("Rotation: %s" % exc)

    def on_exposure(self, value):
        try:
            builder.set_exposure(value)
        except Exception as exc:  # noqa: BLE001
            self._log("Exposure: %s" % exc)

    def on_background(self, on):
        try:
            builder.set_background_visible(on)
        except Exception as exc:  # noqa: BLE001
            self._log("Background: %s" % exc)

    def on_save_default(self):
        state = builder.hdri_state()
        if not state:
            return
        name = state["hdri"]
        r = QtWidgets.QMessageBox.question(
            self, "Save as HDRI default",
            "Save rotation %.1f° and intensity for '%s' in the shared library?\n\n"
            "Every toolbar will start from these values." % (state["rotation"], name))
        if r != QtWidgets.QMessageBox.Yes:
            return
        try:
            saved = builder.save_hdri_defaults()
        except Exception as exc:  # noqa: BLE001
            self._log("Save default: %s" % exc)
            return
        self._log("Saved %s · rot %.1f° · intensity %.3f"
                  % (name, saved["rotation_offset_deg"], saved["intensity"]))
        self.refresh()

    def on_refresh_library(self, make_tx=False, force=False):
        try:
            from . import library_max
        except Exception as exc:  # noqa: BLE001
            self._log("Library: %s" % exc)
            return
        if make_tx and not library_max.find_maketx():
            self._log("maketx not found (Arnold) — previews only")
            make_tx = False
        jobs = library_max.pending(want_tx=make_tx, force=force)
        if not jobs:
            self._log("Library up to date")
            return
        dlg = QtWidgets.QProgressDialog("Preparing…", "Cancel", 0, len(jobs), self)
        dlg.setWindowTitle("Refresh library")
        dlg.setWindowModality(QtCore.Qt.WindowModal)
        dlg.setMinimumDuration(0)

        def progress(i, total, label):
            dlg.setValue(i)
            if label:
                dlg.setLabelText("%d / %d  ·  %s" % (i + 1, total, label))
            QtWidgets.QApplication.processEvents()
            return not dlg.wasCanceled()

        report = library_max.refresh(make_tx=make_tx, force=force, progress=progress)
        dlg.close()
        self._log("Library: %d updated%s" % (len(report.done),
                                              (", %d errors" % len(report.errors)) if report.errors else ""))
        for e in report.errors:
            self._log("  " + e)
        self.refresh()

    def on_open_folder(self):
        if os.path.isdir(core.HDRI_DIR):
            os.startfile(core.HDRI_DIR)
        else:
            self._log("Folder not found: %s" % core.HDRI_DIR)

    def on_build(self):
        hdri = self._current_hdri()
        if hdri is None:
            self._log("Pick an HDRI.")
            return
        preset_name = self.cmb_preset.currentText() or "turntable_default"
        overrides = {
            "turntable": {"enabled": self.chk_turntable.isChecked()},
            "ground": {"shadow_catcher": self.chk_ground.isChecked()},
            "clay": {"enabled": self.chk_clay.isChecked()},
        }
        self._update_camera_label()
        try:
            rig = builder.build(hdri, preset_name, overrides=overrides)
        except Exception as exc:  # noqa: BLE001
            self._log("ERROR: %s" % exc)
            return

        msg = "Rig built · %s · %s · %d nodes" % (rig["adapter"], hdri.label, len(rig["nodes"]))
        if "render_range" in rig:
            msg += " · frames %d-%d" % rig["render_range"]
        if rig.get("camera_source"):
            msg += " · camera copied from %s" % rig["camera_source"]
        self._log(msg)
        for line in rig["warnings"] + rig["log"]:
            self._log(line)
        self._sync_clay()
        self._sync_live()

    def on_clay(self, on):
        try:
            n = builder.set_clay(on)
        except Exception as exc:  # noqa: BLE001
            self._log("Clay: %s" % exc)
            self._sync_clay()
            return
        rt.redrawViews()
        self._log("Clay %s · %d objects" % ("on" if on else "off", n))

    def on_remove(self):
        with pymxs.undo(True, "Delete Lookdev Rig"):
            builder.remove_rig()
        rt.redrawViews()
        self._sync_clay()
        self._sync_live()
        self._log("Rig deleted (asset materials restored).")


def show():
    """Opens the dialog; if it is already open, brings it to the front."""
    global _INSTANCE
    if _INSTANCE is not None:
        try:
            if _INSTANCE.isVisible():
                _INSTANCE.refresh()
                _INSTANCE.raise_()
                _INSTANCE.activateWindow()
                return _INSTANCE
            _INSTANCE.deleteLater()
        except RuntimeError:
            pass
    _INSTANCE = LookdevRigDialog()
    _INSTANCE.show()
    return _INSTANCE
