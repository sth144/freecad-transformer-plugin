"""GUI commands exposed by the Transform Gizmo workbench."""

from pathlib import Path

import FreeCADGui as Gui

try:
    from .transform_controller import controller
except ImportError:  # Loaded by FreeCAD from the workbench directory.
    from transform_controller import controller


ICON = str(Path(__file__).resolve().parent / "Resources" / "icons" / "transform-gizmo.svg")
COMMANDS = ("MoveGizmo_Toggle", "MoveGizmo_Apply", "MoveGizmo_Cancel")


class _Toggle:
    def GetResources(self):
        return {"Pixmap": ICON, "MenuText": "Toggle gizmo", "ToolTip": "Show or hide the transform gizmo for the selection"}

    def Activated(self):
        controller.toggle()

    def IsActive(self):
        return Gui.activeDocument() is not None


class _Apply:
    def GetResources(self):
        return {"Pixmap": ICON, "MenuText": "Apply transform", "ToolTip": "Commit the active gizmo transformation"}

    def Activated(self):
        controller.finish(commit=True)

    def IsActive(self):
        return controller.active


class _Cancel:
    def GetResources(self):
        return {"Pixmap": ICON, "MenuText": "Cancel transform", "ToolTip": "Restore placements from before the gizmo drag"}

    def Activated(self):
        controller.finish(commit=False)

    def IsActive(self):
        return controller.active


def register():
    Gui.addCommand("MoveGizmo_Toggle", _Toggle())
    Gui.addCommand("MoveGizmo_Apply", _Apply())
    Gui.addCommand("MoveGizmo_Cancel", _Cancel())
