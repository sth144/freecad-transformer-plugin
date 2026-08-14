"""Regression tests for how FreeCAD executes ``InitGui.py``.

FreeCAD does not import the file, it execs it in a bare namespace: no
``__file__``, no ``__name__``, and separate globals/locals dicts. That last
point means a class body cannot see module-level assignments. Every one of
those three has silently broken workbench registration before, so the tests
below reproduce the environment exactly rather than importing the module.
"""

import os
import unittest

import FreeCADGui


INITGUI = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "MoveWidget",
    "InitGui.py",
)


class InitGuiContractTests(unittest.TestCase):
    def _exec_initgui(self):
        """Exec InitGui.py the way FreeCAD does, capturing what it registers."""
        with open(INITGUI) as handle:
            source = handle.read()

        registered = []
        original = FreeCADGui.addWorkbench
        FreeCADGui.addWorkbench = registered.append
        try:
            # No __file__, no __name__, and globals is not locals.
            exec(compile(source, INITGUI, "exec"), {"Workbench": FreeCADGui.Workbench}, {})
        finally:
            FreeCADGui.addWorkbench = original

        self.assertEqual(len(registered), 1)
        return registered[0]

    def test_registers_workbench_without_dunder_file_or_name(self):
        workbench = self._exec_initgui()
        self.assertEqual(workbench.MenuText, "Transform Handle")

    def test_icon_resolves_to_an_existing_file(self):
        # Icon is bound after the class statement precisely because a class
        # body cannot read module-level names under FreeCAD's split namespace.
        workbench = self._exec_initgui()
        self.assertTrue(os.path.isfile(workbench.Icon), workbench.Icon)

    def test_initialize_imports_commands_without_a_package_context(self):
        workbench = self._exec_initgui()

        added = []
        original = FreeCADGui.addCommand
        FreeCADGui.addCommand = lambda name, obj: added.append(name)
        workbench.appendToolbar = lambda *args, **kwargs: None
        workbench.appendMenu = lambda *args, **kwargs: None
        try:
            # The relative import raises KeyError, not ImportError, when
            # __name__ is absent; the fallback has to catch both.
            workbench.Initialize()
        finally:
            FreeCADGui.addCommand = original

        self.assertEqual(
            added,
            ["MoveWidget_Toggle", "MoveWidget_Apply", "MoveWidget_Cancel"],
        )


if __name__ == "__main__":
    unittest.main()
