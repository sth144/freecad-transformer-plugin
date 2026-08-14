"""FreeCAD entry point for Transform Handle.

The commands are registered here, at startup, rather than inside the
workbench's ``Initialize()``. That makes them available from every workbench:
bind one to a shortcut under Tools > Customize > Keyboard, or drop it on a
custom toolbar, and moving an object no longer costs a workbench switch. The
workbench itself remains only so the addon is discoverable.

FreeCAD does not import this file, it execs it in a bare namespace: no
``__file__``, no ``__name__``, and globals is not locals. Module-level names
therefore live somewhere a class body or a function body cannot reach, which
means top-level functions cannot even call each other. Hence the single
self-contained ``_bootstrap`` below, called at module level.
"""

import FreeCADGui as Gui


def _bootstrap():
    """Register the commands and return the workbench icon path."""
    import inspect
    import sys
    from pathlib import Path

    try:
        here = __file__
    except NameError:
        here = inspect.getfile(inspect.currentframe())
    directory = Path(here).resolve().parent

    # FreeCAD normally puts this directory on sys.path before running us, but
    # do not depend on that ordering for the startup import.
    if str(directory) not in sys.path:
        sys.path.append(str(directory))

    try:
        from . import commands
    except (ImportError, KeyError):
        # Without __name__ in globals the relative import raises KeyError,
        # not ImportError, so the fallback has to catch both.
        import commands

    commands.register()
    return str(directory / "Resources" / "icons" / "transform-widget.svg")


class MoveWidgetWorkbench(Workbench):
    """Discoverability shell: the commands work without ever activating it."""

    MenuText = "Transform Handle"
    ToolTip = "Direct move, rotate and safe-scale handle"

    def Initialize(self):
        try:
            from . import commands
        except (ImportError, KeyError):
            import commands

        # Already registered at startup; only surface them here.
        self.appendToolbar("Transform Handle", commands.COMMANDS)
        self.appendMenu("Transform Handle", commands.COMMANDS)

    def GetClassName(self):
        return "Gui::PythonWorkbench"


MoveWidgetWorkbench.Icon = _bootstrap()
Gui.addWorkbench(MoveWidgetWorkbench())
