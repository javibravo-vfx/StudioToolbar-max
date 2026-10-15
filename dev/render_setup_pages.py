import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
SRC, PREFIX = sys.argv[1], sys.argv[2]; sys.argv = ['x', SRC, '/dev/null']
exec(open(os.path.join(HERE, 'render_toolbar.py')).read().replace('pix.save(OUT)', 'pass').replace('print("saved"', '0 and print("saved"'))
from PySide6 import QtWidgets
dlg = stm.PipelineSetupDialog(parent=dock.widget())
dlg.show()
for i in range(dlg.nav.count()):
    dlg.nav.setCurrentRow(i)
    for _ in range(8): app.processEvents()
    dlg.grab().save(f"{PREFIX}{i}.png")
print(dlg.width(), dlg.height())
