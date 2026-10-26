"""Offscreen smoke test for the installed RCAIDE GUI.

Starts the real main window (offscreen Qt platform), lets it settle briefly,
then quits and reports OK plus the list of tabs.
"""

import os
import sys

if os.environ.get("GUI_SMOKE_OFFSCREEN", "0") == "1":
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication
from qt_material import apply_stylesheet

import main as gui_main
from utilities import APP_DATA

app = QApplication(sys.argv)
window = gui_main.App()

extra = {
    "density_scale": "-2",
    "delete": "#b0220c",
    "save": "#0291de",
    "menubar": "#021a32",
    "font_size": "15px",
}
apply_stylesheet(
    app,
    theme=os.path.join(APP_DATA, "style_sheets", "rcaide_dark_theme.xml"),
    extra=extra,
)
window.show()

hold_ms = int(os.environ.get("GUI_SMOKE_HOLD_MS", "8000"))
QTimer.singleShot(hold_ms, app.quit)
rc = app.exec()

tabs = [window.tabs.tabText(i) for i in range(window.tabs.count())]
print("SMOKE_OK rc=%s" % rc)
print("TABS=%s" % " | ".join(tabs))
