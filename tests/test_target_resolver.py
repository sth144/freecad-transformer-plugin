"""Regression tests runnable inside FreeCAD's Python console/test runner."""

import unittest

import FreeCAD as App

from MoveGizmo.transform_controller import TargetResolver


class TargetResolverTests(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("MoveGizmoTest")

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def test_part_feature_uses_placement(self):
        box = self.doc.addObject("Part::Feature", "Box")
        target = TargetResolver.resolve([box])[0]
        self.assertIs(target.obj, box)
        self.assertEqual(target.property_name, "Placement")

    def test_attached_object_uses_attachment_offset(self):
        obj = self.doc.addObject("PartDesign::Feature", "AttachedFeature")
        obj.addProperty("App::PropertyPlacement", "AttachmentOffset")
        obj.addProperty("App::PropertyString", "MapMode")
        obj.MapMode = "FlatFace"
        target = TargetResolver.resolve([obj])[0]
        self.assertEqual(target.property_name, "AttachmentOffset")

    def test_part_design_feature_promotes_to_its_body(self):
        body = self.doc.addObject("PartDesign::Body", "Body")
        feature = body.newObject("PartDesign::Feature", "Feature")
        target = TargetResolver.resolve([feature])[0]
        self.assertIs(target.obj, body)
        self.assertEqual(target.property_name, "Placement")

    def test_link_is_transformed_without_touching_its_source(self):
        source = self.doc.addObject("Part::Feature", "Source")
        link = self.doc.addObject("App::Link", "Link")
        link.LinkedObject = source
        target = TargetResolver.resolve([link])[0]
        self.assertIs(target.obj, link)
        self.assertEqual(target.property_name, "Placement")


if __name__ == "__main__":
    unittest.main()
