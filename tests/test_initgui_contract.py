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
        """Exec InitGui.py the way FreeCAD does, capturing what it registers.

        Returns (workbench, command_names_registered_at_startup).
        """
        with open(INITGUI) as handle:
            source = handle.read()

        registered, commands = [], []
        original_wb = FreeCADGui.addWorkbench
        original_cmd = FreeCADGui.addCommand
        FreeCADGui.addWorkbench = registered.append
        FreeCADGui.addCommand = lambda name, obj: commands.append(name)
        try:
            # No __file__, no __name__, and globals is not locals.
            exec(compile(source, INITGUI, "exec"), {"Workbench": FreeCADGui.Workbench}, {})
        finally:
            FreeCADGui.addWorkbench = original_wb
            FreeCADGui.addCommand = original_cmd

        self.assertEqual(len(registered), 1)
        return registered[0], commands

    def test_registers_workbench_without_dunder_file_or_name(self):
        workbench, _ = self._exec_initgui()
        self.assertEqual(workbench.MenuText, "Transform Handle")

    def test_icon_resolves_to_an_existing_file(self):
        # Icon is bound after the class statement precisely because a class
        # body cannot read module-level names under FreeCAD's split namespace.
        workbench, _ = self._exec_initgui()
        self.assertTrue(os.path.isfile(workbench.Icon), workbench.Icon)

    def test_commands_are_registered_at_startup_not_on_activation(self):
        # This is what makes the commands reachable from every workbench: they
        # must exist after the exec alone, without Initialize() ever running.
        _, commands = self._exec_initgui()
        self.assertEqual(
            commands,
            ["MoveWidget_Toggle", "MoveWidget_Apply", "MoveWidget_Cancel"],
        )

    def test_initialize_surfaces_commands_without_a_package_context(self):
        workbench, _ = self._exec_initgui()

        toolbars, menus = [], []
        workbench.appendToolbar = lambda name, cmds: toolbars.append((name, cmds))
        workbench.appendMenu = lambda name, cmds: menus.append((name, cmds))
        # The relative import raises KeyError, not ImportError, when __name__
        # is absent; the fallback has to catch both.
        workbench.Initialize()

        self.assertEqual(len(toolbars), 1)
        self.assertEqual(len(menus), 1)
        self.assertEqual(
            list(toolbars[0][1]),
            ["MoveWidget_Toggle", "MoveWidget_Apply", "MoveWidget_Cancel"],
        )


if __name__ == "__main__":
    unittest.main()
