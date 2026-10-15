# -*- coding: utf-8 -*-
"""
StudioLibrary MAX v2.0.0

Changes v0.11.16:
- UX 1: + New Folder moved to the top bar, LEFT side. + Save Pose stays on the right.
- UX 2: Save Pose form: Name sits right above its input (spacing=2), same for Comment,
        no excessive gaps between fields.
- UX 5: Larger Key / Mirror / Additive checkboxes (16px indicator, 11pt font).
- UX 6: Filter T R S checkboxes under Additive to choose which channels are applied.
- UX 7: "Details" button at the bottom of the panel — opens a window listing the pose objects.
- FUNC 3 FIX: Thumbnail uses Tools > Screen Capture > captureStillImage via MAXScript
              (equivalent to the MAX 2025 menu Tools > Screen Capture > Capture Still Image).
              Saves to %TEMP% and loads it as the preview. No Arnold.
- FUNC 4 FIX: Key uses 'at time currentTime animate on (...)' — the correct MAXScript syntax
              to create keyframes on the current frame without relying on individual controllers.
"""

from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtWidgets import (
    QTreeWidget, QTreeWidgetItem, QColorDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QVBoxLayout, QListWidgetItem,
    QCheckBox, QSizePolicy
)
import os
import json
import shutil
import getpass
import configparser
import tempfile
import pymxs
from datetime import datetime

rt = pymxs.runtime

__version__ = "2.0.0"

# -------------------------------------------------------------
#  UI constants
# -------------------------------------------------------------

THUMB_W      = 148
THUMB_H      = 124
ITEM_W       = THUMB_W + 16
ITEM_H       = THUMB_H + 40

POSE_NAME_PT = 11
FORM_TEXT_PT = 9

# Neutral gray palette
C_BG        = "#1C1C1C"
C_BG2       = "#222222"
C_BG3       = "#191919"
C_BORDER    = "#2E2E2E"
C_BORDER_HI = "#484848"
C_TEXT      = "#C8C8C8"
C_TEXT_DIM  = "#666666"
C_SEL_BG    = "#303030"
C_SEL_TEXT  = "#E8E8E8"
C_BTN       = "#2A2A2A"
C_BTN_HO    = "#353535"
C_ACCENT_BG = "#2E2E2E"
C_ACCENT_BO = "#484848"
C_ACCENT_TX = "#D0D0D0"
C_ACCENT_HO = "#3A3A3A"
C_STATUS    = "#1A1A1A"

PLACEHOLDER_BG = C_BG3
PLACEHOLDER_FG = "#3A3A3A"


# -------------------------------------------------------------
#  Persistent settings
# -------------------------------------------------------------

def _settings_path():
    base = os.path.join(os.path.expanduser("~"), ".studio-toolbar")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "studiolibrarymax_state.ini")


def load_state():
    cfg = configparser.ConfigParser()
    cfg.read(_settings_path(), encoding="utf-8")
    return {
        "library_path":    cfg.get("state", "library_path",    fallback=""),
        "current_project": cfg.get("state", "current_project", fallback=""),
    }


def save_state(library_path, current_project=""):
    cfg = configparser.ConfigParser()
    cfg["state"] = {
        "library_path":    library_path    or "",
        "current_project": current_project or "",
    }
    with open(_settings_path(), "w", encoding="utf-8") as f:
        cfg.write(f)


# -------------------------------------------------------------
#  Transform helpers
# -------------------------------------------------------------

def quat_to_list(q):
    return [q.x, q.y, q.z, q.w]


def list_to_quat(lst):
    if len(lst) == 4:
        x, y, z, w = lst
        return rt.Quat(x, y, z, w)
    return rt.Quat(0, 0, 0, 1)


def apply_node_transform(node, pos_list, rot_list, scale_list,
                         mirror=False, additive=False, key=False,
                         do_pos=True, do_rot=True, do_scale=True):
    """
    FIX: rt.execute() does NOT accept 'local' at the top level — it must be inside a ( ) block.
    Without key: direct pymxs. With key: MAXScript in a ( ) block.
    """
    try:
        px = -pos_list[0] if mirror else pos_list[0]
        py, pz = pos_list[1], pos_list[2]
        sx, sy, sz = scale_list[0], scale_list[1], scale_list[2]
        if mirror:
            rot = rt.Quat(-rot_list[0], rot_list[1], rot_list[2], -rot_list[3])
        else:
            rot = list_to_quat(rot_list)

        if not key:
            pos   = rt.Point3(px, py, pz)
            scale = rt.Point3(sx, sy, sz)
            if additive:
                if do_scale:
                    node.scale = rt.Point3(
                        node.scale.x * scale.x,
                        node.scale.y * scale.y,
                        node.scale.z * scale.z)
                if do_rot:   node.rotation = node.rotation * rot
                if do_pos:   node.pos      = node.pos + pos
            else:
                if do_scale: node.scale    = scale
                if do_rot:   node.rotation = rot
                if do_pos:   node.pos      = pos
            return

        # With key: MAXScript in a ( ) block so 'local' can be used
        n_name = node.name.replace('"', '\\"')
        rx = -rot_list[0] if mirror else rot_list[0]
        ry, rz = rot_list[1], rot_list[2]
        rw = -rot_list[3] if mirror else rot_list[3]

        pos_s   = f"[{px},{py},{pz}]"
        rot_s   = f"(quat {rx} {ry} {rz} {rw})"
        scale_s = f"[{sx},{sy},{sz}]"

        body_lines = []
        if additive:
            if do_pos:   body_lines.append(f"      n.pos      += {pos_s}")
            if do_rot:   body_lines.append(f"      n.rotation  = n.rotation * {rot_s}")
            if do_scale: body_lines.append(f"      n.scale    *= {scale_s}")
        else:
            if do_scale: body_lines.append(f"      n.scale     = {scale_s}")
            if do_rot:   body_lines.append(f"      n.rotation  = {rot_s}")
            if do_pos:   body_lines.append(f"      n.pos       = {pos_s}")

        if not body_lines:
            return

        body = "\n".join(body_lines)
        mxs = (
            "(\n"
            f'  local n = getNodeByName "{n_name}"\n'
            "  if n != undefined do (\n"
            "    at time currentTime animate on (\n"
            f"{body}\n"
            "    )\n"
            "  )\n"
            ")"
        )
        rt.execute(mxs)

    except Exception as e:
        print(f"[StudioLibMAX] Error on '{node.name}': {e}")


def capture_viewport_to_file(out_path):
    """
    Captures the active viewport using gw.getViewportDib() with .filename + save.
    Confirmed working in MAX 2025:

      img = gw.getViewportDib()
      img.filename = "C:/path/snapshot.png"
      save img

    rt.execute() requires a ( ) block to use local variables.
    """
    out_fwd = out_path.replace("\\", "/")
    captured = False

    # Method A: gw.getViewportDib() with .filename — confirmed in MAX 2025
    if not captured:
        try:
            mxs = (
                f'( ' +
                f'local img = gw.getViewportDib() ; ' +
                f'img.filename = "{out_fwd}" ; ' +
                f'save img ' +
                f')' 
            )
            rt.execute(mxs)
            if os.path.exists(out_path):
                captured = True
                print("[thumb A] gw.getViewportDib() + .filename + save OK")
        except Exception as e:
            print(f"[thumb A gw+filename+save] {e}")

    # Method B: direct pymxs — assign filename to the bitmap object and save
    if not captured:
        try:
            img = rt.gw.getViewportDib()
            if img is not None:
                img.filename = out_path
                rt.save(img)
                if os.path.exists(out_path):
                    captured = True
                    print("[thumb B] pymxs gw.getViewportDib() + rt.save OK")
        except Exception as e:
            print(f"[thumb B pymxs gw+save] {e}")

    # Method C: grabView() with .filename inside a ( ) block
    if not captured:
        try:
            mxs = f'( local b = grabView() ; b.filename = "{out_fwd}" ; save b )'
            rt.execute(mxs)
            if os.path.exists(out_path):
                captured = True
                print("[thumb C] grabView() + .filename OK")
        except Exception as e:
            print(f"[thumb C grabView+filename] {e}")

    return captured


def make_pose_icon(preview_path):
    pix = QtGui.QPixmap(THUMB_W, THUMB_H)
    pix.fill(QtGui.QColor(PLACEHOLDER_BG))

    if preview_path and os.path.exists(preview_path):
        img = QtGui.QPixmap(preview_path)
        if not img.isNull():
            img = img.scaled(
                THUMB_W, THUMB_H,
                QtCore.Qt.KeepAspectRatioByExpanding,
                QtCore.Qt.SmoothTransformation
            )
            ox = (img.width()  - THUMB_W) // 2
            oy = (img.height() - THUMB_H) // 2
            pix = img.copy(ox, oy, THUMB_W, THUMB_H)
    else:
        painter = QtGui.QPainter(pix)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.fillRect(0, 0, THUMB_W, THUMB_H, QtGui.QColor(PLACEHOLDER_BG))
        # Use SVG/text image with font metrics for exact centering
        font = QtGui.QFont("Segoe UI", 26)
        painter.setFont(font)
        fm = QtGui.QFontMetrics(font)
        icon_char = "◇"   # placeholder glyph for poses without a thumbnail
        # boundingRect gives the actual glyph dimensions
        br = fm.boundingRect(icon_char)
        x = (THUMB_W - br.width())  // 2 - br.left()
        y = (THUMB_H - br.height()) // 2 - br.top()
        painter.setPen(QtGui.QColor(PLACEHOLDER_FG))
        painter.drawText(x, y, icon_char)
        pen = QtGui.QPen(QtGui.QColor(PLACEHOLDER_FG), 1)
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.NoBrush)
        painter.drawRoundedRect(1, 1, THUMB_W - 2, THUMB_H - 2, 3, 3)
        painter.end()

    return QtGui.QIcon(pix)


# -------------------------------------------------------------
#  Helper: section label
# -------------------------------------------------------------

def make_section_label(text):
    lbl = QtWidgets.QLabel(text)
    lbl.setStyleSheet(
        f"color: {C_TEXT_DIM}; font-size: 9pt; font-weight: bold; "
        "letter-spacing: 1px; padding: 0px 2px 3px 2px; background: transparent;"
    )
    return lbl


def make_field_label(text):
    """Field label inside the Save Pose form."""
    lbl = QtWidgets.QLabel(text)
    lbl.setStyleSheet(
        f"color: {C_TEXT_DIM}; font-size: 9pt; font-weight: bold; "
        "letter-spacing: 0.3px; background: transparent; margin: 0px; padding: 0px;"
    )
    return lbl


# -------------------------------------------------------------
#  Dialog: pose object list + single rename + batch rename
# -------------------------------------------------------------

class PoseDetailsDialog(QtWidgets.QDialog):
    def __init__(self, pose_path, pose_name, node_names, parent=None):
        super().__init__(parent)
        self.pose_path  = pose_path
        self.pose_name  = pose_name
        self.node_names = list(node_names)

        self.setWindowTitle(f"Pose Details — {pose_name}")
        self.resize(380, 500)
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)

        self.setStyleSheet(f"""
            QDialog, QWidget {{
                background-color: {C_BG};
                color: {C_TEXT};
                font-family: "Segoe UI", Arial, sans-serif;
                font-size: 10pt;
            }}
            QLabel {{ background: transparent; color: {C_TEXT}; }}
            QLineEdit {{
                background: {C_BG3}; color: {C_TEXT};
                border: 1px solid {C_BORDER}; border-radius: 4px;
                padding: 3px 6px; font-size: 9pt;
            }}
            QLineEdit:focus {{ border-color: {C_BORDER_HI}; }}
            QPushButton {{
                background-color: {C_BTN};
                border: 1px solid {C_BORDER};
                color: {C_TEXT};
                padding: 5px 12px;
                border-radius: 4px;
                font-size: 9pt;
            }}
            QPushButton:hover {{ background-color: {C_BTN_HO}; border-color: {C_BORDER_HI}; }}
            QPushButton#primary {{
                background-color: {C_ACCENT_BG};
                border: 1px solid {C_ACCENT_BO};
                color: {C_ACCENT_TX};
                font-weight: bold;
            }}
            QPushButton#primary:hover {{ background-color: {C_ACCENT_HO}; }}
            QPushButton#rename_inline {{
                background: transparent; border: none;
                color: {C_TEXT_DIM}; padding: 1px 4px;
                font-size: 8pt;
            }}
            QPushButton#rename_inline:hover {{ color: {C_TEXT}; }}
            QListWidget {{
                background: {C_BG3}; color: {C_TEXT};
                border: 1px solid {C_BORDER}; border-radius: 4px;
            }}
            QListWidget::item {{ padding: 3px 6px; }}
            QListWidget::item:selected {{
                background: {C_SEL_BG}; color: {C_SEL_TEXT};
            }}
            QGroupBox {{
                border: 1px solid {C_BORDER}; border-radius: 5px;
                margin-top: 10px; padding: 10px 8px 8px 8px;
                background: {C_BG2};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; left: 8px; padding: 0 4px;
                color: {C_TEXT_DIM}; font-size: 9pt; font-weight: bold;
            }}
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        # -- Header ----------------------------------------------
        hdr = QtWidgets.QLabel(
            f"{len(self.node_names)} object{'s' if len(self.node_names) != 1 else ''} in pose:"
        )
        hdr.setStyleSheet(f"color: {C_TEXT_DIM}; font-size: 9pt;")
        lay.addWidget(hdr)

        # -- List with a Rename button per row ------------------
        # QListWidget + one QWidget per item via setItemWidget
        self.lst = QtWidgets.QListWidget()
        self.lst.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        lay.addWidget(self.lst, 1)
        self._populate_list()

        # -- Batch Rename -----------------------------------------
        batch_box = QtWidgets.QGroupBox("Batch Rename")
        batch_lay = QtWidgets.QGridLayout(batch_box)
        batch_lay.setSpacing(6)

        batch_lay.addWidget(QtWidgets.QLabel("Find:"),   0, 0)
        self.find_edit = QtWidgets.QLineEdit()
        self.find_edit.setPlaceholderText("e.g.  ctrl")
        batch_lay.addWidget(self.find_edit, 0, 1)

        batch_lay.addWidget(QtWidgets.QLabel("Replace:"), 1, 0)
        self.replace_edit = QtWidgets.QLineEdit()
        self.replace_edit.setPlaceholderText("e.g.  bone")
        batch_lay.addWidget(self.replace_edit, 1, 1)

        self.case_chk = QtWidgets.QCheckBox("Case sensitive")
        self.case_chk.setChecked(True)
        batch_lay.addWidget(self.case_chk, 2, 0, 1, 2)

        preview_btn = QtWidgets.QPushButton("Preview")
        preview_btn.clicked.connect(self._batch_preview)
        apply_batch_btn = QtWidgets.QPushButton("Apply Batch Rename")
        apply_batch_btn.setObjectName("primary")
        apply_batch_btn.clicked.connect(self._batch_apply)
        btn_row = QHBoxLayout()
        btn_row.addWidget(preview_btn)
        btn_row.addWidget(apply_batch_btn)
        batch_lay.addLayout(btn_row, 3, 0, 1, 2)

        lay.addWidget(batch_box)

        # -- Close button -----------------------------------------
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.setObjectName("primary")
        close_btn.clicked.connect(self.accept)
        lay.addWidget(close_btn)

    # ---------------------------------------------
    def _populate_list(self):
        self.lst.clear()
        for nm in self.node_names:
            item = QtWidgets.QListWidgetItem(self.lst)
            row_w = QtWidgets.QWidget()
            row_lay = QHBoxLayout(row_w)
            row_lay.setContentsMargins(4, 0, 4, 0)
            row_lay.setSpacing(4)
            lbl = QtWidgets.QLabel(nm)
            lbl.setStyleSheet(f"color: {C_TEXT}; font-size: 9pt; background: transparent;")
            ren_btn = QtWidgets.QPushButton("rename")
            ren_btn.setObjectName("rename_inline")
            ren_btn.setFixedHeight(18)
            ren_btn.clicked.connect(lambda checked=False, n=nm: self._rename_one(n))
            row_lay.addWidget(lbl, 1)
            row_lay.addWidget(ren_btn)
            item.setSizeHint(QtCore.QSize(0, 28))
            self.lst.setItemWidget(item, row_w)

    def _rename_one(self, old_name):
        """Renames a single object in pose_data.json."""
        new_name, ok = QtWidgets.QInputDialog.getText(
            self, "Rename Object", f"New name for '{old_name}':", text=old_name
        )
        if not ok or not new_name.strip() or new_name == old_name:
            return
        self._apply_rename({old_name: new_name.strip()})

    def _batch_preview(self):
        """Shows a message with what the names would become after the batch rename."""
        mapping = self._build_mapping()
        if not mapping:
            QtWidgets.QMessageBox.information(
                self, "Batch Rename Preview", "No matches found."
            )
            return
        lines = [f"  {old}  →  {new}" for old, new in mapping.items()]
        QtWidgets.QMessageBox.information(
            self, "Batch Rename Preview",
            f"{len(lines)} object(s) will be renamed:\n\n" + "\n".join(lines)
        )

    def _batch_apply(self):
        mapping = self._build_mapping()
        if not mapping:
            QtWidgets.QMessageBox.information(
                self, "Batch Rename", "No matches found."
            )
            return
        reply = QtWidgets.QMessageBox.question(
            self, "Batch Rename",
            f"Rename {len(mapping)} object(s)?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )
        if reply != QtWidgets.QMessageBox.Yes:
            return
        self._apply_rename(mapping)

    def _build_mapping(self):
        find    = self.find_edit.text()
        replace = self.replace_edit.text()
        if not find:
            return {}
        case = self.case_chk.isChecked()
        mapping = {}
        for nm in self.node_names:
            if case:
                if find in nm:
                    mapping[nm] = nm.replace(find, replace)
            else:
                if find.lower() in nm.lower():
                    import re
                    mapping[nm] = re.sub(re.escape(find), replace, nm, flags=re.IGNORECASE)
        return {k: v for k, v in mapping.items() if k != v}

    def _apply_rename(self, mapping):
        """Writes the old→new mapping to pose_data.json and refreshes the UI."""
        json_file = os.path.join(self.pose_path, "pose_data.json")
        if not os.path.exists(json_file):
            return
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Rename in nodes
            for node in data.get("nodes", []):
                if node["name"] in mapping:
                    node["name"] = mapping[node["name"]]
            # Rename in metadata.contains
            contains = data.get("metadata", {}).get("contains", "")
            if contains:
                parts = [mapping.get(p.strip(), p.strip()) for p in contains.split(",")]
                data["metadata"]["contains"] = ",".join(parts)
            with open(json_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
            # Update local list
            self.node_names = [mapping.get(n, n) for n in self.node_names]
            self._populate_list()
            renamed = len(mapping)
            QtWidgets.QMessageBox.information(
                self, "Renamed", f"{renamed} object(s) renamed successfully."
            )
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", str(e))


# -------------------------------------------------------------
#  Dialog: Batch Rename Objects across multiple poses
# -------------------------------------------------------------

class BatchRenameMultiDialog(QtWidgets.QDialog):
    """
    Applies a Find & Replace on object names across multiple poses at once.
    Shows a preview of all changes before confirming.
    """
    def __init__(self, pose_paths, parent=None):
        super().__init__(parent)
        self.pose_paths = pose_paths
        self.setWindowTitle(f"Batch Rename Objects — {len(pose_paths)} poses")
        self.resize(460, 520)
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)

        self.setStyleSheet(f"""
            QDialog, QWidget {{
                background-color: {C_BG};
                color: {C_TEXT};
                font-family: "Segoe UI", Arial, sans-serif;
                font-size: 10pt;
            }}
            QLabel {{ background: transparent; color: {C_TEXT}; }}
            QLineEdit {{
                background: {C_BG3}; color: {C_TEXT};
                border: 1px solid {C_BORDER}; border-radius: 4px;
                padding: 3px 6px; font-size: 9pt;
            }}
            QLineEdit:focus {{ border-color: {C_BORDER_HI}; }}
            QPushButton {{
                background-color: {C_BTN}; border: 1px solid {C_BORDER};
                color: {C_TEXT}; padding: 5px 12px;
                border-radius: 4px; font-size: 9pt;
            }}
            QPushButton:hover {{ background-color: {C_BTN_HO}; border-color: {C_BORDER_HI}; }}
            QPushButton#primary {{
                background-color: {C_ACCENT_BG}; border: 1px solid {C_ACCENT_BO};
                color: {C_ACCENT_TX}; font-weight: bold;
            }}
            QPushButton#primary:hover {{ background-color: {C_ACCENT_HO}; }}
            QPlainTextEdit {{
                background: {C_BG3}; color: {C_TEXT};
                border: 1px solid {C_BORDER}; border-radius: 4px;
                font-size: 9pt; font-family: "Consolas", monospace;
            }}
            QCheckBox {{ color: {C_TEXT}; spacing: 6px; }}
            QCheckBox::indicator {{
                width: 13px; height: 13px;
                border: 1px solid {C_BORDER_HI}; border-radius: 3px;
                background: {C_BG3};
            }}
            QCheckBox::indicator:checked {{
                background: {C_BORDER_HI}; border-color: #888;
            }}
            QGroupBox {{
                border: 1px solid {C_BORDER}; border-radius: 5px;
                margin-top: 10px; padding: 10px 8px 8px 8px;
                background: {C_BG2};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; left: 8px; padding: 0 4px;
                color: {C_TEXT_DIM}; font-size: 9pt; font-weight: bold;
            }}
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        # Info
        info_lbl = QtWidgets.QLabel(
            f"This will rename objects across <b>{len(pose_paths)}</b> poses."
        )
        info_lbl.setStyleSheet(f"color: {C_TEXT_DIM}; font-size: 9pt;")
        lay.addWidget(info_lbl)

        # Find / Replace
        fr_box = QtWidgets.QGroupBox("Find & Replace")
        fr_lay = QtWidgets.QGridLayout(fr_box)
        fr_lay.setSpacing(6)

        fr_lay.addWidget(QtWidgets.QLabel("Find:"), 0, 0)
        self.find_edit = QtWidgets.QLineEdit()
        self.find_edit.setPlaceholderText("e.g.  ctrl")
        fr_lay.addWidget(self.find_edit, 0, 1)

        fr_lay.addWidget(QtWidgets.QLabel("Replace:"), 1, 0)
        self.replace_edit = QtWidgets.QLineEdit()
        self.replace_edit.setPlaceholderText("e.g.  bone")
        fr_lay.addWidget(self.replace_edit, 1, 1)

        self.case_chk = QtWidgets.QCheckBox("Case sensitive")
        self.case_chk.setChecked(True)
        fr_lay.addWidget(self.case_chk, 2, 0, 1, 2)

        btn_row = QHBoxLayout()
        preview_btn = QtWidgets.QPushButton("Preview")
        preview_btn.clicked.connect(self._preview)
        btn_row.addWidget(preview_btn)
        btn_row.addStretch(1)
        fr_lay.addLayout(btn_row, 3, 0, 1, 2)
        lay.addWidget(fr_box)

        # Preview output
        prev_box = QtWidgets.QGroupBox("Preview")
        prev_lay = QVBoxLayout(prev_box)
        self.preview_txt = QtWidgets.QPlainTextEdit()
        self.preview_txt.setReadOnly(True)
        self.preview_txt.setPlaceholderText("Click Preview to see changes…")
        self.preview_txt.setMinimumHeight(140)
        prev_lay.addWidget(self.preview_txt)
        lay.addWidget(prev_box, 1)

        # Apply / Close buttons
        bot_row = QHBoxLayout()
        self.apply_btn = QtWidgets.QPushButton("Apply to All Poses")
        self.apply_btn.setObjectName("primary")
        self.apply_btn.clicked.connect(self._apply)
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        bot_row.addWidget(self.apply_btn)
        bot_row.addWidget(close_btn)
        lay.addLayout(bot_row)

        self._last_mapping = {}   # pose_path -> {old: new}

    # ---------------------------------------------

    def _build_all_mappings(self):
        """Builds the mapping for each pose and stores it in self._last_mapping."""
        find    = self.find_edit.text()
        replace = self.replace_edit.text()
        case    = self.case_chk.isChecked()
        self._last_mapping = {}

        if not find:
            return

        import re
        for path in self.pose_paths:
            json_file = os.path.join(path, "pose_data.json")
            if not os.path.exists(json_file):
                continue
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue
            mapping = {}
            for node in data.get("nodes", []):
                nm = node["name"]
                if case:
                    if find in nm:
                        mapping[nm] = nm.replace(find, replace)
                else:
                    if find.lower() in nm.lower():
                        mapping[nm] = re.sub(
                            re.escape(find), replace, nm, flags=re.IGNORECASE
                        )
            mapping = {k: v for k, v in mapping.items() if k != v}
            if mapping:
                self._last_mapping[path] = mapping

    def _preview(self):
        self._build_all_mappings()
        if not self._last_mapping:
            self.preview_txt.setPlainText("No matches found.")
            return
        lines = []
        total = 0
        for path, mapping in self._last_mapping.items():
            pose_name = os.path.basename(path).replace(".pose", "")
            lines.append(f"-- {pose_name} --")
            for old, new in mapping.items():
                lines.append(f"   {old}  →  {new}")
                total += 1
            lines.append("")
        self.preview_txt.setPlainText(
            f"{total} rename(s) across {len(self._last_mapping)} pose(s):\n\n" +
            "\n".join(lines)
        )

    def _apply(self):
        self._build_all_mappings()
        if not self._last_mapping:
            QtWidgets.QMessageBox.information(self, "Batch Rename", "No matches found.")
            return
        total = sum(len(m) for m in self._last_mapping.values())
        reply = QtWidgets.QMessageBox.question(
            self, "Batch Rename",
            f"Apply {total} rename(s) across {len(self._last_mapping)} pose(s)?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )
        if reply != QtWidgets.QMessageBox.Yes:
            return
        done = 0
        for path, mapping in self._last_mapping.items():
            json_file = os.path.join(path, "pose_data.json")
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for node in data.get("nodes", []):
                    if node["name"] in mapping:
                        node["name"] = mapping[node["name"]]
                contains = data.get("metadata", {}).get("contains", "")
                if contains:
                    parts = [mapping.get(p.strip(), p.strip())
                             for p in contains.split(",")]
                    data["metadata"]["contains"] = ",".join(parts)
                with open(json_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4)
                done += 1
            except Exception as e:
                print(f"[batch rename] {path}: {e}")
        QtWidgets.QMessageBox.information(
            self, "Done",
            f"Renamed successfully in {done} pose(s)."
        )
        self.preview_txt.setPlainText(f"Done — {done} pose(s) updated.")


# -------------------------------------------------------------
#  Editable comment widget — Enter finishes without a line break
# -------------------------------------------------------------

class _CommentEdit(QtWidgets.QPlainTextEdit):
    """QPlainTextEdit where Enter/Return drops focus instead of inserting \n."""
    def keyPressEvent(self, event):
        if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            self.clearFocus()
        else:
            super().keyPressEvent(event)


# -------------------------------------------------------------
#  UI Principal
# -------------------------------------------------------------

class StudioLibraryMaxUI(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"STM  ·  StudioLibrary MAX  v{__version__}")
        self.resize(1200, 760)
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)
        self.setObjectName("StudioLibMax")

        self.library_path        = None
        self.current_project     = None   # path to the active project folder
        self.current_folder_path = None
        self.current_pose_path   = None
        self.folder_colors       = {}
        self.color_config_path   = None
        self._current_pose_nodes = []   # cache for the Details dialog

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 4)
        main_layout.setSpacing(6)

        # -- Project row -----------------------------------------
        self._proj_stack = QtWidgets.QStackedWidget()
        self._proj_stack.setFixedHeight(34)

        # — Page 0: no projects — light-blue New Project button —
        page_empty = QtWidgets.QWidget()
        pe_lay = QHBoxLayout(page_empty)
        pe_lay.setContentsMargins(0, 0, 0, 0)
        pe_lay.setSpacing(0)
        self.new_proj_empty_btn = QtWidgets.QPushButton("+  New Project")
        self.new_proj_empty_btn.setObjectName("new_proj_btn")
        self.new_proj_empty_btn.setFixedHeight(34)
        self.new_proj_empty_btn.clicked.connect(self._new_project)
        pe_lay.addWidget(self.new_proj_empty_btn)
        pe_lay.addStretch(1)
        self._proj_stack.addWidget(page_empty)

        # — Page 1: has projects — combo + 3 text buttons —
        page_active = QtWidgets.QWidget()
        pa_lay = QHBoxLayout(page_active)
        pa_lay.setContentsMargins(0, 0, 0, 0)
        pa_lay.setSpacing(5)

        self.project_combo = QtWidgets.QComboBox()
        self.project_combo.setFixedHeight(26)
        self.project_combo.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )
        self.project_combo.setStyleSheet(f"""
            QComboBox {{
                background: {C_BG2}; color: {C_TEXT};
                border: 1px solid {C_BORDER}; border-radius: 4px;
                padding: 2px 6px; font-size: 9.5pt;
            }}
            QComboBox:hover {{ border-color: {C_BORDER_HI}; }}
            QComboBox::drop-down {{ border: none; width: 18px; }}
            QComboBox QAbstractItemView {{
                background: {C_BG2}; color: {C_TEXT};
                border: 1px solid {C_BORDER};
                selection-background-color: {C_SEL_BG};
            }}
        """)
        self.project_combo.currentIndexChanged.connect(self._on_project_changed)

        self.new_proj_btn = QtWidgets.QPushButton("+  New")
        self.new_proj_btn.setObjectName("lib_btn")
        self.new_proj_btn.setFixedHeight(24)
        self.new_proj_btn.setToolTip("New project")
        self.new_proj_btn.clicked.connect(self._new_project)

        self.ren_proj_btn = QtWidgets.QPushButton("Rename")
        self.ren_proj_btn.setObjectName("lib_btn")
        self.ren_proj_btn.setFixedHeight(24)
        self.ren_proj_btn.setToolTip("Rename project")
        self.ren_proj_btn.clicked.connect(self._rename_project)

        self.del_proj_btn = QtWidgets.QPushButton("Delete")
        self.del_proj_btn.setObjectName("lib_btn")
        self.del_proj_btn.setFixedHeight(24)
        self.del_proj_btn.setToolTip("Delete project")
        self.del_proj_btn.clicked.connect(self._delete_project)

        _lbl1 = QtWidgets.QLabel("Project")
        _lbl1.setStyleSheet(
            f"color: {C_TEXT_DIM}; font-size: 9pt; font-weight: bold; "
            "background: transparent;"
        )
        pa_lay.addWidget(_lbl1)
        pa_lay.addSpacing(6)
        pa_lay.addWidget(self.project_combo, 3)   # stretch=3: takes most of the space
        pa_lay.addWidget(self.new_proj_btn)
        pa_lay.addWidget(self.ren_proj_btn)
        pa_lay.addWidget(self.del_proj_btn)
        self._proj_stack.addWidget(page_active)

        main_layout.addWidget(self._proj_stack)

        # -- Top bar: + New Folder left | + Save Pose right --------------
        top_layout = QHBoxLayout()
        top_layout.setSpacing(6)

        self.new_folder_btn = QtWidgets.QPushButton("+  New Folder")
        self.new_folder_btn.setObjectName("action_btn")
        self.new_folder_btn.clicked.connect(self.create_top_folder)

        self.quick_save_btn = QtWidgets.QPushButton("+  Save Pose")
        self.quick_save_btn.setObjectName("action_btn")
        self.quick_save_btn.clicked.connect(self.show_new_pose_form)
        self.quick_save_btn.setToolTip("Save a pose from the selected objects")

        top_layout.addWidget(self.new_folder_btn)
        top_layout.addStretch(1)
        top_layout.addWidget(self.quick_save_btn)
        main_layout.addLayout(top_layout)

        # -- Search bar ------------------------------------------
        self.search_bar = QtWidgets.QLineEdit()
        self.search_bar.setPlaceholderText("Search poses...")
        self.search_bar.setFixedHeight(28)
        self.search_bar.textChanged.connect(self.filter_poses)
        main_layout.addWidget(self.search_bar)

        # -- Splitter --------------------------------------------
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)

        # -- Column 1: Folders -----------------------------------
        self.sidebar = QTreeWidget()
        self.sidebar.setHeaderHidden(True)
        self.sidebar.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.sidebar.customContextMenuRequested.connect(
            lambda pos: self.show_context_menu(pos, True)
        )
        self.sidebar.itemClicked.connect(self.on_folder_selected)
        self.sidebar.mousePressEvent = self.sidebar_mouse_press
        # Dropping poses onto folders
        self.sidebar.setAcceptDrops(True)
        self.sidebar.setDropIndicatorShown(True)
        self.sidebar.dragEnterEvent = self._sidebar_drag_enter
        self.sidebar.dragMoveEvent  = self._sidebar_drag_move
        self.sidebar.dropEvent      = self._sidebar_drop_poses

        folder_panel = QtWidgets.QWidget()
        fl = QVBoxLayout(folder_panel)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(4)
        fl.addWidget(make_section_label("Folders"))
        fl.addWidget(self.sidebar)
        folder_panel.setMinimumWidth(180)
        splitter.addWidget(folder_panel)

        # -- Column 2: Poses -------------------------------------
        self.items_view = QtWidgets.QListWidget()
        self.items_view.setViewMode(QtWidgets.QListView.IconMode)
        self.items_view.setIconSize(QtCore.QSize(THUMB_W, THUMB_H))
        self.items_view.setGridSize(QtCore.QSize(ITEM_W, ITEM_H))
        self.items_view.setResizeMode(QtWidgets.QListWidget.Adjust)
        self.items_view.setSpacing(4)
        self.items_view.setUniformItemSizes(True)
        self.items_view.setWordWrap(True)
        self.items_view.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.items_view.customContextMenuRequested.connect(
            lambda pos: self.show_context_menu(pos, False)
        )
        self.items_view.itemClicked.connect(self.on_pose_selected)
        self.items_view.itemDoubleClicked.connect(self.apply_selected_pose)
        self.items_view.mousePressEvent = self.items_view_mouse_press
        # Drag from the poses panel
        self.items_view.setDragEnabled(True)
        self.items_view.setDragDropMode(QtWidgets.QAbstractItemView.DragOnly)
        self.items_view.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)

        poses_panel = QtWidgets.QWidget()
        pl = QVBoxLayout(poses_panel)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(4)
        pl.addWidget(make_section_label("Poses"))
        pl.addWidget(self.items_view)
        splitter.addWidget(poses_panel)

        # -- Column 3: Details -----------------------------------
        self.preview_panel = QtWidgets.QWidget()
        self.preview_layout = QVBoxLayout(self.preview_panel)
        # No AlignTop: stretch controls the vertical distribution
        self.preview_layout.setSpacing(6)
        self.preview_layout.setContentsMargins(4, 0, 4, 4)

        # Persistent widgets of the right panel
        self.preview_label = QtWidgets.QLabel("No preview")
        self.preview_label.setFixedSize(230, 152)
        self.preview_label.setAlignment(QtCore.Qt.AlignCenter)
        self.preview_label.setStyleSheet(
            f"border:1px solid {C_BORDER}; background-color:{C_BG3}; border-radius:5px;"
        )

        # Load button — below the preview, same style as Library...
        self.load_thumb_btn = QtWidgets.QPushButton("Load image…")
        self.load_thumb_btn.setObjectName("lib_btn")
        self.load_thumb_btn.setFixedHeight(22)
        self.load_thumb_btn.clicked.connect(self.load_thumbnail_for_pose)
        self.load_thumb_btn.setToolTip("Load an image as the pose thumbnail")

        self.info_box = QGroupBox("Pose Info")
        self.info_box.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
        )
        info_layout = QFormLayout(self.info_box)
        info_layout.setSpacing(3)
        info_layout.setContentsMargins(8, 6, 8, 6)
        _info_style = "font-size: 9pt; padding: 1px 4px;"
        self.name_info     = QtWidgets.QLineEdit(); self.name_info.setReadOnly(True); self.name_info.setStyleSheet(_info_style)
        self.owner_info    = QtWidgets.QLineEdit(); self.owner_info.setReadOnly(True); self.owner_info.setStyleSheet(_info_style)
        self.created_info  = QtWidgets.QLineEdit(); self.created_info.setReadOnly(True); self.created_info.setStyleSheet(_info_style)
        self.contains_info = QtWidgets.QLineEdit(); self.contains_info.setReadOnly(True); self.contains_info.setStyleSheet(_info_style)
        self.comment_info  = _CommentEdit()
        # editable — Enter ends editing (does not add a line break)
        self.comment_info.setMinimumHeight(36)
        self.comment_info.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
        )
        self.comment_info.setStyleSheet(_info_style)
        info_layout.addRow("Name:",     self.name_info)
        info_layout.addRow("Owner:",    self.owner_info)
        info_layout.addRow("Created:",  self.created_info)
        info_layout.addRow("Contains:", self.contains_info)
        info_layout.addRow("Comment:",  self.comment_info)

        # Options: Key / Mirror / Additive (larger checkboxes)
        # + Filter T R S
        # + Details button
        self.options_box = QGroupBox("Options")
        opts_v = QVBoxLayout(self.options_box)
        opts_v.setContentsMargins(10, 10, 10, 10)
        opts_v.setSpacing(6)

        def big_check(label):
            cb = QCheckBox(label)
            cb.setStyleSheet(
                f"font-size: 9pt; color: {C_TEXT}; spacing: 7px;"
                f"QCheckBox::indicator {{ width:13px; height:13px; }}"
            )
            return cb

        self.opt_key      = big_check("Key")
        self.opt_mirror   = big_check("Mirror")
        self.opt_additive = big_check("Additive")
        opts_v.addWidget(self.opt_key)
        opts_v.addWidget(self.opt_mirror)
        opts_v.addWidget(self.opt_additive)

        # Thin separator
        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.HLine)
        sep.setStyleSheet(f"color: {C_BORDER}; background: {C_BORDER}; border: none; max-height:1px;")
        opts_v.addWidget(sep)

        # Filter T R S
        filter_lbl = QtWidgets.QLabel("Filter")
        filter_lbl.setStyleSheet(f"color: {C_TEXT_DIM}; font-size: 9pt; font-weight: bold;")
        opts_v.addWidget(filter_lbl)

        trs_row = QHBoxLayout()
        trs_row.setSpacing(12)
        trs_row.setContentsMargins(0, 0, 0, 0)
        self.filter_t = big_check("T")
        self.filter_r = big_check("R")
        self.filter_s = big_check("S")
        self.filter_t.setChecked(True)
        self.filter_r.setChecked(True)
        self.filter_s.setChecked(True)
        trs_row.addWidget(self.filter_t)
        trs_row.addWidget(self.filter_r)
        trs_row.addWidget(self.filter_s)
        trs_row.addStretch(1)
        opts_v.addLayout(trs_row)

        self.apply_btn = QtWidgets.QPushButton("Apply Pose")
        self.apply_btn.setObjectName("apply_btn")
        self.apply_btn.setMinimumHeight(34)
        self.apply_btn.clicked.connect(self.apply_selected_pose)

        # Details button (opens a window with the object list)
        self.details_btn = QtWidgets.QPushButton("Details")
        self.details_btn.setObjectName("details_btn")
        self.details_btn.setFixedHeight(26)
        self.details_btn.clicked.connect(self.show_pose_details)

        self._build_default_preview_panel()

        details_wrapper = QtWidgets.QWidget()
        dw_layout = QVBoxLayout(details_wrapper)
        dw_layout.setContentsMargins(0, 0, 0, 0)
        dw_layout.setSpacing(4)
        dw_layout.addWidget(make_section_label("Details"))
        dw_layout.addWidget(self.preview_panel)
        details_wrapper.setMinimumWidth(280)

        splitter.addWidget(details_wrapper)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setStretchFactor(2, 2)
        splitter.setSizes([220, 620, 360])

        main_layout.addWidget(splitter, 1)

        # -- Status bar + Library on the right -------------------
        status_layout = QHBoxLayout()
        status_layout.setContentsMargins(4, 0, 6, 0)
        status_layout.setSpacing(14)

        self.status_bar = QtWidgets.QStatusBar()
        self.status_bar.showMessage("Ready")
        self.status_bar.setSizeGripEnabled(False)

        self.library_label = QtWidgets.QLabel("No library selected")
        self.library_label.setStyleSheet(
            f"color: {C_TEXT_DIM}; font-size: 9pt; background: transparent;"
        )

        self.load_library_btn = QtWidgets.QPushButton("Library…")
        self.load_library_btn.setObjectName("lib_btn")
        self.load_library_btn.clicked.connect(self.select_library_folder)

        status_layout.addWidget(self.status_bar, 1)
        status_layout.addWidget(self.library_label)
        status_layout.addWidget(self.load_library_btn)
        main_layout.addLayout(status_layout)

        self.apply_style()

        state = load_state()
        if state["library_path"] and os.path.isdir(state["library_path"]):
            self._load_library(state["library_path"],
                               restore_project=state["current_project"])

    # ---------------------------------------------
    #  Right panel
    # ---------------------------------------------

    def _clear_preview_layout(self):
        """
        Removes all items from preview_layout (widgets AND sub-layouts).
        - Persistent widgets: taken out of the layout with setParent(None).
        - Temporary widgets: destroyed with deleteLater().
        - Sub-layouts (e.g. the Save/Cancel QHBoxLayout): emptied
          recursively and destroyed — otherwise they are left floating
          behind the panel.
        """
        persistent = {
            self.preview_label, self.load_thumb_btn, self.info_box,
            self.options_box, self.apply_btn, self.details_btn
        }

        def _purge_layout(layout):
            while layout.count():
                child = layout.takeAt(0)
                w = child.widget()
                sub = child.layout()
                if w:
                    if w in persistent:
                        w.setParent(None)
                    else:
                        w.hide()
                        w.deleteLater()
                elif sub:
                    _purge_layout(sub)

        _purge_layout(self.preview_layout)

    def _build_default_preview_panel(self):
        self._clear_preview_layout()
        # Fixed at top: preview + thumb buttons + info (info grows with stretch)
        self.preview_layout.addWidget(self.preview_label, 0, QtCore.Qt.AlignHCenter)
        self.preview_layout.addWidget(self._make_thumb_btn_row())
        self.preview_layout.addWidget(self.info_box, 1)   # stretch=1: info_box absorbs free space
        # Fixed at bottom: options + buttons
        self.preview_layout.addWidget(self.options_box)
        self.preview_layout.addWidget(self.apply_btn)
        self.preview_layout.addWidget(self.details_btn)

    def _make_thumb_btn_row(self):
        """Row with Load Image + Generate Thumbnail for the Details panel."""
        c = QtWidgets.QWidget()
        row = QHBoxLayout(c)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        gt = QtWidgets.QPushButton("Generate Thumbnail")
        gt.setObjectName("lib_btn")
        gt.setFixedHeight(22)
        gt.clicked.connect(self._generate_thumbnail_for_existing_pose)
        li = QtWidgets.QPushButton("Load Image…")
        li.setObjectName("lib_btn")
        li.setFixedHeight(22)
        li.clicked.connect(self.load_thumbnail_for_pose)
        row.addWidget(gt)
        row.addWidget(li)
        return c

    def reset_preview_panel(self):
        self._build_default_preview_panel()
        self.preview_label.clear()
        self.preview_label.setText("Preview")
        self.name_info.clear()
        self.owner_info.clear()
        self.created_info.clear()
        self.contains_info.clear()
        self.comment_info.clear()
        self.current_pose_path  = None
        self._current_pose_nodes = []

    # ---------------------------------------------
    #  Style
    # ---------------------------------------------

    def apply_style(self):
        self.setStyleSheet(f"""
            #StudioLibMax {{
                background-color: {C_BG};
                color: {C_TEXT};
                font-family: "Segoe UI", "Arial", sans-serif;
                font-size: 11pt;
            }}
            QWidget {{
                background-color: {C_BG};
                color: {C_TEXT};
            }}
            QGroupBox {{
                margin-top: 12px;
                border: 1px solid {C_BORDER};
                border-radius: 6px;
                padding: 14px 10px 10px 10px;
                background-color: {C_BG2};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 6px;
                color: {C_TEXT_DIM};
                font-weight: bold;
                font-size: 9pt;
                letter-spacing: 0.5px;
            }}
            QPushButton {{
                background-color: {C_BTN};
                color: {C_TEXT};
                border: 1px solid {C_BORDER};
                padding: 5px 14px;
                border-radius: 5px;
                font-size: 9.5pt;
            }}
            QPushButton:hover {{
                background-color: {C_BTN_HO};
                border-color: {C_BORDER_HI};
            }}
            QPushButton:pressed {{
                background-color: {C_BG};
            }}
            QPushButton#action_btn {{
                background-color: {C_ACCENT_BG};
                border: 1px solid {C_ACCENT_BO};
                color: {C_ACCENT_TX};
                font-weight: bold;
                font-size: 9.5pt;
                padding: 5px 14px;
            }}
            QPushButton#action_btn:hover {{
                background-color: {C_ACCENT_HO};
                border-color: #606060;
                color: #EFEFEF;
            }}
            QPushButton#apply_btn {{
                background-color: {C_ACCENT_BG};
                border: 1px solid {C_ACCENT_BO};
                color: {C_ACCENT_TX};
                font-weight: bold;
                font-size: 9.5pt;
            }}
            QPushButton#apply_btn:hover {{
                background-color: {C_ACCENT_HO};
                border-color: #606060;
                color: #EFEFEF;
            }}
            QPushButton#details_btn {{
                background-color: transparent;
                border: 1px solid {C_BORDER};
                color: {C_TEXT_DIM};
                font-size: 9pt;
                padding: 3px 10px;
                border-radius: 4px;
                text-align: center;
            }}
            QPushButton#details_btn:hover {{
                border-color: {C_BORDER_HI};
                color: {C_TEXT};
            }}
            QPushButton#load_thumb_btn {{
                background-color: rgba(30,30,30,210);
                border: 1px solid {C_BORDER_HI};
                color: {C_TEXT_DIM};
                font-size: 8pt;
                border-radius: 3px;
                padding: 1px 4px;
            }}
            QPushButton#load_thumb_btn:hover {{
                background-color: rgba(50,50,50,230);
                color: {C_TEXT};
            }}
            QPushButton#lib_btn {{
                background-color: {C_BG};
                border: 1px solid {C_BORDER};
                color: {C_TEXT_DIM};
                font-size: 8.5pt;
                padding: 3px 10px;
                border-radius: 4px;
            }}
            QPushButton#lib_btn:hover {{
                border-color: {C_BORDER_HI};
                color: {C_TEXT};
            }}
            QLineEdit, QPlainTextEdit {{
                background-color: {C_BG3};
                color: {C_TEXT};
                border: 1px solid {C_BORDER};
                padding: 4px 7px;
                border-radius: 4px;
                selection-background-color: #444444;
                font-size: {FORM_TEXT_PT}pt;
            }}
            QLineEdit:focus, QPlainTextEdit:focus {{
                border-color: {C_BORDER_HI};
            }}
            QTreeWidget {{
                background-color: {C_BG3};
                color: {C_TEXT};
                border: 1px solid {C_BORDER};
                border-radius: 5px;
                outline: none;
                font-size: 9pt;
            }}
            QTreeWidget::item {{
                height: 26px;
                padding-left: 4px;
                border-radius: 3px;
            }}
            QTreeWidget::item:hover   {{ background-color: {C_BTN}; }}
            QTreeWidget::item:selected {{ background-color: {C_SEL_BG}; color: {C_SEL_TEXT}; }}
            QTreeWidget::branch       {{ background-color: {C_BG3}; }}
            QListWidget {{
                background-color: {C_BG3};
                color: {C_TEXT};
                border: 1px solid {C_BORDER};
                border-radius: 5px;
                show-decoration-selected: 1;
                outline: none;
            }}
            QListWidget::item {{
                border-radius: 4px;
                padding: 2px;
                color: {C_TEXT};
                font-size: {POSE_NAME_PT}pt;
                margin: 1px;
            }}
            QListWidget::item:selected {{
                background-color: {C_SEL_BG};
                color: {C_SEL_TEXT};
                border: 1px solid {C_BORDER_HI};
            }}
            QListWidget::item:hover {{ background-color: {C_BTN}; }}
            QStatusBar {{
                background-color: {C_STATUS};
                color: {C_TEXT_DIM};
                border-top: 1px solid {C_BORDER};
                font-size: 9pt;
            }}
            QCheckBox {{
                color: {C_TEXT};
                font-size: 11pt;
                spacing: 10px;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border: 1px solid {C_BORDER_HI};
                border-radius: 3px;
                background-color: {C_BG3};
            }}
            QCheckBox::indicator:checked {{
                background-color: {C_BORDER_HI};
                border-color: #888888;
            }}
            QMenu {{
                background-color: {C_BG2};
                color: {C_TEXT};
                border: 1px solid {C_BORDER};
                border-radius: 5px;
                font-size: 10pt;
                padding: 4px 0px;
            }}
            QMenu::item {{
                padding: 6px 28px 6px 16px;
                border-radius: 3px;
                margin: 2px 4px;
            }}
            QMenu::item:selected {{ background-color: {C_SEL_BG}; }}
            QMenu::separator {{
                height: 1px;
                background: {C_BORDER};
                margin: 4px 8px;
            }}
            QSplitter::handle {{ background-color: {C_BORDER}; width: 1px; }}
            QSplitter         {{ background-color: {C_BG}; }}
            QScrollBar:vertical {{
                background: {C_BG3}; width: 7px; border-radius: 3px;
            }}
            QScrollBar::handle:vertical {{
                background: {C_BORDER_HI}; border-radius: 3px; min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{ background: #606060; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
            QScrollBar:horizontal {{
                background: {C_BG3}; height: 7px; border-radius: 3px;
            }}
            QScrollBar::handle:horizontal {{
                background: {C_BORDER_HI}; border-radius: 3px; min-width: 20px;
            }}
            QScrollBar::handle:horizontal:hover {{ background: #606060; }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0px; }}
            QLabel {{ color: {C_TEXT}; background-color: transparent; }}
            QPushButton#new_proj_btn {{
                background-color: #1A3A4A;
                border: 1px solid #2A6E8A;
                color: #7EC8E3;
                font-weight: bold;
                font-size: 9.5pt;
                padding: 5px 14px;
                border-radius: 5px;
            }}
            QPushButton#new_proj_btn:hover {{
                background-color: #1F4D63;
                border-color: #3A9EC0;
                color: #A8DCEF;
            }}
        """)

    # ---------------------------------------------
    #  Library
    # ---------------------------------------------

    def select_library_folder(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Select library folder")
        if folder:
            self._load_library(folder)

    def _load_library(self, folder, restore_project=""):
        self.library_path = folder
        config_dir = os.path.join(folder, ".studiolibrarymax")
        os.makedirs(config_dir, exist_ok=True)
        self.color_config_path = os.path.join(config_dir, "folder_colors.json")
        try:
            with open(self.color_config_path, "r", encoding="utf-8") as f:
                self.folder_colors = json.load(f)
        except Exception:
            self.folder_colors = {}
        short = folder if len(folder) <= 70 else "..." + folder[-67:]
        self.library_label.setText(short)
        self.library_label.setToolTip(folder)
        self._refresh_project_combo(restore_project)
        save_state(folder, self.current_project or "")
        self.status_bar.showMessage(f"Library loaded: {folder}")

    def _refresh_project_combo(self, select_project=""):
        """
        Reloads the combo with the projects (library subfolders).
        No projects  → shows page 0 (highlighted New Project button).
        Has projects → shows page 1 (combo + buttons).
        Projects are ONLY direct subfolders of the library that do NOT
        contain poses directly (they are folder containers).
        """
        self.project_combo.blockSignals(True)
        self.project_combo.clear()

        if not self.library_path or not os.path.isdir(self.library_path):
            self.project_combo.blockSignals(False)
            self._proj_stack.setCurrentIndex(0)
            return

        projects = sorted(
            nm for nm in os.listdir(self.library_path)
            if not nm.startswith(".")
            and os.path.isdir(os.path.join(self.library_path, nm))
        )

        if not projects:
            # No projects — show highlighted button
            self.project_combo.blockSignals(False)
            self._proj_stack.setCurrentIndex(0)
            self.current_project = None
            self.populate_sidebar()
            return

        # Has projects — show combo
        self._proj_stack.setCurrentIndex(1)
        for nm in projects:
            self.project_combo.addItem(nm, os.path.join(self.library_path, nm))

        # Select the saved project, or the first one
        idx = 0
        if select_project:
            for i in range(self.project_combo.count()):
                if self.project_combo.itemData(i) == select_project:
                    idx = i
                    break
        self.project_combo.setCurrentIndex(idx)
        self.project_combo.blockSignals(False)
        self._on_project_changed(idx)

    def _on_project_changed(self, index):
        """Switches the active project and reloads the sidebar."""
        proj_path = self.project_combo.itemData(index) if index >= 0 else ""
        self.current_project = proj_path or None
        # The sidebar shows the folders of the active project (or the library root)
        self.populate_sidebar()
        save_state(self.library_path or "", self.current_project or "")

    def _new_project(self):
        """Creates a new project subfolder in the library."""
        if not self.library_path:
            QtWidgets.QMessageBox.warning(self, "Warning", "Select a library first.")
            return
        name, ok = QtWidgets.QInputDialog.getText(self, "New Project", "Project name:")
        if not ok or not name.strip():
            return
        path = os.path.join(self.library_path, name.strip().upper())
        if os.path.exists(path):
            QtWidgets.QMessageBox.warning(self, "Warning", "Project already exists.")
            return
        os.makedirs(path)
        self._refresh_project_combo(path)

    def _rename_project(self):
        """Renames the active project."""
        if not self.current_project:
            QtWidgets.QMessageBox.warning(self, "Warning", "Select a project first.")
            return
        old_name = os.path.basename(self.current_project)
        new_name, ok = QtWidgets.QInputDialog.getText(
            self, "Rename Project", "New name:", text=old_name
        )
        if not ok or not new_name.strip() or new_name == old_name:
            return
        new_path = os.path.join(self.library_path, new_name.strip().upper())
        if os.path.exists(new_path):
            QtWidgets.QMessageBox.warning(self, "Warning", "Name already taken.")
            return
        os.rename(self.current_project, new_path)
        self._refresh_project_combo(new_path)

    def _delete_project(self):
        """Deletes the active project after confirmation."""
        if not self.current_project:
            QtWidgets.QMessageBox.warning(self, "Warning", "Select a project first.")
            return
        name = os.path.basename(self.current_project)
        reply = QtWidgets.QMessageBox.question(
            self, "Delete Project",
            f"Delete project '{name}' and ALL its contents?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )
        if reply != QtWidgets.QMessageBox.Yes:
            return
        shutil.rmtree(self.current_project)
        self.current_project = None
        self._refresh_project_combo("")

    def populate_sidebar(self):
        self.sidebar.clear()
        self.items_view.clear()
        self.reset_preview_panel()
        # Only show folders if there is an active project
        # Never use the library root directly (avoids mixing projects/folders)
        if not self.current_project or not os.path.isdir(self.current_project):
            return
        for name in sorted(os.listdir(self.current_project)):
            if name.startswith("."):
                continue
            full = os.path.join(self.current_project, name)
            if os.path.isdir(full) and not full.endswith(".pose"):
                item = QTreeWidgetItem(self.sidebar, [name])
                item.setData(0, QtCore.Qt.UserRole, full)
                color = self.folder_colors.get(full, "#606060")
                item.setIcon(0, self.create_color_icon(QtGui.QColor(color)))
                self.populate_tree(full, item)

    def populate_tree(self, path, parent_item):
        for nm in sorted(os.listdir(path)):
            if nm.startswith(".") or nm.endswith(".pose"):
                continue
            fp = os.path.join(path, nm)
            if os.path.isdir(fp):
                it = QTreeWidgetItem(parent_item, [nm])
                it.setData(0, QtCore.Qt.UserRole, fp)
                col = self.folder_colors.get(fp, "#606060")
                it.setIcon(0, self.create_color_icon(QtGui.QColor(col)))
                self.populate_tree(fp, it)

    def save_folder_colors(self):
        if self.color_config_path:
            with open(self.color_config_path, "w", encoding="utf-8") as f:
                json.dump(self.folder_colors, f, indent=4)

    # ---------------------------------------------
    #  Sidebar
    # ---------------------------------------------

    def sidebar_mouse_press(self, event):
        pos  = event.position().toPoint()
        item = self.sidebar.itemAt(pos)
        if not item:
            self.sidebar.clearSelection()
            self.current_folder_path = None
            self.items_view.clear()
            self.reset_preview_panel()
            self.status_bar.showMessage("No folder selected")
        QTreeWidget.mousePressEvent(self.sidebar, event)

    def on_folder_selected(self, item, column):
        self.current_folder_path = item.data(0, QtCore.Qt.UserRole)
        self.load_poses_from_folder(self.current_folder_path)

    def load_poses_from_folder(self, folder):
        self.items_view.clear()
        self.reset_preview_panel()
        if not folder or not os.path.isdir(folder):
            return
        count = 0
        for nm in sorted(os.listdir(folder)):
            if not nm.endswith(".pose"):
                continue
            fp      = os.path.join(folder, nm)
            prev    = os.path.join(fp, "preview.png")
            label   = nm[:-5]
            icon    = make_pose_icon(prev)
            lw_item = QListWidgetItem(icon, label)
            lw_item.setData(QtCore.Qt.UserRole, nm)
            lw_item.setTextAlignment(QtCore.Qt.AlignHCenter | QtCore.Qt.AlignBottom)
            lw_item.setSizeHint(QtCore.QSize(ITEM_W, ITEM_H))
            self.items_view.addItem(lw_item)
            count += 1
        self.status_bar.showMessage(
            f"{count} pose{'s' if count != 1 else ''} in folder"
        )

    def filter_poses(self, text):
        for i in range(self.items_view.count()):
            it = self.items_view.item(i)
            it.setHidden(text.lower() not in it.text().lower())

    # ---------------------------------------------
    #  Pose selection
    # ---------------------------------------------

    def on_pose_selected(self, item):
        real_name = item.data(QtCore.Qt.UserRole)
        self.current_pose_path  = os.path.join(self.current_folder_path, real_name)
        self._current_pose_nodes = []
        self._build_default_preview_panel()

        prev = os.path.join(self.current_pose_path, "preview.png")
        if os.path.exists(prev):
            pix = QtGui.QPixmap(prev).scaled(
                230, 188, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation
            )
            self.preview_label.setPixmap(pix)
        else:
            self.preview_label.clear()
            self.preview_label.setText("No preview")

        md_file = os.path.join(self.current_pose_path, "pose_data.json")
        if os.path.exists(md_file):
            try:
                with open(md_file, "r", encoding="utf-8") as f:
                    d = json.load(f)
                m = d.get("metadata", {})
                self.name_info.setText(m.get("name", ""))
                self.owner_info.setText(m.get("owner", ""))
                created = m.get("created", "")
                try:
                    dt  = datetime.strptime(created, "%Y-%m-%d %H:%M:%S")
                    s   = int((datetime.now() - dt).total_seconds())
                    if s < 60:     txt = f"{s}s ago"
                    elif s < 3600: txt = f"{s//60}m ago"
                    elif s < 86400:txt = f"{s//3600}h ago"
                    else:          txt = f"{s//86400}d ago"
                    self.created_info.setText(txt)
                except Exception:
                    self.created_info.setText(created)
                contains = m.get("contains", "")
                cnt = len(contains.split(",")) if contains else 0
                self.contains_info.setText(f"{cnt} object{'s' if cnt != 1 else ''}")
                self.comment_info.setPlainText(m.get("comment", ""))
                # Hook up auto-save when the comment is edited
                try:
                    self.comment_info.textChanged.disconnect()
                except Exception:
                    pass
                self.comment_info.textChanged.connect(self._save_comment)
                # Store node list for Details
                nodes_data = d.get("nodes", [])
                self._current_pose_nodes = [nd["name"] for nd in nodes_data]
            except Exception as e:
                self.status_bar.showMessage(f"Error loading info: {e}")

    def items_view_mouse_press(self, event):
        pos  = event.position().toPoint()
        item = self.items_view.itemAt(pos)
        if not item:
            self.items_view.clearSelection()
            self.reset_preview_panel()
        QtWidgets.QListWidget.mousePressEvent(self.items_view, event)

    # ---------------------------------------------
    #  Pose DETAILS (floating window)
    # ---------------------------------------------

    def show_pose_details(self):
        if not self.current_pose_path:
            QtWidgets.QMessageBox.information(self, "Details", "No pose selected.")
            return
        pose_name = os.path.basename(self.current_pose_path).replace(".pose", "")
        dlg = PoseDetailsDialog(self.current_pose_path, pose_name, self._current_pose_nodes, parent=self)
        dlg.exec()

    # ---------------------------------------------
    #  APPLY POSE
    # ---------------------------------------------

    def apply_selected_pose(self):
        if not self.current_pose_path:
            QtWidgets.QMessageBox.warning(self, "Warning", "No pose selected.")
            return
        json_file = os.path.join(self.current_pose_path, "pose_data.json")
        if not os.path.exists(json_file):
            QtWidgets.QMessageBox.critical(self, "Error", "pose_data.json not found.")
            return

        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        nodes_data = data.get("nodes", [])
        if not nodes_data:
            self.status_bar.showMessage("Pose has no node data.")
            return

        do_key      = self.opt_key.isChecked()
        do_mirror   = self.opt_mirror.isChecked()
        do_additive = self.opt_additive.isChecked()
        do_pos      = self.filter_t.isChecked()
        do_rot      = self.filter_r.isChecked()
        do_scale    = self.filter_s.isChecked()

        applied = 0
        missing = []
        # NOTE: suspendEditing() blocks animate on — NOT used when key=True
        if not do_key:
            rt.suspendEditing()
        try:
            for nd in nodes_data:
                obj = rt.getNodeByName(nd["name"])
                if obj is None:
                    missing.append(nd["name"])
                    continue
                apply_node_transform(
                    obj,
                    nd.get("position", [0, 0, 0]),
                    nd.get("rotation", [0, 0, 0, 1]),
                    nd.get("scale",    [1, 1, 1]),
                    mirror=do_mirror,
                    additive=do_additive,
                    key=do_key,
                    do_pos=do_pos,
                    do_rot=do_rot,
                    do_scale=do_scale,
                )
                applied += 1
        finally:
            if not do_key:
                rt.resumeEditing()
            rt.redrawViews()

        msg = f"Pose applied: {applied} object(s)"
        if missing:
            msg += f"  |  Not found: {', '.join(missing)}"
        if do_key:
            msg += "  |  Keys set"
        self.status_bar.showMessage(msg)

    # ---------------------------------------------
    #  SAVE POSE
    # ---------------------------------------------

    def show_new_pose_form(self):
        if not self.current_folder_path:
            QtWidgets.QMessageBox.warning(self, "Warning", "Select a folder first.")
            return

        self._clear_preview_layout()
        self._tmp_thumb_path = None

        # -- Thumbnail preview -------------------------------------
        self.new_pose_preview_label = QtWidgets.QLabel("No thumbnail")
        # Square: width = height. Updated in resizeEvent if needed.
        self.new_pose_preview_label.setMinimumHeight(THUMB_W)
        self.new_pose_preview_label.setMaximumHeight(THUMB_W)
        self.new_pose_preview_label.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )
        self.new_pose_preview_label.setAlignment(QtCore.Qt.AlignCenter)
        self.new_pose_preview_label.setStyleSheet(
            f"border:1px solid {C_BORDER}; background-color:{C_BG3}; border-radius:5px;"
        )
        self.preview_layout.addWidget(self.new_pose_preview_label)

        # Two buttons below the preview — same lib_btn style
        thumb_btns = QtWidgets.QWidget()
        thumb_btns_row = QHBoxLayout(thumb_btns)
        thumb_btns_row.setContentsMargins(0, 0, 0, 0)
        thumb_btns_row.setSpacing(6)
        self.gen_thumb_btn = QtWidgets.QPushButton("Generate Thumbnail")
        self.gen_thumb_btn.setObjectName("lib_btn")
        self.gen_thumb_btn.setFixedHeight(22)
        self.gen_thumb_btn.clicked.connect(self.generate_thumbnail)
        load_img_btn = QtWidgets.QPushButton("Load Image…")
        load_img_btn.setObjectName("lib_btn")
        load_img_btn.setFixedHeight(22)
        load_img_btn.clicked.connect(self._load_image_for_new_pose)
        thumb_btns_row.addWidget(self.gen_thumb_btn)
        thumb_btns_row.addWidget(load_img_btn)
        self.preview_layout.addWidget(thumb_btns)

        # -- Form — layout that stretches with the window ---------
        # The container takes all remaining vertical space
        form_outer = QtWidgets.QWidget()
        form_outer.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
        )
        form_outer.setStyleSheet(
            f"QWidget#form_outer {{ background: {C_BG2}; border: 1px solid {C_BORDER}; border-radius: 5px; }}"
            f"QLabel {{ background: transparent; border: none; }}"
            f"QLineEdit {{ border: 1px solid {C_BORDER}; border-radius: 3px; background: {C_BG3}; }}"
            f"QPlainTextEdit {{ border: 1px solid {C_BORDER}; border-radius: 3px; background: {C_BG3}; }}"
        )
        form_outer.setObjectName("form_outer")
        form_lay = QVBoxLayout(form_outer)
        form_lay.setContentsMargins(8, 6, 8, 8)
        form_lay.setSpacing(0)

        # "New Pose" at the top
        title_lbl = QtWidgets.QLabel("New Pose")
        title_lbl.setStyleSheet(
            f"color: {C_TEXT_DIM}; font-size: 9pt; font-weight: bold; "
            "letter-spacing: 0.5px;"
        )
        form_lay.addWidget(title_lbl)
        form_lay.addSpacing(18)   # ~2 lines of visual space

        # Name label + input — fixed height, does not grow
        form_lay.addWidget(make_field_label("Name"))
        self.new_pose_name = QtWidgets.QLineEdit()
        self.new_pose_name.setFixedHeight(40)
        self.new_pose_name.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )
        self.new_pose_name.setStyleSheet(
            f"font-size: {FORM_TEXT_PT}pt; padding: 4px 6px;"
        )
        self.new_pose_name.returnPressed.connect(self.save_new_pose)
        form_lay.addWidget(self.new_pose_name)   # no stretch

        # 3 visual lines of fixed space between Name and Comment
        form_lay.addSpacing(27)

        # Comment label + input — THIS is the one that grows with the window
        form_lay.addWidget(make_field_label("Comment"))
        self.new_pose_comment = QtWidgets.QPlainTextEdit()
        self.new_pose_comment.setMinimumHeight(36)
        self.new_pose_comment.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
        )
        self.new_pose_comment.setStyleSheet(
            f"font-size: {FORM_TEXT_PT}pt;"
        )
        form_lay.addWidget(self.new_pose_comment, 1)   # stretch=1: grows with the window

        self.preview_layout.addWidget(form_outer, 1)   # stretch=1: the form takes the free space

        # -- Save / Cancel buttons ---------------------------------
        btn_container = QtWidgets.QWidget()
        btn_row = QHBoxLayout(btn_container)
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(6)
        save_btn   = QtWidgets.QPushButton("Save Pose")
        save_btn.setObjectName("apply_btn")
        cancel_btn = QtWidgets.QPushButton("Cancel")
        save_btn.clicked.connect(self.save_new_pose)
        cancel_btn.clicked.connect(self.reset_preview_panel)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(cancel_btn)
        self.preview_layout.addWidget(btn_container)

    def _load_image_for_new_pose(self):
        """Loads an image for the New Pose form thumbnail (before saving)."""
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select thumbnail image", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.tga *.tif *.tiff)"
        )
        if not path:
            return
        pix = QtGui.QPixmap(path)
        if pix.isNull():
            self.status_bar.showMessage("Invalid image.")
            return
        pix_s = pix.scaled(THUMB_W, THUMB_H, QtCore.Qt.KeepAspectRatioByExpanding,
                            QtCore.Qt.SmoothTransformation)
        ox = (pix_s.width()  - THUMB_W) // 2
        oy = (pix_s.height() - THUMB_H) // 2
        pix_crop = pix_s.copy(ox, oy, THUMB_W, THUMB_H)
        import tempfile, os as _os
        tmp = _os.path.join(tempfile.gettempdir(), "_slmax_loadimg.png")
        pix_crop.save(tmp, "PNG")
        self._tmp_thumb_path = tmp
        w = self.new_pose_preview_label.width() or THUMB_W
        h = self.new_pose_preview_label.height() or THUMB_H
        self.new_pose_preview_label.setPixmap(
            pix_crop.scaled(w, h, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        )
        self.status_bar.showMessage("Image loaded OK.")

    def _generate_thumbnail_for_existing_pose(self):
        """Generates and replaces the thumbnail of an already saved pose."""
        if not self.current_pose_path:
            self.status_bar.showMessage("Select a pose first.")
            return
        out_path = os.path.join(self.current_pose_path, "preview.png")
        if os.path.exists(out_path):
            try: os.remove(out_path)
            except Exception: pass
        ok = capture_viewport_to_file(out_path)
        if ok and os.path.exists(out_path):
            pix = QtGui.QPixmap(out_path)
            w = self.preview_label.width() or 230
            h = int(w * 3 / 4)
            self.preview_label.setFixedHeight(h)
            self.preview_label.setPixmap(
                pix.scaled(w, h, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
            )
            self.load_poses_from_folder(self.current_folder_path)
            self.status_bar.showMessage("Thumbnail replaced OK.")
        else:
            self.status_bar.showMessage("Could not capture the viewport.")

    def load_thumbnail_for_pose(self):
        """Loads an external image as the thumbnail of the selected pose."""
        if not self.current_pose_path:
            self.status_bar.showMessage("Load thumbnail: select a pose first.")
            return
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select thumbnail image", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.tga *.tif *.tiff)"
        )
        if not path:
            return
        dst = os.path.join(self.current_pose_path, "preview.png")
        try:
            pix = QtGui.QPixmap(path)
            if pix.isNull():
                self.status_bar.showMessage("Load thumbnail: invalid image.")
                return
            pix_scaled = pix.scaled(THUMB_W, THUMB_H, QtCore.Qt.KeepAspectRatioByExpanding,
                                    QtCore.Qt.SmoothTransformation)
            ox = (pix_scaled.width()  - THUMB_W) // 2
            oy = (pix_scaled.height() - THUMB_H) // 2
            pix_crop = pix_scaled.copy(ox, oy, THUMB_W, THUMB_H)
            pix_crop.save(dst, "PNG")
            # Update preview immediately
            pix_show = pix_crop.scaled(230, 188, QtCore.Qt.KeepAspectRatio,
                                       QtCore.Qt.SmoothTransformation)
            self.preview_label.setPixmap(pix_show)
            # Reload the grid to show the new thumb
            self.load_poses_from_folder(self.current_folder_path)
            self.status_bar.showMessage("Thumbnail loaded OK.")
        except Exception as e:
            self.status_bar.showMessage(f"Load thumbnail error: {e}")

    def generate_thumbnail(self):
        """
        Captures the active viewport:
        1. Zoom extents on the selected object (centers the camera).
        2. Enables solid shading (no background gradient).
        3. Captures with gw.getViewportDib().
        4. Restores the viewport state.
        """
        if not self.library_path:
            self.status_bar.showMessage("Thumbnail: select a library first.")
            return

        out_path = os.path.join(self.library_path, "_thumb_preview.png")
        if os.path.exists(out_path):
            try:
                os.remove(out_path)
            except Exception:
                pass

        # 1. Zoom to the selected object and solid background
        # Store the gradient state to restore it afterwards
        rt.execute("(viewport.setRenderLevel #smoothhighlights)")
        try:
            # Disable the viewport background gradient
            rt.execute(
                "( local vc = viewport.getCamera() ; "
                "  IDisplayGamma.displayGamma = 1.0 ;"
                "  if selection.count > 0 do "
                "    max zoomext sel all )"
            )
        except Exception:
            pass

        ok = capture_viewport_to_file(out_path)

        if not ok or not os.path.exists(out_path):
            self.status_bar.showMessage(
                "Thumbnail: capture failed. Check MAX 2010+."
            )
            return

        self._tmp_thumb_path = out_path
        w = self.new_pose_preview_label.width() or 230
        h = self.new_pose_preview_label.height() or 152
        pix = QtGui.QPixmap(out_path).scaled(
            w, h, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation
        )
        self.new_pose_preview_label.setPixmap(pix)
        self.status_bar.showMessage("Thumbnail captured OK.")

    def save_new_pose(self):
        if not self.current_folder_path:
            QtWidgets.QMessageBox.warning(self, "Warning", "Select a folder first.")
            return
        if rt.selection.count == 0:
            QtWidgets.QMessageBox.warning(self, "Warning", "Select at least one object.")
            return
        name = self.new_pose_name.text().strip()
        if not name:
            QtWidgets.QMessageBox.warning(self, "Warning", "Pose name cannot be empty.")
            return
        comment = self.new_pose_comment.toPlainText().strip()

        target = os.path.join(self.current_folder_path, f"{name}.pose")
        if os.path.exists(target):
            QtWidgets.QMessageBox.warning(self, "Warning", f"Pose '{name}' already exists.")
            return
        os.makedirs(target)

        nodes    = list(rt.selection)
        contains = ",".join(n.name for n in nodes)
        metadata = {
            "name":     name,
            "owner":    getpass.getuser(),
            "created":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "contains": contains,
            "comment":  comment,
        }
        node_data = [{
            "name":     node.name,
            "position": [node.pos.x,   node.pos.y,   node.pos.z],
            "rotation": quat_to_list(node.rotation),
            "scale":    [node.scale.x,  node.scale.y,  node.scale.z],
        } for node in nodes]

        with open(os.path.join(target, "pose_data.json"), "w", encoding="utf-8") as f:
            json.dump({"metadata": metadata, "nodes": node_data}, f, indent=4)

        thumb_dst = os.path.join(target, "preview.png")
        if self._tmp_thumb_path and os.path.exists(self._tmp_thumb_path):
            shutil.copy2(self._tmp_thumb_path, thumb_dst)

        self._clear_preview_layout()  # clears the Save Pose form before reloading
        self.load_poses_from_folder(self.current_folder_path)
        self.status_bar.showMessage(f"Pose '{name}' saved.")
        for i in range(self.items_view.count()):
            it = self.items_view.item(i)
            if it.data(QtCore.Qt.UserRole) == f"{name}.pose":
                self.items_view.setCurrentItem(it)
                self.on_pose_selected(it)
                break

    # ---------------------------------------------
    #  Context menus
    # ---------------------------------------------

    # ---------------------------------------------
    #  Drag & Drop — poses → sidebar folder
    # ---------------------------------------------

    def _sidebar_drag_enter(self, event):
        if event.mimeData().hasFormat("application/x-qabstractitemmodeldatalist"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def _sidebar_drag_move(self, event):
        item = self.sidebar.itemAt(event.position().toPoint())
        if item:
            self.sidebar.setCurrentItem(item)   # highlights the target folder
            event.acceptProposedAction()
        else:
            event.ignore()

    def _sidebar_drop_poses(self, event):
        """Moves the selected poses to the folder they were dropped on."""
        target_item = self.sidebar.itemAt(event.position().toPoint())
        if not target_item:
            event.ignore()
            return
        target_folder = target_item.data(0, QtCore.Qt.UserRole)
        if not target_folder or not os.path.isdir(target_folder):
            event.ignore()
            return
        if not self.current_folder_path or target_folder == self.current_folder_path:
            event.ignore()
            return
        selected = self.items_view.selectedItems()
        if not selected:
            event.ignore()
            return
        moved = 0
        for it in selected:
            real_name = it.data(QtCore.Qt.UserRole)
            src = os.path.join(self.current_folder_path, real_name)
            dst = os.path.join(target_folder, real_name)
            if not os.path.exists(src):
                continue
            if os.path.exists(dst):
                base = real_name[:-5]
                dst = os.path.join(target_folder, f"{base}_moved.pose")
            try:
                shutil.move(src, dst)
                moved += 1
            except Exception as e:
                print(f"[drag drop] {real_name}: {e}")
        if moved:
            self.load_poses_from_folder(self.current_folder_path)
            tgt_name = os.path.basename(target_folder)
            self.status_bar.showMessage(
                f"{moved} pose(s) moved to '{tgt_name}'."
            )
        event.acceptProposedAction()

    def _save_comment(self):
        """Saves the edited comment directly to pose_data.json."""
        if not self.current_pose_path:
            return
        json_file = os.path.join(self.current_pose_path, "pose_data.json")
        if not os.path.exists(json_file):
            return
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            data.setdefault("metadata", {})["comment"] =                 self.comment_info.toPlainText()
            with open(json_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"[save comment] {e}")

    def show_context_menu(self, pos, is_folder):
        menu = QtWidgets.QMenu(self)

        if is_folder:
            # Left panel: folder actions only (no New Pose)
            item = self.sidebar.itemAt(pos)
            if item:
                in_sub = bool(item.parent())
                na = menu.addAction("New Subfolder" if in_sub else "New Folder")
                na.triggered.connect(self.create_new_folder if in_sub else self.create_top_folder)
                menu.addSeparator()
                r = menu.addAction("Rename Folder")
                d = menu.addAction("Delete Folder")
                c = menu.addAction("Change Icon Color")
                act = menu.exec(self.sidebar.viewport().mapToGlobal(pos))
                if act == na:  (self.create_new_folder if in_sub else self.create_top_folder)()
                elif act == r: self.rename_folder(item)
                elif act == d: self.delete_folder(item)
                elif act == c: self.change_folder_color(item)
            else:
                na = menu.addAction("New Folder")
                na.triggered.connect(self.create_top_folder)
                menu.exec(self.sidebar.viewport().mapToGlobal(pos))
        else:
            # Center panel: pose actions only (no New Folder)
            item = self.items_view.itemAt(pos)
            selected = self.items_view.selectedItems()
            if item:
                if len(selected) > 1:
                    d = menu.addAction(f"Delete {len(selected)} poses")
                    br = menu.addAction(f"Batch Rename Objects in {len(selected)} poses…")
                    act = menu.exec(self.items_view.viewport().mapToGlobal(pos))
                    if act == d:
                        self._delete_multiple_poses(selected)
                    elif act == br:
                        self._batch_rename_multi_poses(selected)
                else:
                    r = menu.addAction("Rename Pose")
                    d = menu.addAction("Delete Pose")
                    act = menu.exec(self.items_view.viewport().mapToGlobal(pos))
                    if act == r:   self.rename_pose(item)
                    elif act == d: self.delete_pose(item)
            else:
                if self.current_folder_path:
                    np = menu.addAction("New Pose")
                    np.triggered.connect(self.show_new_pose_form)
                    menu.exec(self.items_view.viewport().mapToGlobal(pos))

    # ---------------------------------------------
    #  Folder CRUD
    # ---------------------------------------------

    def _batch_rename_multi_poses(self, items):
        """Opens a Batch Rename dialog that applies to all selected poses."""
        pose_paths = []
        for it in items:
            real_name = it.data(QtCore.Qt.UserRole)
            pose_paths.append(os.path.join(self.current_folder_path, real_name))
        dlg = BatchRenameMultiDialog(pose_paths, parent=self)
        dlg.exec()

    def _delete_multiple_poses(self, items):
        reply = QtWidgets.QMessageBox.question(
            self, "Delete Poses",
            f"Delete all {len(items)} selected poses?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )
        if reply != QtWidgets.QMessageBox.Yes:
            return
        deleted = 0
        for it in items:
            real_name = it.data(QtCore.Qt.UserRole)
            path = os.path.join(self.current_folder_path, real_name)
            try:
                shutil.rmtree(path)
                deleted += 1
            except Exception as e:
                print(f"[delete multi] {e}")
        self.current_pose_path = None
        self.reset_preview_panel()
        self.load_poses_from_folder(self.current_folder_path)
        self.status_bar.showMessage(f"{deleted} pose(s) deleted.")

    def create_new_folder(self):
        if not self.current_folder_path:
            QtWidgets.QMessageBox.warning(self, "Warning", "Select a folder first.")
            return
        name, ok = QtWidgets.QInputDialog.getText(self, "New Subfolder", "Name:")
        if not ok or not name.strip(): return
        tg = os.path.join(self.current_folder_path, name.strip())
        if os.path.exists(tg):
            QtWidgets.QMessageBox.warning(self, "Warning", "Folder already exists.")
            return
        os.makedirs(tg)
        self.save_folder_colors()
        self.populate_sidebar()

    def create_top_folder(self):
        root = self.current_project
        if not root:
            QtWidgets.QMessageBox.warning(self, "Warning", "Select or create a project first.")
            return
        name, ok = QtWidgets.QInputDialog.getText(self, "New Folder", "Name:")
        if not ok or not name.strip(): return
        tg = os.path.join(root, name.strip())
        if os.path.exists(tg):
            QtWidgets.QMessageBox.warning(self, "Warning", "Folder already exists.")
            return
        os.makedirs(tg)
        self.save_folder_colors()
        self.populate_sidebar()

    def rename_folder(self, item):
        if not item: return
        old = item.text(0)
        new, ok = QtWidgets.QInputDialog.getText(self, "Rename Folder", "New name:", text=old)
        if not ok or not new.strip() or new == old: return
        src = item.data(0, QtCore.Qt.UserRole)
        dst = os.path.join(os.path.dirname(src), new.strip())
        if os.path.exists(dst):
            QtWidgets.QMessageBox.warning(self, "Warning", "Folder already exists.")
            return
        os.rename(src, dst)
        if src in self.folder_colors:
            self.folder_colors[dst] = self.folder_colors.pop(src)
            self.save_folder_colors()
        self.populate_sidebar()

    def delete_folder(self, item):
        if not item: return
        src = item.data(0, QtCore.Qt.UserRole)
        r = QtWidgets.QMessageBox.question(
            self, "Delete Folder", f"Delete '{item.text(0)}' and all its contents?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )
        if r != QtWidgets.QMessageBox.Yes: return
        shutil.rmtree(src)
        if src in self.folder_colors:
            del self.folder_colors[src]
            self.save_folder_colors()
        if self.current_folder_path and (
            self.current_folder_path == src
            or self.current_folder_path.startswith(src + os.sep)
        ):
            self.current_folder_path = None
            self.items_view.clear()
            self.reset_preview_panel()
        self.populate_sidebar()
        self.status_bar.showMessage(f"Folder '{item.text(0)}' deleted.")

    # ---------------------------------------------
    #  Pose CRUD
    # ---------------------------------------------

    def rename_pose(self, item):
        if not item: return
        real_name = item.data(QtCore.Qt.UserRole)
        new, ok = QtWidgets.QInputDialog.getText(
            self, "Rename Pose", "New name:", text=item.text()
        )
        if not ok or not new.strip(): return
        src = os.path.join(self.current_folder_path, real_name)
        dst = os.path.join(self.current_folder_path, f"{new.strip()}.pose")
        if os.path.exists(dst):
            QtWidgets.QMessageBox.warning(self, "Warning", "Pose already exists.")
            return
        os.rename(src, dst)
        md = os.path.join(dst, "pose_data.json")
        if os.path.exists(md):
            try:
                with open(md, "r", encoding="utf-8") as f: d = json.load(f)
                d.setdefault("metadata", {})["name"] = new.strip()
                with open(md, "w", encoding="utf-8") as f: json.dump(d, f, indent=4)
            except Exception:
                pass
        self.load_poses_from_folder(self.current_folder_path)

    def delete_pose(self, item):
        if not item: return
        real_name = item.data(QtCore.Qt.UserRole)
        r = QtWidgets.QMessageBox.question(
            self, "Delete Pose", f"Delete pose '{item.text()}'?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )
        if r != QtWidgets.QMessageBox.Yes: return
        shutil.rmtree(os.path.join(self.current_folder_path, real_name))
        if self.current_pose_path and \
           os.path.basename(self.current_pose_path) == real_name:
            self.current_pose_path = None
            self.reset_preview_panel()
        self.load_poses_from_folder(self.current_folder_path)

    # ---------------------------------------------
    #  Folder colors
    # ---------------------------------------------

    def change_folder_color(self, item):
        if not item: return
        src     = item.data(0, QtCore.Qt.UserRole)
        initial = QtGui.QColor(self.folder_colors.get(src, "#606060"))
        color   = QColorDialog.getColor(initial, self, "Select Icon Color")
        if not color.isValid(): return
        self.folder_colors[src] = color.name()
        self.save_folder_colors()
        item.setIcon(0, self.create_color_icon(color))

    def create_color_icon(self, color, size=14):
        pix     = QtGui.QPixmap(size, size)
        pix.fill(QtCore.Qt.transparent)
        painter = QtGui.QPainter(pix)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        painter.setBrush(QtGui.QBrush(color))
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawEllipse(1, 1, size - 2, size - 2)
        painter.end()
        return QtGui.QIcon(pix)


# -------------------------------------------------------------
#  Entry point
# -------------------------------------------------------------

if __name__ == "__main__":
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = StudioLibraryMaxUI()
    window.show()
