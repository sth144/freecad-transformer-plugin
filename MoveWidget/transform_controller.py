"""Selection-aware transform session and Coin3D handle.

The controller owns no document objects.  It only adds a temporary scene-graph
node and writes native FreeCAD properties inside one document transaction.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import cos, pi, sin
from typing import Iterable

import FreeCAD as App
import FreeCADGui as Gui
from pivy import coin


EPSILON = 1.0e-8

# How often to sample the dragger while a handle is up, in milliseconds.
POLL_INTERVAL_MS = 40


@dataclass
class Target:
    """A mutable transform property and its exact starting value."""

    obj: object
    property_name: str
    initial: object
    supports_scale: bool
    initial_scale: object = None

    @property
    def label(self):
        return self.obj.Label


class TargetResolver:
    """Map arbitrary GUI selections to the least-surprising transform owner."""

    @staticmethod
    def resolve(selection: Iterable[object]) -> list[Target]:
        result: list[Target] = []
        seen: set[str] = set()
        for selected in selection:
            obj = TargetResolver._placement_owner(selected)
            key = f"{obj.Document.Name}:{obj.Name}"
            if key in seen:
                continue
            seen.add(key)
            property_name = TargetResolver._property_for(obj)
            if not property_name:
                App.Console.PrintWarning(f"Transform Handle: {obj.Label} has no writable placement or attachment offset.\n")
                continue
            scale_property = TargetResolver._scale_property(obj)
            result.append(
                Target(
                    obj,
                    property_name,
                    getattr(obj, property_name),
                    bool(scale_property),
                    getattr(obj, scale_property) if scale_property else None,
                )
            )
        return result

    @staticmethod
    def _placement_owner(obj):
        """Promote a Part Design feature to its Body, never alter its history node."""
        type_id = getattr(obj, "TypeId", "")
        if type_id.startswith("PartDesign::") and type_id != "PartDesign::Body":
            get_body = getattr(obj, "getBody", None)
            if get_body:
                body = get_body()
                if body:
                    return body
            for parent in getattr(obj, "InList", []):
                if getattr(parent, "TypeId", "") == "PartDesign::Body":
                    return parent
        return obj

    @staticmethod
    def _property_for(obj) -> str | None:
        # Attached Arch/BIM objects must retain their Support and MapMode.
        if "AttachmentOffset" in obj.PropertiesList and getattr(obj, "MapMode", "Deactivated") != "Deactivated":
            return "AttachmentOffset"
        # FreeCAD's Python API does not expose a portable read-only query for
        # all object classes. Assignment is guarded by the controller instead.
        if "Placement" in obj.PropertiesList:
            return "Placement"
        return None

    @staticmethod
    def _scale_property(obj) -> str | None:
        for name in ("ScaleFactor", "Scale"):
            if name in obj.PropertiesList:
                return name
        return None


class TransformController:
    """A reversible direct-manipulation session."""

    def __init__(self):
        self.active = False
        self._targets: list[Target] = []
        self._root = None
        self._dragger = None
        self._handle_transform = None
        self._view = None
        self._timer = None
        self._last_sample = None
        self._document = None
        self._visual_scale = 1.0
        self._changed = False
        self._scale_notice_shown = False

    def toggle(self):
        if self.active:
            self.finish(commit=True)
        else:
            self.start()

    def start(self):
        selection = Gui.Selection.getSelection()
        self._targets = TargetResolver.resolve(selection)
        if not self._targets:
            App.Console.PrintWarning("Transform Handle: select an object, Body, Part, Link, or attached BIM object first.\n")
            return
        self._document = self._targets[0].obj.Document
        if any(target.obj.Document != self._document for target in self._targets):
            App.Console.PrintWarning("Transform Handle: selection must be in one document.\n")
            self._targets = []
            return
        self._document.openTransaction("Transform Handle")
        self._add_handle(self._shared_center())
        self.active = True
        self._changed = False
        self._scale_notice_shown = False
        App.Console.PrintMessage("Transform Handle: drag handles, then use Apply or Cancel.\n")

    def finish(self, commit: bool):
        if not self.active:
            return
        self._remove_handle()
        if commit:
            # The drag no longer recomputes per motion event, so this is the
            # single recompute for the whole gesture.
            self._document.recompute()
            self._document.commitTransaction()
        else:
            for target in self._targets:
                setattr(target.obj, target.property_name, target.initial)
            self._document.recompute()
            self._document.abortTransaction()
        self.active = False
        self._targets = []
        self._document = None
        Gui.activeDocument().activeView().redraw()

    def _shared_center(self):
        points = []
        for target in self._targets:
            try:
                box = target.obj.Shape.BoundBox
                points.extend((box.XMin, box.YMin, box.ZMin, box.XMax, box.YMax, box.ZMax))
            except Exception:
                placement = getattr(target.obj, "Placement", App.Placement())
                points.extend((placement.Base.x, placement.Base.y, placement.Base.z) * 2)
        xs, ys, zs = points[0::3], points[1::3], points[2::3]
        diagonal = App.Vector(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)).Length
        self._visual_scale = max(diagonal * 0.35, 10.0)
        return App.Vector((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, (min(zs) + max(zs)) / 2)

    def _add_handle(self, center):
        self._root = coin.SoSeparator()
        # Coin nodes start at refcount 0, so addChild would take this to 1 and
        # removeChild straight back to 0 -- destroying the node while Python
        # still holds wrappers to it and its children, which segfaults inside
        # the destructor chain. Hold our own reference and drop it explicitly.
        self._root.ref()
        position = coin.SoTranslation()
        position.translation.setValue(center.x, center.y, center.z)
        scale = coin.SoScale()
        scale.scaleFactor.setValue(self._visual_scale, self._visual_scale, self._visual_scale)
        self._dragger = coin.SoTransformBoxDragger()
        # Deliberately no addValueChangedCallback here. Coin invokes dragger
        # callbacks from its handleEvent traversal with no Python thread state
        # current, so pivy's bridge dereferences a NULL tstate and segfaults
        # inside PyDict_New. FreeCAD's own Std_TransformManip uses a C++
        # dragger for the same reason. Poll from a Qt timer instead: that runs
        # on the main thread with the GIL properly held.
        self._start_polling()
        self._root.addChild(position)
        self._root.addChild(scale)
        # The arrows and rings are siblings of the dragger, so the dragger's
        # motion does not reach them; drive them from a transform of our own,
        # updated on each poll. Wrapped in a separator so that transform does
        # not leak onto the dragger that follows it.
        decoration = coin.SoSeparator()
        self._handle_transform = coin.SoTransform()
        decoration.addChild(self._handle_transform)
        decoration.addChild(self._blender_style_handle())
        self._root.addChild(decoration)
        self._root.addChild(self._dragger)
        # Remember the view we attached to. Re-querying activeView() at
        # teardown would target whatever document is in front by then.
        self._view = Gui.activeDocument().activeView()
        self._view.getSceneGraph().addChild(self._root)

    @staticmethod
    def _blender_style_handle():
        """Draw a familiar X/Y/Z arrow-and-ring affordance at unit size.

        It is kept separate from the Coin dragger so replacing the interaction
        implementation later does not require changing the visual language.
        The parent scale makes it fit the selected objects.
        """
        handle = coin.SoSeparator()
        handle.addChild(TransformController._axis((1, 0, 0), (0.95, 0.18, 0.22)))
        handle.addChild(TransformController._axis((0, 1, 0), (0.32, 0.75, 0.18)))
        handle.addChild(TransformController._axis((0, 0, 1), (0.20, 0.46, 0.95)))
        handle.addChild(TransformController._ring("x", (0.95, 0.18, 0.22)))
        handle.addChild(TransformController._ring("y", (0.32, 0.75, 0.18)))
        handle.addChild(TransformController._ring("z", (0.20, 0.46, 0.95)))
        return handle

    @staticmethod
    def _axis(direction, colour):
        axis = coin.SoSeparator()
        material = coin.SoMaterial()
        material.diffuseColor.setValue(*colour)
        axis.addChild(material)
        rotation = coin.SoRotation()
        if direction == (1, 0, 0):
            rotation.rotation.setValue(coin.SbVec3f(0, 0, 1), -pi / 2)
        elif direction == (0, 0, 1):
            rotation.rotation.setValue(coin.SbVec3f(1, 0, 0), pi / 2)
        axis.addChild(rotation)
        shaft = coin.SoCylinder()
        shaft.radius = 0.025
        shaft.height = 1.25
        axis.addChild(shaft)
        tip_offset = coin.SoTranslation()
        tip_offset.translation.setValue(0, 0.82, 0)
        axis.addChild(tip_offset)
        tip = coin.SoCone()
        tip.bottomRadius = 0.09
        tip.height = 0.28
        axis.addChild(tip)
        return axis

    @staticmethod
    def _ring(axis, colour):
        ring = coin.SoSeparator()
        material = coin.SoMaterial()
        material.diffuseColor.setValue(*colour)
        ring.addChild(material)
        style = coin.SoDrawStyle()
        style.lineWidth = 3.0
        ring.addChild(style)
        points = []
        for index in range(49):
            angle = 2 * pi * index / 48
            a, b = 0.52 * cos(angle), 0.52 * sin(angle)
            if axis == "x":
                points.append((0, a, b))
            elif axis == "y":
                points.append((a, 0, b))
            else:
                points.append((a, b, 0))
        coordinates = coin.SoCoordinate3()
        coordinates.point.setValues(0, len(points), points)
        ring.addChild(coordinates)
        lines = coin.SoLineSet()
        lines.numVertices = len(points)
        ring.addChild(lines)
        return ring

    def _start_polling(self):
        """Sample the dragger on a timer rather than via a Coin callback."""
        try:
            from PySide6 import QtCore
        except ImportError:
            from PySide2 import QtCore

        self._timer = QtCore.QTimer()
        self._timer.setInterval(POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._on_changed)
        self._timer.start()

    def _stop_polling(self):
        if self._timer is not None:
            self._timer.stop()
            self._timer.timeout.disconnect(self._on_changed)
        self._timer = None

    def _remove_handle(self):
        self._stop_polling()
        root, self._root = self._root, None
        view, self._view = self._view, None
        # Drop the Python wrappers before the nodes die, so nothing here
        # references freed memory once the refcount reaches zero.
        self._dragger = None
        self._handle_transform = None
        self._last_sample = None
        if root is None:
            return
        if view is not None:
            view.getSceneGraph().removeChild(root)
        root.unref()

    def _on_changed(self):
        if not self.active or self._dragger is None:
            return
        try:
            tx, ty, tz = self._dragger.translation.getValue().getValue()
            qx, qy, qz, qw = self._dragger.rotation.getValue().getValue()
            sx, sy, sz = self._dragger.scaleFactor.getValue().getValue()
            sample = (tx, ty, tz, qx, qy, qz, qw, sx, sy, sz)
            if sample == self._last_sample:
                # Polling runs continuously; only write when the user has
                # actually moved the dragger.
                return
            self._last_sample = sample
            # Keep the arrows and rings on the object. Scale is deliberately
            # not mirrored: the affordance should stay a constant size.
            self._handle_transform.translation.setValue(tx, ty, tz)
            self._handle_transform.rotation.setValue(qx, qy, qz, qw)
            delta = App.Placement(App.Vector(tx, ty, tz) * self._visual_scale, App.Rotation(qx, qy, qz, qw))
            for target in self._targets:
                # Attachment offsets are intentionally composed in attachment-local space.
                if target.property_name == "AttachmentOffset":
                    setattr(target.obj, target.property_name, target.initial.multiply(delta))
                else:
                    setattr(target.obj, target.property_name, delta.multiply(target.initial))
                self._apply_scale(target, (sx, sy, sz))
            # Deliberately no recompute here: it would run many times a second
            # and is very slow on large models. finish() recomputes once.
            self._changed = True
        except Exception as error:
            App.Console.PrintError(f"Transform Handle: transform failed: {error}\n")

    def _apply_scale(self, target: Target, factors):
        if max(abs(value - 1.0) for value in factors) < EPSILON:
            return
        if not target.supports_scale:
            if not self._scale_notice_shown:
                App.Console.PrintWarning("Transform Handle: scale skipped for placement-only/parametric objects; use a native dimension or Scale property.\n")
                self._scale_notice_shown = True
            return
        name = TargetResolver._scale_property(target.obj)
        initial = target.initial_scale
        try:
            if hasattr(initial, "x"):
                value = App.Vector(initial.x * factors[0], initial.y * factors[1], initial.z * factors[2])
            else:
                # Scalar Scale means uniform scale. Non-uniform input uses X by convention.
                value = initial * factors[0]
            setattr(target.obj, name, value)
        except Exception as error:
            App.Console.PrintWarning(f"Transform Handle: scale skipped for {target.label}: {error}\n")


controller = TransformController()
