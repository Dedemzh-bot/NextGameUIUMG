"""Synthetic batch integration tests; never imports UE assets or writes tables."""
import hashlib
import json
from pathlib import Path
import shutil
import struct
import sys
import unittest
import uuid
import zlib

from art_resources import load_resource_batch, validate_catalog, write_catalog, main
import art_resources as resources
from unittest.mock import patch


def digest(data):
    return hashlib.sha256(data).hexdigest()


def png_bytes():
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    raw = (b"\0" + bytes((40, 80, 120, 180)) * 2) * 3
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 3, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


class ResourceBatchTests(unittest.TestCase):
    def setUp(self):
        actual_project = next(p for p in Path(__file__).resolve().parents if (p / "Tools/UIResourceImport/import_contract.py").is_file())
        self.base = actual_project / "Saved/CodexArtResourceTests"
        self.root = self.base / ("batch-" + uuid.uuid4().hex)
        self.root.mkdir(parents=True)
        self.addCleanup(self.cleanup)
        self.project = self.root / "Project"
        self.content = self.project / "Content"
        self.content.mkdir(parents=True)
        (self.project / "Test.uproject").write_text("{}")
        self.tools = self.project / "Tools/UIResourceImport"
        self.tools.mkdir(parents=True)
        for name in ("import_contract.py", "register_icons.py", "resource_ids.py"):
            shutil.copy2(actual_project / "Tools/UIResourceImport" / name, self.tools / name)
        self.source, self.stage, self.published = (self.root / name for name in ("source", "stage", "published"))
        for path in (self.source, self.stage, self.published):
            path.mkdir()
        self.manifest_path, self.readback_path = self.root / "manifest.json", self.root / "readback.json"
        self.catalog_path = self.root / "art-resource-catalog.json"

    def cleanup(self):
        resolved = self.root.resolve()
        if resolved.parent != self.base.resolve() or not resolved.name.startswith("batch-"):
            raise ValueError("Refusing cleanup outside this test's owned directory")
        shutil.rmtree(resolved)

    def write_json(self, path, value):
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")

    def fixture(self, atlas=False, prefix=None):
        prefix = prefix or ("gui" if atlas else "pic")
        branch, engine_root, registered = {
            "gui": ("图片", "/Game/UI/UI", False), "icon": ("图标", "/Game/UI/ICON", True),
            "pic": ("图片", "/Game/UI/Textures", False), "por": ("图标", "/Game/UI/Portrait", True)}[prefix]
        name = prefix + "_demo_001.png"
        source_relative = "buttons/" + name
        original = self.source / source_relative
        original.parent.mkdir()
        original.write_bytes(png_bytes())
        relative = f"{branch}/" + ("图集/资源" if atlas else "单图") + "/Demo/" + name
        published = self.published / relative
        published.parent.mkdir(parents=True)
        published.write_bytes(png_bytes())
        destination = engine_root + "/Demo"
        basename = name.replace(".", "_") if atlas else Path(name).stem
        asset = destination + ("/Frames/" if atlas else "/") + basename + "." + basename
        item = {"original": str(original), "source_relative": source_relative, "source": str(published), "relative": relative,
            "name": name, "sha256": digest(png_bytes()), "dimensions": [2, 3], "asset": asset}
        group = {"kind": "atlas" if atlas else "standalone_texture", "branch": branch, "system": "Demo",
            "destination": destination, "register_icon": registered, "files": [item]}
        expected = [asset]
        directories = [Path(relative).parent.as_posix()]
        assets = [{"path": asset, "class": "/Script/Paper2D.PaperSprite" if atlas else "/Script/Engine.Texture2D", "dimensions": [2, 3]}]
        if atlas:
            out = f"{branch}/图集/图集/Demo"
            directories.append(out)
            for key, suffix in (("project_relative", ".tps"), ("descriptor_relative", ".paper2dsprites"), ("image_relative", ".png")):
                group[key] = out + "/Demo" + suffix
                (self.published / group[key]).parent.mkdir(parents=True, exist_ok=True)
            group.update(dimensions=[2, 3], sheet_asset=destination + "/Demo.Demo", texture_asset=destination + "/Textures/Demo.Demo")
            expected += [group["sheet_asset"], group["texture_asset"]]
            frame = {"frame": {"x": 0, "y": 0, "w": 2, "h": 3}, "rotated": False, "trimmed": False}
            item["frame"] = frame
            (self.published / group["project_relative"]).write_text("<data />")
            (self.published / group["image_relative"]).write_bytes(png_bytes())
            self.write_json(self.published / group["descriptor_relative"], {"frames": {name: frame}, "meta": {"image": "Demo.png", "size": {"w": 2, "h": 3}}})
            assets[0]["properties"] = {"source_texture": group["texture_asset"], "source_texture_dimension": [2, 3], "source_uv": [0, 0],
                "source_dimension": [2, 3], "rotated_in_source_image": False, "trimmed_in_source_image": False}
            assets += [{"path": group["sheet_asset"], "class": "/Script/PaperSpriteSheetImporter.PaperSpriteSheet", "texture": group["texture_asset"], "sprite_count": 1},
                {"path": group["texture_asset"], "class": "/Script/Engine.Texture2D", "dimensions": [2, 3]}]
        for row in assets:
            saved = self.content / (row["path"].split(".")[0].removeprefix("/Game/") + ".uasset")
            saved.parent.mkdir(parents=True, exist_ok=True)
            payload = ("synthetic saved resource " + row["path"]).encode()
            saved.write_bytes(payload)
            row["saved_file"] = {"path": str(saved), "bytes": len(payload), "sha256": digest(payload)}
        self.manifest = {"source": str(self.source), "stage": str(self.stage), "destination": str(self.published), "project_dir": str(self.project),
            "groups": [group], "expected_assets": expected, "directories": directories, "packed_verified": True,
            "publish_files": [{"relative": p.relative_to(self.published).as_posix(), "sha256": digest(p.read_bytes()), "bytes": p.stat().st_size}
                for p in self.published.rglob("*") if p.is_file()]}
        self.readback = {"success": True, "status": "complete", "operation": "independent_readback", "project_dir": str(self.project),
            "project_content_dir": str(self.content), "assets": assets, "dirty_targets_after": [], "parameter_mismatches": []}
        self.flush()
        return item

    def flush(self):
        self.write_json(self.manifest_path, self.manifest)
        self.readback["manifest_sha256"] = digest(self.manifest_path.read_bytes())
        self.write_json(self.readback_path, self.readback)

    def load(self):
        return load_resource_batch(self.manifest_path, self.readback_path, project_root=self.project)

    def save_catalog(self):
        catalog = self.load()
        write_catalog(self.catalog_path, catalog, tool_root=self.tools, protected_roots=[self.source, self.stage, self.published, self.content])
        return catalog

    def test_standalone_catalog_deterministic_read_only_and_no_registry_ids(self):
        item = self.fixture()
        before = {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        first, second = self.load(), self.load()
        self.assertEqual(first, second)
        self.assertEqual(first["resources"][0]["sourceRelative"], item["source_relative"])
        self.assertEqual(first["resources"][0]["brushResourceObject"], {"refPath": item["asset"]})
        self.assertEqual(first["resources"][0]["dependencies"], [])
        self.assertFalse(first["resourceIdsIncluded"])
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})

    def test_atlas_uses_actual_sprite_and_binds_both_dependencies(self):
        item = self.fixture(atlas=True, prefix="icon")
        catalog = self.load()
        resource = catalog["resources"][0]
        self.assertEqual(resource["classPath"], "/Script/Paper2D.PaperSprite")
        self.assertEqual(resource["brushResourceObject"]["refPath"], item["asset"])
        self.assertIn("/Frames/", resource["assetPath"])
        self.assertEqual({d["classPath"] for d in resource["dependencies"]}, {"/Script/Engine.Texture2D", "/Script/PaperSpriteSheetImporter.PaperSpriteSheet"})
        self.assertEqual(resource["atlas"]["sourceDimensions"], [2, 3])

    def test_legacy_source_relative_derived_without_guessing_filename(self):
        self.fixture()
        del self.manifest["groups"][0]["files"][0]["source_relative"]
        self.flush()
        self.assertEqual(self.load()["resources"][0]["sourceRelative"], "buttons/pic_demo_001.png")

    def test_stale_manifest_refused(self):
        self.fixture()
        self.manifest_path.write_bytes(self.manifest_path.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "current manifest"):
            self.load()

    def test_source_and_published_pixel_changes_refused(self):
        item = self.fixture()
        Path(item["original"]).write_bytes(png_bytes() + b"changed")
        with self.assertRaisesRegex(ValueError, "Original input changed"):
            self.load()
        Path(item["original"]).write_bytes(png_bytes())
        Path(item["source"]).write_bytes(png_bytes() + b"changed")
        with self.assertRaisesRegex(ValueError, "Published source changed"):
            self.load()

    def test_import_result_not_independent_readback(self):
        self.fixture()
        self.readback["operation"] = "import"
        self.write_json(self.readback_path, self.readback)
        with self.assertRaisesRegex(ValueError, "independent readback"):
            self.load()

    def test_saved_atlas_dependency_change_refused(self):
        self.fixture(atlas=True)
        texture = next(r for r in self.readback["assets"] if r["class"] == "/Script/Engine.Texture2D")
        Path(texture["saved_file"]["path"]).write_bytes(b"different atlas")
        with self.assertRaisesRegex(ValueError, "Saved asset changed"):
            self.load()

    def test_readback_frame_and_project_conflicts_refused(self):
        self.fixture(atlas=True)
        self.readback["assets"][0]["properties"]["source_uv"] = [1, 0]
        self.write_json(self.readback_path, self.readback)
        with self.assertRaisesRegex(ValueError, "Sprite frame"):
            self.load()
        self.readback["project_dir"] = str(self.root / "AnotherProject")
        self.write_json(self.readback_path, self.readback)
        with self.assertRaisesRegex(ValueError, "project identity"):
            self.load()

    def test_validate_catalog_rechecks_saved_assets_and_mapping(self):
        self.fixture()
        catalog = self.save_catalog()
        self.assertEqual(validate_catalog(self.catalog_path), catalog)
        altered = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        altered["resources"][0]["assetPath"] = "/Game/Wrong.Wrong"
        self.write_json(self.catalog_path, altered)
        with self.assertRaisesRegex(ValueError, "mapping differs"):
            validate_catalog(self.catalog_path)
        self.write_json(self.catalog_path, catalog)
        Path(self.readback["assets"][0]["saved_file"]["path"]).write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "Saved asset changed"):
            validate_catalog(self.catalog_path)

    def test_validate_catalog_rejects_changed_readback_or_validator(self):
        self.fixture()
        self.save_catalog()
        self.readback_path.write_bytes(self.readback_path.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "binding is stale"):
            validate_catalog(self.catalog_path)
        self.flush()
        validator = self.tools / "import_contract.py"
        validator.write_bytes(validator.read_bytes() + b"\n# changed validator\n")
        with self.assertRaisesRegex(ValueError, "binding is stale"):
            validate_catalog(self.catalog_path)

    def test_cli_uses_runtime_output_and_forbids_source_or_plugin_output(self):
        self.fixture()
        args = ["--manifest", str(self.manifest_path), "--readback", str(self.readback_path), "--project-root", str(self.project)]
        self.assertEqual(main(args + ["--output", str(self.catalog_path)]), 0)
        self.assertEqual(len(validate_catalog(self.catalog_path)["resources"]), 1)
        catalog = self.load()
        for output in [self.source / "new.json", self.content / "new.json", Path(__file__).parent / "must-not-write.json"]:
            with self.assertRaisesRegex(ValueError, "outside plugin/tools"):
                write_catalog(output, catalog, tool_root=self.tools, protected_roots=[self.source, self.content])
            self.assertFalse(output.exists())

    def existing_fixture(self, *, overrides=None):
        """Synthetic tool receipts only; production collector has no fake provider hook."""
        self.fixture()
        self.save_catalog()
        base = "/Game/UI/UI/Common"
        sprite, sheet, texture = base + "/Frames/gui_common_01_png", base + "/Common", base + "/Textures/Common"
        object_ref = lambda p: {"refPath": resources._object_path(p)}
        frame = {"frame": {"x": 0, "y": 0, "w": 2, "h": 3}, "sourceSize": {"w": 2, "h": 3},
            "spriteSourceSize": {"x": 0, "y": 0, "w": 2, "h": 3}, "trimmed": False, "rotated": False}
        image = self.source / "Common.png"
        descriptor = self.source / "Common.paper2dsprites"
        image.write_bytes(png_bytes())
        self.write_json(descriptor, {"meta": {"image": "Common.png", "size": {"w": 2, "h": 3}}, "frames": {"gui_common_01.png": frame}})
        props = {sprite: {"sourceTexture": object_ref(texture), "sourceTextureDimension": {"x": 2, "y": 3},
            "sourceUV": {"x": 0, "y": 0}, "sourceDimension": {"x": 2, "y": 3}, "bRotatedInSourceImage": False,
            "bTrimmedInSourceImage": False, "originInSourceImageBeforeTrimming": {"x": 0, "y": 0}, "sourceImageDimensionBeforeTrimming": {"x": 2, "y": 3}},
            sheet: {"spriteNames": ["gui_common_01.png"], "sprites": [object_ref(sprite)], "texture": object_ref(texture),
                "assetImportData": {"refPath": resources._object_path(sheet) + ":AssetImportData"}},
            texture: {"assetImportData": {"refPath": resources._object_path(texture) + ":AssetImportData"}}}
        classes = {sprite: resources._SPRITE, sheet: resources._SHEET, texture: resources._TEXTURE}
        scope = [{"spriteAssetPath": sprite, "sheetAssetPath": sheet}]
        def execute(tool, arguments):
            args = json.loads(arguments)
            name = tool.rsplit(".", 1)[-1]
            if name == "load_asset": value = object_ref(args["asset_path"])
            elif name == "is_dirty": value = False
            elif name == "get_class": value = {"refPath": classes[args["instance"]["refPath"].split(".")[0]]}
            elif name == "get_properties":
                value = json.dumps({"sourceData": {}} if args["properties"] == ["sourceData"] else props[args["instance"]["refPath"].split(".")[0]])
            else: raise AssertionError(tool)
            if overrides:
                value = overrides(tool, args, value)
            return {"returnValue": value}
        namespace = {"execute_tool": execute}
        program = resources._existing_program(scope)
        exec(program, namespace)
        official = {"programSha256": digest(program.encode()), "receipt": {"returnValue": json.dumps(namespace["run"]())}}
        objects = [{"assetPath": p, "classPath": classes[p], "sourceFiles": [str(descriptor if p == sheet else image)],
            "sourceId": None if p == sheet else "ACTUAL-SYNTHETIC-TEXTURE-SOURCE-ID"} for p in sorted([sheet, texture])]
        identity = {"scriptSha256": digest(resources._EXISTING_IDENTITY.encode()), "arguments": {"assetPaths": sorted([sheet, texture])},
            "receipt": {"ok": True, "data": {"output": "NEXTGAME_EXISTING_RESOURCE_IDENTITY=" + json.dumps({"objects": objects})}}}
        saved = []
        for path in [sprite, sheet, texture]:
            file = self.content / (path.removeprefix("/Game/") + ".uasset")
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(("synthetic existing asset " + path).encode())
            saved.append({"path": resources._object_path(path), "saved_file": {**resources._binding(file), "bytes": file.stat().st_size}})
        crop = self.root / "crop.png"
        crop.write_bytes(png_bytes())
        self.existing = {"version": 1, "kind": "existing-project-resource-readback", "provider": resources._EXISTING_PROVIDER,
            "projectRoot": str(self.project.resolve()), "capturedAt": "2026-09-17T15:00:00+00:00", "scope": scope, "official": official,
            "sourceIdentity": identity, "savedAssets": saved, "frames": [{"assetPath": sprite, "sourceImage": resources._binding(image),
                "sourceDescriptor": resources._binding(descriptor), "sourceFrame": resources._binding(crop), "textureSourceId": objects[1]["sourceId"]}]}
        self.existing_path = self.root / "existing.json"
        self.write_json(self.existing_path, self.existing)
        return self.existing

    def test_existing_resources_merge_keeps_original_batch_and_revalidates(self):
        self.existing_fixture()
        original = validate_catalog(self.catalog_path)
        merged = resources.merge_existing_resources(self.catalog_path, self.existing_path)
        self.assertEqual(len(merged["resources"]), 2)
        self.assertIn(original["resources"][0], merged["resources"])
        self.assertFalse(merged["resourceIdsIncluded"])
        path = self.root / "merged.json"
        self.write_json(path, merged)
        # Revalidation is offline and cannot reach either UE bridge.
        with patch.object(resources.subprocess, "run", side_effect=AssertionError("Unexpected subprocess")):
            self.assertEqual(validate_catalog(path), merged)
        merged["resources"][-1]["brushResourceObject"] = {"refPath": "/Game/Fake.Fake"}
        self.write_json(path, merged)
        with self.assertRaisesRegex(ValueError, "differs"):
            validate_catalog(path)

    def test_existing_rejects_free_claims_provider_and_program(self):
        data = self.existing_fixture()
        changes = [{"provider": "FakeProvider"}, {"fixture": False}, {"actualVerified": True}]
        for change in changes:
            with self.subTest(change=change):
                self.write_json(self.existing_path, {**data, **change})
                with self.assertRaises(ValueError): resources.load_existing_resources(self.existing_path)
        data["official"]["programSha256"] = "0" * 64
        self.write_json(self.existing_path, data)
        with self.assertRaisesRegex(ValueError, "program identity"):
            resources.load_existing_resources(self.existing_path)

    def test_existing_rejects_missing_extra_or_mutating_calls(self):
        data = self.existing_fixture()
        pristine = resources._unpack(data["official"]["receipt"])
        for kind in ["missing", "extra", "mutation", "projection"]:
            with self.subTest(kind=kind):
                actual = json.loads(json.dumps(pristine))
                if kind == "missing": actual["calls"].pop()
                if kind == "extra": actual["calls"].append(actual["calls"][0])
                if kind == "mutation": actual["calls"][0]["tool"] = resources._ASSET + ".save_assets"
                if kind == "projection": actual["assets"][0]["properties"]["sourceUV"]["x"] = 100
                data["official"]["receipt"] = {"returnValue": json.dumps(actual)}
                self.write_json(self.existing_path, data)
                with self.assertRaises(ValueError): resources.load_existing_resources(self.existing_path)

    def test_existing_rejects_actual_dirty_class_or_frame_conflicts(self):
        for kind in ["dirty", "class", "frame", "source-gap", "membership"]:
            with self.subTest(kind=kind):
                # Each receipt is internally consistent; semantic failures must
                # still reject it rather than trusting a successful tool call.
                def override(tool, args, value):
                    if kind == "dirty" and tool.endswith(".is_dirty"): return True
                    if kind == "class" and tool.endswith(".get_class"): return {"refPath": resources._TEXTURE}
                    if tool.endswith(".get_properties"):
                        prop = json.loads(value)
                        if kind == "frame" and "sourceUV" in prop: prop["sourceUV"]["x"] = 1
                        if kind == "source-gap" and "sourceData" in prop: prop["sourceData"] = {"sourceFiles": ["available"]}
                        if kind == "membership" and "sprites" in prop: prop["sprites"] = [{"refPath": "/Game/Other.Other"}]
                        return json.dumps(prop)
                    return value
                # Reset only this test fixture's paths before creating again.
                if hasattr(self, "existing_path"):
                    self.doCleanups()
                    self.setUp()
                self.existing_fixture(overrides=override)
                with self.assertRaises(ValueError): resources.load_existing_resources(self.existing_path)

    def test_existing_rechecks_source_bytes_saved_assets_and_crop_pixels(self):
        data = self.existing_fixture()
        for kind in ["source", "saved", "crop"]:
            with self.subTest(kind=kind):
                record = data["frames"][0]
                path = Path(record["sourceImage"]["path"] if kind == "source" else data["savedAssets"][0]["saved_file"]["path"] if kind == "saved" else record["sourceFrame"]["path"])
                before = path.read_bytes()
                if kind == "crop":
                    from PIL import Image
                    Image.new("RGBA", (2, 3), (255, 0, 0, 255)).save(path)
                    record["sourceFrame"] = resources._binding(path)
                    self.write_json(self.existing_path, data)
                else: path.write_bytes(before + b"changed")
                with self.assertRaises(ValueError): resources.load_existing_resources(self.existing_path)
                path.write_bytes(before)
                record["sourceFrame"] = resources._binding(Path(record["sourceFrame"]["path"]))
                self.write_json(self.existing_path, data)

    def test_existing_rejects_nxue_identity_scope_script_and_source_id(self):
        data = self.existing_fixture()
        pristine = json.loads(json.dumps(data))
        for kind in ["scope", "script", "source-id", "provider"]:
            data = json.loads(json.dumps(pristine))
            identity = data["sourceIdentity"]
            if kind == "scope": identity["arguments"]["assetPaths"].pop()
            if kind == "script": identity["scriptSha256"] = "0" * 64
            if kind == "source-id":
                objects = json.loads(identity["receipt"]["data"]["output"].split("=", 1)[1])
                objects["objects"][1]["sourceId"] = ""
                identity["receipt"]["data"]["output"] = "NEXTGAME_EXISTING_RESOURCE_IDENTITY=" + json.dumps(objects)
            if kind == "provider": identity["provider"] = "fixture"
            self.write_json(self.existing_path, data)
            with self.subTest(kind=kind), self.assertRaises(ValueError): resources.load_existing_resources(self.existing_path)


if __name__ == "__main__":
    unittest.main()
