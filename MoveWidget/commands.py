"""GUI commands exposed by the Transform Handle workbench."""

from pathlib import Path

import FreeCADGui as Gui

try:
    from .transform_controller import controller
except ImportError:  # Loaded by FreeCAD from the workbench directory.
    from transform_controller import controller


ICON = str(Path(__file__).resolve().parent / "Resources" / "icons" / "transform-widget.svg")
# A list, not a tuple: Workbench.appendToolbar rejects tuples.
COMMANDS = ["MoveWidget_Toggle", "MoveWidget_Apply", "MoveWidget_Cancel"]


class _Toggle:
    def GetResources(self):
        return {"Pixmap": ICON, "MenuText": "Toggle handle", "ToolTip": "Show or hide the transform handle for the selection"}

    def Activated(self):
        controller.toggle()

    def IsActive(self):
        return Gui.activeDocument() is not None


class _Apply:
    def GetResources(self):
        return {"Pixmap": ICON, "MenuText": "Apply transform", "ToolTip": "Commit the active handle transformation"}

    def Activated(self):
        controller.finish(commit=True)

    def IsActive(self):
        return controller.active


class _Cancel:
    def GetResources(self):
        return {"Pixmap": ICON, "MenuText": "Cancel transform", "ToolTip": "Restore placements from before the handle drag"}

    def Activated(self):
        controller.finish(commit=False)

    def IsActive(self):
        return controller.active


def register():
    Gui.addCommand("MoveWidget_Toggle", _Toggle())
    Gui.addCommand("MoveWidget_Apply", _Apply())
    Gui.addCommand("MoveWidget_Cancel", _Cancel())
    _claim_actions()


# FreeCAD creates a command's QAction lazily, after InitGui.py has run, so
# the first attempt to claim them usually finds nothing. Retry for a while.
CLAIM_ATTEMPTS = 20
CLAIM_INTERVAL_MS = 500


def _claim_actions(attempt=0):
    """Give each command's QAction an owning widget.

    Qt only activates a WindowShortcut when some widget owns the QAction. A
    workbench normally supplies that owner by putting the command in a menu
    or toolbar; this addon has no workbench, so without an explicit owner any
    shortcut the user assigns is accepted by the Customize dialog and then
    silently never fires. Hand the actions to the main window instead.
    """
    main_window = Gui.getMainWindow()
    claimed = 0
    if main_window is not None:
        for name in COMMANDS:
            command = Gui.Command.get(name)
            for action in (command.getAction() if command else None) or []:
                if main_window not in action.associatedWidgets():
                    main_window.addAction(action)
                claimed += 1

    if claimed < len(COMMANDS) and attempt < CLAIM_ATTEMPTS:
        _defer(lambda: _claim_actions(attempt + 1), CLAIM_INTERVAL_MS)


def _defer(callback, delay_ms):
    try:
        from PySide6 import QtCore
    except ImportError:
        from PySide2 import QtCore
    QtCore.QTimer.singleShot(delay_ms, callback)
