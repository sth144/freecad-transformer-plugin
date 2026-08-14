"""FreeCAD workbench entry point for Transform Handle.

FreeCAD execs this file in a bare namespace rather than importing it: there is
no ``__file__``, no ``__name__``, and globals/locals are separate dicts, so a
class body cannot see module-level assignments. Everything this file needs is
therefore resolved inside a function or bound after the class statement.
"""

import FreeCADGui as Gui


def _icon_path():
    """Absolute path to the workbench icon, without relying on ``__file__``."""
    import inspect
    from pathlib import Path

    try:
        here = __file__
    except NameError:
        here = inspect.getfile(inspect.currentframe())

    directory = Path(here).resolve().parent
    return str(directory / "Resources" / "icons" / "transform-widget.svg")


class MoveWidgetWorkbench(Workbench):
    """A small, standalone direct-manipulation workbench."""

    MenuText = "Transform Handle"
    ToolTip = "Direct move, rotate and safe-scale handle"

    def Initialize(self):
        try:
            from . import commands
        except (ImportError, KeyError):
            # Without __name__ in globals the relative import raises KeyError,
            # not ImportError. FreeCAD puts this directory on sys.path, so the
            # flat import resolves.
            import commands

        commands.register()
        self.appendToolbar("Transform Handle", commands.COMMANDS)
        self.appendMenu("Transform Handle", commands.COMMANDS)

    def GetClassName(self):
        return "Gui::PythonWorkbench"


MoveWidgetWorkbench.Icon = _icon_path()
Gui.addWorkbench(MoveWidgetWorkbench())
