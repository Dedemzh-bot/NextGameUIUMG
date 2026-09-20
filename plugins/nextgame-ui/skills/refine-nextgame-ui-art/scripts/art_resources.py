"""Read completed NextGameUIResource batches without importing or registering.

The catalog maps original image bytes to saved engine objects. Atlas entries
reference PaperSprite, never the whole atlas texture. This module does not
connect to Unreal or use the resource tool's mutating pipeline entry points.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from types import ModuleType
import uuid


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _binding(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": _hash(path.read_bytes())}


def _json(data: bytes) -> dict:
    def invalid(value):
        raise ValueError("Non-finite JSON number: " + value)
    value = json.loads(data.decode("utf-8-sig"), parse_constant=invalid)
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return value


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError("Cannot load resource validator: " + str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


def _run_existing_validators(tool_root: Path, manifest_path: Path, readback_path: Path, manifest: dict):
    """Load exact project files without trusting same-named ambient modules."""
    paths = {name: (tool_root / (name + ".py")).resolve(strict=True)
        for name in ("import_contract", "register_icons", "resource_ids")}
    if any(path.parent != tool_root for path in paths.values()):
        raise ValueError("Resource validator symlinks must remain in the selected tool directory")
    before = [_binding(path) for path in paths.values()]
    suffix = uuid.uuid4().hex
    loaded_names = []
    previous_ids = sys.modules.get("resource_ids")
    previous_bytecode = sys.dont_write_bytecode
    # register_icons imports resource_ids by its historic absolute name. Borrow
    # that alias only during loading and restore it, so another tool's module
    # cannot silently supply a different validator. Loading writes no pyc files.
    sys.dont_write_bytecode = True
    try:
        for key in ("resource_ids", "import_contract", "register_icons"):
            module_name = "_nextgame_art_" + key + "_" + suffix
            loaded_names.append(module_name)
            module = _load_module(paths[key], module_name)
            if key == "resource_ids":
                sys.modules["resource_ids"] = module
            elif key == "import_contract":
                contract = module
            else:
                registry = module
        contract.validate_import_contract(manifest)
        verified_manifest, _, _ = registry._verify_readback(manifest_path, readback_path)
        if verified_manifest != manifest:
            raise ValueError("Manifest changed while resource validators were running")
    finally:
        if previous_ids is None:
            sys.modules.pop("resource_ids", None)
        else:
            sys.modules["resource_ids"] = previous_ids
        for name in loaded_names:
            sys.modules.pop(name, None)
        sys.dont_write_bytecode = previous_bytecode
    if before != [_binding(path) for path in paths.values()]:
        raise ValueError("Resource validator code changed during verification")
    return before


def _saved(row: dict, content_root: Path) -> dict:
    asset_path = row["path"]
    if not asset_path.startswith("/Game/") or "." not in asset_path:
        raise ValueError("Expected a /Game object path in resource readback")
    package = asset_path.split(".", 1)[0]
    expected = (content_root / (package.removeprefix("/Game/") + ".uasset")).resolve()
    if not expected.is_relative_to(content_root):
        raise ValueError("Saved resource escaped current project Content")
    record = row["saved_file"]
    if Path(record["path"]).resolve() != expected:
        raise ValueError("Saved resource path belongs to another project")
    data = expected.read_bytes()
    if not data or _hash(data) != record["sha256"] or record.get("bytes", len(data)) != len(data):
        raise ValueError("Saved resource changed since independent readback: " + asset_path)
    return {"path": str(expected), "sha256": _hash(data), "bytes": len(data)}


def load_resource_batch(manifest_path: Path, readback_path: Path, *, project_root: Path, tool_root: Path | None = None) -> dict:
    """Validate a completed batch and return a read-only art-resource catalog.

    ``project_root`` is required and must contain a .uproject file. ``tool_root``
    defaults only to that project's Tools/UIResourceImport directory; a separate
    trusted installation must be selected explicitly. No registry IDs are
    inferred, generated or copied from unapplied plans in this first version.
    """
    manifest_path, readback_path = Path(manifest_path).resolve(strict=True), Path(readback_path).resolve(strict=True)
    project_root = Path(project_root).resolve(strict=True)
    if not project_root.is_dir() or not any(project_root.glob("*.uproject")):
        raise ValueError("project_root must identify an explicit Unreal project")
    content_root = (project_root / "Content").resolve(strict=True)
    selected_tools = Path(tool_root).resolve(strict=True) if tool_root is not None else (project_root / "Tools/UIResourceImport").resolve(strict=True)
    if not selected_tools.is_dir():
        raise ValueError("NextGameUIResource tool directory is unavailable")
    manifest_bytes, readback_bytes = manifest_path.read_bytes(), readback_path.read_bytes()
    manifest, readback = _json(manifest_bytes), _json(readback_bytes)
    if (readback.get("success") is not True or readback.get("status") != "complete"
            or readback.get("operation") != "independent_readback"):
        raise ValueError("A completed independent readback is required; import-result alone is insufficient")
    if readback.get("manifest_sha256") != _hash(manifest_bytes):
        raise ValueError("Readback is not bound to the current manifest")
    if readback.get("parameter_mismatches") or readback.get("dirty_targets_after"):
        raise ValueError("Independent readback reports incorrect or unsaved resources")
    for document in (manifest, readback):
        if document.get("project_dir") and Path(document["project_dir"]).resolve() != project_root:
            raise ValueError("Resource batch project identity does not match the requested project")
        if document.get("project_content_dir") and Path(document["project_content_dir"]).resolve() != content_root:
            raise ValueError("Resource batch Content identity does not match the requested project")
    validators = _run_existing_validators(selected_tools, manifest_path, readback_path, manifest)
    rows = {row["path"]: row for row in readback["assets"]}
    saved = {path: _saved(row, content_root) for path, row in rows.items()}
    source_root = Path(manifest["source"]).resolve(strict=True)
    resources, seen_sources = [], set()
    for group in manifest["groups"]:
        atlas = group["kind"] == "atlas"
        dependencies = []
        if atlas:
            for key in ("texture_asset", "sheet_asset"):
                path = group[key]
                dependencies.append({"assetPath": path, "classPath": rows[path]["class"], "savedFile": saved[path]})
            sheet = rows[group["sheet_asset"]]
            if sheet.get("texture") != group["texture_asset"] or sheet.get("sprite_count") != len(group["files"]):
                raise ValueError("Independent readback SpriteSheet dependency differs from the manifest")
        for item in group["files"]:
            original = Path(item["original"]).resolve(strict=True)
            source_relative = original.relative_to(source_root).as_posix()
            if item.get("source_relative", source_relative) != source_relative:
                raise ValueError("Original source-relative mapping changed")
            if source_relative.casefold() in seen_sources:
                raise ValueError("Source-relative resource mapping is ambiguous")
            seen_sources.add(source_relative.casefold())
            path = item["asset"]
            row = rows[path]
            if atlas:
                actual = row.get("properties", {})
                rectangle = item["frame"]["frame"]
                if (actual.get("source_texture") != group["texture_asset"]
                        or actual.get("source_texture_dimension") != group["dimensions"]
                        or actual.get("source_uv") != [rectangle["x"], rectangle["y"]]
                        or actual.get("source_dimension") != item["dimensions"]
                        or actual.get("rotated_in_source_image") is not False
                        or actual.get("trimmed_in_source_image") is not False):
                    raise ValueError("Independent readback Sprite frame differs from the source mapping")
            elif row.get("dimensions") != item["dimensions"]:
                raise ValueError("Independent readback texture dimensions differ from the source")
            if _hash(original.read_bytes()) != item["sha256"]:
                raise ValueError("Original source changed during batch verification")
            resource = {"id": "batch-resource-" + _hash((source_relative + "\0" + path).encode())[:24],
                "sourceRelative": source_relative, "sourcePath": str(original), "sourceSha256": item["sha256"],
                "dimensions": item["dimensions"], "prefix": item["name"].partition("_")[0], "system": group["system"],
                "assetPath": path, "classPath": row["class"], "savedFile": saved[path], "dependencies": dependencies,
                "brushResourceObject": {"refPath": path}}
            if atlas:
                resource["atlas"] = {"textureAssetPath": group["texture_asset"], "sheetAssetPath": group["sheet_asset"],
                    "frame": item["frame"], "sourceUV": actual["source_uv"], "sourceDimensions": actual["source_dimension"]}
            resources.append(resource)
    if manifest_path.read_bytes() != manifest_bytes or readback_path.read_bytes() != readback_bytes:
        raise ValueError("Resource batch evidence changed during verification")
    resources.sort(key=lambda item: (item["sourceRelative"].casefold(), item["assetPath"]))
    return {"version": 1, "kind": "nextgame-ui-art-resource-catalog", "provider": "NextGameUIResource",
        "projectRoot": str(project_root), "sourceRoot": str(source_root), "resources": resources,
        "provenance": {"manifest": {"path": str(manifest_path), "sha256": _hash(manifest_bytes)},
            "readback": {"path": str(readback_path), "sha256": _hash(readback_bytes)}, "validatorFiles": validators},
        "resourceIdsIncluded": False}


def validate_catalog(catalog_path: Path) -> dict:
    """Revalidate recorded inputs, validators and saved assets on every reuse."""
    catalog_path = Path(catalog_path).resolve(strict=True)
    catalog_bytes = catalog_path.read_bytes()
    catalog = _json(catalog_bytes)
    if catalog.get("provider") == "ExistingProjectResourceCatalog/1":
        provenance = catalog["provenance"]
        if set(provenance) != {"baseCatalog", "existingReadback"}:
            raise ValueError("Unexpected merged resource provenance")
        for record in provenance.values():
            _checked_binding(record)
        actual = merge_existing_resources(Path(provenance["baseCatalog"]["path"]),
            Path(provenance["existingReadback"]["path"]))
        if actual != catalog or catalog_path.read_bytes() != catalog_bytes:
            raise ValueError("Merged catalog differs from current closed resource evidence")
        return actual
    if (catalog.get("version") != 1 or catalog.get("kind") != "nextgame-ui-art-resource-catalog"
            or catalog.get("provider") != "NextGameUIResource"):
        raise ValueError("Unsupported art resource catalog")
    provenance = catalog["provenance"]
    validator_bindings = provenance["validatorFiles"]
    if not isinstance(validator_bindings, list) or len(validator_bindings) != 3:
        raise ValueError("Catalog validator provenance must cover the three actual validator modules")
    validator_paths = [Path(item["path"]).resolve(strict=True) for item in validator_bindings]
    tool_root = validator_paths[0].parent
    if ({path.name for path in validator_paths} != {"import_contract.py", "register_icons.py", "resource_ids.py"}
            or any(path.parent != tool_root for path in validator_paths)):
        raise ValueError("Catalog validator module identities are inconsistent")
    for record in [provenance["manifest"], provenance["readback"], *validator_bindings]:
        if set(record) != {"path", "sha256"} or _binding(Path(record["path"])) != record:
            raise ValueError("Catalog source or validator binding is stale")
    actual = load_resource_batch(Path(provenance["manifest"]["path"]), Path(provenance["readback"]["path"]),
        project_root=Path(catalog["projectRoot"]), tool_root=tool_root)
    canonical = lambda value: json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    if canonical(actual) != canonical(catalog):
        raise ValueError("Catalog mapping differs from current validated batch evidence")
    if catalog_path.read_bytes() != catalog_bytes:
        raise ValueError("Catalog changed during verification")
    return actual


def write_catalog(path: Path, catalog: dict, *, tool_root: Path, protected_roots: list[Path]) -> None:
    """Write only a new runtime artifact outside plugin/tools/source/Content."""
    output = Path(path).resolve()
    plugin_root = Path(__file__).resolve().parents[3]
    forbidden = [plugin_root, Path(tool_root).resolve(), *(Path(p).resolve() for p in protected_roots)]
    if any(output.is_relative_to(root) for root in forbidden):
        raise ValueError("Catalog output must be outside plugin/tools, source, publication, staging and project Content")
    data = (json.dumps(catalog, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    if output.exists():
        if output.is_file() and output.read_bytes() == data:
            return
        raise FileExistsError("Choose a new catalog output revision; existing output differs")
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation never replaces evidence or a concurrently created file.
    with output.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


_EXISTING_PROVIDER = "ExistingProjectResourceCatalog/1"
_ASSET = "editor_toolset.toolsets.asset.AssetTools"
_OBJECT = "editor_toolset.toolsets.object.ObjectTools"
_PROGRAM = "editor_toolset.toolsets.programmatic.ProgrammaticToolset"
_SPRITE = "/Script/Paper2D.PaperSprite"
_SHEET = "/Script/PaperSpriteSheetImporter.PaperSpriteSheet"
_TEXTURE = "/Script/Engine.Texture2D"
_SPRITE_FIELDS = ["sourceTexture", "sourceTextureDimension", "sourceUV", "sourceDimension",
    "bRotatedInSourceImage", "bTrimmedInSourceImage", "originInSourceImageBeforeTrimming", "sourceImageDimensionBeforeTrimming"]

# A single fixed, read-only program produces a complete call ledger. Validation
# replays this reviewed program against its recorded results; it never executes
# code supplied by an evidence file or accepts normalized resource claims.
_EXISTING_PROGRAM = '''import json
def asset_call(name, args):
    return execute_tool("editor_toolset.toolsets.asset.AssetTools." + name, json.dumps(args))
def object_call(name, args):
    return execute_tool("editor_toolset.toolsets.object.ObjectTools." + name, json.dumps(args))
def unpack(value):
    value = value['returnValue'] if 'returnValue' in value else value
    return json.loads(value) if isinstance(value, str) else value
def run():
    scope = json.loads(SCOPE_JSON)
    calls, assets = [], {}
    def call(group, name, args):
        result = asset_call(name, args) if group == 'asset' else object_call(name, args)
        tool = ('editor_toolset.toolsets.asset.AssetTools.' if group == 'asset' else 'editor_toolset.toolsets.object.ObjectTools.') + name
        calls.append({'tool': tool, 'arguments': args, 'result': result})
        return unpack(result)
    def read(path, fields):
        if path in assets:
            return assets[path]
        ref = call('asset', 'load_asset', {'asset_path': path})
        actual_class = call('object', 'get_class', {'instance': ref})
        before = call('asset', 'is_dirty', {'asset_path': path})
        properties = call('object', 'get_properties', {'instance': ref, 'properties': fields})
        row = {'assetPath': path, 'object': ref, 'actualClass': actual_class, 'dirtyBefore': before, 'properties': properties}
        assets[path] = row
        if 'assetImportData' in properties:
            row['officialSourceData'] = call('object', 'get_properties', {'instance': properties['assetImportData'], 'properties': ['sourceData']})
        return row
    for item in scope:
        sprite = read(item['spriteAssetPath'], SPRITE_FIELDS)
        read(item['sheetAssetPath'], ['spriteNames', 'sprites', 'texture', 'assetImportData'])
        texture = sprite['properties']['sourceTexture']['refPath'].split('.')[0]
        read(texture, ['assetImportData'])
    for path in assets:
        assets[path]['dirtyAfter'] = call('asset', 'is_dirty', {'asset_path': path})
    return {'calls': calls, 'assets': list(assets.values())}
'''

_EXISTING_IDENTITY = '''import unreal, json
args = unreal.get_nxue_args()
objects = []
for path in args['assetPaths']:
    obj = unreal.load_asset(path)
    cls = obj.get_class().get_path_name()
    if cls not in ['/Script/Engine.Texture2D', '/Script/PaperSpriteSheetImporter.PaperSpriteSheet']:
        raise RuntimeError('Unexpected existing resource dependency class')
    source_id = obj.blueprint_get_texture_source_id_string() if cls == '/Script/Engine.Texture2D' else None
    objects.append({'assetPath': path, 'classPath': cls, 'sourceFiles': list(obj.get_editor_property('asset_import_data').extract_filenames()), 'sourceId': source_id})
print('NEXTGAME_EXISTING_RESOURCE_IDENTITY=' + json.dumps({'objects': objects}))
'''


def _object_path(package: str) -> str:
    if not isinstance(package, str) or not re.fullmatch(r"/Game/[A-Za-z0-9_/]+", package):
        raise ValueError("Expected an explicit project asset package")
    return package + "." + package.rsplit("/", 1)[-1]


def _checked_binding(binding: dict) -> Path:
    if not isinstance(binding, dict) or set(binding) != {"path", "sha256"}:
        raise ValueError("Expected an exact path/SHA-256 binding")
    path = Path(binding["path"]).resolve(strict=True)
    if _binding(path) != binding:
        raise ValueError("Existing resource evidence binding is stale")
    return path


def _scope(scope: list[dict]) -> list[dict]:
    if not isinstance(scope, list) or not scope:
        raise ValueError("Existing resource scope must be nonempty")
    for item in scope:
        if not isinstance(item, dict) or set(item) != {"spriteAssetPath", "sheetAssetPath"}:
            raise ValueError("Scope requires only explicit Sprite and SpriteSheet identities")
        for path in item.values():
            _object_path(path)
    if len({x["spriteAssetPath"] for x in scope}) != len(scope):
        raise ValueError("Duplicate existing Sprite scope")
    return sorted(scope, key=lambda x: x["spriteAssetPath"])


def _existing_program(scope: list[dict]) -> str:
    return _EXISTING_PROGRAM.replace("SPRITE_FIELDS", repr(_SPRITE_FIELDS)).replace("SCOPE_JSON", repr(json.dumps(scope, sort_keys=True)))


def _unpack(value):
    value = value["returnValue"] if isinstance(value, dict) and "returnValue" in value else value
    return json.loads(value) if isinstance(value, str) else value


def _replay_existing(scope, official):
    if set(official) != {"programSha256", "receipt"} or official["programSha256"] != _hash(_existing_program(scope).encode()):
        raise ValueError("Existing resource acquisition program identity differs")
    actual = _unpack(official["receipt"])
    if set(actual) != {"calls", "assets"}:
        raise ValueError("Invalid actual existing resource receipt")
    calls = iter(actual["calls"])
    def replay(tool, arguments):
        row = next(calls, None)
        if not isinstance(row, dict) or set(row) != {"tool", "arguments", "result"} or row["tool"] != tool or row["arguments"] != json.loads(arguments):
            raise ValueError("Existing resource read-only call ledger is incomplete or changed")
        result = row["result"]
        if not isinstance(result, dict) or set(result) != {"returnValue"}:
            raise ValueError("Official read receipt must retain its exact return envelope")
        return result
    namespace = {"execute_tool": replay}
    exec(_existing_program(scope), namespace)  # Only the fixed module-owned program.
    if namespace["run"]() != actual or next(calls, None) is not None:
        raise ValueError("Resource rows are not the deterministic official call projection")
    return actual["assets"]


def _identity_objects(identity, dependencies):
    if set(identity) != {"scriptSha256", "arguments", "receipt"} or identity["scriptSha256"] != _hash(_EXISTING_IDENTITY.encode()):
        raise ValueError("Unrecognized source identity acquisition")
    if identity["arguments"] != {"assetPaths": sorted(dependencies)}:
        raise ValueError("Source identity scope differs from actual dependencies")
    receipt = identity["receipt"]
    if receipt.get("ok") is not True:
        raise ValueError("Source identity acquisition failed")
    prefix = "NEXTGAME_EXISTING_RESOURCE_IDENTITY="
    lines = [line[len(prefix):] for line in receipt.get("data", {}).get("output", "").splitlines() if line.startswith(prefix)]
    if len(lines) != 1:
        raise ValueError("Missing exact source identity receipt")
    data = _json(lines[0].encode())
    objects = data.get("objects")
    if set(data) != {"objects"} or not isinstance(objects, list) or [x.get("assetPath") for x in objects] != sorted(dependencies):
        raise ValueError("Source identity receipt coverage differs")
    for item in objects:
        if set(item) != {"assetPath", "classPath", "sourceFiles", "sourceId"} or item["classPath"] != dependencies[item["assetPath"]]["actualClass"]["refPath"]:
            raise ValueError("Source identity class differs from official readback")
        if not isinstance(item["sourceFiles"], list) or len(item["sourceFiles"]) != 1 or not isinstance(item["sourceFiles"][0], str):
            raise ValueError("Exactly one actual imported source file is required")
        if item["classPath"] == _TEXTURE and (not isinstance(item["sourceId"], str) or not item["sourceId"].strip()):
            raise ValueError("Actual Texture2D source identity is missing")
        if item["classPath"] == _SHEET and item["sourceId"] is not None:
            raise ValueError("SpriteSheet does not declare a texture source ID")
    return {item["assetPath"]: item for item in objects}


def _actual_existing_rows(scope, official):
    rows = _replay_existing(scope, official)
    expected_sprites = {x["spriteAssetPath"] for x in scope}
    expected_sheets = {x["sheetAssetPath"] for x in scope}
    by_path = {}
    for row in rows:
        path = row["assetPath"]
        if path in by_path or row["object"] != {"refPath": _object_path(path)} or row["dirtyBefore"] is not False or row["dirtyAfter"] is not False:
            raise ValueError("Resource object is duplicated, redirected or unsaved")
        expected = _SPRITE if path in expected_sprites else _SHEET if path in expected_sheets else _TEXTURE
        if row["actualClass"] != {"refPath": expected}:
            raise ValueError("Actual resource class differs from the required type")
        if expected != _SPRITE and row.get("officialSourceData") != {"sourceData": {}}:
            raise ValueError("Source fallback requires the official sourceData serialization gap")
        by_path[path] = row
    return by_path


def _existing_frames(scope, rows, identities):
    """Derive source frames solely from actual sheet membership and source bytes."""
    from PIL import Image
    for item in scope:
        sprite, sheet = rows[item["spriteAssetPath"]], rows[item["sheetAssetPath"]]
        sp, sh = sprite["properties"], sheet["properties"]
        texture_ref = sp["sourceTexture"]
        texture_path = texture_ref["refPath"].split(".")[0]
        if sh["texture"] != texture_ref or texture_ref != {"refPath": _object_path(texture_path)}:
            raise ValueError("Actual Sprite and SpriteSheet texture identities differ")
        if len(sh["spriteNames"]) != len(sh["sprites"]) or len(set(sh["spriteNames"])) != len(sh["spriteNames"]):
            raise ValueError("Actual SpriteSheet membership is ambiguous")
        names = [name for name, ref in zip(sh["spriteNames"], sh["sprites"]) if ref == sprite["object"]]
        if len(names) != 1:
            raise ValueError("Sprite must occur exactly once in the actual SpriteSheet")
        source_name = names[0]
        descriptor_path = Path(identities[item["sheetAssetPath"]]["sourceFiles"][0]).resolve(strict=True)
        texture_source = Path(identities[texture_path]["sourceFiles"][0]).resolve(strict=True)
        descriptor = _json(descriptor_path.read_bytes())
        if (descriptor_path.parent / descriptor["meta"]["image"]).resolve() != texture_source:
            raise ValueError("Actual atlas source and SpriteSheet source disagree")
        frame = descriptor["frames"][source_name]
        rect, size = frame["frame"], frame["sourceSize"]
        x, y, w, h = (rect[k] for k in ("x", "y", "w", "h"))
        if any(type(v) is not int for v in (x, y, w, h)) or min(x, y) < 0 or min(w, h) <= 0:
            raise ValueError("Invalid existing atlas frame")
        if (frame["rotated"] is not False or frame["trimmed"] is not False or size != {"w": w, "h": h}
                or frame["spriteSourceSize"] != {"x": 0, "y": 0, "w": w, "h": h}
                or sp["bRotatedInSourceImage"] is not False or sp["bTrimmedInSourceImage"] is not False
                or sp["sourceUV"] != {"x": x, "y": y} or sp["sourceDimension"] != {"x": w, "y": h}
                or sp["originInSourceImageBeforeTrimming"] != {"x": 0, "y": 0}
                or sp["sourceImageDimensionBeforeTrimming"] != {"x": w, "y": h}):
            raise ValueError("Actual untrimmed/unrotated Sprite frame differs from its source")
        with Image.open(texture_source) as image:
            iw, ih = image.size
            if (x + w > iw or y + h > ih or descriptor["meta"]["size"] != {"w": iw, "h": ih}
                    or sp["sourceTextureDimension"] != {"x": iw, "y": ih}):
                raise ValueError("Atlas dimensions differ from actual source frame metadata")
            crop = image.convert("RGBA").crop((x, y, x + w, y + h))
        yield item, texture_path, source_name, frame, texture_source, descriptor_path, crop


def load_existing_resources(readback_path: Path) -> dict:
    """Closed existing-project-resource-catalog/1 evidence; no import manifest invented."""
    data_bytes = Path(readback_path).read_bytes()
    data = _json(data_bytes)
    if set(data) != {"version", "kind", "provider", "projectRoot", "capturedAt", "scope", "official", "sourceIdentity", "savedAssets", "frames"} or data["version"] != 1 or data["kind"] != "existing-project-resource-readback" or data["provider"] != _EXISTING_PROVIDER:
        raise ValueError("Unsupported existing project resource readback")
    if dt.datetime.fromisoformat(data["capturedAt"].replace("Z", "+00:00")).tzinfo is None:
        raise ValueError("Actual acquisition time requires a timezone")
    project = Path(data["projectRoot"]).resolve(strict=True)
    if not any(project.glob("*.uproject")):
        raise ValueError("Existing resources require an explicit Unreal project")
    scope = _scope(data["scope"])
    if scope != data["scope"]:
        raise ValueError("Existing scope must be canonical")
    rows = _actual_existing_rows(scope, data["official"])
    dependencies = {p: row for p, row in rows.items() if row["actualClass"]["refPath"] != _SPRITE}
    identities = _identity_objects(data["sourceIdentity"], dependencies)
    saved = {row["path"]: row for row in data["savedAssets"]}
    if any(set(row) != {"path", "saved_file"} or set(row["saved_file"]) != {"path", "sha256", "bytes"} for row in data["savedAssets"]):
        raise ValueError("Saved resource evidence must retain exact file identity and size")
    if len(saved) != len(data["savedAssets"]) or set(saved) != {_object_path(p) for p in rows}:
        raise ValueError("Saved asset evidence coverage differs from the actual resources")
    saved = {p: _saved(row, (project / "Content").resolve(strict=True)) for p, row in saved.items()}
    frames = data["frames"]
    if not isinstance(frames, list) or len(frames) != len(scope):
        raise ValueError("Cropped source frame coverage differs")
    resources = []
    for evidence, derived in zip(frames, _existing_frames(scope, rows, identities)):
        item, texture, name, frame, source, descriptor, crop = derived
        if set(evidence) != {"assetPath", "sourceImage", "sourceDescriptor", "sourceFrame", "textureSourceId"} or evidence["assetPath"] != item["spriteAssetPath"]:
            raise ValueError("Unexpected derived frame evidence")
        if _checked_binding(evidence["sourceImage"]) != source or _checked_binding(evidence["sourceDescriptor"]) != descriptor or evidence["textureSourceId"] != identities[texture]["sourceId"]:
            raise ValueError("Imported source identity binding differs")
        frame_path = _checked_binding(evidence["sourceFrame"])
        from PIL import Image
        with Image.open(frame_path) as image:
            if image.size != crop.size or image.convert("RGBA").tobytes() != crop.tobytes():
                raise ValueError("Resource source frame pixels differ from the actual atlas crop")
        path, sheet = _object_path(item["spriteAssetPath"]), _object_path(item["sheetAssetPath"])
        texture_object = _object_path(texture)
        relative = "existing/" + item["sheetAssetPath"].removeprefix("/Game/") + "/" + name
        resources.append({"id": "existing-resource-" + _hash((relative + "\0" + path).encode())[:24],
            "sourceRelative": relative, "sourcePath": str(frame_path), "sourceSha256": evidence["sourceFrame"]["sha256"],
            "dimensions": list(crop.size), "prefix": name.partition("_")[0], "system": item["sheetAssetPath"].rsplit("/", 1)[-1],
            "assetPath": path, "classPath": _SPRITE, "savedFile": saved[path],
            "dependencies": [{"assetPath": p, "classPath": c, "savedFile": saved[p]} for p, c in [(texture_object, _TEXTURE), (sheet, _SHEET)]],
            "brushResourceObject": {"refPath": path}, "atlas": {"textureAssetPath": texture_object, "sheetAssetPath": sheet,
                "frame": frame, "sourceUV": [frame["frame"]["x"], frame["frame"]["y"]], "sourceDimensions": list(crop.size)},
            "existingSource": {"image": evidence["sourceImage"], "descriptor": evidence["sourceDescriptor"], "textureSourceId": evidence["textureSourceId"]}})
    if Path(readback_path).read_bytes() != data_bytes:
        raise ValueError("Existing resource readback changed during validation")
    return {"projectRoot": str(project), "resources": resources}


def merge_existing_resources(base_catalog_path: Path, readback_path: Path) -> dict:
    base_header = _json(Path(base_catalog_path).read_bytes())
    if base_header.get("provider") != "NextGameUIResource":
        raise ValueError("Merge requires the original verified import catalog, not nested merged catalogs")
    base = validate_catalog(base_catalog_path)
    existing = load_existing_resources(readback_path)
    if base["projectRoot"] != existing["projectRoot"]:
        raise ValueError("Merged resources belong to different projects")
    resources = {row["assetPath"]: row for row in base["resources"]}
    from PIL import Image
    for row in existing["resources"]:
        previous = resources.get(row["assetPath"])
        if previous is not None:
            keys = ("dimensions", "classPath", "savedFile", "dependencies", "brushResourceObject", "atlas")
            if any(previous.get(key) != row.get(key) for key in keys):
                raise ValueError("Existing resource conflicts with its original import record")
            with Image.open(previous["sourcePath"]) as left, Image.open(row["sourcePath"]) as right:
                if left.size != right.size or left.convert("RGBA").tobytes() != right.convert("RGBA").tobytes():
                    raise ValueError("Existing resource pixels conflict with original import source")
        else:
            resources[row["assetPath"]] = row
    return {"version": 1, "kind": "nextgame-ui-art-resource-catalog", "provider": _EXISTING_PROVIDER,
        "projectRoot": base["projectRoot"], "sourceRoot": base["sourceRoot"],
        "resources": sorted(resources.values(), key=lambda r: (r["sourceRelative"].casefold(), r["assetPath"])),
        "provenance": {"baseCatalog": _binding(Path(base_catalog_path)), "existingReadback": _binding(Path(readback_path))},
        "resourceIdsIncluded": False}


def collect_existing_resources(scope: list[dict], *, project_root: Path, output_dir: Path,
        url: str = "http://127.0.0.1:8000/mcp") -> Path:
    """Fresh read-only acquisition; no caller-supplied provider or executable code."""
    from art_editor import HttpTransport
    project = Path(project_root).resolve(strict=True)
    if not any(project.glob("*.uproject")) or not (project / "Content").is_dir():
        raise ValueError("Existing resources require an explicit Unreal project")
    output = Path(output_dir).resolve()
    if any(output.is_relative_to(p) for p in [(project / "Content").resolve(), (project / "Tools").resolve(), Path(__file__).resolve().parents[3]]):
        raise ValueError("Evidence must be outside project Content and tool/plugin code")
    if output.exists():
        raise FileExistsError("Choose a new acquisition directory")
    scope = _scope(scope)
    transport = HttpTransport(url)
    schemas = {name: transport.describe(name) for name in (_ASSET, _OBJECT, _PROGRAM)}
    for toolset, names in [(_ASSET, ["load_asset", "is_dirty"]), (_OBJECT, ["get_class", "get_properties"]), (_PROGRAM, ["get_execution_environment", "execute_tool_script"])]:
        for name in names:
            matches = [x for x in schemas[toolset]["tools"] if x["name"] == toolset + "." + name]
            if len(matches) != 1 or "outputSchema" not in matches[0]:
                raise ValueError("Required official read tool output schema unavailable")
    environment = transport.call(_PROGRAM, "get_execution_environment", {})
    env = _unpack(environment)
    if env.get("language") != "python" or "execute_tool" not in env.get("instructions", "") or "json" not in {m["name"] for m in env.get("supported_modules", [])}:
        raise ValueError("Unsupported official programmatic environment")
    program = _existing_program(scope)
    receipt = transport.call(_PROGRAM, "execute_tool_script", {"script": program})
    official = {"programSha256": _hash(program.encode()), "receipt": receipt}
    rows = _actual_existing_rows(scope, official)
    dependencies = {p: row for p, row in rows.items() if row["actualClass"]["refPath"] != _SPRITE}
    # The official sourceData gap is checked above before invoking NxUE.
    args = {"assetPaths": sorted(dependencies)}
    completed = subprocess.run([sys.executable, str(project / "Tools/nxue/nxue.py"), "exec-python", "--script", _EXISTING_IDENTITY,
        "--args-json", json.dumps(args)], cwd=project, capture_output=True, text=True, encoding="utf-8", timeout=120)
    if completed.returncode:
        raise ValueError("Read-only source identity fallback failed: " + completed.stderr[-1000:])
    identity = {"scriptSha256": _hash(_EXISTING_IDENTITY.encode()), "arguments": args, "receipt": _json(completed.stdout.encode())}
    identities = _identity_objects(identity, dependencies)
    output.mkdir(parents=True)
    (output / "discovery.json").write_text(json.dumps({"schemas": schemas, "environment": environment}, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "official-program.py").write_text(program, encoding="utf-8")
    saved, frames = [], []
    for path in rows:
        saved_path = project / "Content" / (path.removeprefix("/Game/") + ".uasset")
        saved.append({"path": _object_path(path), "saved_file": {**_binding(saved_path), "bytes": saved_path.stat().st_size}})
    for item, texture, name, frame, source, descriptor, crop in _existing_frames(scope, rows, identities):
        filename = _hash(item["spriteAssetPath"].encode())[:16] + ".png"
        frame_path = output / filename
        crop.save(frame_path)
        frames.append({"assetPath": item["spriteAssetPath"], "sourceImage": _binding(source), "sourceDescriptor": _binding(descriptor),
            "sourceFrame": _binding(frame_path), "textureSourceId": identities[texture]["sourceId"]})
    readback = {"version": 1, "kind": "existing-project-resource-readback", "provider": _EXISTING_PROVIDER,
        "projectRoot": str(project), "capturedAt": dt.datetime.now(dt.timezone.utc).isoformat(), "scope": scope,
        "official": official, "sourceIdentity": identity, "savedAssets": saved, "frames": frames}
    readback_path = output / "readback.json"
    readback_path.write_text(json.dumps(readback, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    load_existing_resources(readback_path)
    return readback_path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--readback", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--tool-root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        catalog = load_resource_batch(args.manifest, args.readback, project_root=args.project_root, tool_root=args.tool_root)
        manifest_data = args.manifest.read_bytes()
        if _hash(manifest_data) != catalog["provenance"]["manifest"]["sha256"]:
            raise ValueError("Manifest changed before catalog output")
        manifest = _json(manifest_data)
        tools = args.tool_root or args.project_root / "Tools/UIResourceImport"
        write_catalog(args.output, catalog, tool_root=tools,
            protected_roots=[args.manifest, args.readback,
                *(Path(manifest[key]) for key in ("source", "stage", "destination")), args.project_root / "Content"])
        print(json.dumps({"ok": True, "catalog": str(args.output.resolve()), "resources": len(catalog["resources"])}))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
