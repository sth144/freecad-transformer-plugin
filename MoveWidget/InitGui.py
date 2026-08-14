"""FreeCAD entry point for Transform Handle.

This addon registers commands, not a workbench. Transforming an object is
something you do *while* modelling, so putting the handle behind a workbench
switch would cost you the PartDesign or BIM toolbars you were just using.
Registering at startup instead makes the commands available everywhere: bind
one to a shortcut under Tools > Customize > Keyboard, or drop them on a custom
toolbar. They are grouped there under "Transform Handle".

FreeCAD does not import this file, it execs it in a bare namespace: no
``__file__``, no ``__name__``, and globals is not locals. Module-level names
therefore live somewhere a function body cannot reach, which means top-level
functions cannot even call each other. Hence the single self-contained
``_bootstrap`` below, called at module level.
"""


def _bootstrap():
    """Put this directory on sys.path and register the commands."""
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


_bootstrap()
