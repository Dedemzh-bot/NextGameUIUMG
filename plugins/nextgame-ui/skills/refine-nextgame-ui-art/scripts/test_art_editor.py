"""Adapter contract tests; fixtures are synthetic, never Unreal evidence."""
import copy
import hashlib
import json
import math
import struct
import unittest
import uuid
from contextlib import contextmanager
from pathlib import Path

from art_editor import ArtEditor, CapabilityError, NxueFallback, OBJ, UMG, BP, ASSET, PROGRAM, IMAGING, TEXTURE, TEXTURE_STANDARD, _object, _FLOAT32_PROGRAM

PATH = "/Game/UI/UMG/Test/uw_test_item"
ROOT = {"refPath": PATH + ".uw_test_item:WidgetTree.PanelRoot"}
IMAGE = {"refPath": PATH + ".uw_test_item:WidgetTree.ImgIcon"}
SLOT = {"refPath": PATH + ".uw_test_item:WidgetTree.PanelRoot.CanvasPanelSlot_0"}
CDO = {"refPath": PATH + ".Default__uw_test_item_C"}


@contextmanager
def scratch():
    # Python 3.14's mode-0700 tempfile dirs are inaccessible to the Windows
    # restricted-token runner; use an ordinary, uniquely owned workspace dir.
    directory = Path(__file__).resolve().parent / ("art-test-" + uuid.uuid4().hex)
    directory.mkdir()
    try:
        yield directory
    finally:
        for path in directory.iterdir():
            path.unlink()
        directory.rmdir()


class FakeTransport:
    def __init__(self):
        self.events = []
        self.fail_compile = False
        self.silent_set = False
        self.native_float32 = False
        self.tags = {}
        self.refs = {ROOT["refPath"]: {"renderOpacity": 1.0, "visibility": "SelfHitTestInvisible"},
            IMAGE["refPath"]: {"brush": {"resourceObject": {"refPath": "/Game/UI/Textures/Test/pic_old.pic_old"},
                "imageSize": {"x": 32.0, "y": 32.0}, "margin": {"left": 0.25, "top": 0.25, "right": 0.25, "bottom": 0.25}},
                "renderOpacity": 1.0, "visibility": "SelfHitTestInvisible"},
            SLOT["refPath"]: {"layoutData": {"offsets": {"left": 8.0, "top": 8.0, "right": 32.0, "bottom": 32.0}}, "zOrder": 2},
            CDO["refPath"]: {"designSizeMode": "Desired"}}
        self.tree = {"info": {"parentClass": {"refPath": "/Script/UIFramework.UGameWidget"}}, "widgets": [
            {"widgetName": "PanelRoot", "widget": ROOT, "slot": "None", "parent": "None", "namedSlotHost": "None",
                "widgetClassPath": {"refPath": "/Script/UMG.CanvasPanel"}, "bIsVariable": False, "bInherited": False},
            {"widgetName": "ImgIcon", "widget": IMAGE, "slot": SLOT, "parent": ROOT, "namedSlotHost": "None",
                "widgetClassPath": {"refPath": "/Script/UIFramework.GameImage"}, "bIsVariable": True, "bInherited": False}]}

    def describe(self, toolset):
        self.events.append(("describe", toolset))
        inputs = {
            UMG: {"GetWidgets": ["widgetBlueprint"], "GetNamedSlots": ["widgetBlueprint"],
                "CompileWidgetBlueprint": ["widgetBlueprint"], "AddWidget": ["widgetBlueprint", "widgetClass", "widgetDisplayName", "parentWidget", "childIndex"],
                "ToggleWidgetAsVariable": ["widgetBlueprint", "widget", "bIsVariable"]},
            OBJ: {"list_properties": ["instance"], "get_properties": ["instance", "properties"],
                "set_properties": ["instance", "values"], "get_class": ["instance"]},
            BP: {"get_default_object": ["blueprint"], "list_graphs": ["blueprint"], "read_graph_dsl": ["graph"]},
            ASSET: {"save_assets": ["asset_paths"], "exists": ["path"], "get_metadata_tags": ["asset_path"], "update_metadata_tags": ["asset_path", "set_tags"]},
            TEXTURE: {"import_file": ["folder_path", "asset_name", "source_file"]},
            PROGRAM: {"get_execution_environment": [], "execute_tool_script": ["script"]},
            IMAGING: {"CaptureAssetImage": ["assetPath"]}}
        return {"tools": [{"name": toolset + "." + tool, "inputSchema": {"properties": {k: {} for k in args}, "required": args},
            "outputSchema": {"type": "object", "properties": {"returnValue": {}}}} for tool, args in inputs[toolset].items()]}

    def call(self, toolset, tool, args):
        self.events.append(("call", toolset, tool, copy.deepcopy(args)))
        if tool == "get_execution_environment":
            return {"returnValue": {"language": "python", "instructions": "Use execute_tool.", "supported_modules": [{"name": "json"}, {"name": "math"}]}}
        if tool == "execute_tool_script":
            def dispatch(name, raw):
                ts, t = name.rsplit(".", 1)
                return self.call(ts, t, json.loads(raw))
            scope = {"execute_tool": dispatch}
            exec(args["script"], scope)
            return {"returnValue": json.dumps(scope["run"]())}
        if tool == "GetWidgets":
            return {"returnValue": copy.deepcopy(self.tree)}
        if tool == "get_default_object":
            return {"returnValue": CDO}
        if tool == "GetNamedSlots":
            return {"returnValue": []}
        if tool == "list_graphs":
            return {"returnValue": [{"refPath": PATH + ".uw_test_item:EventGraph"}]}
        if tool == "read_graph_dsl":
            return {"returnValue": "(event Construct (Get ImgIcon))"}
        if tool == "get_class":
            for widget in self.tree['widgets']:
                if widget['widget'] == args['instance']:
                    return {'returnValue': widget.get('actualClass', widget['widgetClassPath'])}
            return {"returnValue": {"refPath": "/Script/Engine.Texture2D" if args["instance"]["refPath"].startswith("/Game/UI/Textures/") else "/Script/UMG.CanvasPanelSlot"}}
        if tool == "list_properties":
            def schema(v):
                return {"type": "object", "properties": {k: schema(x) for k, x in v.items()}} if isinstance(v, dict) else {"type": "number"}
            path = args["instance"]["refPath"]
            if path == "/Script/UIFramework.GameImage":
                path = IMAGE["refPath"]
            elif path == "/Script/UMG.CanvasPanelSlot":
                path = SLOT["refPath"]
            return {"returnValue": json.dumps({k: schema(v) for k, v in self.refs[path].items()})}
        if tool == "get_properties":
            values = self.refs[args["instance"]["refPath"]]
            return {"returnValue": json.dumps({k: values[k] for k in args["properties"]})}
        if tool == "set_properties":
            if not self.silent_set:
                def normalize(value):
                    if isinstance(value, float):
                        return struct.unpack('f', struct.pack('f', value))[0]
                    if isinstance(value, dict):
                        return {key: normalize(item) for key, item in value.items()}
                    if isinstance(value, list):
                        return [normalize(item) for item in value]
                    return value
                values = json.loads(args["values"])
                self.refs[args["instance"]["refPath"]].update(normalize(values) if self.native_float32 else values)
            return {"returnValue": True}
        if tool == "CompileWidgetBlueprint":
            return {"returnValue": not self.fail_compile}
        if tool == "save_assets":
            return {"returnValue": True}
        if tool == "exists":
            return {"returnValue": _object(args["path"])["refPath"] in self.refs}
        if tool == "get_metadata_tags":
            return {"returnValue": self.tags.get(args["asset_path"], {})}
        if tool == "update_metadata_tags":
            self.tags.setdefault(args["asset_path"], {}).update(args["set_tags"])
            return {}
        if tool == "import_file":
            ref = _object(args["folder_path"] + "/" + args["asset_name"])
            self.refs[ref["refPath"]] = dict(TEXTURE_STANDARD)
            self.refs[ref["refPath"]]["compressionSettings"] = "TC_Default"
            return {"returnValue": [ref]}
        if tool == "AddWidget":
            name = args["widgetDisplayName"]
            widget = {"refPath": PATH + ".uw_test_item:WidgetTree." + name}
            slot = {"refPath": widget["refPath"] + "_slot"}
            entry = {"widgetName": name, "widget": widget, "slot": slot, "parent": args["parentWidget"], "namedSlotHost": "None",
                "widgetClassPath": args["widgetClass"], "bIsVariable": True, "bInherited": False}
            self.tree["widgets"].append(entry)
            self.refs[widget["refPath"]] = {"renderOpacity": 1.0, "visibility": "SelfHitTestInvisible"}
            self.refs[slot["refPath"]] = {"zOrder": 0, "layoutData": copy.deepcopy(self.refs[SLOT["refPath"]]["layoutData"])}
            return {"returnValue": copy.deepcopy(entry)}
        if tool == "ToggleWidgetAsVariable":
            for widget in self.tree["widgets"]:
                if widget["widget"] == args["widget"]:
                    widget["bIsVariable"] = args["bIsVariable"]
            return {}
        raise AssertionError("Unexpected tool " + tool)


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.transport = FakeTransport()
        self.editor = ArtEditor(self.transport)

    def operation(self, **changes):
        op = {"id": "opacity", "kind": "set-property", "assetPath": PATH, "widgetName": "ImgIcon",
            "property": "renderOpacity", "before": 1.0, "after": 0.5}
        op.update(changes)
        return op

    def calls(self, name):
        return [e for e in self.transport.events if e[0] == "call" and e[2] == name]

    def test_batch_executes_native_identity_cas_set_postread_for_each_operation(self):
        operations = [self.operation(), self.operation(id='z', kind='set-slot', property='zOrder', before=2, after=4)]
        result = self.editor.execute_batch(operations)
        self.assertEqual('completed', result['status'])
        self.assertEqual([IMAGE, SLOT], [r['instance'] for r in result['results']])
        self.assertEqual(1, len(self.calls('GetWidgets')))
        names = [e[2] for e in self.transport.events if e[0] == 'call' and e[2] in ('GetWidgets','list_properties','get_properties','set_properties')]
        self.assertEqual(['GetWidgets','list_properties','get_properties','set_properties','get_properties',
                          'list_properties','get_properties','set_properties','get_properties'], names)

    def test_batch_stale_per_operation_cas_prevents_write(self):
        self.transport.refs[IMAGE['refPath']]['renderOpacity'] = .7
        result = self.editor.execute_batch([self.operation()])
        self.assertEqual('failed', result['status']); self.assertEqual([], self.calls('set_properties'))

    def test_batch_false_native_setter_preserves_actual_changed_after(self):
        original = self.transport.call
        def call(ts, tool, args):
            result = original(ts, tool, args)
            return {'returnValue': False} if tool == 'set_properties' else result
        self.transport.call = call
        result = self.editor.execute_batch([self.operation()])
        row = result['results'][0]
        self.assertEqual('failed', result['status']); self.assertIs(False, row['setResult'])
        self.assertEqual({'renderOpacity': .5}, row['after'])
        self.assertEqual({'renderOpacity': 1.0}, row['before'])

    def test_batch_true_native_setter_without_change_fails(self):
        self.transport.silent_set = True
        result = self.editor.execute_batch([self.operation()])
        self.assertEqual('failed', result['status']); self.assertIs(True, result['results'][0]['setResult'])

    def test_batch_native_float32_exact_domain_and_nested_before_copy(self):
        self.transport.native_float32 = True
        op = self.operation(property='brush.margin.left', before=.25, after=.123456789)
        result = self.editor.execute_batch([op]); row = result['results'][0]
        self.assertEqual('completed', result['status'])
        self.assertEqual(.25, row['before']['brush']['margin']['left'])
        self.assertEqual(struct.unpack('f',struct.pack('f',op['after']))[0], row['after']['brush']['margin']['left'])

    def test_batch_rejects_duplicate_overlap_structural_and_oversize_without_mutation(self):
        for operations in ([self.operation(), self.operation(id='dup')],
            [self.operation(property='brush'), self.operation(id='child',property='brush.margin.left')],
            [self.operation(kind='add-widget')], [self.operation(id=str(i)) for i in range(257)]):
            with self.subTest(operations=len(operations)):
                with self.assertRaises(CapabilityError): self.editor.execute_batch(operations)
        self.assertEqual([], self.calls('set_properties'))

    def test_batch_postread_exception_is_real_failed_receipt(self):
        original = self.transport.call; reads = [0]
        def call(ts, tool, args):
            if tool == 'get_properties':
                reads[0] += 1
                if reads[0] == 2: raise RuntimeError('postread lost')
            return original(ts, tool, args)
        self.transport.call = call
        result = self.editor.execute_batch([self.operation()]); row = result['results'][0]
        self.assertEqual('failed', result['status']); self.assertIs(True, row['setResult']); self.assertIsNone(row['after'])

    def test_snapshot_reads_actual_resource_geometry_and_protects_bindings(self):
        snap = self.editor.snapshot([PATH])
        asset = snap["assets"][0]
        self.assertEqual(asset["designSizeMode"], "Desired")
        self.assertFalse(asset["referencesComplete"])
        self.assertEqual(asset["protectedReferences"], ["ImgIcon"])
        image = asset["widgets"][1]
        self.assertEqual(image["parentWidgetName"], "PanelRoot")
        self.assertEqual(image["properties"]["brush"]["imageSize"], {"x": 32.0, "y": 32.0})
        self.assertEqual(image["slot"]["properties"]["zOrder"], 2)
        self.assertEqual(snap["acquisition"]["method"], "official-unreal-mcp")
        self.assertEqual(len(self.calls("execute_tool_script")), 1)
        self.assertLess(self.transport.events.index(self.calls("get_execution_environment")[0]),
            self.transport.events.index(self.calls("execute_tool_script")[0]))

    def test_missing_design_mode_stays_unknown(self):
        self.transport.refs[CDO["refPath"]] = {}
        asset = self.editor.snapshot([PATH])["assets"][0]
        self.assertIsNone(asset["designSizeMode"])
        self.assertIn("designSizeMode", asset["uncertainties"][-1])

    def test_generated_widget_class_uses_actual_object_class(self):
        self.transport.tree['widgets'][1]['widgetClassPath'] = {'refPath': PATH + '.uw_test_item'}
        self.transport.tree['widgets'][1]['actualClass'] = {'refPath': PATH + '.uw_test_item_C'}
        snap = self.editor.snapshot([PATH])
        self.assertEqual(snap['assets'][0]['widgets'][1]['classPath'], PATH + '.uw_test_item_C')
        self.assertTrue(any(c[3]['instance'] == IMAGE for c in self.calls('get_class')))

    def test_design_mode_exact_readonly_fallback_is_marked_mixed(self):
        self.transport.refs[CDO['refPath']] = {}
        seen = []
        class Fallback:
            def design_size_mode(self, cdo):
                seen.append(cdo)
                return 'FillScreen'
        snap = ArtEditor(self.transport, nxue=Fallback()).snapshot([PATH])
        self.assertEqual(seen, [CDO['refPath']])
        self.assertEqual(snap['assets'][0]['designSizeMode'], 'FillScreen')
        self.assertEqual(snap['acquisition']['method'], 'mixed')
        self.assertIn('DesignSizeMode', snap['acquisition']['fallbackReason'])
        self.assertFalse(self.calls('set_properties'))

    def test_failed_mode_fallback_keeps_unknown(self):
        self.transport.refs[CDO['refPath']] = {}
        class Fallback:
            def design_size_mode(self, cdo):
                raise CapabilityError('missing capability')
        snap = ArtEditor(self.transport, nxue=Fallback()).snapshot([PATH])
        self.assertIsNone(snap['assets'][0]['designSizeMode'])
        self.assertEqual(snap['acquisition']['method'], 'official-unreal-mcp')

    def test_mode_fallback_checks_exact_identity_and_enum(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        fallback = object.__new__(NxueFallback)
        fallback.cli, fallback.project, fallback.timeout = Path('nxue.py'), Path.cwd(), 1
        good = {'ok': True, 'data': {'target': {'path': CDO['refPath']}, 'propertyPath': 'DesignSizeMode', 'value': 'Desired'}}
        with patch('art_editor.subprocess.run', return_value=SimpleNamespace(returncode=0, stdout=json.dumps(good))) as run:
            self.assertEqual(fallback.design_size_mode(CDO['refPath']), 'Desired')
            self.assertEqual(json.loads(run.call_args.args[0][-1])['action'], 'get')
        for target, prop, value in [('other', 'DesignSizeMode', 'Desired'), (CDO['refPath'], 'other', 'Desired'), (CDO['refPath'], 'DesignSizeMode', 'Guessed')]:
            bad = {'ok': True, 'data': {'target': {'path': target}, 'propertyPath': prop, 'value': value}}
            with patch('art_editor.subprocess.run', return_value=SimpleNamespace(returncode=0, stdout=json.dumps(bad))):
                with self.assertRaises(CapabilityError):
                    fallback.design_size_mode(CDO['refPath'])

    def test_property_write_readback_and_idempotent_retry(self):
        self.editor.execute(self.operation())
        self.editor.execute(self.operation())
        self.assertEqual(self.transport.refs[IMAGE["refPath"]]["renderOpacity"], 0.5)
        self.assertEqual(len(self.calls("set_properties")), 1)
        self.assertEqual(len(self.calls("GetWidgets")), 2)

    def test_stale_precondition_blocks_write(self):
        self.transport.refs[IMAGE["refPath"]]["renderOpacity"] = 0.7
        with self.assertRaisesRegex(RuntimeError, "precondition"):
            self.editor.execute(self.operation())
        self.assertFalse(self.calls("set_properties"))

    def test_float32_precondition_readback_and_retry(self):
        self.transport.native_float32 = True
        self.transport.refs[IMAGE["refPath"]]["renderOpacity"] = struct.unpack('f', struct.pack('f', 0.6))[0]
        operation = self.operation(before=0.6, after=0.4)
        self.editor.execute(operation)
        self.editor.execute(operation)
        self.assertEqual(self.transport.refs[IMAGE["refPath"]]["renderOpacity"], struct.unpack('f', struct.pack('f', 0.4))[0])
        self.assertEqual(len(self.calls("set_properties")), 1)

    def test_recursive_float32_comparison_keeps_distinct_native_values(self):
        self.transport.native_float32 = True
        before = dict(self.transport.refs[IMAGE["refPath"]]["brush"]["margin"])
        after = {"left": 0.6, "top": 0.2, "right": 0.3, "bottom": 0.7}
        operation = self.operation(property="brush.margin", before=before, after=after)
        self.editor.execute(operation)
        self.editor.execute(operation)
        self.assertEqual(len(self.calls("set_properties")), 1)
        self.transport.refs[IMAGE["refPath"]]["brush"]["margin"]["left"] = struct.unpack('f', struct.pack('f', 0.60000008))[0]
        with self.assertRaisesRegex(RuntimeError, "precondition"):
            self.editor.execute(operation)
        self.assertEqual(len(self.calls("set_properties")), 1)

    def test_safe_binary32_projection_matches_struct_at_boundaries(self):
        values = [0.0, -0.0, 0.6, -0.6, 0.1, 1.0000000596046448, 1.0000001788139343,
            math.ldexp(1.0, -150), math.ldexp(3.0, -150), math.ldexp(1.0, -126),
            math.ldexp(2.0 - math.ldexp(1.0, -23), 127), 1e-300]
        result = self.editor._program(_FLOAT32_PROGRAM + "return {'values': native_numbers(data['values'])}",
            {"values": values}, [], modules=("math",))
        self.assertEqual(result["values"], [struct.unpack('f', struct.pack('f', value))[0] for value in values])
        for value in [1e100, float('inf'), float('nan')]:
            with self.assertRaises(RuntimeError):
                self.editor._program(_FLOAT32_PROGRAM + "return {'values': native_numbers(data['values'])}",
                    {"values": [value]}, [], modules=("math",))

    def test_math_capability_checked_even_after_snapshot_environment_cached(self):
        self.editor.snapshot([PATH])
        self.editor.environment["supported_modules"] = [{"name": "json"}]
        with self.assertRaisesRegex(CapabilityError, "safe.*module"):
            self.editor.execute(self.operation(after=0.6))
        self.assertFalse(self.calls("set_properties"))

    def test_nested_property_preserves_other_brush_fields(self):
        old = copy.deepcopy(self.transport.refs[IMAGE["refPath"]]["brush"])
        self.editor.execute(self.operation(property="brush.margin.left", before=0.25, after=0.5))
        actual = self.transport.refs[IMAGE["refPath"]]["brush"]
        self.assertEqual(actual["resourceObject"], old["resourceObject"])
        self.assertEqual(actual["margin"]["right"], 0.25)
        self.assertEqual(actual["margin"]["left"], 0.5)

    def test_slot_write_reacquires_slot_and_verifies(self):
        self.editor.execute(self.operation(kind="set-slot", property="zOrder", before=2, after=3))
        self.assertEqual(self.transport.refs[SLOT["refPath"]]["zOrder"], 3)

    def test_missing_property_schema_and_silent_failure_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "schema"):
            self.editor.execute(self.operation(property="font.size", before=20, after=24))
        self.transport.silent_set = True
        with self.assertRaisesRegex(RuntimeError, "persist"):
            self.editor.execute(self.operation())

    def test_arbitrary_binding_and_script_injection_rejected(self):
        for path in ["entryWidgetClass", "navigation", "brush.__class__", "renderOpacity;import os"]:
            with self.assertRaises((ValueError, RuntimeError)):
                self.editor.execute(self.operation(property=path))
        with self.assertRaises(ValueError):
            self.editor.execute(self.operation(kind="execute-python"))
        self.assertFalse(self.calls("set_properties"))

    def test_remove_reparent_require_actual_reference_evidence(self):
        for kind in ["remove-widget", "reparent-widget"]:
            with self.assertRaisesRegex(CapabilityError, "references are incomplete"):
                self.editor.execute(self.operation(kind=kind, referencesComplete=True))

    def test_native_image_add_and_duplicate_rejected(self):
        with self.assertRaisesRegex(ValueError, "static visual"):
            self.editor.execute(self.operation(kind="add-widget", after={"classPath": "/Script/UMG.Image", "isVariable": False}))
        with self.assertRaisesRegex(CapabilityError, "already exists"):
            self.editor.execute(self.operation(kind="add-widget", after={"classPath": "/Script/UIFramework.GameImage", "isVariable": False}))

    def test_compile_failure_does_not_save(self):
        self.transport.fail_compile = True
        with self.assertRaisesRegex(RuntimeError, "compile failed"):
            self.editor.compile_save([PATH])
        self.assertFalse(self.calls("save_assets"))

    def test_compile_save_targets_only_requested_packages(self):
        self.editor.compile_save([PATH, PATH])
        self.assertEqual(len(self.calls("CompileWidgetBlueprint")), 1)
        self.assertEqual(self.calls("save_assets")[0][3]["asset_paths"], [PATH])

    def test_capture_cannot_relabel_thumbnail_canonical(self):
        with scratch() as temp:
            output = Path(temp) / "preview.png"
            with self.assertRaisesRegex(CapabilityError, "Canonical UMG capture unavailable"):
                self.editor.capture(PATH, output, {"width": 2560, "height": 1440, "dpiScale": 1.0})
            self.assertFalse(output.exists())
            self.assertFalse(self.calls("CaptureAssetImage"))

    def test_import_hash_guard_and_verified_fallback_receipt(self):
        class Importer:
            calls = []
            source_id = "source-1"
            def check_texture_identity_capability(self):
                return None
            def texture_identity(self, destination):
                self.calls.append(destination)
                return {"assetPath": destination, "sourceId": self.source_id}
        importer = Importer()
        editor = ArtEditor(self.transport, nxue=importer)
        with scratch() as temp:
            source = Path(temp) / "pic_sample.png"
            source.write_bytes(b"synthetic fixture")
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            after = {"sourcePath": str(source), "sha256": digest, "destinationPath": "/Game/UI/Textures/Test/pic_sample"}
            editor.execute({"kind": "import-resource", "after": after})
            self.assertEqual(len(self.calls("import_file")), 1)
            editor.execute({"kind": "import-resource", "after": after})
            self.assertEqual(len(self.calls("import_file")), 1)
            importer.source_id = "changed-source"
            with self.assertRaisesRegex(CapabilityError, "identity or appearance changed"):
                editor.verify_import({"kind": "import-resource", "after": after})
            source.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "source changed"):
                editor.execute({"kind": "import-resource", "after": after})
            self.assertEqual(len(self.calls("import_file")), 1)

    def test_preflight_rejects_later_unsupported_op_before_mutation(self):
        with self.assertRaisesRegex(CapabilityError, "references are incomplete"):
            self.editor.preflight([self.operation(), self.operation(kind="remove-widget")])
        self.assertFalse(self.calls("set_properties"))

    def test_preflight_does_not_apply_supported_writes(self):
        result = self.editor.preflight([self.operation()])
        self.assertTrue(result["ok"])
        self.assertFalse(self.calls("set_properties"))

    def test_static_append_discovered_schema_and_exact_slot(self):
        after = {"classPath": "/Script/UIFramework.GameImage", "isVariable": False, "parentWidgetName": "PanelRoot",
            "properties": {"renderOpacity": 0.25}, "slot": {"classPath": "/Script/UMG.CanvasPanelSlot", "properties": {"zOrder": 4}}}
        operation = self.operation(kind="add-widget", widgetName="ImgDecoration", after=after)
        self.editor.preflight([operation])
        self.assertFalse(self.calls("AddWidget"))
        self.editor.execute(operation)
        added = self.transport.tree["widgets"][-1]
        self.assertEqual(added["widgetName"], "ImgDecoration")
        self.assertFalse(added["bIsVariable"])
        self.assertEqual(self.transport.refs[added["widget"]["refPath"]]["renderOpacity"], 0.25)
        self.assertEqual(self.transport.refs[added["slot"]["refPath"]]["zOrder"], 4)
        # A completed add remains preflightable so core can verify its no-op.
        self.editor.preflight([operation])
        self.assertEqual(len(self.calls("AddWidget")), 1)

    def test_static_append_rejects_cardinality_and_missing_fields(self):
        after = {"classPath": "/Script/UIFramework.GameImage", "isVariable": False, "parentWidgetName": "PanelRoot",
            "properties": {"nonexistentProperty": 1}, "slot": {"classPath": "/Script/UMG.CanvasPanelSlot", "properties": {}}}
        operation = self.operation(kind="add-widget", widgetName="ImgDecoration", after=after)
        with self.assertRaisesRegex(ValueError, "non-art"):
            self.editor.preflight([operation])
        after["properties"] = {}
        self.transport.tree["widgets"][0]["widgetClassPath"] = {"refPath": "/Script/UMG.Button"}
        with self.assertRaisesRegex(CapabilityError, "single-child"):
            self.editor.preflight([operation])
        self.assertFalse(self.calls("AddWidget"))

    def test_schema_missing_and_bad_asset_paths_fail_before_execution(self):
        with self.assertRaises(ValueError):
            self.editor.snapshot([PATH + "/../Other"])
        with self.assertRaises(ValueError):
            _object(PATH + ".WrongName")
        self.transport.describe = lambda ts: {"tools": []}
        with self.assertRaisesRegex(CapabilityError, "registered tool absent"):
            self.editor.compile_save([PATH])


if __name__ == "__main__":
    unittest.main()

