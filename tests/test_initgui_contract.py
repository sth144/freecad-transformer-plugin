"""Regression tests for how FreeCAD executes ``InitGui.py``.

FreeCAD does not import the file, it execs it in a bare namespace: no
``__file__``, no ``__name__``, and separate globals/locals dicts. That last
point means a function body cannot see module-level assignments, so top-level
functions cannot call each other. Every one of those has silently broken
registration before, so the tests below reproduce the environment exactly
rather than importing the module.
"""

import os
import unittest

import FreeCADGui


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INITGUI = os.path.join(ROOT, "MoveWidget", "InitGui.py")

EXPECTED = ["MoveWidget_Toggle", "MoveWidget_Apply", "MoveWidget_Cancel"]


class InitGuiContractTests(unittest.TestCase):
    def _exec_initgui(self):
        """Exec InitGui.py the way FreeCAD does, returning the commands added."""
        with open(INITGUI) as handle:
            source = handle.read()

        added = []
        original = FreeCADGui.addCommand
        FreeCADGui.addCommand = lambda name, obj: added.append((name, obj))
        try:
            # No __file__, no __name__, and globals is not locals.
            exec(compile(source, INITGUI, "exec"), {}, {})
        finally:
            FreeCADGui.addCommand = original
        return added

    def test_registers_commands_without_dunder_file_or_name(self):
        self.assertEqual([name for name, _ in self._exec_initgui()], EXPECTED)

    def test_commands_declare_a_group_so_customize_can_find_them(self):
        # Without a workbench toolbar, Tools > Customize is the only way in,
        # and it groups by GroupName.
        for name, command in self._exec_initgui():
            resources = command.GetResources()
            self.assertEqual(resources.get("GroupName"), "Transform Handle", name)

    def test_command_icons_resolve_to_an_existing_file(self):
        for name, command in self._exec_initgui():
            icon = command.GetResources()["Pixmap"]
            self.assertTrue(os.path.isfile(icon), "%s -> %s" % (name, icon))

    def test_commands_is_a_list_not_a_tuple(self):
        # Workbench.appendToolbar rejects a tuple with "Expected a list as
        # second argument", so anyone putting these on a toolbar needs a list.
        import commands

        self.assertIsInstance(commands.COMMANDS, list)
        self.assertEqual(commands.COMMANDS, EXPECTED)


if __name__ == "__main__":
    unittest.main()
