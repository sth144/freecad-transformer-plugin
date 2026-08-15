"""GUI commands exposed by the Transform Handle workbench."""

from pathlib import Path

import FreeCAD as App
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
    _install_shortcut_actions()


RETRY_INTERVAL_MS = 500
RETRY_ATTEMPTS = 20

# Where Tools > Customize > Keyboard saves user-assigned shortcuts.
SHORTCUT_PARAMS = App.ParamGet("User parameter:BaseApp/Preferences/Shortcut")

# Keeps our QActions alive for the life of the session.
_SHORTCUT_ACTIONS = []
_INSTALLED = set()


def _install_shortcut_actions(attempt=0):
    """Create main-window-owned QActions so assigned shortcuts actually fire.

    Qt only activates a WindowShortcut when a widget owns the QAction, and a
    workbench is what normally supplies that owner by putting a command in a
    menu or toolbar. With no workbench, FreeCAD never creates a QAction for
    these commands at all, so there is nothing to give an owner to and any
    shortcut assigned in Customize is silently dead.

    So build our own actions, mirroring whatever shortcut the user configured,
    and let the main window own them. FreeCAD's own action, if something later
    creates one, stays ownerless and therefore inert -- no ambiguity. The
    exception is putting these commands on a toolbar, which would activate
    FreeCAD's action too and make the shortcut ambiguous.
    """
    main_window = Gui.getMainWindow()
    if main_window is None:
        # register() runs from InitGui.py, which can be before the main window
        # exists. Retry until it does.
        if attempt < RETRY_ATTEMPTS:
            _defer(lambda: _install_shortcut_actions(attempt + 1), RETRY_INTERVAL_MS)
        return

    try:
        from PySide6 import QtWidgets, QtGui
    except ImportError:
        from PySide2 import QtWidgets, QtGui
    action_type = getattr(QtWidgets, "QAction", None) or QtGui.QAction

    for name in COMMANDS:
        if name in _INSTALLED:
            # Installing twice would leave two actions on the same shortcut,
            # which Qt treats as ambiguous and refuses to fire.
            continue
        command = Gui.Command.get(name)
        if command is None:
            continue
        # Command.getShortcut() reads the QAction, which does not exist here,
        # so it always returns "". Read what Customize actually saved instead.
        shortcut = SHORTCUT_PARAMS.GetString(name, "")
        if not shortcut:
            # Nothing bound in Customize; no action needed.
            continue
        info = command.getInfo() or {}
        action = action_type(info.get("menuText", name), main_window)
        action.setObjectName("MoveWidgetShortcut_%s" % name)
        action.setShortcut(shortcut)
        action.triggered.connect(_runner(name))
        main_window.addAction(action)
        _SHORTCUT_ACTIONS.append(action)
        _INSTALLED.add(name)


def _runner(name):
    def run():
        Gui.runCommand(name, 0)
    return run


def _defer(callback, delay_ms):
    try:
        from PySide6 import QtCore
    except ImportError:
        from PySide2 import QtCore
    QtCore.QTimer.singleShot(delay_ms, callback)
