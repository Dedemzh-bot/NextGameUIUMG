"""Explicit static sizing contracts. No function here measures Slate or text."""
from __future__ import annotations

import math
import re

ID = re.compile(r"^[a-z][a-z0-9_-]*$")
EVIDENCE = re.compile(r"^[a-z][a-z0-9.-]{2,95}$")


def number(value, positive=False):
    try:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and (not positive or value > 0)
    except (OverflowError, ValueError):
        return False


def vector(value, size, positive=False):
    return isinstance(value, list) and len(value) == size and all(number(v, positive) for v in value)


def size_constraints(value):
    return (isinstance(value, dict) and set(value) == {"version", "widthOverride", "heightOverride"}
            and type(value["version"]) is int and value["version"] == 1
            and number(value["widthOverride"], True) and value["heightOverride"] is None)


def slot_fields(slot, flow=False):
    required = {"horizontalAlignment", "verticalAlignment"} | ({"size", "padding"} if flow else set())
    allowed = required | {"padding"}
    if not isinstance(slot, dict) or not required <= set(slot) or set(slot) - allowed:
        return False
    padding = slot.get("padding", [0, 0, 0, 0])
    if not vector(padding, 4) or any(v < 0 for v in padding):
        return False
    if slot["horizontalAlignment"] not in {"Fill", "Left", "Center", "Right"} or slot["verticalAlignment"] not in {"Fill", "Top", "Center", "Bottom"}:
        return False
    if flow:
        size = slot["size"]
        return isinstance(size, dict) and (size == {"rule": "Auto"} or (
            set(size) == {"rule", "weight"} and size["rule"] == "Fill" and number(size["weight"], True)))
    return True


def dependency_bounds_v2(node, by_id):
    """Return (minimum width, minimum height, maximum width), or fail closed.

    A real, root-direct width-only SizeBox supplies width authority. Explicit
    horizontal Fill alignment carries that authority; HBox Auto widths and
    padding reserve space before positive weighted Fill text leaves receive it.
    Only reachable visible image sources contribute to the height lower bound.
    """
    proof = node.get("contentSizeProof")
    if not isinstance(proof, dict) or set(proof) != {"kind", "minimumDesiredSize", "sourceNodeIds", "evidenceId"} or proof["kind"] != "layout-dependency/2":
        return None
    source_ids = proof["sourceNodeIds"]
    if (not vector(proof["minimumDesiredSize"], 2, True) or not isinstance(source_ids, list) or not source_ids
            or any(not isinstance(v, str) or not ID.fullmatch(v) for v in source_ids)
            or len(set(source_ids)) != len(source_ids) or not isinstance(proof["evidenceId"], str) or not EVIDENCE.fullmatch(proof["evidenceId"])):
        return None
    roots = [n for n in by_id.values() if n.get("parent") is None]
    if (len(roots) != 1 or roots[0].get("role") not in {"screen.root", "container.canvas"}
            or not isinstance(roots[0].get("properties", {}), dict)
            or roots[0].get("properties", {}).get("visibility") in {"Hidden", "Collapsed"}):
        return None
    children = {}
    for n in by_id.values():
        if not isinstance(n.get("properties", {}), dict):
            return None
        children.setdefault(n.get("parent"), []).append(n)
    visible_roots = [n for n in children.get(roots[0].get("id"), []) if n.get("properties", {}).get("visibility") != "Collapsed"]
    slot = node.get("slotLayout", {})
    if (len(visible_roots) != 1 or visible_roots[0] is not node or node.get("role") != "container.size"
            or not size_constraints(node.get("sizeBoxConstraints")) or not isinstance(slot, dict)
            or slot.get("autoSize") is not True or slot.get("anchors") != {"minimum": [0, 0], "maximum": [0, 0]}
            or slot.get("alignment", [0, 0]) != [0, 0] or not isinstance(slot.get("offsets", {}), dict)
            or slot.get("offsets", {}).get("left", 0) != 0 or slot.get("offsets", {}).get("top", 0) != 0):
        return None
    sources, reached, visiting = set(source_ids), set(), set()

    def walk(current, available=None, fill_leaf=False):
        cid, role = current.get("id"), current.get("role")
        if cid in visiting:
            return None
        props = current.get("properties", {})
        if not isinstance(props, dict):
            return None
        if props.get("visibility") in {"Hidden", "Collapsed"}:
            return None  # Hidden graphics cannot establish a visible lower bound.
        contents = children.get(cid, [])
        if role in {"visual.image", "text.label"}:
            if contents:
                return None
            if role == "visual.image":
                size = props.get("brushImageSize")
                if fill_leaf or not vector(size, 2, True):
                    return None
                if cid in sources:
                    reached.add(cid)
                return (float(size[0]) if cid in sources else 0.0,
                        float(size[1]) if cid in sources else 0.0, float(size[0]))
            if cid in sources:
                return None
            wrap = props.get("wrapTextAt")
            if fill_leaf:
                if not number(available, True) or (wrap is not None and (not number(wrap) or wrap < 0)):
                    return None
                # Allocated width is known; no font metric or line-height is invented.
                return (0.0, 0.0, float(available))
            return (0.0, 0.0, float(wrap)) if number(wrap, True) else None
        if cid in sources:
            return None
        visiting.add(cid)
        try:
            if role == "container.size":
                constraints = current.get("sizeBoxConstraints")
                if set(props) - {"visibility"} or not size_constraints(constraints) or len(contents) != 1:
                    return None
                child = contents[0]
                child_slot = child.get("sizeBoxSlot")
                if (not slot_fields(child_slot) or set(child_slot) != {"padding", "horizontalAlignment", "verticalAlignment"}
                        or child_slot["padding"] != [0, 0, 0, 0] or child_slot["horizontalAlignment"] != "Fill" or child_slot["verticalAlignment"] != "Fill"):
                    return None
                width = constraints["widthOverride"]
                value = walk(child, width)
                if value is None or value[2] > width + 1e-6:
                    return None
                return (float(width), value[1], float(width))
            if role not in {"container.overlay", "container.vertical", "container.horizontal"}:
                return None
            values, fills, reserved = [], [], 0.0
            for child in contents:
                child_slot = child.get("overlaySlot" if role == "container.overlay" else "flowSlot")
                if not slot_fields(child_slot, role != "container.overlay"):
                    return None
                padding = child_slot.get("padding", [0, 0, 0, 0])
                px, py = padding[0] + padding[2], padding[1] + padding[3]
                fill = role != "container.overlay" and child_slot["size"]["rule"] == "Fill"
                if fill:
                    if role != "container.horizontal" or child.get("role") != "text.label" or children.get(child.get("id")) or not number(available, True):
                        return None
                    fills.append((child, child_slot["size"]["weight"], px, py))
                    reserved += px
                    continue
                child_width = available - px if number(available, True) and child_slot["horizontalAlignment"] == "Fill" and role != "container.horizontal" else None
                if child_width is not None and child_width <= 0:
                    return None
                value = walk(child, child_width)
                if value is None:
                    return None
                values.append((value[0] + px, value[1] + py, value[2] + px))
                reserved += value[2] + px
            if fills:
                if reserved >= available:
                    return None
                weight = sum(item[1] for item in fills)
                if not number(weight, True):
                    return None
                for child, fraction, px, py in fills:
                    value = walk(child, (available - reserved) * fraction / weight, True)
                    if value is None:
                        return None
                    values.append((px, py, value[2] + px))
            if not values:
                return (0.0, 0.0, 0.0)
            return (sum(v[0] for v in values) if role == "container.horizontal" else max(v[0] for v in values),
                    sum(v[1] for v in values) if role == "container.vertical" else max(v[1] for v in values),
                    sum(v[2] for v in values) if role == "container.horizontal" else max(v[2] for v in values))
        finally:
            visiting.remove(cid)

    result = walk(node)
    expected = proof["minimumDesiredSize"]
    if (result is None or reached != sources or result[0] != expected[0]
            or not all(number(v, True) for v in result) or abs(result[1] - expected[1]) > 1e-6):
        return None
    return result


def bounded_wrap_capacity(node, parent, reference_size):
    """Validate a declared fixed capacity; maxLines does not prove rendered fit."""
    capacity = node.get("textCapacity")
    if not isinstance(capacity, dict) or set(capacity) != {"kind", "capacitySize", "maxLines", "evidenceId"}:
        return False
    size = capacity["capacitySize"]
    if (capacity["kind"] != "bounded-wrap/1" or not vector(size, 2, True)
            or type(capacity["maxLines"]) is not int or capacity["maxLines"] <= 0
            or not isinstance(capacity["evidenceId"], str) or not EVIDENCE.fullmatch(capacity["evidenceId"])):
        return False
    props, slot = node.get("properties", {}), node.get("slotLayout", {})
    if (node.get("role") != "text.label" or parent.get("role") not in {"screen.root", "container.canvas"}
            or not isinstance(props, dict) or not number(props.get("wrapTextAt"), True) or props["wrapTextAt"] > size[0]
            or not isinstance(slot, dict) or slot.get("autoSize") is not False):
        return False
    anchors, offsets = slot.get("anchors", {}), slot.get("offsets", {})
    rect, parent_rect = node.get("rect"), parent.get("rect")
    if (not isinstance(anchors, dict) or not vector(anchors.get("minimum"), 2) or anchors.get("minimum") != anchors.get("maximum")
            or any(v not in {0, 0.5, 1} for v in anchors["minimum"])
            or not vector(slot.get("alignment"), 2) or any(v < 0 or v > 1 for v in slot["alignment"])
            or not isinstance(offsets, dict) or not all(number(offsets.get(k)) for k in ("left", "top", "right", "bottom"))
            or not vector(rect, 4) or not vector(parent_rect, 4) or not vector(reference_size, 2, True)):
        return False
    # Fixed dimensions are exact; only normalized-coordinate arithmetic gets epsilon.
    if [offsets["right"], offsets["bottom"]] != size:
        return False
    for axis in (0, 1):
        dimension = reference_size[axis]
        expected_position = ((rect[axis] - parent_rect[axis]) * dimension
                             - anchors["minimum"][axis] * parent_rect[axis + 2] * dimension
                             + slot["alignment"][axis] * size[axis])
        if abs(rect[axis + 2] * dimension - size[axis]) > 1e-6 or abs(offsets[("left", "top")[axis]] - expected_position) > 1e-6:
            return False
    return True
