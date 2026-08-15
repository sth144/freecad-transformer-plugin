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


def _claim_actions():
    """Give each command's QAction an owning widget.

    Qt only activates a WindowShortcut when some widget owns the QAction.
    A workbench normally supplies that owner by putting the command in a
    menu or toolbar; this addon has no workbench, so without an explicit
    owner any shortcut the user assigns is accepted by the Customize dialog
    and then silently never fires. Hand them to the main window instead.
    """
    main_window = Gui.getMainWindow()
    if main_window is None:
        # Too early in startup; retry once the event loop is running.
        _defer(_claim_actions)
        return

    for name in COMMANDS:
        command = Gui.Command.get(name)
        if command is None:
            continue
        for action in command.getAction() or []:
            main_window.addAction(action)


def _defer(callback):
    try:
        from PySide6 import QtCore
    except ImportError:
        from PySide2 import QtCore
    QtCore.QTimer.singleShot(0, callback)
