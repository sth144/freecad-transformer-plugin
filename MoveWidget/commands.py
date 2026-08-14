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

# Groups the commands in Tools > Customize, which is how they are found
# without a workbench toolbar.
GROUP = "Transform Handle"


class _Toggle:
    def GetResources(self):
        return {"Pixmap": ICON, "GroupName": GROUP, "MenuText": "Toggle handle", "ToolTip": "Show or hide the transform handle for the selection"}

    def Activated(self):
        controller.toggle()

    def IsActive(self):
        return Gui.activeDocument() is not None


class _Apply:
    def GetResources(self):
        return {"Pixmap": ICON, "GroupName": GROUP, "MenuText": "Apply transform", "ToolTip": "Commit the active handle transformation"}

    def Activated(self):
        controller.finish(commit=True)

    def IsActive(self):
        return controller.active


class _Cancel:
    def GetResources(self):
        return {"Pixmap": ICON, "GroupName": GROUP, "MenuText": "Cancel transform", "ToolTip": "Restore placements from before the handle drag"}

    def Activated(self):
        controller.finish(commit=False)

    def IsActive(self):
        return controller.active


def register():
    Gui.addCommand("MoveWidget_Toggle", _Toggle())
    Gui.addCommand("MoveWidget_Apply", _Apply())
    Gui.addCommand("MoveWidget_Cancel", _Cancel())
