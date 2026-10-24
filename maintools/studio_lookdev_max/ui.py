"""
Lookdev Rig — window opened from the Studio Toolbar (Lookdev button).

    from studio_lookdev_max import ui
    ui.show()

Layout in the spirit of Studio Library:
    top bar      search · renderer · refresh library · open folder
    sidebar      All / Missing preview / tags from the sidecars
    grid         HDRI thumbnails — size from the slider or Ctrl + mouse wheel
    right panel  preview (scales with the panel), RIG options, DOME · LIVE controls
    status bar   last message (click for history) · thumbnail size

Window position / size, panel sizes, thumbnail size, filter, preset, last HDRI and the rig
options are remembered per user in ~/.studio-toolbar/lookdev_rig.ini.
"""

import configparser
import json
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

SETTINGS_PATH = os.path.join(os.path.expanduser("~"), ".studio-toolbar", "lookdev_rig.ini")

THUMB_MIN, THUMB_MAX, THUMB_DEFAULT = 96, 512, 176

# ── palette (shared with StudioLibrary MAX) ──────────────────────────────────
C_BG = "#1C1C1C"
C_PANEL = "#232323"
C_BORDER = "#2E2E2E"
C_BORDER_HI = "#484848"
C_TEXT = "#C8C8C8"
C_TEXT_DIM = "#666666"
C_SEL_BG = "#303030"
C_SEL_TEXT = "#E8E8E8"
C_BTN = "#2A2A2A"
C_BTN_HO = "#353535"
C_STATUS = "#1A1A1A"
C_ACCENT = "#4ec9c9"
C_ACCENT_BG = "#2f7f8f"
C_OK, C_WARN, C_ERR = "#70aa70", "#d4b44a", "#e06060"

STYLE = """
QDialog {{ background-color: {bg}; color: {text};
          font-family: "Segoe UI","Tahoma",sans-serif; font-size: 9pt; }}
QLabel {{ color: {text}; background: transparent; }}
QLabel#dim {{ color: {dim}; }}
QLabel#title {{ color: {seltext}; font-size: 10pt; font-weight: bold; }}
QLabel#appname {{ color: {seltext}; font-size: 10pt; font-weight: bold; letter-spacing: 1px; }}
QLabel#badge {{ color: {accent}; border: 1px solid {accentbg}; border-radius: 2px; padding: 1px 6px; }}
QLabel#badge[error="true"] {{ color: {err}; border-color: #884444; }}
QLabel#formlabel {{ color: #8a8a8a; }}
QLabel#section {{ color: {dim}; font-size: 8pt; font-weight: bold; letter-spacing: 1px; }}
QFrame#topbar {{ background-color: {panel}; border-bottom: 1px solid {border}; }}
QFrame#statusbar {{ background-color: {status}; border-top: 1px solid {border}; }}
QFrame#sep {{ background-color: {border}; max-height: 1px; min-height: 1px; border: none; }}
QWidget#rightpanel, QScrollArea#rightscroll {{ background-color: {panel}; border: none; }}
QLineEdit {{ background-color: {bg}; color: {text}; border: 1px solid {border};
            border-radius: 2px; padding: 3px 6px; selection-background-color: {accentbg}; }}
QLineEdit:focus {{ border-color: {borderhi}; }}
QListWidget {{ background-color: {bg}; color: {text}; border: none; outline: none; }}
QListWidget#sidebar {{ background-color: {panel}; padding-top: 4px; }}
QListWidget#sidebar::item {{ padding: 4px 10px; }}
QListWidget#sidebar::item:selected {{ background-color: {selbg}; color: {seltext};
            border-left: 2px solid {accent}; }}
QListWidget#grid {{ padding: 8px; }}
QListWidget#grid::item {{ color: {text}; border-radius: 2px; }}
QListWidget#grid::item:hover {{ background-color: #262626; }}
QListWidget#grid::item:selected {{ background-color: {selbg}; color: {seltext};
            border: 1px solid {accentbg}; }}
QComboBox, QPushButton, QToolButton {{ background-color: {btn}; color: {text};
            border: 1px solid {border}; border-radius: 2px; padding: 4px 10px; min-height: 16px; }}
QComboBox:hover, QPushButton:hover, QToolButton:hover {{ background-color: {btnho};
            border-color: {borderhi}; }}
QPushButton:pressed, QToolButton:pressed {{ background-color: #202020; }}
QPushButton#primary {{ background-color: {accentbg}; border-color: {accent}; color: #ffffff;
            font-weight: bold; }}
QPushButton#primary:hover {{ background-color: #36909f; }}
QPushButton:disabled, QToolButton:disabled {{ color: #4a4a4a; border-color: #262626; }}
QToolButton::menu-button {{ border-left: 1px solid {border}; width: 14px; }}
QComboBox QAbstractItemView {{ background-color: {panel}; color: {text};
            selection-background-color: {selbg}; border: 1px solid {border}; }}
QDoubleSpinBox {{ padding-right: 4px; background-color: {bg}; color: {text};
            border: 1px solid {border}; border-radius: 2px; min-height: 18px; }}
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
            subcontrol-origin: border; width: 0px; height: 0px; border: none; }}
QDoubleSpinBox:disabled {{ color: #4a4a4a; }}
QSlider::groove:horizontal {{ height: 3px; background: {border}; border-radius: 1px; }}
QSlider::sub-page:horizontal {{ background: #3d6d75; border-radius: 1px; }}
QSlider::handle:horizontal {{ background: #a0a0a0; width: 10px; margin: -5px 0; border-radius: 5px; }}
QSlider::handle:horizontal:hover {{ background: {seltext}; }}
QSlider::handle:horizontal:disabled {{ background: #444444; }}
QSlider::sub-page:horizontal:disabled {{ background: {border}; }}
QCheckBox {{ color: {text}; spacing: 6px; }}
QCheckBox:disabled {{ color: #4a4a4a; }}
QCheckBox::indicator {{ width: 12px; height: 12px; border: 1px solid {borderhi};
            border-radius: 2px; background: {bg}; }}
QCheckBox::indicator:checked {{ background: {accentbg}; border-color: {accent}; }}
QSplitter::handle {{ background-color: {border}; }}
QSplitter::handle:horizontal {{ width: 2px; }}
QScrollBar:vertical {{ background: {bg}; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: #3a3a3a; min-height: 24px; border-radius: 4px; margin: 2px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QMenu {{ background-color: {panel}; color: {text}; border: 1px solid {border}; }}
QMenu::item {{ padding: 5px 20px 5px 10px; }}
QMenu::item:selected {{ background-color: {selbg}; color: {seltext}; }}
QMenu::separator {{ height: 1px; background: {border}; margin: 3px 6px; }}
QToolTip {{ background-color: #2a2a2a; color: {text}; border: 1px solid {border}; padding: 3px 6px; }}
""".format(bg=C_BG, panel=C_PANEL, border=C_BORDER, borderhi=C_BORDER_HI, text=C_TEXT,
           dim=C_TEXT_DIM, selbg=C_SEL_BG, seltext=C_SEL_TEXT, btn=C_BTN, btnho=C_BTN_HO,
           status=C_STATUS, accent=C_ACCENT, accentbg=C_ACCENT_BG, err=C_ERR)

FILTER_ALL, FILTER_MISSING, FILTER_TAG, FILTER_DIR = "all", "missing", "tag:", "dir:"
FORM_LABEL_W = 82
RIGHT_MIN_W = 340
SWATCH_W = 40
CORNER_LABELS = (("bottom_right", "Bottom right"), ("bottom_left", "Bottom left"),
                 ("top_right", "Top right"), ("top_left", "Top left"))


def _srgb_to_lin(v):
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def _lin_to_srgb(v):
    v = max(0.0, min(1.0, v))
    return 12.92 * v if v <= 0.0031308 else 1.055 * (v ** (1 / 2.4)) - 0.055


def _qcolor_from_linear(rgb):
    return QtGui.QColor(*[int(round(_lin_to_srgb(c) * 255)) for c in rgb[:3]])


def _linear_from_qcolor(qc):
    return tuple(_srgb_to_lin(c / 255.0) for c in (qc.red(), qc.green(), qc.blue()))


# ── settings ─────────────────────────────────────────────────────────────────
def load_settings():
    cfg = configparser.ConfigParser()
    cfg.read(SETTINGS_PATH, encoding="utf-8")
    return dict(cfg["window"]) if "window" in cfg else {}


def save_settings(**values):
    try:
        cfg = configparser.ConfigParser()
        cfg.read(SETTINGS_PATH, encoding="utf-8")
        if "window" not in cfg:
            cfg["window"] = {}
        for k, v in values.items():
            cfg["window"][k] = "" if v is None else str(v)
        os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
        with open(SETTINGS_PATH, "w", encoding="utf-8") as fh:
            cfg.write(fh)
    except Exception as exc:  # noqa: BLE001
        print("[Lookdev Rig] save settings: %s" % exc)


def _short_path(p, keep=2):
    parts = os.path.normpath(p).split(os.sep)
    return p if len(parts) <= keep + 1 else os.path.join(parts[0] + os.sep, "…", *parts[-keep:])


def _max_main_window():
    try:
        import qtmax
        return qtmax.GetQMaxMainWindow()
    except ImportError:
        return None


def _placeholder(w, h, text):
    pm = QtGui.QPixmap(w, h)
    pm.fill(QtGui.QColor("#262626"))
    p = QtGui.QPainter(pm)
    p.setPen(QtGui.QColor("#555555"))
    p.drawText(pm.rect(), QtCore.Qt.AlignCenter | QtCore.Qt.TextWordWrap, text)
    p.end()
    return pm


def _sep():
    f = QtWidgets.QFrame()
    f.setObjectName("sep")
    return f


def _section(text):
    w = QtWidgets.QWidget()
    lay = QtWidgets.QHBoxLayout(w)
    lay.setContentsMargins(0, 10, 0, 2)
    lbl = QtWidgets.QLabel(text.upper())
    lbl.setObjectName("section")
    lay.addWidget(lbl)
    line = _sep()
    lay.addWidget(line, 1)
    lay.setAlignment(line, QtCore.Qt.AlignVCenter)
    return w


# ── widgets ──────────────────────────────────────────────────────────────────
class _Preview(QtWidgets.QLabel):
    """Lat-long preview that always fills the panel width at 2:1."""

    def __init__(self, parent=None):
        super(_Preview, self).__init__(parent)
        self._src = None
        self.setAlignment(QtCore.Qt.AlignCenter)
        self.setMinimumWidth(200)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.setStyleSheet("background-color: #262626; border: 1px solid %s;" % C_BORDER)

    def set_source(self, pixmap):
        self._src = pixmap
        self._update()

    def resizeEvent(self, e):
        super(_Preview, self).resizeEvent(e)
        self._update()

    def _update(self):
        w = max(1, self.width())
        h = max(1, w // 2)
        if self.height() != h:
            self.setFixedHeight(h)
        if self._src is None or self._src.isNull():
            self.setPixmap(_placeholder(w - 2, h - 2, "No preview"))
        else:
            self.setPixmap(self._src.scaled(w - 2, h - 2, QtCore.Qt.IgnoreAspectRatio,
                                            QtCore.Qt.SmoothTransformation))


class _ElidedLabel(QtWidgets.QLabel):
    """One-line label that elides with "…" instead of widening the panel; full text in tooltip."""

    def __init__(self, text="", parent=None):
        super(_ElidedLabel, self).__init__(parent)
        self._full = ""
        self.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        self.setMinimumWidth(10)
        self.setText(text)

    def setText(self, text):
        self._full = text or ""
        self.setToolTip(self._full if self._full else "")
        self._elide()

    def text(self):
        return self._full

    def resizeEvent(self, e):
        super(_ElidedLabel, self).resizeEvent(e)
        self._elide()

    def _elide(self):
        fm = self.fontMetrics()
        QtWidgets.QLabel.setText(self, fm.elidedText(self._full, QtCore.Qt.ElideRight,
                                                     max(10, self.width())))

    def sizeHint(self):
        return QtCore.QSize(10, self.fontMetrics().height() + 2)


class _SliderRow(QtWidgets.QWidget):
    """Label + slider + value box, kept in sync. Emits valueChanged(float)."""
    valueChanged = QtCore.Signal(float)

    def __init__(self, lo, hi, step, decimals, suffix="", default=0.0, parent=None):
        super(_SliderRow, self).__init__(parent)
        self._scale = 10 ** decimals
        self._default = default
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider.setRange(int(lo * self._scale), int(hi * self._scale))
        self.spin = QtWidgets.QDoubleSpinBox()
        self.spin.setRange(lo, hi)
        self.spin.setDecimals(decimals)
        self.spin.setSingleStep(step)
        self.spin.setSuffix(suffix)
        widest = max(("%.*f%s" % (decimals, v, suffix) for v in (lo, hi)), key=len)
        self.spin.setFixedWidth(self.spin.fontMetrics().horizontalAdvance(widest + "  ") + 16)
        self.spin.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self.spin.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self.spin.setToolTip("Double-click the slider to reset")
        lay.addWidget(self.slider, 1)
        lay.addWidget(self.spin)
        self.slider.valueChanged.connect(self._from_slider)
        self.spin.valueChanged.connect(self._from_spin)
        self.slider.installEventFilter(self)

    def eventFilter(self, obj, ev):
        if obj is self.slider and ev.type() == QtCore.QEvent.MouseButtonDblClick:
            self.set_value(self._default)
            self.valueChanged.emit(self._default)
            return True
        return super(_SliderRow, self).eventFilter(obj, ev)

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


# ── window ───────────────────────────────────────────────────────────────────
class LookdevRigDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super(LookdevRigDialog, self).__init__(parent or _max_main_window())
        self.setWindowTitle("Lookdev Rig · Studio Toolbar")
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowMinMaxButtonsHint)
        self.setMinimumSize(780, 520)
        self.resize(1180, 720)
        self.setStyleSheet(STYLE)
        self._hdris = []
        self._loading = False
        self._history = []
        self._thumb = THUMB_DEFAULT
        self._settings = load_settings()
        self._root = self._settings.get("library") or core.HDRI_DIR
        if not os.path.isdir(self._root):
            self._root = core.HDRI_DIR
        try:
            self._recent = [p for p in json.loads(self._settings.get("recent_libraries", "[]"))
                            if isinstance(p, str)]
        except ValueError:
            self._recent = []
        self._build_ui()
        self._geom_timer = QtCore.QTimer(self)
        self._geom_timer.setSingleShot(True)
        self._geom_timer.setInterval(600)
        self._geom_timer.timeout.connect(self._save_layout)
        self._restore_settings()
        self.refresh()

    # -- UI -----------------------------------------------------------------

    def _build_ui(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_topbar())

        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(self._build_sidebar())
        self.splitter.addWidget(self._build_grid())
        self.splitter.addWidget(self._build_right())
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)
        self.splitter.setSizes([170, 640, 340])
        self.splitter.splitterMoved.connect(lambda *_: self._geom_timer.start())
        root.addWidget(self.splitter, 1)
        root.addWidget(self._build_statusbar())

    def _build_topbar(self):
        bar = QtWidgets.QFrame()
        bar.setObjectName("topbar")
        lay = QtWidgets.QHBoxLayout(bar)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(6)
        name = QtWidgets.QLabel("LOOKDEV RIG")
        name.setObjectName("appname")
        lay.addWidget(name)
        lay.addSpacing(14)
        self.cmb_library = QtWidgets.QComboBox()
        self.cmb_library.setMinimumWidth(190)
        self.cmb_library.setMaximumWidth(320)
        self.cmb_library.setToolTip("HDRI library: the shared studio one, or any folder (e.g. a\n"
                                    "collection on the NAS) to try HDRIs without copying them.\n"
                                    "Previews of other folders are cached locally — the folder is\n"
                                    "never written to.")
        self.cmb_library.activated.connect(self._on_library_activated)
        lay.addWidget(self.cmb_library)
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("Search HDRIs, tags…")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(220)
        self.search.textChanged.connect(self._apply_filter)
        lay.addWidget(self.search, 1)
        lay.addSpacing(10)
        self.lbl_renderer = QtWidgets.QLabel()
        self.lbl_renderer.setObjectName("badge")
        lay.addWidget(self.lbl_renderer)

        self.b_library = QtWidgets.QToolButton()
        self.b_library.setText("Refresh library")
        self.b_library.setToolTip("Generates missing thumbnails and blurred backgrounds\n"
                                  "in hdri\\_cache (shared by every DCC toolbar)")
        self.b_library.setPopupMode(QtWidgets.QToolButton.MenuButtonPopup)
        self.b_library.clicked.connect(lambda: self.on_refresh_library())
        m = QtWidgets.QMenu(self.b_library)
        m.addAction("Missing only", lambda: self.on_refresh_library())
        m.addAction("Missing + Arnold .tx", lambda: self.on_refresh_library(make_tx=True))
        m.addSeparator()
        m.addAction("Rebuild all previews", lambda: self.on_refresh_library(force=True))
        m.addSeparator()
        m.addAction("Reload list", self.refresh)
        self.b_library.setMenu(m)
        lay.addWidget(self.b_library)
        b_folder = QtWidgets.QPushButton("Open folder")
        b_folder.setToolTip("Opens the current library folder")
        b_folder.clicked.connect(self.on_open_folder)
        lay.addWidget(b_folder)
        return bar

    def _build_sidebar(self):
        self.sidebar = QtWidgets.QListWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setMinimumWidth(130)
        self.sidebar.currentItemChanged.connect(lambda *_: self._on_filter_changed())
        return self.sidebar

    def _build_grid(self):
        self.grid = QtWidgets.QListWidget()
        self.grid.setObjectName("grid")
        self.grid.setViewMode(QtWidgets.QListView.IconMode)
        self.grid.setResizeMode(QtWidgets.QListView.Adjust)
        self.grid.setMovement(QtWidgets.QListView.Static)
        self.grid.setUniformItemSizes(True)
        self.grid.setSpacing(6)
        self.grid.setWordWrap(True)
        self.grid.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        self.grid.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.grid.currentItemChanged.connect(self.on_hdri_changed)
        self.grid.itemDoubleClicked.connect(lambda *_: self.on_build())
        self.grid.viewport().installEventFilter(self)
        self.grid.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.grid.customContextMenuRequested.connect(self._grid_menu)
        return self.grid

    def _form_label(self, text):
        lbl = QtWidgets.QLabel(text)
        lbl.setObjectName("formlabel")
        lbl.setFixedWidth(FORM_LABEL_W)
        return lbl

    def _build_right(self):
        scroll = QtWidgets.QScrollArea()
        scroll.setObjectName("rightscroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        scroll.setMinimumWidth(RIGHT_MIN_W)
        panel = QtWidgets.QWidget()
        panel.setObjectName("rightpanel")
        v = QtWidgets.QVBoxLayout(panel)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(4)

        # ── HDRI preview + details (fixed height: nothing below jumps) ──
        self.preview = _Preview()
        v.addWidget(self.preview)
        v.addSpacing(6)
        details = QtWidgets.QWidget()
        d = QtWidgets.QVBoxLayout(details)
        d.setContentsMargins(0, 0, 0, 0)
        d.setSpacing(2)
        self.lbl_name = _ElidedLabel()
        self.lbl_name.setObjectName("title")
        d.addWidget(self.lbl_name)
        self.lbl_info = [_ElidedLabel() for _ in range(3)]
        for lbl in self.lbl_info:
            lbl.setObjectName("dim")
            d.addWidget(lbl)
        details.setFixedHeight(details.sizeHint().height())
        v.addWidget(details)

        # ── RIG ──
        v.addWidget(_section("Rig"))
        g = self._grid()
        self.cmb_preset = QtWidgets.QComboBox()
        self.cmb_preset.setToolTip("Rig presets (shared\\lookdev\\presets): camera framing, reference sizes,\n"
                                   "turntable length / start frame / direction, ground and clay defaults.\n"
                                   "Applied when the rig is built.")
        self.cmb_preset.currentIndexChanged.connect(lambda *_: self._on_preset_changed(self._preset_id()))
        g.addWidget(self._form_label("Preset"), 0, 0)
        g.addWidget(self.cmb_preset, 0, 1)
        self.chk_turntable = QtWidgets.QCheckBox("Turntable")
        self.chk_turntable.setToolTip("Object turn, then HDRI turn — frames and direction from the preset.\n"
                                      "The asset itself never moves")
        self.chk_ground = QtWidgets.QCheckBox("Shadow catcher")
        self.chk_ground.setToolTip("Ground plane under the asset that only shows shadows")
        self.chk_clay = QtWidgets.QCheckBox("Clay  (grey override, live)")
        self.chk_clay.setToolTip("Swaps the asset materials for a grey diffuse; refs untouched.\n"
                                 "Turning it off puts the originals back — material edits made\n"
                                 "while clay is on are discarded.")
        self.chk_clay.toggled.connect(self.on_clay)
        g.addWidget(self._form_label("Options"), 1, 0, QtCore.Qt.AlignTop)
        opts = QtWidgets.QVBoxLayout()
        opts.setSpacing(4)
        for w in (self.chk_turntable, self.chk_ground, self.chk_clay):
            opts.addWidget(w)
            w.toggled.connect(lambda *_: self._save_options())
        g.addLayout(opts, 1, 1)
        self.lbl_camera = _ElidedLabel()
        self.lbl_camera.setObjectName("dim")
        g.addWidget(self._form_label("Camera"), 2, 0)
        g.addWidget(self.lbl_camera, 2, 1)
        v.addLayout(g)
        v.addSpacing(6)
        brow = QtWidgets.QHBoxLayout()
        brow.setSpacing(6)
        self.b_build = QtWidgets.QPushButton("Build / update rig")
        self.b_build.setObjectName("primary")
        self.b_build.setToolTip("Builds the rig around the selection (double-click an HDRI does the same)")
        self.b_build.clicked.connect(self.on_build)
        b_remove = QtWidgets.QPushButton("Delete rig")
        b_remove.setToolTip("Deletes the rig and its layer; restores materials and scene background")
        b_remove.clicked.connect(self.on_remove)
        brow.addWidget(self.b_build, 1)
        brow.addWidget(b_remove)
        v.addLayout(brow)

        # ── REFERENCES ──
        v.addWidget(_section("References"))
        g = self._grid()
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(12)
        self.chk_chrome = QtWidgets.QCheckBox("Chrome")
        self.chk_grey = QtWidgets.QCheckBox("Grey")
        self.chk_chart = QtWidgets.QCheckBox("Chart")
        for c in (self.chk_chrome, self.chk_grey, self.chk_chart):
            c.setChecked(True)
            c.setToolTip("Toggle this reference — the others pack towards the corner")
            c.toggled.connect(lambda *_: self.on_refs_changed())
            row.addWidget(c)
        row.addStretch(1)
        g.addWidget(self._form_label("Show"), 0, 0)
        g.addLayout(row, 0, 1)
        self.cmb_corner = QtWidgets.QComboBox()
        for key, text in CORNER_LABELS:
            self.cmb_corner.addItem(text, key)
        self.cmb_corner.currentIndexChanged.connect(lambda *_: self.on_refs_changed())
        g.addWidget(self._form_label("Corner"), 1, 0)
        g.addWidget(self.cmb_corner, 1, 1)
        self.cmb_chart = QtWidgets.QComboBox()
        self.cmb_chart.setToolTip("Chart definitions in shared\\lookdev\\reference\\ "
                                  "(see _TEMPLATE_chart.json to add one)")
        self.cmb_chart.currentIndexChanged.connect(lambda *_: self.on_refs_changed())
        g.addWidget(self._form_label("Chart"), 2, 0)
        g.addWidget(self.cmb_chart, 2, 1)
        v.addLayout(g)

        # ── DOME · LIVE ──
        v.addWidget(_section("Dome · live"))
        g = self._grid()
        self.row_rot = _SliderRow(-180.0, 180.0, 1.0, 1, "°")
        self.row_rot.setToolTip("HDRI rotation; the turntable spin is added on top")
        self.row_rot.valueChanged.connect(self.on_rotation)
        self.row_ev = _SliderRow(-5.0, 5.0, 0.1, 2, " EV")
        self.row_ev.setToolTip("Dome intensity in stops over the HDRI default")
        self.row_ev.valueChanged.connect(self.on_exposure)
        g.addWidget(self._form_label("Rotation"), 0, 0)
        g.addWidget(self.row_rot, 0, 1)
        w = max(self.row_rot.spin.maximumWidth(), self.row_ev.spin.maximumWidth())
        for r in (self.row_rot, self.row_ev):
            r.spin.setFixedWidth(w)                 # value boxes line up
        g.addWidget(self._form_label("Exposure"), 1, 0)
        g.addWidget(self.row_ev, 1, 1)
        self.cmb_bg = QtWidgets.QComboBox()
        for key, text in (("hdri", "HDRI"), ("blur", "Blurred HDRI"), ("color", "Colour")):
            self.cmb_bg.addItem(text, key)
        self.cmb_bg.setToolTip("What the camera sees behind the asset — the light always comes\n"
                               "from the full HDRI.\n"
                               "Blurred HDRI: soft copy from the library (Refresh library makes it)\n"
                               "Colour: flat colour; alpha stays clean for comp")
        self.cmb_bg.currentIndexChanged.connect(lambda *_: self.on_background_mode())
        self.b_bg_color = QtWidgets.QToolButton()
        self.b_bg_color.setToolTip("Background colour (Colour mode)")
        self.b_bg_color.clicked.connect(self.on_pick_bg_color)
        self.b_bg_color.setFixedSize(SWATCH_W, self.cmb_bg.sizeHint().height())
        self._bg_color = (0.18, 0.18, 0.18)
        bg_row = QtWidgets.QHBoxLayout()
        bg_row.setSpacing(6)
        bg_row.addWidget(self.cmb_bg, 1)
        bg_row.addWidget(self.b_bg_color, 0, QtCore.Qt.AlignVCenter)
        g.addWidget(self._form_label("Background"), 2, 0)
        g.addLayout(bg_row, 2, 1)
        v.addLayout(g)
        v.addSpacing(6)
        self.b_save_default = QtWidgets.QPushButton("Save as HDRI default")
        self.b_save_default.setToolTip("Writes rotation and intensity as this HDRI's default\n"
                                       "(studio library: shared .json sidecar, read by every toolbar;\n"
                                       " other folders: local cache, the collection is never touched)")
        self.b_save_default.clicked.connect(self.on_save_default)
        v.addWidget(self.b_save_default)
        self.lbl_live = _ElidedLabel()
        self.lbl_live.setObjectName("dim")
        v.addWidget(self.lbl_live)
        self._paint_bg_button()
        v.addStretch(1)
        scroll.setWidget(panel)
        return scroll

    def _grid(self):
        g = QtWidgets.QGridLayout()
        g.setContentsMargins(0, 2, 0, 0)
        g.setHorizontalSpacing(8)
        g.setVerticalSpacing(6)
        g.setColumnMinimumWidth(0, FORM_LABEL_W)
        g.setColumnStretch(1, 1)
        return g

    def _build_statusbar(self):
        bar = QtWidgets.QFrame()
        bar.setObjectName("statusbar")
        lay = QtWidgets.QHBoxLayout(bar)
        lay.setContentsMargins(10, 3, 10, 3)
        self.lbl_status = QtWidgets.QLabel()
        self.lbl_status.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.lbl_status.setToolTip("Click for the message history")
        self.lbl_status.installEventFilter(self)
        lay.addWidget(self.lbl_status, 1)
        self.lbl_count = QtWidgets.QLabel()
        self.lbl_count.setObjectName("dim")
        lay.addWidget(self.lbl_count)
        lay.addSpacing(14)
        small = QtWidgets.QLabel("▫")
        small.setObjectName("dim")
        lay.addWidget(small)
        self.size_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.size_slider.setRange(THUMB_MIN, THUMB_MAX)
        self.size_slider.setFixedWidth(120)
        self.size_slider.setToolTip("Thumbnail size (Ctrl + mouse wheel on the grid)")
        self.size_slider.valueChanged.connect(self._set_thumb_size)
        lay.addWidget(self.size_slider)
        big = QtWidgets.QLabel("◻")
        big.setObjectName("dim")
        lay.addWidget(big)
        return bar

    # -- settings -----------------------------------------------------------

    def _restore_settings(self):
        s = self._settings
        if s.get("geometry"):
            try:
                self.restoreGeometry(QtCore.QByteArray.fromBase64(s["geometry"].encode("ascii")))
            except Exception:  # noqa: BLE001
                pass
        if s.get("splitter"):
            try:
                self.splitter.restoreState(QtCore.QByteArray.fromBase64(s["splitter"].encode("ascii")))
            except Exception:  # noqa: BLE001
                pass
        self._ensure_on_screen()
        try:
            self._thumb = max(THUMB_MIN, min(THUMB_MAX, int(s.get("thumb", THUMB_DEFAULT))))
        except ValueError:
            self._thumb = THUMB_DEFAULT
        self.size_slider.blockSignals(True)
        self.size_slider.setValue(self._thumb)
        self.size_slider.blockSignals(False)
        self._apply_thumb_size()
        corner = s.get("corner", "bottom_right")
        idx = self.cmb_corner.findData(corner)
        self.cmb_corner.blockSignals(True)
        self.cmb_corner.setCurrentIndex(max(0, idx))
        self.cmb_corner.blockSignals(False)
        try:
            self._bg_color = tuple(float(x) for x in s["bg_color"].split(","))[:3]
        except (KeyError, ValueError):
            pass
        self._paint_bg_button()
        for chk, key, default in ((self.chk_turntable, "turntable", "1"),
                                  (self.chk_ground, "ground", "1"),
                                  (self.chk_chrome, "chrome", "1"),
                                  (self.chk_grey, "grey", "1"),
                                  (self.chk_chart, "chart_on", "1")):
            chk.blockSignals(True)
            chk.setChecked(s.get(key, default) == "1")
            chk.blockSignals(False)

    def _ensure_on_screen(self):
        """Saved position off every screen (monitor unplugged…) → centre the window."""
        frame = self.frameGeometry()
        for scr in QtGui.QGuiApplication.screens():
            g = scr.availableGeometry()
            if g.intersects(frame) and g.contains(frame.topLeft() + QtCore.QPoint(40, 15)):
                return
        scr = QtGui.QGuiApplication.primaryScreen()
        if scr is not None:
            g = scr.availableGeometry()
            w, h = min(self.width(), g.width() - 40), min(self.height(), g.height() - 40)
            self.resize(w, h)
            self.move(g.center() - QtCore.QPoint(w // 2, h // 2))

    def _save_layout(self):
        save_settings(
            geometry=bytes(self.saveGeometry().toBase64()).decode("ascii"),
            splitter=bytes(self.splitter.saveState().toBase64()).decode("ascii"),
            thumb=self._thumb)

    def _save_options(self):
        if self._loading:
            return
        save_settings(turntable=int(self.chk_turntable.isChecked()),
                      ground=int(self.chk_ground.isChecked()),
                      preset=self._preset_id(),
                      chrome=int(self.chk_chrome.isChecked()),
                      grey=int(self.chk_grey.isChecked()),
                      chart_on=int(self.chk_chart.isChecked()),
                      corner=self.cmb_corner.currentData(),
                      chart=self.cmb_chart.currentData() or "",
                      bg_color=",".join("%.6f" % c for c in self._bg_color))

    def _save_selection(self):
        if self._loading:
            return
        h = self._current_hdri()
        it = self.sidebar.currentItem()
        save_settings(hdri=h.name if h else "",
                      filter=it.data(QtCore.Qt.UserRole) if it else FILTER_ALL)

    def moveEvent(self, e):
        super(LookdevRigDialog, self).moveEvent(e)
        self._geom_timer.start()

    def resizeEvent(self, e):
        super(LookdevRigDialog, self).resizeEvent(e)
        if hasattr(self, "_geom_timer"):
            self._geom_timer.start()

    def closeEvent(self, e):
        self._geom_timer.stop()
        self._save_layout()
        self._save_selection()
        self._save_options()
        super(LookdevRigDialog, self).closeEvent(e)

    # -- thumbnails size ----------------------------------------------------

    def _set_thumb_size(self, v):
        self._thumb = int(v)
        self._apply_thumb_size()
        self._geom_timer.start()

    def _apply_thumb_size(self):
        # never wider than the grid, so a narrow panel never crops the thumbnails
        avail = self.grid.viewport().width() - 34
        w = max(THUMB_MIN // 2, min(self._thumb, avail)) if avail > 0 else self._thumb
        self.grid.setIconSize(QtCore.QSize(w, w // 2))
        self.grid.setGridSize(QtCore.QSize(w + 14, w // 2 + 30))

    def eventFilter(self, obj, ev):
        grid = getattr(self, "grid", None)
        if grid is not None and obj is grid.viewport() and ev.type() == QtCore.QEvent.Resize:
            QtCore.QTimer.singleShot(0, self._apply_thumb_size)
        if grid is not None and obj is grid.viewport() and ev.type() == QtCore.QEvent.Wheel \
                and ev.modifiers() & QtCore.Qt.ControlModifier:
            step = 16 if ev.angleDelta().y() > 0 else -16
            self.size_slider.setValue(self._thumb + step)
            return True
        if obj is getattr(self, "lbl_status", None) and ev.type() == QtCore.QEvent.MouseButtonPress:
            self._show_history()
            return True
        return super(LookdevRigDialog, self).eventFilter(obj, ev)

    # -- data ---------------------------------------------------------------

    def refresh(self):
        self._loading = True
        try:
            try:
                a = adapters.detect()
                self.lbl_renderer.setText(a.label)
                self.lbl_renderer.setProperty("error", False)
                self.lbl_renderer.setToolTip("Active renderer")
                self.b_build.setEnabled(True)
            except Exception as exc:  # noqa: BLE001
                self.lbl_renderer.setText("Renderer not supported")
                self.lbl_renderer.setProperty("error", True)
                self.lbl_renderer.setToolTip(str(exc))
                self.b_build.setEnabled(False)
            self.lbl_renderer.style().unpolish(self.lbl_renderer)
            self.lbl_renderer.style().polish(self.lbl_renderer)

            current = self._preset_id() if self.cmb_preset.count() else \
                self._settings.get("preset", "turntable_default")
            self.cmb_preset.clear()
            labels = core.preset_labels() or {"turntable_default": "turntable_default"}
            for name in sorted(labels, key=lambda n: (n != "turntable_default", labels[n].lower())):
                self.cmb_preset.addItem(labels[name], name)
            self._select_preset(current)

            cur_chart = self.cmb_chart.currentData() or self._settings.get("chart") \
                or core.DEFAULT_CHART
            self.cmb_chart.clear()
            for cid, label in core.list_charts().items():
                self.cmb_chart.addItem(label, cid)
            i = self.cmb_chart.findData(cur_chart)
            self.cmb_chart.setCurrentIndex(max(0, i))

            self._fill_library_combo()
            self._hdris = core.list_hdris(self._root)
            self._fill_sidebar()
            self.grid.clear()
            for h in self._hdris:
                pm = QtGui.QPixmap(h.thumb) if h.thumb else QtGui.QPixmap()
                if pm.isNull():
                    pm = _placeholder(256, 128, "no preview")
                it = QtWidgets.QListWidgetItem(QtGui.QIcon(pm), h.label)
                it.setData(QtCore.Qt.UserRole, h.name)
                it.setToolTip("%s\n%s" % (h.label, h.path))
                it.setTextAlignment(QtCore.Qt.AlignHCenter | QtCore.Qt.AlignTop)
                self.grid.addItem(it)
            if not self._hdris:
                self._status("No HDRIs in %s" % self._root, C_WARN)
            else:
                missing = sum(1 for h in self._hdris if not h.thumb)
                if missing:
                    self._status("%d HDRI(s) without preview — Refresh library" % missing, C_WARN)

            self._select_stored()
            self._apply_filter()
            self._sync_clay()
            self._update_camera_label()
            self._sync_live()
        finally:
            self._loading = False
        self._show_preview(self._current_hdri())

    def _fill_sidebar(self):
        wanted = (self.sidebar.currentItem().data(QtCore.Qt.UserRole)
                  if self.sidebar.currentItem() else self._settings.get("filter", FILTER_ALL))
        self.sidebar.blockSignals(True)
        self.sidebar.clear()

        def add(text, key, count=None, selectable=True):
            it = QtWidgets.QListWidgetItem(text if count is None else "%s   %d" % (text, count))
            it.setData(QtCore.Qt.UserRole, key)
            if not selectable:
                it.setFlags(QtCore.Qt.NoItemFlags)
                it.setForeground(QtGui.QColor(C_TEXT_DIM))
                f = it.font(); f.setBold(True); f.setPointSize(7); it.setFont(f)
            self.sidebar.addItem(it)
            return it

        add("All HDRIs", FILTER_ALL, len(self._hdris))
        missing = sum(1 for h in self._hdris if not h.thumb)
        if missing:
            add("Missing preview", FILTER_MISSING, missing)
        groups = {}
        for h in self._hdris:
            parts = h.group.split("/") if h.group else []
            for i in range(1, len(parts) + 1):
                g = "/".join(parts[:i])
                groups[g] = groups.get(g, 0) + 1
        if groups:
            add("", None, selectable=False)
            add("FOLDERS", None, selectable=False)
            for g in sorted(groups, key=str.lower):
                depth = g.count("/")
                it = add("    " * depth + g.split("/")[-1], FILTER_DIR + g, groups[g])
                it.setToolTip(g)
        tags = {}
        for h in self._hdris:
            for t in h.meta.get("tags") or []:
                tags[str(t)] = tags.get(str(t), 0) + 1
        if tags:
            add("", None, selectable=False)
            add("TAGS", None, selectable=False)
            for t in sorted(tags, key=str.lower):
                add(t, FILTER_TAG + t, tags[t])
        row = 0
        for i in range(self.sidebar.count()):
            if self.sidebar.item(i).data(QtCore.Qt.UserRole) == wanted:
                row = i
                break
        self.sidebar.setCurrentRow(row)
        self.sidebar.blockSignals(False)

    def _on_filter_changed(self):
        self._apply_filter()
        self._save_selection()

    def _apply_filter(self, *_):
        it = self.sidebar.currentItem()
        key = it.data(QtCore.Qt.UserRole) if it else FILTER_ALL
        text = self.search.text().strip().lower()
        by_name = {h.name: h for h in self._hdris}
        shown = 0
        for i in range(self.grid.count()):
            item = self.grid.item(i)
            h = by_name.get(item.data(QtCore.Qt.UserRole))
            ok = h is not None
            if ok and key == FILTER_MISSING:
                ok = not h.thumb
            elif ok and key and key.startswith(FILTER_TAG):
                ok = key[len(FILTER_TAG):] in [str(t) for t in h.meta.get("tags") or []]
            elif ok and key and key.startswith(FILTER_DIR):
                g = key[len(FILTER_DIR):]
                ok = h.group == g or h.group.startswith(g + "/")
            if ok and text:
                hay = " ".join([h.name, h.label, h.group]
                               + [str(t) for t in h.meta.get("tags") or []]).lower()
                ok = all(word in hay for word in text.split())
            item.setHidden(not ok)
            shown += ok
        self.lbl_count.setText("%d / %d HDRIs" % (shown, len(self._hdris)))

    def _current_hdri(self):
        item = self.grid.currentItem()
        if not item:
            return None
        name = item.data(QtCore.Qt.UserRole)
        return next((h for h in self._hdris if h.name == name), None)

    def _show_preview(self, h):
        if h is None:
            self.preview.set_source(None)
            self.lbl_name.setText("")
            for lbl in self.lbl_info:
                lbl.setText("")
            return
        self.preview.set_source(QtGui.QPixmap(h.thumb) if h.thumb else None)
        self.lbl_name.setText(h.label)
        where = h.group or "(top level)"
        tags = ", ".join(str(t) for t in h.meta.get("tags") or [])
        lines = ["Rotation %.1f°   ·   intensity %.2f" % (h.rotation_offset, h.intensity),
                 "Folder: %s" % where + ("   ·   Tags: %s" % tags if tags else ""),
                 os.path.basename(h.path) + ("   ·   blurred bg ready" if h.bg else "   ·   no blurred bg")]
        for lbl, text in zip(self.lbl_info, lines):
            lbl.setText(text)

    def _sync_live(self):
        """Live controls follow the built rig; disabled when there is none."""
        state = builder.hdri_state()
        on = state is not None
        for w in (self.row_rot, self.row_ev, self.cmb_bg, self.b_save_default):
            w.setEnabled(on)
        if on:
            self.row_rot.set_value(state["rotation"])
            self.row_ev.set_value(state["exposure"])
            self.cmb_bg.blockSignals(True)
            self.cmb_bg.setCurrentIndex(max(0, self.cmb_bg.findData(state["bg_mode"])))
            self.cmb_bg.blockSignals(False)
            self.lbl_live.setText("Acting on the rig  ·  %s" % state["hdri"])
            self._bg_color = builder.background_color()
            self._paint_bg_button()
            refs = builder.refs_state()
            if refs:
                for chk, key in ((self.chk_chrome, "chrome"), (self.chk_grey, "grey18"),
                                 (self.chk_chart, "colorchecker")):
                    chk.blockSignals(True)
                    chk.setChecked(key in refs["items"])
                    chk.blockSignals(False)
                for cmb, val in ((self.cmb_corner, refs.get("corner")),
                                 (self.cmb_chart, refs.get("chart"))):
                    i = cmb.findData(val)
                    if i >= 0:
                        cmb.blockSignals(True)
                        cmb.setCurrentIndex(i)
                        cmb.blockSignals(False)
        else:
            self.lbl_live.setText("Build the rig to adjust the dome live")
        self.b_bg_color.setEnabled(self.cmb_bg.currentData() == "color" or not on)
        h = self._current_hdri()
        blur_item = self.cmb_bg.model().item(1)
        if blur_item is not None:
            blur_item.setEnabled(bool(h and h.bg))
        self.cmb_chart.setEnabled(self.chk_chart.isChecked())

    def _update_camera_label(self):
        _geo, cam = builder._split_selection(list(rt.selection))
        if cam is not None:
            self.lbl_camera.setText("Copy of %s" % cam.name)
            self.lbl_camera.setToolTip("A camera is selected with the asset: the rig copies its "
                                       "framing (the original is never moved)")
        else:
            self.lbl_camera.setText("Automatic framing")
            self.lbl_camera.setToolTip("Select a camera together with the asset to use its framing")

    def _sync_clay(self):
        self.chk_clay.blockSignals(True)
        try:
            self.chk_clay.setChecked(builder.clay_is_on())
        except Exception:  # noqa: BLE001
            self.chk_clay.setChecked(False)
        self.chk_clay.blockSignals(False)

    def _select_stored(self):
        """Rig HDRI first, then the one stored on the selected asset, then the last one used."""
        state = builder.hdri_state()
        hdri = state["hdri"] if state else None
        sel = list(rt.selection)
        if sel and hdri is None:
            hdri, preset = builder.stored_settings(sel[0])
            if preset:
                self._select_preset(preset)
        hdri = hdri or self._settings.get("hdri")
        for i in range(self.grid.count()):
            if self.grid.item(i).data(QtCore.Qt.UserRole) == hdri:
                self.grid.setCurrentRow(i)
                self.grid.scrollToItem(self.grid.item(i))
                return
        if self.grid.count():
            self.grid.setCurrentRow(0)

    def _preset_id(self):
        return self.cmb_preset.currentData() or "turntable_default"

    def _select_preset(self, name):
        i = self.cmb_preset.findData(name)
        if i >= 0:
            self.cmb_preset.setCurrentIndex(i)

    def _on_preset_changed(self, name):
        if not name or self._loading:
            return
        p = core.load_preset(name)
        self.chk_ground.setChecked(bool(p["ground"].get("shadow_catcher", True)))
        self._save_options()

    # -- status -------------------------------------------------------------

    def _status(self, msg, color=C_TEXT):
        from datetime import datetime
        self._history.append((datetime.now().strftime("%H:%M:%S"), msg, color))
        self._history = self._history[-60:]
        self.lbl_status.setText("<span style='color:%s'>●</span>&nbsp; %s" % (color, msg))

    def _log(self, msg):
        self._status(msg, C_TEXT)

    def _show_history(self):
        if not self._history:
            return
        m = QtWidgets.QMenu(self)
        for t, msg, _c in reversed(self._history[-25:]):
            a = m.addAction("%s   %s" % (t, msg))
            a.setEnabled(False)
        m.exec(self.lbl_status.mapToGlobal(QtCore.QPoint(0, -m.sizeHint().height())))

    # -- actions ------------------------------------------------------------

    def _grid_menu(self, pos):
        h = self._current_hdri()
        if h is None:
            return
        m = QtWidgets.QMenu(self)
        m.addAction("Build rig with this HDRI", self.on_build)
        a = m.addAction("Use on the rig", lambda: self.on_hdri_changed(force=True))
        a.setEnabled(builder.hdri_state() is not None)
        m.addSeparator()
        m.addAction("Show in folder", lambda: self._reveal(h.path))
        m.exec(self.grid.viewport().mapToGlobal(pos))

    def _reveal(self, path):
        try:
            import subprocess
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        except Exception as exc:  # noqa: BLE001
            self._status("Show in folder: %s" % exc, C_ERR)

    def on_hdri_changed(self, *_, force=False):
        h = self._current_hdri()
        self._show_preview(h)
        if self._loading or h is None:
            return
        self._save_selection()
        state = builder.hdri_state()
        if state is None or (state["hdri"] == h.name and not force):
            return
        try:
            builder.set_hdri(h)
        except Exception as exc:  # noqa: BLE001
            self._status("HDRI: %s" % exc, C_ERR)
            return
        rt.redrawViews()
        self._sync_live()
        self._status("Dome → %s" % h.label, C_OK)

    def _refs_values(self):
        items = [k for chk, k in ((self.chk_chrome, "chrome"), (self.chk_grey, "grey18"),
                                  (self.chk_chart, "colorchecker")) if chk.isChecked()]
        return {"items": items, "corner": self.cmb_corner.currentData() or "bottom_right",
                "chart": self.cmb_chart.currentData() or core.DEFAULT_CHART}

    def on_refs_changed(self):
        if self._loading:
            return
        self.cmb_chart.setEnabled(self.chk_chart.isChecked())
        self._save_options()
        if builder.hdri_state() is None:
            return
        v = self._refs_values()
        try:
            res = builder.update_refs(items=v["items"], corner=v["corner"], chart=v["chart"])
        except Exception as exc:  # noqa: BLE001
            self._status("References: %s" % exc, C_ERR)
            return
        for line in res["log"]:
            self._status(line.strip(), C_WARN)
        names = {"chrome": "chrome", "grey18": "grey", "colorchecker": "chart"}
        self._status("References: %s  ·  %s" % (
            ", ".join(names[i] for i in v["items"]) or "none",
            self.cmb_corner.currentText().lower()), C_OK)

    def _paint_bg_button(self):
        qc = _qcolor_from_linear(self._bg_color)
        self.b_bg_color.setStyleSheet(
            "QToolButton { background-color: %s; border: 1px solid %s; border-radius: 2px; }"
            "QToolButton:disabled { background-color: #2a2a2a; border-color: #262626; }"
            % (qc.name(), C_BORDER_HI))

    def on_pick_bg_color(self):
        qc = QtWidgets.QColorDialog.getColor(_qcolor_from_linear(self._bg_color), self,
                                             "Background colour")
        if not qc.isValid():
            return
        self._bg_color = _linear_from_qcolor(qc)
        self._paint_bg_button()
        self._save_options()
        if builder.hdri_state() is not None:
            try:
                builder.set_background_color(self._bg_color)
                self._status("Background colour %s" % qc.name(), C_OK)
            except Exception as exc:  # noqa: BLE001
                self._status("Background colour: %s" % exc, C_ERR)

    def on_rotation(self, value):
        try:
            builder.set_rotation(value)
            rt.redrawViews()
        except Exception as exc:  # noqa: BLE001
            self._status("Rotation: %s" % exc, C_ERR)

    def on_exposure(self, value):
        try:
            builder.set_exposure(value)
        except Exception as exc:  # noqa: BLE001
            self._status("Exposure: %s" % exc, C_ERR)

    def on_background_mode(self):
        mode = self.cmb_bg.currentData()
        self.b_bg_color.setEnabled(mode == "color")
        if self._loading or builder.hdri_state() is None:
            return
        try:
            log = builder.set_background_mode(mode, color=self._bg_color)
        except Exception as exc:  # noqa: BLE001
            self._status("Background: %s" % exc, C_ERR)
            self._sync_live()
            return
        for line in log:
            self._status(line.strip(), C_WARN)
        text = {"hdri": "HDRI", "blur": "blurred HDRI",
                "color": "colour %s" % _qcolor_from_linear(self._bg_color).name()}[mode]
        self._status("Background: %s" % text, C_OK)

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
            self._status("Save default: %s" % exc, C_ERR)
            return
        self.refresh()
        self._status("Saved %s  ·  rot %.1f°  ·  intensity %.3f"
                     % (name, saved["rotation_offset_deg"], saved["intensity"]), C_OK)

    def on_refresh_library(self, make_tx=False, force=False):
        try:
            from . import library_max
        except Exception as exc:  # noqa: BLE001
            self._status("Library: %s" % exc, C_ERR)
            return
        if make_tx and not library_max.find_maketx():
            self._status("maketx not found (Arnold) — previews only", C_WARN)
            make_tx = False
        jobs = library_max.pending(want_tx=make_tx, force=force, folder=self._root)
        if not jobs:
            self._status("Library up to date", C_OK)
            return
        if not core.is_default_library(self._root) and len(jobs) > 20:
            r = QtWidgets.QMessageBox.question(
                self, "Refresh library",
                "Generate previews for %d HDRIs in\n%s ?\n\nIt can take a while (each HDRI is read "
                "once). Previews go to your local cache; the folder itself is not modified.\n"
                "You can cancel at any time and continue later." % (len(jobs), self._root))
            if r != QtWidgets.QMessageBox.Yes:
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

        report = library_max.refresh(make_tx=make_tx, force=force, progress=progress,
                                     folder=self._root)
        dlg.close()
        self.refresh()
        if report.errors:
            for e in report.errors:
                self._status(e, C_ERR)
            self._status("Library: %d updated, %d errors (click for details)"
                         % (len(report.done), len(report.errors)), C_ERR)
        else:
            self._status("Library: %d updated" % len(report.done), C_OK)

    def on_open_folder(self):
        if os.path.isdir(self._root):
            os.startfile(self._root)
        else:
            self._status("Folder not found: %s" % self._root, C_ERR)

    # -- libraries ----------------------------------------------------------

    def _fill_library_combo(self):
        cb = self.cmb_library
        cb.blockSignals(True)
        cb.clear()
        cb.addItem("Studio library", core.HDRI_DIR)
        cb.setItemData(0, core.HDRI_DIR, QtCore.Qt.ToolTipRole)
        for p in self._recent:
            if not core.is_default_library(p):
                cb.addItem(_short_path(p), p)
                cb.setItemData(cb.count() - 1, p, QtCore.Qt.ToolTipRole)
        cb.insertSeparator(cb.count())
        cb.addItem("Browse folder…", "__browse__")
        if self._recent:
            cb.addItem("Clear recent folders", "__clear__")
        i = cb.findData(self._root)
        if i < 0:
            cb.insertItem(1, _short_path(self._root), self._root)
            i = 1
        cb.setCurrentIndex(i)
        cb.blockSignals(False)

    def _on_library_activated(self, index):
        data = self.cmb_library.itemData(index)
        if data == "__browse__":
            start = self._root if not core.is_default_library(self._root) else \
                (self._recent[0] if self._recent else "")
            folder = QtWidgets.QFileDialog.getExistingDirectory(self, "HDRI folder", start)
            if folder:
                self.set_library(folder)
            else:
                self._fill_library_combo()
            return
        if data == "__clear__":
            self._recent = []
            save_settings(recent_libraries="[]")
            self._fill_library_combo()
            return
        if data and data != self._root:
            self.set_library(data)

    def set_library(self, folder):
        folder = os.path.normpath(folder)
        if not os.path.isdir(folder):
            self._status("Folder not found: %s" % folder, C_ERR)
            return
        self._root = folder
        if not core.is_default_library(folder):
            self._recent = [folder] + [p for p in self._recent
                                       if os.path.normcase(p) != os.path.normcase(folder)]
            self._recent = self._recent[:8]
        save_settings(library=folder, recent_libraries=json.dumps(self._recent), filter=FILTER_ALL)
        self.sidebar.setCurrentRow(0)
        self.search.clear()
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            self.refresh()
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
        name = "Studio library" if core.is_default_library(folder) else folder
        self._status("Library: %s  ·  %d HDRIs" % (name, len(self._hdris)), C_OK)

    def on_build(self):
        hdri = self._current_hdri()
        if hdri is None:
            self._status("Pick an HDRI", C_WARN)
            return
        preset_name = self._preset_id()
        overrides = {
            "turntable": {"enabled": self.chk_turntable.isChecked()},
            "ground": {"shadow_catcher": self.chk_ground.isChecked()},
            "clay": {"enabled": self.chk_clay.isChecked()},
            "refs": self._refs_values(),
            "background": {"mode": self.cmb_bg.currentData() or "hdri",
                           "color": list(self._bg_color)},
        }
        self._update_camera_label()
        try:
            rig = builder.build(hdri, preset_name, overrides=overrides)
        except Exception as exc:  # noqa: BLE001
            self._status(str(exc), C_ERR)
            return
        for line in rig["warnings"] + rig["log"]:
            self._status(line.strip(), C_WARN)
        msg = "Rig built  ·  %s  ·  %d nodes" % (hdri.label, len(rig["nodes"]))
        if "render_range" in rig:
            msg += "  ·  frames %d-%d" % rig["render_range"]
        if rig.get("camera_source"):
            msg += "  ·  camera from %s" % rig["camera_source"]
        warn = rig["warnings"] or rig["log"]
        self._status(msg + ("  ·  check messages" if warn else ""), C_WARN if warn else C_OK)
        self._sync_clay()
        self._sync_live()

    def on_clay(self, on):
        try:
            n = builder.set_clay(on)
        except Exception as exc:  # noqa: BLE001
            self._status("Clay: %s" % exc, C_ERR)
            self._sync_clay()
            return
        rt.redrawViews()
        self._status("Clay %s  ·  %d objects" % ("on" if on else "off", n), C_OK)

    def on_remove(self):
        with pymxs.undo(True, "Delete Lookdev Rig"):
            builder.remove_rig()
        rt.redrawViews()
        self._sync_clay()
        self._sync_live()
        self._status("Rig deleted  ·  asset materials restored", C_OK)


def show():
    """Opens the window; if it is already open, brings it to the front."""
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
