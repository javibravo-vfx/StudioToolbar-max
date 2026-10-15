import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
SRC, OUTP = sys.argv[1], sys.argv[2]; sys.argv = ['x', SRC, '/dev/null']
exec(open(os.path.join(HERE, 'render_toolbar.py')).read().replace('pix.save(OUT)', 'pass').replace('print("saved"', '0 and print("saved"'))
from PySide6 import QtWidgets, QtGui
app.setFont(QtGui.QFont("DejaVu Sans", 11))          # fuente más grande, como Segoe UI en Max
dlg = stm.PipelineSetupDialog(parent=dock.widget()); dlg.show(); app.processEvents()
print("min size", dlg.minimumSize().width(), dlg.minimumSize().height(), " open size", dlg.width(), dlg.height())
dlg.resize(300, 300); [app.processEvents() for _ in range(5)]
print("after shrink attempt", dlg.width(), dlg.height())
bad = [(w.text(), w.width(), w.sizeHint().width()) for w in dlg.findChildren(QtWidgets.QPushButton) if w.isVisible() and w.width() < w.sizeHint().width()]
print("squeezed buttons:", bad)
dlg.grab().save(OUTP)
