"""FreeCAD workbench entry point for Transform Handle."""

from pathlib import Path

import FreeCADGui as Gui


try:
    MODULE_DIR = Path(__file__).resolve().parent
except NameError:  # FreeCAD execs InitGui.py without setting __file__.
    import inspect

    MODULE_DIR = Path(inspect.getfile(inspect.currentframe())).resolve().parent
ICON = str(MODULE_DIR / "Resources" / "icons" / "transform-widget.svg")


class MoveWidgetWorkbench(Workbench):
    """A small, standalone direct-manipulation workbench."""

    MenuText = "Transform Handle"
    ToolTip = "Direct move, rotate and safe-scale handle"
    Icon = ICON

    def Initialize(self):
        try:
            from . import commands
        except ImportError:  # Loaded by FreeCAD as a top-level InitGui module.
            import commands

        commands.register()
        self.appendToolbar("Transform Handle", commands.COMMANDS)
        self.appendMenu("Transform Handle", commands.COMMANDS)

    def GetClassName(self):
        return "Gui::PythonWorkbench"


Gui.addWorkbench(MoveWidgetWorkbench())
