"""FreeCAD workbench entry point for Transform Gizmo."""

from pathlib import Path

import FreeCADGui as Gui


MODULE_DIR = Path(__file__).resolve().parent
ICON = str(MODULE_DIR / "Resources" / "icons" / "transform-gizmo.svg")


class MoveGizmoWorkbench(Workbench):
    """A small, standalone direct-manipulation workbench."""

    MenuText = "Transform Gizmo"
    ToolTip = "Direct move, rotate and safe-scale gizmo"
    Icon = ICON

    def Initialize(self):
        try:
            from . import commands
        except ImportError:  # Loaded by FreeCAD as a top-level InitGui module.
            import commands

        commands.register()
        self.appendToolbar("Transform Gizmo", commands.COMMANDS)
        self.appendMenu("Transform Gizmo", commands.COMMANDS)

    def GetClassName(self):
        return "Gui::PythonWorkbench"


Gui.addWorkbench(MoveGizmoWorkbench())
