"""
Lookdev Rig — dialog opened from the Studio Toolbar (Lookdev button).

    from studio_lookdev_max import ui
    ui.show()
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
THUMB = QtCore.QSize(160, 80)

STYLE = """
QDialog { background-color: #3c3c3c; color: #d8d8d8;
          font-family: "Tahoma","Segoe UI",sans-serif; font-size: 9pt; }
QLabel { color: #d8d8d8; background: transparent; }
QLabel#dim { color: #8a8a8a; }
QListWidget, QPlainTextEdit { background-color: #2b2b2b; color: #d8d8d8;
          border: 1px solid #262626; }
QListWidget::item { padding: 4px; }
QListWidget::item:selected { background-color: #24404a; color: #ffffff; }
QComboBox, QPushButton { background-color: #484848; color: #d8d8d8;
          border: 1px solid #262626; border-radius: 1px; padding: 3px 10px; min-height: 18px; }
QPushButton:hover, QComboBox:hover { background-color: #555555; border-color: #707070; }
QPushButton:pressed { background-color: #2f2f2f; }
QPushButton#primary { background-color: #2f5560; border-color: #3f8a9a; color: #ffffff; }
QPushButton#primary:hover { background-color: #3a6a77; }
QPushButton:disabled { color: #6a6a6a; }
QCheckBox { color: #d8d8d8; }
"""


def _max_main_window():
    try:
        import qtmax
        return qtmax.GetQMaxMainWindow()
    except ImportError:
        return None


def _placeholder_icon(text):
    pm = QtGui.QPixmap(THUMB)
    pm.fill(QtGui.QColor(45, 45, 48))
    p = QtGui.QPainter(pm)
    p.setPen(QtGui.QColor(150, 150, 150))
    p.drawText(pm.rect(), QtCore.Qt.AlignCenter, text[:18])
    p.end()
    return QtGui.QIcon(pm)


class LookdevRigDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super(LookdevRigDialog, self).__init__(parent or _max_main_window())
        self.setWindowTitle("Lookdev Rig · Studio Toolbar")
        self.setMinimumSize(580, 520)
        self.setStyleSheet(STYLE)
        self._hdris = []
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

        self.lst_hdri = QtWidgets.QListWidget()
        self.lst_hdri.setViewMode(QtWidgets.QListView.IconMode)
        self.lst_hdri.setIconSize(THUMB)
        self.lst_hdri.setResizeMode(QtWidgets.QListView.Adjust)
        self.lst_hdri.setMovement(QtWidgets.QListView.Static)
        self.lst_hdri.setSpacing(6)
        self.lst_hdri.setWordWrap(True)
        self.lst_hdri.itemDoubleClicked.connect(lambda *_: self.on_build())
        lay.addWidget(self.lst_hdri, 1)

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

        self.lbl_path = QtWidgets.QLabel(core.HDRI_DIR)
        self.lbl_path.setObjectName("dim")
        lay.addWidget(self.lbl_path)

        btns = QtWidgets.QHBoxLayout()
        b_folder = QtWidgets.QPushButton("Open folder")
        b_folder.setToolTip("Opens the shared HDRI folder")
        b_folder.clicked.connect(self.on_open_folder)
        b_refresh = QtWidgets.QPushButton("Refresh")
        b_refresh.clicked.connect(self.refresh)
        b_remove = QtWidgets.QPushButton("Delete rig")
        b_remove.setToolTip("Deletes every LKD_ node (the asset is untouched)")
        b_remove.clicked.connect(self.on_remove)
        self.b_build = QtWidgets.QPushButton("Build / update rig")
        self.b_build.setObjectName("primary")
        self.b_build.setDefault(True)
        self.b_build.clicked.connect(self.on_build)
        for b in (b_folder, b_refresh, b_remove):
            btns.addWidget(b)
        btns.addStretch(1)
        btns.addWidget(self.b_build)
        lay.addLayout(btns)

        self.txt_log = QtWidgets.QPlainTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setMaximumHeight(90)
        lay.addWidget(self.txt_log)

    # -- data ---------------------------------------------------------------

    def refresh(self):
        # Renderer
        try:
            a = adapters.detect()
            self.lbl_renderer.setText("Renderer: <b>%s</b>" % a.label)
            self.b_build.setEnabled(True)
        except Exception as exc:  # noqa: BLE001
            self.lbl_renderer.setText("<span style='color:#e06060'>%s</span>" % exc)
            self.b_build.setEnabled(False)

        # Presets
        current = self.cmb_preset.currentText()
        self.cmb_preset.clear()
        names = list(core.list_presets().keys()) or ["turntable_default"]
        self.cmb_preset.addItems(names)
        if current in names:
            self.cmb_preset.setCurrentText(current)

        # HDRIs
        self.lst_hdri.clear()
        self._hdris = core.list_hdris()
        for h in self._hdris:
            icon = QtGui.QIcon(h.thumb) if h.thumb else _placeholder_icon(h.label)
            it = QtWidgets.QListWidgetItem(icon, h.label)
            it.setData(QtCore.Qt.UserRole, h.name)
            it.setToolTip(h.path)
            self.lst_hdri.addItem(it)
        if not self._hdris:
            self._log("No HDRIs in %s" % core.HDRI_DIR)

        self._select_stored()
        self._sync_clay()
        self._update_camera_label()

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
        """If the selected asset already has a stored setup, preselect it."""
        sel = list(rt.selection)
        hdri, preset = builder.stored_settings(sel[0]) if sel else (None, None)
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

    def on_open_folder(self):
        if os.path.isdir(core.HDRI_DIR):
            os.startfile(core.HDRI_DIR)
        else:
            self._log("Folder not found: %s" % core.HDRI_DIR)

    def on_build(self):
        item = self.lst_hdri.currentItem()
        if not item:
            self._log("Pick an HDRI.")
            return
        name = item.data(QtCore.Qt.UserRole)
        preset_name = self.cmb_preset.currentText() or "turntable_default"
        hdri = next(h for h in self._hdris if h.name == name)

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
