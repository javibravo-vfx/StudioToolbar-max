# dev — test the toolbar without 3ds Max

These scripts fake `pymxs` / `qtmax` and a pipeline folder tree, then build the real
toolbar with PySide6 so it can be rendered and tested on any machine.

```
pip install PySide6-Essentials
QT_QPA_PLATFORM=offscreen python dev/render_toolbar.py StudioToolbar-max.py toolbar.png
QT_QPA_PLATFORM=offscreen python dev/test_features.py  StudioToolbar-max.py
QT_QPA_PLATFORM=offscreen python dev/preview.py        StudioToolbar-max.py   # toolbar + menus PNGs
QT_QPA_PLATFORM=offscreen python dev/test_setup.py     StudioToolbar-max.py   # Setup dialog tests
QT_QPA_PLATFORM=offscreen python dev/render_setup_pages.py StudioToolbar-max.py setup_   # Setup pages PNGs
QT_QPA_PLATFORM=offscreen python dev/test_studiolibrary.py maintools/STM_StudioLibraryMAX.py   # pose engine + UI
```

They are not used by the toolbar itself. Fonts differ from Windows (no Tahoma), so
check final looks inside Max.
