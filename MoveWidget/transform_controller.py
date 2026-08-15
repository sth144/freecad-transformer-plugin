"""Selection-aware transform session and Coin3D handle.

The controller owns no document objects.  It only adds a temporary scene-graph
node and writes native FreeCAD properties inside one document transaction.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import cos, degrees, pi, sin
from typing import Iterable

import FreeCAD as App
import FreeCADGui as Gui
from pivy import coin


EPSILON = 1.0e-8

# How often to sample the dragger while a handle is up, in milliseconds.
POLL_INTERVAL_MS = 40

# Segments used to draw each rotation ring.
RING_SEGMENTS = 48


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
        self._translators = []
        self._rotators = []
        self._scalers = []
        self._nodes = []
        self._attached = set()
        self._switch = None
        self._position = None
        self._scale = None
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
        self._show_handle(self._shared_center())
        self.active = True
        self._changed = False
        self._scale_notice_shown = False
        App.Console.PrintMessage("Transform Handle: drag handles, then use Apply or Cancel.\n")

    def finish(self, commit: bool):
        if not self.active:
            return
        self._hide_handle()
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

    # name, world axis, colour
    AXES = (
        ("x", (1.0, 0.0, 0.0), (0.95, 0.18, 0.22)),
        ("y", (0.0, 1.0, 0.0), (0.32, 0.75, 0.18)),
        ("z", (0.0, 0.0, 1.0), (0.20, 0.46, 0.95)),
    )

    def _show_handle(self, center):
        """Position the handle over the selection and reveal it.

        The scene graph is built once and then shown and hidden. Every crash
        during bring-up was in destruction -- a dragger's destructor, reached
        when a Python wrapper was freed and pivy deleted the node underneath
        the graph. Nothing is destroyed here, so that whole class of fault is
        out of reach; the nodes simply outlive the session.
        """
        self._build_handle()
        self._position.translation.setValue(center.x, center.y, center.z)
        self._scale.scaleFactor.setValue(
            self._visual_scale, self._visual_scale, self._visual_scale)
        self._reset_draggers()
        gui_document = Gui.activeDocument()
        self._attach(gui_document.activeView(), gui_document.Document.Name)
        self._switch.whichChild = 0
        self._start_polling()

    def _build_handle(self):
        if self._root is not None:
            return
        self._root = coin.SoSeparator()
        # Held for the life of the session, so the refcount never reaches zero
        # and no destructor ever runs while the graph is live.
        self._root.ref()
        self._switch = coin.SoSwitch()
        self._switch.whichChild = -1
        self._position = coin.SoTranslation()
        self._scale = coin.SoScale()
        body = coin.SoSeparator()
        body.addChild(self._position)
        body.addChild(self._scale)

        # One dragger per axis instead of a single SoTransformBoxDragger. This
        # is what constrains a drag to the arrow you actually grabbed, and it
        # makes the arrows and rings the handles rather than decoration drawn
        # alongside a separate, differently shaped dragger.
        for _name, direction, colour in self.AXES:
            body.addChild(self._axis_translator(direction, colour))
            body.addChild(self._axis_rotator(direction, colour))
            body.addChild(self._axis_scaler(direction, colour))

        self._switch.addChild(body)
        self._root.addChild(self._switch)
        # Keep a Python reference to everything: a wrapper being garbage
        # collected is what deleted live nodes and segfaulted Coin.
        self._nodes.extend([self._switch, self._position, self._scale, body])

    def _attach(self, view, document_name):
        """Attach the handle to this document's view, safely.

        Views are tracked by document name and never by object. Calling
        getSceneGraph() on the view of a closed document segfaults inside
        SoBase::ref() -- a hard fault, not a Python exception, so it cannot be
        caught. The only safe move is to never dereference a dead view, hence
        pruning against the list of open documents first.
        """
        live = set(App.listDocuments())
        self._attached &= live
        if document_name in self._attached:
            return
        for other in list(self._attached):
            # Still open, so its view is alive and safe to touch.
            other_view = Gui.getDocument(other).ActiveView
            other_view.getSceneGraph().removeChild(self._root)
            self._attached.discard(other)
        view.getSceneGraph().addChild(self._root)
        self._attached.add(document_name)

    def _reset_draggers(self):
        identity = coin.SbRotation(coin.SbVec3f(0.0, 0.0, 1.0), 0.0)
        for dragger, _direction in self._translators:
            dragger.translation.setValue(0.0, 0.0, 0.0)
        for dragger, _direction in self._rotators:
            dragger.rotation.setValue(identity)
        for dragger, _direction in self._scalers:
            dragger.scaleFactor.setValue(1.0, 1.0, 1.0)
        self._last_sample = None

    def _hide_handle(self):
        self._stop_polling()
        if self._switch is not None:
            self._switch.whichChild = -1
        self._last_sample = None

    def _axis_translator(self, direction, colour):
        """An arrow whose drag is constrained to one axis."""
        group = coin.SoSeparator()
        orient = coin.SoRotation()
        # SoTranslate1Dragger translates along its own local X; aim that here.
        orient.rotation.setValue(
            coin.SbRotation(coin.SbVec3f(1.0, 0.0, 0.0), coin.SbVec3f(*direction)))
        group.addChild(orient)
        dragger = coin.SoTranslate1Dragger()
        dragger.setPart("translator", self._arrow(colour, False))
        dragger.setPart("translatorActive", self._arrow(colour, True))
        group.addChild(dragger)
        self._translators.append((dragger, direction))
        self._nodes.extend([group, orient, dragger])
        return group

    def _axis_rotator(self, direction, colour):
        """A ring whose drag is constrained to rotation about one axis."""
        group = coin.SoSeparator()
        orient = coin.SoRotation()
        # SoRotateDiscDragger rotates about its own local Z; aim that here.
        orient.rotation.setValue(
            coin.SbRotation(coin.SbVec3f(0.0, 0.0, 1.0), coin.SbVec3f(*direction)))
        group.addChild(orient)
        # Draw the ring as an ordinary sibling. SoRotateDiscDragger does not
        # render its rotator part here -- not even the stock geometry -- so
        # relying on the part for visibility left two of the three rings
        # invisible. The dragger still gets a matching copy at the same radius,
        # which is what a click actually hits.
        visible = self._ring(colour, False)
        group.addChild(visible)
        dragger = coin.SoRotateDiscDragger()
        dragger.setPart("rotator", self._ring(colour, False))
        dragger.setPart("rotatorActive", self._ring(colour, True))
        group.addChild(dragger)
        self._rotators.append((dragger, direction))
        self._nodes.extend([group, orient, dragger, visible])
        return group

    def _axis_scaler(self, direction, colour):
        """A knob whose drag scales along one axis."""
        group = coin.SoSeparator()
        orient = coin.SoRotation()
        # SoScale1Dragger scales along its own local X; aim that here.
        orient.rotation.setValue(
            coin.SbRotation(coin.SbVec3f(1.0, 0.0, 0.0), coin.SbVec3f(*direction)))
        group.addChild(orient)
        visible = self._scale_knob(colour, False)
        group.addChild(visible)
        dragger = coin.SoScale1Dragger()
        dragger.setPart("scaler", self._scale_knob(colour, False))
        dragger.setPart("scalerActive", self._scale_knob(colour, True))
        group.addChild(dragger)
        self._scalers.append((dragger, direction))
        self._nodes.extend([group, orient, dragger, visible])
        return group

    @staticmethod
    def _scale_knob(colour, active):
        """A cube sitting just beyond the arrow tip."""
        node = coin.SoSeparator()
        material = coin.SoMaterial()
        material.diffuseColor.setValue(*colour)
        if active:
            material.emissiveColor.setValue(*colour)
        node.addChild(material)
        offset = coin.SoTranslation()
        offset.translation.setValue(1.75, 0.0, 0.0)
        node.addChild(offset)
        knob = coin.SoCube()
        knob.width = knob.height = knob.depth = 0.17
        node.addChild(knob)
        return node

    @staticmethod
    def _arrow(colour, active):
        """A solid arrow along +X. Solid geometry is a reliable pick target."""
        node = coin.SoSeparator()
        material = coin.SoMaterial()
        material.diffuseColor.setValue(*colour)
        if active:
            material.emissiveColor.setValue(*colour)
        node.addChild(material)
        orient = coin.SoRotation()
        orient.rotation.setValue(
            coin.SbRotation(coin.SbVec3f(0.0, 1.0, 0.0), coin.SbVec3f(1.0, 0.0, 0.0)))
        node.addChild(orient)
        shaft_offset = coin.SoTranslation()
        shaft_offset.translation.setValue(0.0, 0.62, 0.0)
        node.addChild(shaft_offset)
        shaft = coin.SoCylinder()
        shaft.radius = 0.035
        shaft.height = 1.25
        node.addChild(shaft)
        tip_offset = coin.SoTranslation()
        tip_offset.translation.setValue(0.0, 0.78, 0.0)
        node.addChild(tip_offset)
        tip = coin.SoCone()
        tip.bottomRadius = 0.12
        tip.height = 0.32
        node.addChild(tip)
        return node

    @staticmethod
    def _ring(colour, active):
        """A flat annulus in the XY plane, drawn as a solid band.

        The previous rings were a 3px line loop, which is both hard to see and
        nearly impossible to click -- grabbing one fell through to whatever was
        behind it. A band has real area to hit. BASE_COLOR keeps it evenly
        visible from either side regardless of surface normals.
        """
        node = coin.SoSeparator()
        light = coin.SoLightModel()
        light.model = coin.SoLightModel.BASE_COLOR
        node.addChild(light)
        tint = [min(1.0, channel + 0.35) for channel in colour] if active else list(colour)
        base = coin.SoBaseColor()
        base.rgb.setValue(*tint)
        node.addChild(base)
        # Thin enough to read as a ring, wide enough to be an easy pick target.
        inner, outer = (1.00, 1.15) if active else (1.03, 1.12)
        points = []
        for index in range(RING_SEGMENTS + 1):
            angle = 2 * pi * index / RING_SEGMENTS
            cosine, sine = cos(angle), sin(angle)
            points.append((outer * cosine, outer * sine, 0.0))
            points.append((inner * cosine, inner * sine, 0.0))
        coordinates = coin.SoCoordinate3()
        coordinates.point.setValues(0, len(points), points)
        node.addChild(coordinates)
        strip = coin.SoTriangleStripSet()
        strip.numVertices.setValue(len(points))
        node.addChild(strip)
        return node

    @staticmethod
    def _disc_angle(dragger):
        """Signed rotation of a disc dragger about its own local Z."""
        axis, angle = dragger.rotation.getValue().getAxisAngle()
        return angle if axis.getValue()[2] >= 0.0 else -angle

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

    def _on_changed(self):
        if not self.active or not self._translators:
            return
        try:
            # Each translator reports distance along its own local X, and each
            # rotator an angle about its own local Z; both were aimed at a
            # world axis when built, so the components compose directly.
            offsets = [dragger.translation.getValue().getValue()[0]
                       for dragger, _direction in self._translators]
            angles = [self._disc_angle(dragger)
                      for dragger, _direction in self._rotators]
            # SoScale1Dragger reports its factor on its own local X.
            factors = [dragger.scaleFactor.getValue().getValue()[0]
                       for dragger, _direction in self._scalers]
            sample = tuple(round(value, 7) for value in offsets + angles + factors)
            if sample == self._last_sample:
                # Polling runs continuously; only write when something moved.
                return
            self._last_sample = sample

            translation = App.Vector(0.0, 0.0, 0.0)
            for offset, (_dragger, direction) in zip(offsets, self._translators):
                translation = translation + App.Vector(*direction) * offset
            rotation = App.Rotation()
            for angle, (_dragger, direction) in zip(angles, self._rotators):
                if abs(angle) > EPSILON:
                    rotation = App.Rotation(App.Vector(*direction), degrees(angle)).multiply(rotation)

            delta = App.Placement(translation * self._visual_scale, rotation)
            for target in self._targets:
                # Attachment offsets are intentionally composed in attachment-local space.
                if target.property_name == "AttachmentOffset":
                    setattr(target.obj, target.property_name, target.initial.multiply(delta))
                else:
                    setattr(target.obj, target.property_name, delta.multiply(target.initial))
            # _apply_scale enforces the rule that only objects with a
            # writable Scale/ScaleFactor may be scaled; a Placement cannot
            # represent one, so parametric solids are refused rather than
            # silently mangled.
            if any(abs(f - 1.0) > EPSILON for f in factors):
                scale_by = [1.0, 1.0, 1.0]
                for factor, (_dragger, direction) in zip(factors, self._scalers):
                    for index in range(3):
                        if direction[index]:
                            scale_by[index] = factor
                for target in self._targets:
                    self._apply_scale(target, tuple(scale_by))
            # No recompute here: it would run many times a second and is very
            # slow on large models. finish() recomputes once.
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
