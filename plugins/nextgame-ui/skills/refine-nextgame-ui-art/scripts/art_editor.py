"""Reviewed, schema-discovered Unreal adapter for the optional art stage.

Only the fixed operations below reach the Editor. Model-produced Python or MCP
tool names are never accepted. Unknown host capabilities fail explicitly.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Protocol

UMG = "UMGToolSet.UMGToolSet"
OBJ = "editor_toolset.toolsets.object.ObjectTools"
BP = "editor_toolset.toolsets.blueprint.BlueprintTools"
ASSET = "editor_toolset.toolsets.asset.AssetTools"
PROGRAM = "editor_toolset.toolsets.programmatic.ProgrammaticToolset"
IMAGING = "EditorToolset.EditorAppToolset"
TEXTURE = "editor_toolset.toolsets.texture.TextureTools"
TEXTURE_STANDARD = {"compressionSettings": "TC_BC7", "lODGroup": "TEXTUREGROUP_UI", "mipGenSettings": "TMGS_NoMipmaps", "sRGB": True}
TEXTURE_VISUAL_FIELDS = frozenset(TEXTURE_STANDARD) | {"filter", "neverStream", "virtualTextureStreaming", "lODBias", "maxTextureSize",
    "powerOfTwoMode", "paddingColor", "bFlipGreenChannel", "sourceColorSettings", "alphaCoverageThresholds"}
VISUAL_PROPERTIES = frozenset({
    "brush", "brushDelegate", "colorAndOpacity", "foregroundColor", "renderOpacity", "font",
    "widgetStyle", "shadowColorAndOpacity", "shadowOffset", "text", "justification", "wrapTextAt",
    "autoWrapText", "minDesiredWidth", "lineHeightPercentage", "renderTransform", "renderTransformPivot",
    "visibility", "clipping", "pixelSnapping", "zOffset", "padding", "entryWidgetClass", "orientation",
    "entryWidth", "entryHeight", "horizontalEntrySpacing", "verticalEntrySpacing", "navigation",
    "widthOverride", "heightOverride", "minDesiredHeight", "maxDesiredWidth", "maxDesiredHeight",
    "bOverride_WidthOverride", "bOverride_HeightOverride", "bOverride_MinDesiredWidth",
    "bOverride_MinDesiredHeight", "bOverride_MaxDesiredWidth", "bOverride_MaxDesiredHeight",
})
SLOT_PROPERTIES = frozenset({
    "layoutData", "anchors", "offsets", "alignment", "autoSize", "bAutoSize", "zOrder", "padding", "size",
    "horizontalAlignment", "verticalAlignment", "row", "column", "rowSpan", "columnSpan", "layer",
    "nudge", "horizontalAlignment", "verticalAlignment",
})
# Top-level setters are intentionally narrower than readback: no input, binding,
# entry class, visibility or runtime-control mutation is authorized by art alone.
WRITE_PROPERTIES = VISUAL_PROPERTIES - {"entryWidgetClass", "navigation", "brushDelegate", "orientation",
    "entryWidth", "entryHeight", "horizontalEntrySpacing", "verticalEntrySpacing"}
STATIC_CLASSES = frozenset({"/Script/UIFramework.GameImage", "/Script/UMG.TextBlock", "/Script/UMG.CanvasPanel",
    "/Script/UMG.Overlay", "/Script/UMG.VerticalBox", "/Script/UMG.HorizontalBox", "/Script/UMG.SizeBox"})
MULTI_CHILD_SLOT_CLASSES = {"/Script/UMG." + panel: "/Script/UMG." + slot for panel, slot in [
    ("CanvasPanel", "CanvasPanelSlot"), ("Overlay", "OverlaySlot"), ("VerticalBox", "VerticalBoxSlot"), ("HorizontalBox", "HorizontalBoxSlot")]}


class CapabilityError(RuntimeError):
    """The connected Editor cannot provide evidence required by this action."""


class RendererUnavailable(CapabilityError):
    """No isolated renderer can prove the requested UMG preview conditions."""


class Transport(Protocol):
    def describe(self, toolset: str) -> dict: ...
    def call(self, toolset: str, tool: str, arguments: dict) -> Any: ...


def _value(result: Any) -> Any:
    value = result.get("returnValue") if isinstance(result, dict) and "returnValue" in result else result
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            pass
    return value


def _ref(value: Any) -> str | None:
    if isinstance(value, dict):
        value = value.get("refPath")
    return value if isinstance(value, str) and value not in {"", "None", "null"} else None


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def _asset(path: str) -> str:
    if not isinstance(path, str) or not re.fullmatch(r"/Game/[A-Za-z0-9_/]+(?:\.[A-Za-z0-9_]+)?", path):
        raise ValueError("Expected a /Game package or object path")
    if "." in path:
        package, name = path.split(".")
        if package.rsplit("/", 1)[-1] != name:
            raise ValueError("Asset object basename does not match its package")
        return package
    return path


def _object(path: str) -> dict:
    package = _asset(path)
    return {"refPath": package + "." + package.rsplit("/", 1)[-1]}


class HttpTransport:
    """Use the bundled MCP client and the server's registry wrappers."""
    def __init__(self, url: str, timeout: float = 60):
        path = Path(__file__).resolve().parents[2] / "build-nextgame-umg/scripts/execute_plan.py"
        spec = importlib.util.spec_from_file_location("_nextgame_art_mcp", path)
        if spec is None or spec.loader is None:
            raise CapabilityError("Bundled NextGame MCP client unavailable")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.client = module.McpClient(url, timeout)
        self.client.initialize()

    def describe(self, toolset: str) -> dict:
        c = self.client
        response, _ = c._post({"jsonrpc": "2.0", "id": c.next_id, "method": "tools/call",
            "params": {"name": "describe_toolset", "arguments": {"toolset_name": toolset}}})
        c.next_id += 1
        if response.get("error") or response.get("result", {}).get("isError"):
            raise CapabilityError(f"Cannot discover {toolset}")
        blocks = response.get("result", {}).get("content", [])
        if not blocks or blocks[0].get("type") != "text":
            raise CapabilityError(f"Registry returned no schema for {toolset}")
        result = json.loads(blocks[0]["text"])
        if not isinstance(result.get("tools"), list):
            raise CapabilityError(f"Registry tool list missing for {toolset}")
        return result

    def call(self, toolset: str, tool: str, arguments: dict) -> Any:
        return self.client.call_tool(toolset, tool, arguments)


class ArtEditor:
    def __init__(self, transport: Transport, *, nxue: Any = None):
        self.transport = transport
        self.nxue = nxue
        self.schemas: dict[str, dict] = {}
        self.environment: dict | None = None

    def _schema(self, toolset: str, tool: str) -> dict:
        if toolset not in self.schemas:
            self.schemas[toolset] = self.transport.describe(toolset)
        full = toolset + "." + tool
        for schema in self.schemas[toolset]["tools"]:
            if schema.get("name") == full:
                if "inputSchema" not in schema:
                    raise CapabilityError(f"Input schema absent: {full}")
                # Missing outputSchema is a declared void return, not an assumed
                # returnValue. Fixed programs below never parse void outputs.
                return schema
        raise CapabilityError(f"Required registered tool absent: {full}")

    def _call(self, toolset: str, tool: str, args: dict) -> Any:
        schema = self._schema(toolset, tool)
        declared = schema["inputSchema"]
        missing = set(declared.get("required", [])) - set(args)
        unknown = set(args) - set(declared.get("properties", {}))
        if missing or unknown:
            raise CapabilityError(f"Host schema mismatch for {tool}: missing={sorted(missing)}, unknown={sorted(unknown)}")
        return self.transport.call(toolset, tool, args)

    def _program(self, body: str, payload: dict, calls: list[tuple[str, str]], *, modules: tuple[str, ...] = ()) -> Any:
        if self.environment is None:
            self.environment = _value(self._call(PROGRAM, "get_execution_environment", {}))
            if (self.environment.get("language") != "python" or
                "execute_tool" not in self.environment.get("instructions", "") or
                "json" not in [x.get("name") for x in self.environment.get("supported_modules", [])]):
                raise CapabilityError("Unsupported ProgrammaticToolset execution environment")
        supported = {item.get("name") for item in self.environment.get("supported_modules", [])}
        if not set(modules) <= supported or not set(modules) <= {"math"}:
            raise CapabilityError("Required safe ProgrammaticToolset module is unavailable")
        wrappers = []
        for index, (toolset, tool) in enumerate(calls):
            self._schema(toolset, tool)  # Input AND output schemas before dispatch.
            wrappers.append(f"def call_{index}(args):\n    try:\n        return execute_tool({(toolset + '.' + tool)!r}, json.dumps(args))\n    except Exception as error:\n        raise RuntimeError({(toolset + '.' + tool)!r} + ' ' + json.dumps(args) + ': ' + str(error))\n")
        script = "import json\n" + "".join("import " + name + "\n" for name in modules) + "\n".join(wrappers)
        script += "\ndef unpack(value):\n    value = value['returnValue'] if 'returnValue' in value else value\n    if isinstance(value, str):\n        try:\n            return json.loads(value)\n        except ValueError:\n            pass\n    return value\n"
        script += "\ndef run():\n    data = json.loads(" + repr(json.dumps(payload, ensure_ascii=False)) + ")\n"
        script += "\n".join("    " + line if line else "" for line in body.splitlines()) + "\n"
        return _value(self._call(PROGRAM, "execute_tool_script", {"script": script}))

    def _tree(self, asset_path: str) -> dict:
        tree = _value(self._call(UMG, "GetWidgets", {"widgetBlueprint": _object(asset_path)}))
        if not isinstance(tree, dict) or not isinstance(tree.get("widgets"), list) or not tree.get("info"):
            raise CapabilityError(f"Invalid actual WidgetTree for {asset_path}")
        return tree

    def snapshot(self, asset_paths: list[str]) -> dict:
        paths = [_asset(p) for p in asset_paths]
        if not paths or len(paths) != len(set(paths)):
            raise ValueError("Snapshot needs nonempty unique asset paths")
        raw = self._program(_SNAPSHOT_PROGRAM,
            {"paths": paths, "visualProperties": sorted(VISUAL_PROPERTIES), "slotProperties": sorted(SLOT_PROPERTIES)},
            [(UMG, "GetWidgets"), (OBJ, "list_properties"), (OBJ, "get_properties"), (OBJ, "get_class"),
             (BP, "get_default_object"), (UMG, "GetNamedSlots"), (BP, "list_graphs"), (BP, "read_graph_dsl")])
        assets = []
        used_mode_fallback = False
        for item in raw["assets"]:
            tree = item["tree"]
            names = {_ref(w["widget"]): w["widgetName"] for w in tree["widgets"]}
            protected = {w["widgetName"] for w in tree["widgets"] if w["bIsVariable"] or w.get("bInherited")}
            for slot in item["namedSlots"]:
                protected.update(names[r] for r in (_ref(slot.get("hostWidget")), _ref(slot.get("contentWidget"))) if r in names)
            # DSL text is retained only in the digest. Incomplete extraction
            # never grants structural permission; every node is conservative.
            graph_text = json.dumps(item["graphs"], ensure_ascii=False)
            protected.update(name for name in names.values() if name in graph_text)
            widgets = []
            for entry in item["widgets"]:
                info = entry["info"]
                actual_class = _ref(entry["actualClass"])
                if not actual_class:
                    raise CapabilityError("Actual widget class was not returned for " + info["widgetName"])
                widgets.append({"widgetName": info["widgetName"], "classPath": actual_class,
                    "parentWidgetName": names.get(_ref(info.get("parent"))) or names.get(_ref(info.get("namedSlotHost"))),
                    "isVariable": info["bIsVariable"], "properties": entry["properties"],
                    "slot": {"classPath": _ref(entry.get("slotClass")), "properties": entry["slotProperties"]}})
            mode = item["cdoProperties"].get("designSizeMode")
            uncertainty = ["Animation bindings, native and external Lua references are not completely enumerated by this adapter."]
            if mode is None and self.nxue is not None and hasattr(self.nxue, "design_size_mode"):
                try:
                    mode = self.nxue.design_size_mode(_ref(item["cdo"]))
                    used_mode_fallback = True
                except CapabilityError as exc:
                    uncertainty.append("Read-only Designer mode fallback failed: " + str(exc))
            if mode is None:
                uncertainty.append("Generated CDO designSizeMode is not exposed by the connected official ObjectTools schema.")
            references = {"graphs": item["graphs"], "namedSlots": item["namedSlots"],
                "protected": sorted(protected), "complete": False, "parentClass": tree["info"]["parentClass"]}
            assets.append({"assetPath": item["assetPath"], "parentClassPath": _ref(tree["info"]["parentClass"]),
                "designSizeMode": mode, "protectedReferences": sorted(protected), "referencesComplete": False,
                "referencesDigest": _digest(references), "uncertainties": uncertainty, "widgets": widgets})
        acquisition = {"method": "official-unreal-mcp"}
        if used_mode_fallback:
            acquisition = {"method": "mixed", "fallbackReason": "Official generated-CDO property schema omits DesignSizeMode; exact returned CDO/property read with NxUE manage-property get."}
        return {"version": 1, "kind": "nextgame-ui-art-snapshot", "capturedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
            "acquisition": acquisition, "assets": assets}

    def _widget(self, asset_path: str, name: str) -> dict:
        matches = [w for w in self._tree(asset_path)["widgets"] if w["widgetName"] == name]
        if len(matches) != 1:
            raise CapabilityError(f"Expected exactly one actual widget {name}, found {len(matches)}")
        return matches[0]

    def _set(self, instance: dict, property_path: str, before: Any, after: Any, *, slot: bool = False):
        parts = property_path.split(".")
        if not parts or any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", p) for p in parts):
            raise ValueError("Invalid property path")
        if parts[0] not in (SLOT_PROPERTIES if slot else WRITE_PROPERTIES):
            raise ValueError("Property outside art adapter allowlist: " + property_path)
        self._program(_SET_PROGRAM, {"instance": instance, "parts": parts, "before": before, "after": after},
            [(OBJ, "list_properties"), (OBJ, "get_properties"), (OBJ, "set_properties")], modules=("math",))

    def execute_batch(self, operations: list[dict]) -> dict:
        """One fixed official program; real per-operation CAS/write/read receipts."""
        if not isinstance(operations, list) or not 1 <= len(operations) <= 256:
            raise CapabilityError("Set batch must contain 1 through 256 operations")
        keys, ids = set(), set()
        for op in operations:
            kind = op.get("kind")
            if kind not in {"set-property", "set-slot"}:
                raise CapabilityError("Only allowlisted property/Slot sets can be batched")
            _asset(op["assetPath"])
            parts = op["property"].split(".")
            if not parts or any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", part) for part in parts):
                raise CapabilityError("Invalid batch property path")
            if parts[0] not in (SLOT_PROPERTIES if kind == "set-slot" else WRITE_PROPERTIES):
                raise CapabilityError("Batch property outside the existing art allowlist")
            key = (op["assetPath"], op["widgetName"], kind, op["property"])
            if op.get("id") in ids or key in keys:
                raise CapabilityError("Duplicate batch operation/property; use the single-step path")
            if any(key[:3] == other[:3] and (key[3].startswith(other[3] + ".") or other[3].startswith(key[3] + ".")) for other in keys):
                raise CapabilityError("Overlapping batch property paths; use the single-step path")
            ids.add(op.get("id")); keys.add(key)
        return self._program(_SET_BATCH_PROGRAM, {"operations": operations},
            [(UMG, "GetWidgets"), (OBJ, "list_properties"), (OBJ, "get_properties"), (OBJ, "set_properties")], modules=("math",))

    def execute(self, operation: dict) -> None:
        kind = operation.get("kind")
        if kind == "import-resource":
            self._import(operation)
            return
        path = _asset(operation["assetPath"])
        if kind in {"remove-widget", "reparent-widget"}:
            # Do not allow a caller-supplied boolean to replace actual reference
            # evidence. This host cannot yet prove all binding types.
            raise CapabilityError("Structural removal/reparent blocked: animation/native/Lua references are incomplete")
        if kind == "add-widget":
            self._add(operation)
            return
        if kind not in {"set-property", "set-slot"}:
            raise ValueError(f"Unsupported art operation {kind!r}")
        widget = self._widget(path, operation["widgetName"])
        instance = widget["slot"] if kind == "set-slot" else widget["widget"]
        if not _ref(instance):
            raise CapabilityError("Root or named-slot content has no editable parent Slot")
        self._set(instance, operation["property"], operation["before"], operation["after"], slot=kind == "set-slot")

    def _add(self, op: dict):
        self._preflight_add(op, allow_existing=False)
        after = op["after"]
        if after.get("classPath") not in STATIC_CLASSES or after.get("isVariable") is not False:
            raise ValueError("Only allowlisted static visual widgets can be added")
        name = op["widgetName"]
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name):
            raise ValueError("Invalid widget name")
        tree = self._tree(op["assetPath"])
        if any(w["widgetName"] == name for w in tree["widgets"]):
            raise CapabilityError("Widget already exists; reconcile actual state before retrying add")
        parent_name = after.get("parentWidgetName")
        parent = self._widget(op["assetPath"], parent_name) if parent_name else None
        if parent is None and tree["widgets"]:
            raise CapabilityError("Cannot replace a nonempty WidgetTree root")
        # Core refuses unproven structural edits. Adapter additionally checks
        # capacity at the destination; only generic multi-child Panels qualify.
        if parent and _ref(parent["widgetClassPath"]) not in {
            "/Script/UMG.CanvasPanel", "/Script/UMG.Overlay", "/Script/UMG.VerticalBox", "/Script/UMG.HorizontalBox"}:
            raise CapabilityError("Adding to single-child, runtime-collection or unknown parents is unsupported")
        args = {"widgetBlueprint": _object(op["assetPath"]), "widgetClass": {"refPath": after["classPath"]},
            "widgetDisplayName": name, "childIndex": -1}
        if parent:
            args["parentWidget"] = parent["widget"]
        # The exact class and Slot schemas were validated before mutation.
        for is_slot, values in [(False, after.get("properties", {})), (True, after.get("slot", {}).get("properties", {}))]:
            allowed = SLOT_PROPERTIES if is_slot else WRITE_PROPERTIES
            if set(values) - allowed:
                raise ValueError("Add contains non-art properties")
        info = _value(self._call(UMG, "AddWidget", args))
        if not isinstance(info, dict) or info.get("widgetName") != name or not _ref(info.get("widget")):
            raise CapabilityError("AddWidget did not create the exact requested widget; inspect partial operation")
        self._call(UMG, "ToggleWidgetAsVariable", {"widgetBlueprint": _object(op["assetPath"]), "widget": info["widget"], "bIsVariable": False})
        # Reacquire after every structural operation. Properties are initialized
        # with live before-values so failed partial initialization is visible.
        for is_slot, values in [(False, after.get("properties", {})), (True, after.get("slot", {}).get("properties", {}))]:
            current = self._widget(op["assetPath"], name)
            instance = current["slot" if is_slot else "widget"]
            if values and not _ref(instance):
                raise CapabilityError("New widget lacks requested Slot; inspect partial operation")
            for key, value in values.items():
                schema = _value(self._call(OBJ, "list_properties", {"instance": instance}))
                if key not in schema:
                    raise CapabilityError(f"New widget property missing: {key}")
                before = _value(self._call(OBJ, "get_properties", {"instance": instance, "properties": [key]}))[key]
                self._set(instance, key, before, value, slot=is_slot)

    def _preflight_add(self, op: dict, *, tree: dict | None = None, allow_existing: bool = True) -> dict:
        after = op["after"]
        name = op["widgetName"]
        if after.get("classPath") not in STATIC_CLASSES or after.get("isVariable") is not False:
            raise ValueError("Only allowlisted static visual widgets can be added")
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name):
            raise ValueError("Invalid widget name")
        tree = self._tree(op["assetPath"]) if tree is None else tree
        existing = next((w for w in tree["widgets"] if w["widgetName"] == name), None)
        if existing:
            if not allow_existing:
                raise CapabilityError("Widget already exists; reconcile actual state before retrying add")
            if _ref(existing["widgetClassPath"]) != after["classPath"] or existing["bIsVariable"] is not False:
                raise CapabilityError("Existing added widget has changed class/variable status")
        parent = next((w for w in tree["widgets"] if w["widgetName"] == after.get("parentWidgetName")), None)
        if parent is None:
            raise CapabilityError("Static append requires an explicit existing or earlier planned parent")
        parent_class = _ref(parent["widgetClassPath"])
        if parent_class not in MULTI_CHILD_SLOT_CLASSES:
            raise CapabilityError("Adding to single-child, runtime-collection or unknown parents is unsupported")
        slot_class = MULTI_CHILD_SLOT_CLASSES[parent_class]
        if after.get("slot", {}).get("classPath") != slot_class:
            raise CapabilityError("Added widget Slot class must match its actual parent")
        for is_slot, class_path, values in [(False, after["classPath"], after.get("properties", {})),
                (True, slot_class, after.get("slot", {}).get("properties", {}))]:
            if set(values) - (SLOT_PROPERTIES if is_slot else WRITE_PROPERTIES):
                raise ValueError("Add contains non-art properties")
            schema = _value(self._call(OBJ, "list_properties", {"instance": {"refPath": class_path}}))
            def check_fields(fields, schemas):
                for key, value in fields.items():
                    if key not in schemas:
                        raise CapabilityError("Added widget property is not exposed: " + key)
                    definition = schemas[key]
                    if "enum" in definition and value not in definition["enum"]:
                        raise CapabilityError("Added widget enum is unsupported: " + key)
                    if isinstance(value, dict) and "properties" in definition:
                        check_fields(value, definition["properties"])
            check_fields(values, schema)
        for tool in ["AddWidget", "ToggleWidgetAsVariable", "CompileWidgetBlueprint"]:
            self._schema(UMG, tool)
        self._schema(OBJ, "set_properties")
        self._schema(ASSET, "save_assets")
        return {"widgetName": name, "widgetClassPath": {"refPath": after["classPath"]}, "bIsVariable": False}

    def _import_input(self, operation: dict) -> tuple[Path, str, str]:
        after = operation["after"]
        source = Path(after["sourcePath"]).resolve(strict=True)
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        if digest != after["sha256"]:
            raise ValueError("Import source changed since planning")
        destination = _asset(after["destinationPath"])
        if source.suffix.lower() != ".png" or not destination.startswith("/Game/UI/Textures/"):
            raise CapabilityError("Direct importer handles UI standalone PNG only; atlas/icon resources require the existing project import workflow")
        self._schema(TEXTURE, "import_file")
        if self.nxue is None:
            raise CapabilityError("Source-identity verification requires the narrow NxUE read fallback; import is blocked before mutation")
        self.nxue.check_texture_identity_capability()
        return source, digest, destination

    def _texture_state(self, destination: str) -> dict:
        instance = _object(destination)
        schema = _value(self._call(OBJ, "list_properties", {"instance": instance}))
        if not set(TEXTURE_STANDARD) <= set(schema):
            raise CapabilityError("Actual texture schema cannot express the confirmed UI texture standard")
        keys = sorted(k for k in schema if k in TEXTURE_VISUAL_FIELDS or k.startswith("adjust"))
        values = _value(self._call(OBJ, "get_properties", {"instance": instance, "properties": keys}))
        identity = self.nxue.texture_identity(destination)
        if identity.get("assetPath") != destination or not identity.get("sourceId"):
            raise CapabilityError("Actual texture source identity is unavailable")
        return {"sourceId": identity["sourceId"], "properties": values}

    def verify_import(self, operation: dict, *, require_exists: bool = True) -> dict:
        """Read-only identity check, including on completed/no-op import retries."""
        source, digest, destination = self._import_input(operation)
        exists = _value(self._call(ASSET, "exists", {"path": destination}))
        if exists is False and not require_exists:
            return {"exists": False, "assetPath": destination}
        if exists is not True:
            raise CapabilityError("Previously imported destination is missing: " + destination)
        tags = _value(self._call(ASSET, "get_metadata_tags", {"asset_path": destination}))
        state = self._texture_state(destination)
        if (tags.get("NextGameArt.SourceSha256") != digest or tags.get("NextGameArt.TextureFingerprint") != _digest(state)
                or any(state["properties"].get(k) != v for k, v in TEXTURE_STANDARD.items())):
            raise CapabilityError("Existing imported texture identity or appearance changed; refusing overwrite/reuse")
        return {"exists": True, "assetPath": destination, "sha256": digest, "textureFingerprint": _digest(state)}

    def _import(self, operation: dict):
        source, digest, destination = self._import_input(operation)
        existing = self.verify_import(operation, require_exists=False)
        if existing["exists"]:
            return
        imported = _value(self._call(TEXTURE, "import_file", {"folder_path": destination.rsplit("/", 1)[0],
            "asset_name": destination.rsplit("/", 1)[1], "source_file": str(source)}))
        if not isinstance(imported, list) or len(imported) != 1 or _ref(imported[0]) != _object(destination)["refPath"]:
            raise CapabilityError("Official import did not produce exactly the requested resource; inspect partial import")
        actual_class = _value(self._call(OBJ, "get_class", {"instance": imported[0]}))
        if _ref(actual_class) != "/Script/Engine.Texture2D":
            raise CapabilityError("Imported resource is not Texture2D")
        self._program("""schema = unpack(call_0({'instance': data['instance']}))
for key, value in data['values'].items():
    if key not in schema or ('enum' in schema[key] and value not in schema[key]['enum']):
        raise RuntimeError('UI texture standard incompatible with actual host schema')
current = unpack(call_1({'instance': data['instance'], 'properties': list(data['values'])}))
if current != data['values'] and unpack(call_2({'instance': data['instance'], 'values': json.dumps(data['values'])})) is not True:
    raise RuntimeError('Failed to apply confirmed UI texture standard')
return {'updated': current != data['values']}""", {"instance": imported[0], "values": TEXTURE_STANDARD},
            [(OBJ, "list_properties"), (OBJ, "get_properties"), (OBJ, "set_properties")])
        state = self._texture_state(destination)
        if any(state["properties"].get(k) != v for k, v in TEXTURE_STANDARD.items()):
            raise CapabilityError("Texture standard readback differs after import")
        self._call(ASSET, "update_metadata_tags", {"asset_path": destination,
            "set_tags": {"NextGameArt.SourceSha256": digest, "NextGameArt.TextureFingerprint": _digest(state)}})
        if _value(self._call(ASSET, "save_assets", {"asset_paths": [destination]})) is not True:
            raise CapabilityError("Imported texture save failed")
        self.verify_import(operation)

    def preflight(self, operations: list[dict]) -> dict:
        """Check all capabilities and completed resource identities before writes."""
        checked = []
        trees = {}
        for op in operations:
            kind = op.get("kind")
            if kind == "import-resource":
                self.verify_import(op, require_exists=False)
            elif kind in {"remove-widget", "reparent-widget"}:
                raise CapabilityError("Structural removal/reparent blocked: animation/native/Lua references are incomplete")
            elif kind == "add-widget":
                path = _asset(op["assetPath"])
                if path not in trees:
                    trees[path] = self._tree(path)
                planned = self._preflight_add(op, tree=trees[path])
                if not any(w["widgetName"] == op["widgetName"] for w in trees[path]["widgets"]):
                    trees[path]["widgets"].append(planned)
            elif kind in {"set-property", "set-slot"}:
                path = _asset(op["assetPath"])
                if path not in trees:
                    trees[path] = self._tree(path)
                matches = [w for w in trees[path]["widgets"] if w["widgetName"] == op["widgetName"]]
                if len(matches) != 1:
                    raise CapabilityError("Expected one actual preflight widget: " + op["widgetName"])
                widget = matches[0]
                instance = widget["slot" if kind == "set-slot" else "widget"]
                if not _ref(instance):
                    raise CapabilityError("Requested widget has no editable Slot")
                parts = op["property"].split(".")
                if parts[0] not in (SLOT_PROPERTIES if kind == "set-slot" else WRITE_PROPERTIES):
                    raise CapabilityError("Non-art property requested")
                schema = _value(self._call(OBJ, "list_properties", {"instance": instance}))
                cursor = {"properties": schema}
                for part in parts:
                    if part not in cursor.get("properties", {}):
                        raise CapabilityError("Actual property schema missing: " + op["property"])
                    cursor = cursor["properties"][part]
                self._schema(OBJ, "set_properties")
                self._schema(UMG, "CompileWidgetBlueprint")
                self._schema(ASSET, "save_assets")
            else:
                raise CapabilityError("Unsupported operation: " + str(kind))
            checked.append(op.get("id"))
        return {"ok": True, "operationIds": checked, "canonicalCapture": False}

    def compile_save(self, asset_paths: list[str]) -> None:
        paths = list(dict.fromkeys(_asset(p) for p in asset_paths))
        if not paths:
            return
        self._program("""for path in data['paths']:
    blueprint = {'refPath': path + '.' + path.rsplit('/', 1)[-1]}
    if unpack(call_0({'widgetBlueprint': blueprint})) is not True:
        raise RuntimeError('Widget Blueprint compile failed: ' + path)
if unpack(call_1({'asset_paths': data['paths']})) is not True:
    raise RuntimeError('Asset save failed')
return {'saved': data['paths']}""", {"paths": paths}, [(UMG, "CompileWidgetBlueprint"), (ASSET, "save_assets")])

    def capture(self, asset_path: str, output_path: Path, context: dict) -> dict:
        _asset(asset_path)
        self._schema(IMAGING, "CaptureAssetImage")
        raise RendererUnavailable("Canonical UMG capture unavailable: registered CaptureAssetImage accepts only assetPath, "
            "not resolution, DPI, state or preview data. Generic thumbnails/screenshots cannot verify fixed render context. "
            "A reviewed host renderer adapter is required; no output or render evidence was written.")

    def capabilities(self) -> dict:
        for ts in [UMG, OBJ, ASSET, TEXTURE, IMAGING, BP, PROGRAM]:
            if ts not in self.schemas:
                self.schemas[ts] = self.transport.describe(ts)
        return {"method": "official-unreal-mcp", "propertyWrites": True, "slotWrites": True,
            "compileSave": True, "staticAdd": True, "removeReparent": False, "referencesComplete": False,
            "canonicalCapture": False, "standalonePngImport": self.nxue is not None,
            "importMethod": "official-unreal-mcp", "importIdentityMethod": "nxue-readonly-fallback" if self.nxue is not None else None,
            "limitations": ["All names are discovered from current registry schemas before use.",
                "Complete animation/native/Lua reference enumeration is unavailable.",
                "Generated-CDO designSizeMode may be absent and is never inferred.",
                "No fixed resolution/DPI/state UMG render API is registered on the probed host.",
                "Atlas/icon imports remain in the existing project resource import workflow."]}


_SNAPSHOT_PROGRAM = """assets = []
for path in data['paths']:
    blueprint = {'refPath': path + '.' + path.rsplit('/', 1)[-1]}
    tree = unpack(call_0({'widgetBlueprint': blueprint}))
    records = []
    for info in tree['widgets']:
        schema = unpack(call_1({'instance': info['widget']}))
        keys = [key for key in data['visualProperties'] if key in schema]
        properties = unpack(call_2({'instance': info['widget'], 'properties': keys})) if keys else {}
        slot = info.get('slot')
        slot_properties = {}
        slot_class = None
        if isinstance(slot, dict) and slot.get('refPath'):
            slot_schema = unpack(call_1({'instance': slot}))
            slot_keys = [key for key in data['slotProperties'] if key in slot_schema]
            slot_properties = unpack(call_2({'instance': slot, 'properties': slot_keys})) if slot_keys else {}
            slot_class = unpack(call_3({'instance': slot}))
        actual_class = unpack(call_3({'instance': info['widget']}))
        records.append({'info': info, 'actualClass': actual_class, 'properties': properties, 'slotProperties': slot_properties, 'slotClass': slot_class})
    cdo = unpack(call_4({'blueprint': blueprint}))
    cdo_schema = unpack(call_1({'instance': cdo}))
    cdo_properties = unpack(call_2({'instance': cdo, 'properties': ['designSizeMode']})) if 'designSizeMode' in cdo_schema else {}
    slots = unpack(call_5({'widgetBlueprint': blueprint}))
    graphs = []
    for graph in unpack(call_6({'blueprint': blueprint})):
        graphs.append({'ref': graph, 'dsl': unpack(call_7({'graph': graph}))})
    assets.append({'assetPath': path, 'tree': tree, 'widgets': records, 'namedSlots': slots, 'graphs': graphs, 'cdo': cdo, 'cdoProperties': cdo_properties})
return {'assets': assets}"""

_FLOAT32_PROGRAM = """def native_numbers(value):
    if isinstance(value, float):
        if not math.isfinite(value):
            raise RuntimeError('Non-finite numeric property')
        exponent = math.frexp(value)[1]
        shift = max(-149, exponent - 24)
        converted = math.ldexp(round(math.ldexp(value, -shift)), shift)
        if abs(converted) > math.ldexp(2.0 - math.ldexp(1.0, -23), 127):
            raise RuntimeError('Property exceeds finite float32 range')
        return int(converted) if converted.is_integer() else converted
    if isinstance(value, dict):
        return {key: native_numbers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [native_numbers(item) for item in value]
    return value

def same_property(left, right):
    # Exact binary32 projection matches the core state hash, including nested
    # structs. No absolute/relative tolerance can conceal a different UE value.
    return json.dumps(native_numbers(left), sort_keys=True, separators=(',', ':')) == json.dumps(native_numbers(right), sort_keys=True, separators=(',', ':'))
"""


_SET_PROGRAM = _FLOAT32_PROGRAM + """schema = unpack(call_0({'instance': data['instance']}))
parts = data['parts']
current_schema = {'properties': schema}
for key in parts:
    if key not in current_schema.get('properties', {}):
        raise RuntimeError('Property path not exposed by actual schema: ' + '.'.join(parts))
    current_schema = current_schema['properties'][key]
current = unpack(call_1({'instance': data['instance'], 'properties': [parts[0]]}))
leaf = current
for key in parts:
    if not isinstance(leaf, dict) or key not in leaf:
        raise RuntimeError('Property path not present in actual readback')
    leaf = leaf[key]
if same_property(leaf, data['after']):
    return {'unchanged': True}
if not same_property(leaf, data['before']):
    raise RuntimeError('Actual property differs from operation precondition')
parent = current
for key in parts[:-1]:
    parent = parent[key]
parent[parts[-1]] = data['after']
if unpack(call_2({'instance': data['instance'], 'values': json.dumps(current)})) is not True:
    raise RuntimeError('Property write failed')
actual = unpack(call_1({'instance': data['instance'], 'properties': [parts[0]]}))
leaf = actual
for key in parts:
    leaf = leaf[key]
if not same_property(leaf, data['after']):
    raise RuntimeError('Property write did not persist in actual object')
return {'changed': True}"""


_SET_BATCH_PROGRAM = _FLOAT32_PROGRAM + """results = []
trees = {}
reference_trees = []
for op in data['operations']:
    path = op['assetPath'].split('.')[0]
    row = {'operationId': op['id'], 'assetPath': op['assetPath'], 'widgetName': op['widgetName'],
        'property': op['property'], 'instance': None, 'propertySchema': None,
        'before': None, 'after': None, 'setResult': None, 'status': 'failed', 'stage': 'identity', 'error': None}
    results.append(row)
    try:
        if path not in trees:
            tree = unpack(call_0({'widgetBlueprint': {'refPath': path + '.' + path.rsplit('/', 1)[-1]}}))
            if not isinstance(tree, dict) or not isinstance(tree.get('widgets'), list):
                raise RuntimeError('Actual WidgetTree is unavailable')
            trees[path] = tree
            reference_trees.append({'assetPath': path, 'tree': tree})
        matches = [widget for widget in trees[path]['widgets'] if widget.get('widgetName') == op['widgetName']]
        if len(matches) != 1:
            raise RuntimeError('Batch widget identity is not unique')
        instance = matches[0].get('slot' if op['kind'] == 'set-slot' else 'widget')
        if not isinstance(instance, dict) or not instance.get('refPath'):
            raise RuntimeError('Actual widget/Slot reference is unavailable')
        row['instance'] = instance
        row['stage'] = 'schema'
        schema = unpack(call_1({'instance': instance}))
        parts = op['property'].split('.')
        cursor = {'properties': schema}
        for key in parts:
            if key not in cursor.get('properties', {}):
                raise RuntimeError('Batch property path is absent from actual native schema')
            cursor = cursor['properties'][key]
        row['propertySchema'] = cursor
        row['stage'] = 'before'
        current = unpack(call_2({'instance': instance, 'properties': [parts[0]]}))
        row['before'] = json.loads(json.dumps(current))
        leaf = current
        for key in parts:
            if not isinstance(leaf, dict) or key not in leaf:
                raise RuntimeError('Batch property is absent from actual pre-read')
            leaf = leaf[key]
        if not same_property(leaf, op['before']):
            raise RuntimeError('Batch compare-and-set precondition differs from actual readback')
        parent = current
        for key in parts[:-1]:
            parent = parent[key]
        parent[parts[-1]] = op['after']
        row['stage'] = 'write'
        row['setResult'] = unpack(call_3({'instance': instance, 'values': json.dumps(current)}))
        row['stage'] = 'after'
        actual = unpack(call_2({'instance': instance, 'properties': [parts[0]]}))
        row['after'] = actual
        if row['setResult'] is not True:
            raise RuntimeError('Batch native setter did not return true')
        leaf = actual
        for key in parts:
            leaf = leaf[key]
        if not same_property(leaf, op['after']):
            raise RuntimeError('Batch native post-read differs from declared result')
        row['status'] = 'passed'
        row['stage'] = 'complete'
    except Exception as error:
        row['error'] = str(error)
        return {'kind': 'nextgame-ui-art-set-batch-result', 'version': 1, 'status': 'failed', 'results': results, 'referenceTrees': reference_trees}
return {'kind': 'nextgame-ui-art-set-batch-result', 'version': 1, 'status': 'completed', 'results': results, 'referenceTrees': reference_trees}"""


class NxueFallback:
    """Read-only source identity and exact protected Designer mode probes."""
    def __init__(self, project: Path, timeout: float = 120):
        self.project, self.timeout = project.resolve(), timeout
        self.cli = self.project / "Tools/nxue/nxue.py"
        if not self.cli.is_file():
            raise CapabilityError("Project NxUE CLI not found")
        self.identity_checked = False

    def check_texture_identity_capability(self):
        if not self.identity_checked:
            result = self._query({"action": "capabilities"})
            if result.get("supported") is not True:
                raise CapabilityError("Connected Editor lacks the required Texture2D source identity getter")
            self.identity_checked = True

    def texture_identity(self, destination: str) -> dict:
        self.check_texture_identity_capability()
        return self._query({"action": "read", "assetPath": _asset(destination)})

    def design_size_mode(self, cdo_path: str) -> str:
        if not isinstance(cdo_path, str) or not cdo_path.startswith("/Game/UI/") or ".Default__" not in cdo_path or not cdo_path.endswith("_C"):
            raise CapabilityError("Designer mode requires an actual generated UI CDO reference")
        args = {"action": "get", "objectPath": cdo_path, "propertyPath": "DesignSizeMode"}
        result = subprocess.run([sys.executable, str(self.cli), "tool", "manage-property", "--args-json", json.dumps(args)],
            cwd=self.project, capture_output=True, text=True, encoding="utf-8", timeout=self.timeout)
        if result.returncode:
            raise CapabilityError("NxUE read-only Designer mode probe failed: " + result.stderr[-1000:])
        try:
            envelope = json.loads(result.stdout)
            data = envelope["data"]
            if envelope.get("ok") is not True or data["target"]["path"] != cdo_path or data["propertyPath"] != "DesignSizeMode":
                raise ValueError("object/property identity mismatch")
            value = data["value"]
            if value not in {"FillScreen", "Desired", "DesiredOnScreen", "Custom", "CustomOnScreen"}:
                raise ValueError("unknown actual enum value")
            return value
        except (ValueError, KeyError, TypeError) as exc:
            raise CapabilityError("Invalid Designer mode receipt: " + str(exc)) from exc

    def _query(self, args: dict) -> dict:
        result = subprocess.run([sys.executable, str(self.cli), "exec-python", "--script", _TEXTURE_IDENTITY_SCRIPT,
            "--args-json", json.dumps(args)], cwd=self.project, capture_output=True, text=True, encoding="utf-8", timeout=self.timeout)
        if result.returncode:
            raise CapabilityError("NxUE read-only texture identity probe failed: " + result.stderr[-1500:])
        envelope = json.loads(result.stdout)
        if envelope.get("ok") is not True:
            raise CapabilityError("NxUE texture identity probe returned failure")
        output = envelope.get("data", {}).get("output", "")
        lines = [x[len("NEXTGAME_ART_TEXTURE="):] for x in output.splitlines() if x.startswith("NEXTGAME_ART_TEXTURE=")]
        if len(lines) != 1:
            raise CapabilityError("NxUE texture identity receipt missing")
        return json.loads(lines[0])


_TEXTURE_IDENTITY_SCRIPT = r'''import unreal, json
args = unreal.get_nxue_args()
if args.get('action') == 'capabilities':
    result = {'supported': hasattr(unreal.Texture2D, 'blueprint_get_texture_source_id_string')}
elif args.get('action') == 'read':
    texture = unreal.EditorAssetLibrary.load_asset(args['assetPath'])
    if not isinstance(texture, unreal.Texture2D):
        raise RuntimeError('Source identity requires Texture2D')
    source_id = texture.blueprint_get_texture_source_id_string()
    if not source_id:
        raise RuntimeError('Texture source identity is empty')
    result = {'assetPath': args['assetPath'], 'sourceId': source_id}
else:
    raise RuntimeError('Unsupported texture identity action')
result.update({'method': 'nxue-readonly-fallback', 'fallbackReason': 'Official TextureTools exposes size/import but no source identity getter'})
print('NEXTGAME_ART_TEXTURE=' + json.dumps(result))
'''


def create_editor(url: str = "http://127.0.0.1:8000/mcp", timeout: float = 60, *, project: Path | None = None) -> ArtEditor:
    project_path = Path(project) if project else next((p for p in [Path.cwd(), *Path.cwd().parents] if (p / "NextGame.uproject").is_file()), None)
    fallback = NxueFallback(project_path, timeout=max(timeout, 120)) if project_path and (project_path / "Tools/nxue/nxue.py").is_file() else None
    return ArtEditor(HttpTransport(url, timeout), nxue=fallback)

