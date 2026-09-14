#!/usr/bin/env python3
"""Mode and asset-boundary regressions for prototype entries and screen lists."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import unittest

from prepare_build import build_plan, effective_design_size_mode
from test_designer_size_mode import child_spec, screen_spec
from test_dynamic_list_rules import container_spec, entry_spec
from validate_layout_spec import load_json, validate_spec


SKILL_ROOT = Path(__file__).resolve().parent.parent
CATALOG = load_json(SKILL_ROOT / "references" / "component-catalog.json")
RULES = load_json(SKILL_ROOT / "references" / "rule-index.json")


def prototype(spec: dict, name: str) -> dict:
    spec = deepcopy(spec)
    spec["mode"] = "prototype"
    spec["asset"] = {"folder": "/Game/UI/AIPrototype/Test/Widgets", "name": name}
    return spec


def screen_collections(count: int = 7, mode: str = "production") -> dict:
    spec = screen_spec()
    spec["profile"].update({
        "listRole": "container",
        "collectionSizing": "fixed-viewport",
        "containsRepeatedElements": True,
        "regionGrouping": True,
        "explicitPanelSlots": True,
    })
    for index in range(count):
        node = deepcopy(container_spec()["nodes"][1])
        node.update({
            "id": f"collection-{index}",
            "name": f"ListCollection{index}",
            "rect": [index / count, 0, 1 / count, 0.5],
            "regionPurpose": f"collection-{index}",
        })
        if index % 2:
            node["role"] = "collection.lua-tile"
            node["name"] = f"TileCollection{index}"
            node["properties"].update({
                "entryWidth": 120, "entryHeight": 80, "verticalEntrySpacing": 0,
            })
        name = f"uw_role_entry{index}_list"
        node["properties"]["entryWidgetClass"] = {
            "refPath": f"/Game/UI/UMG/Role/Widgets/{name}.{name}_C"
        }
        spec["nodes"].append(node)
    return prototype(spec, "umg_ai_role") if mode == "prototype" else spec


def show_all_screen() -> dict:
    spec = screen_collections()
    spec["profile"]["collectionSizing"] = "show-all"
    for node in spec["nodes"][1:]:
        node["slotLayout"] = {
            "anchors": {"minimum": [0, 0], "maximum": [0, 0]},
            "offsets": {"left": 0, "top": 0, "right": 320, "bottom": 720},
            "alignment": [0, 0],
            "autoSize": True,
        }
    return spec


class PrototypeScreenCollectionTests(unittest.TestCase):
    def test_routed_rule_card_includes_prototype_child_naming(self) -> None:
        from route_rule_cards import build_rule_card_pack
        import uuid
        import json
        import os
        spec = prototype(entry_spec(), "uw_ai_task_list")
        spec["profile"]["designSizeMode"] = "Desired"
        test_root = Path(os.environ.get("NEXTGAME_UI_TEST_TMPDIR", str(Path.cwd() / "Saved/CodexUITestTemp"))).resolve()
        if test_root == SKILL_ROOT.parents[1] or test_root.is_relative_to(SKILL_ROOT.parents[1]):
            raise RuntimeError("Test fixtures must be outside the plugin tree")
        test_root.mkdir(parents=True, exist_ok=True)
        directory = test_root / ("prototype-card-" + uuid.uuid4().hex)
        directory.mkdir()
        path = directory / "entry.json"
        try:
            path.write_text(json.dumps(spec), encoding="utf-8")
            pack = build_rule_card_pack(path, stages=["build-planning"])
        finally:
            if path.is_file():
                path.unlink()
            directory.rmdir()
        card = next(c for c in pack["ruleCards"] if c["id"] == "prototype.asset-name")
        self.assertIn("uw_ai_*", card["summary"])
        self.assertIn("child-widget", card["summary"])
        section = next(s for s in pack["detailSections"] if s["heading"] == "## Designer mode analysis contract")
        self.assertIn("prototype `uw_ai_*` child widgets", section["text"])

    def assert_valid(self, spec: dict) -> None:
        report = validate_spec(spec, CATALOG)
        self.assertTrue(report["valid"], report["errors"])

    def assert_error(self, spec: dict, code: str, path: str | None = None) -> None:
        report = validate_spec(spec, CATALOG)
        matching = [item for item in report["errors"] if item["code"] == code]
        self.assertTrue(matching, report)
        if path is not None:
            self.assertIn(path, [item["path"] for item in matching], matching)

    def test_prototype_child_and_entry_allow_uw_ai_desired_or_fill(self) -> None:
        for source in (child_spec(), entry_spec()):
            for designer_mode in ("Desired", "FillScreen"):
                with self.subTest(source=source["profile"].get("listRole"), mode=designer_mode):
                    spec = prototype(source, "uw_ai_role_entry_list")
                    spec["profile"]["designSizeMode"] = designer_mode
                    self.assert_valid(spec)
                    plan = build_plan(Path("prototype-child.json"), spec, CATALOG, RULES)
                    self.assertEqual(plan["designSizeMode"], designer_mode)
                    create = next(step for step in plan["steps"] if step["stepId"] == "create-blueprint")
                    if source["profile"].get("listRole") == "entry":
                        self.assertEqual(create["arguments"]["parentClass"]["refPath"], "/Script/UIFramework.ListViewItem")

    def test_legacy_umg_ai_child_remains_valid_only_with_fill_screen(self) -> None:
        spec = prototype(child_spec(), "umg_ai_legacy_child")
        self.assert_error(spec, "profile.design_size_mode.umg_target")
        self.assertEqual(effective_design_size_mode(spec), "FillScreen")
        spec["profile"]["designSizeMode"] = "FillScreen"
        self.assert_valid(spec)
        del spec["profile"]["designSizeMode"]
        self.assert_valid(spec)
        self.assertEqual(effective_design_size_mode(spec), "FillScreen")

    def test_uw_ai_requires_child_kind_and_prototype_mode(self) -> None:
        for kind in ("screen", "prototype", None):
            with self.subTest(kind=kind):
                spec = prototype(screen_spec(), "uw_ai_screen")
                if kind is None:
                    spec["profile"].pop("assetKind")
                else:
                    spec["profile"]["assetKind"] = kind
                self.assert_error(spec, "asset.name")
        spec = child_spec()
        spec["asset"]["name"] = "uw_ai_entry"
        self.assert_error(spec, "asset.production_target")
        spec["profile"]["targetAsset"]["name"] = "uw_ai_entry"
        self.assert_error(spec, "target.name")

    def test_prototype_names_and_screen_designer_guard(self) -> None:
        for name in ("uw_ai_", "uw_role_entry", "umg_ai_", "uw_AI_entry", "uw_ai_entry\n"):
            with self.subTest(name=name):
                self.assert_error(prototype(child_spec(), name), "asset.name")
        spec = prototype(screen_spec(), "umg_ai_role")
        self.assert_valid(spec)
        spec["profile"]["designSizeMode"] = "Desired"
        self.assert_error(spec, "profile.design_size_mode.umg_target")

    def test_prototype_folder_is_a_safe_descendant(self) -> None:
        for folder in ("/Game/UI/AIPrototype", "/Game/UI/AIPrototype/Test/Widgets"):
            with self.subTest(folder=folder):
                spec = prototype(child_spec(), "uw_ai_entry")
                spec["asset"]["folder"] = folder
                self.assert_valid(spec)
        for suffix in ("Sibling", "/../UMG", "/Test/../../UMG", "/./Widgets", "//Widgets", "/Widgets/", "/Bad Name", "/%2e%2e/UMG", "/Test\\Widgets", "/Test\n"):
            with self.subTest(suffix=suffix):
                spec = prototype(child_spec(), "uw_ai_entry")
                spec["asset"]["folder"] = "/Game/UI/AIPrototype" + suffix
                self.assert_error(spec, "asset.folder")

    def test_nonfight_screens_allow_one_or_seven_distinct_endpoints(self) -> None:
        for mode in ("prototype", "production"):
            for count in (1, 7):
                with self.subTest(mode=mode, count=count):
                    spec = screen_collections(count, mode)
                    self.assert_valid(spec)
                    snapshot = deepcopy(spec)
                    plan = build_plan(Path("screen-local-collections.json"), spec, CATALOG, RULES)
                    self.assertEqual(spec, snapshot)
                    entry_bindings = [
                        step["arguments"]["values"]["entryWidgetClass"]["refPath"]
                        for step in plan["steps"]
                        if step["stepId"].startswith("set-widget-properties-collection-")
                    ]
                    self.assertEqual(entry_bindings, [node["properties"]["entryWidgetClass"]["refPath"] for node in spec["nodes"][1:]])
                    self.assertEqual(len(set(entry_bindings)), count)

    def test_screen_exception_does_not_include_fight_unknown_or_common(self) -> None:
        for system in ("fight", "Fight", "", None):
            with self.subTest(system=system):
                spec = screen_collections()
                if system is None:
                    del spec["profile"]["system"]
                else:
                    spec["profile"]["system"] = system
                self.assert_error(spec, "list.asset_kind")
                self.assert_error(spec, "list.container.multiple")
        spec = screen_collections()
        spec["profile"]["assetScope"] = "project-common"
        self.assert_error(spec, "list.asset_kind")
        self.assert_error(spec, "list.container.multiple")
        spec = screen_collections()
        spec["profile"]["assetKind"] = "prototype"
        self.assert_error(spec, "list.asset_kind")
        self.assert_error(spec, "list.container.multiple")

    def test_child_collection_modules_remain_single_endpoint(self) -> None:
        for mode in ("prototype", "production"):
            for system in ("fight", "role"):
                with self.subTest(mode=mode, system=system):
                    spec = container_spec()
                    if system == "role":
                        spec["profile"].update({"system": "role", "systemFolder": "Role"})
                        spec["asset"] = {"folder": "/Game/UI/UMG/Role/Widgets", "name": "uw_role_task"}
                        spec["profile"]["targetAsset"] = deepcopy(spec["asset"])
                    if mode == "prototype":
                        spec = prototype(spec, "uw_ai_task")
                    self.assert_valid(spec)
                    extra = deepcopy(spec["nodes"][1])
                    extra.update({"id": "extra", "name": "ListExtra", "regionPurpose": "extra"})
                    spec["nodes"].append(extra)
                    self.assert_error(spec, "list.container.multiple")

    def test_entry_and_fight_contracts_remain_strict(self) -> None:
        spec = prototype(entry_spec(), "uw_ai_task_list")
        spec["profile"]["designSizeMode"] = "Desired"
        for field, value, code in (
            ("assetKind", "screen", "list.asset_kind"),
            ("parentClass", "/Script/UMG.UserWidget", "list.entry.parent_class"),
            ("secondaryFunction", "row", "list.entry.secondary_function"),
        ):
            with self.subTest(field=field):
                bad = deepcopy(spec)
                bad["profile"][field] = value
                self.assert_error(bad, code)
        bad = deepcopy(spec)
        bad["nodes"][1]["slotLayout"]["offsets"]["bottom"] = 0
        self.assert_error(bad, "list.entry.root_size")
        self.assert_error(bad, "profile.design_size_mode.desired_root_size")
        bad = deepcopy(spec)
        bad["nodes"].append(deepcopy(container_spec()["nodes"][1]))
        self.assert_error(bad, "list.entry.nested_collection")
        bad = deepcopy(spec)
        bad["profile"]["targetAsset"]["integrationAsset"] = "/Game/UI/UMG/Fight/umg_fight1"
        self.assert_error(bad, "fight.integration_asset")

    def test_entry_paths_follow_mode_and_match_package_class(self) -> None:
        for mode in ("prototype", "production"):
            for root in ("/Game/UI/UMG", "/Game/UI/AIPrototype"):
                with self.subTest(mode=mode, root=root):
                    spec = screen_collections(mode=mode)
                    for node in spec["nodes"][1:]:
                        name = "uw_ai_entry_list" if root.endswith("AIPrototype") else "uw_role_entry_list"
                        node["properties"]["entryWidgetClass"] = {"refPath": f"{root}/Role/Widgets/{name}.{name}_C"}
                    if mode == "production" and root.endswith("AIPrototype"):
                        for index in range(1, 8):
                            self.assert_error(spec, "list.entry_widget_class", f"$.nodes[{index}].properties.entryWidgetClass")
                    else:
                        self.assert_valid(spec)
        # A root-local prototype entry and legacy string reference retain support.
        spec = screen_collections(1, "prototype")
        spec["nodes"][1]["properties"]["entryWidgetClass"] = "/Game/UI/AIPrototype/uw_ai_entry.uw_ai_entry_C"
        self.assert_valid(spec)

    def test_invalid_class_paths_are_rejected_on_every_endpoint(self) -> None:
        suffixes = (
            "Sibling/Widgets/uw_entry.uw_entry_C", "/../Other/uw_entry.uw_entry_C",
            "/Test/../../Other/uw_entry.uw_entry_C", "/./uw_entry.uw_entry_C",
            "//uw_entry.uw_entry_C", "/Widgets\\uw_entry.uw_entry_C",
            "/Bad Name/uw_entry.uw_entry_C", "/%2e%2e/uw_entry.uw_entry_C",
            "/Widgets/uw_entry.uw_other_C", "/Widgets/uw_entry.Uw_entry_C",
            "/Widgets/uw_entry.uw_entry", "/Widgets/uw_entry_C",
            "/Widgets/uw_entry.uw_entry_C:Subobject", "/Widgets/uw_entry.uw_entry_C\n",
        )
        for mode in ("prototype", "production"):
            roots = ("/Game/UI/UMG", "/Game/UI/AIPrototype") if mode == "prototype" else ("/Game/UI/UMG",)
            for root in roots:
                for suffix in suffixes:
                    with self.subTest(mode=mode, root=root, suffix=suffix):
                        spec = screen_collections(mode=mode)
                        for node in spec["nodes"][1:]:
                            node["properties"]["entryWidgetClass"] = {"refPath": root + suffix}
                        for index in range(1, 8):
                            self.assert_error(spec, "list.entry_widget_class", f"$.nodes[{index}].properties.entryWidgetClass")

    def test_each_list_retains_binding_variable_leaf_and_sizing_checks(self) -> None:
        self.assert_valid(show_all_screen())
        for index in range(1, 8):
            with self.subTest(endpoint=index):
                spec = show_all_screen()
                del spec["nodes"][index]["slotLayout"]
                self.assert_error(spec, "list.show_all.auto_size", f"$.nodes[{index}].slotLayout.autoSize")
                spec = screen_collections()
                del spec["nodes"][index]["properties"]["entryWidgetClass"]
                self.assert_error(spec, "list.entry_widget_class", f"$.nodes[{index}].properties.entryWidgetClass")
                spec = screen_collections()
                del spec["nodes"][index]["isVariable"]
                self.assert_error(spec, "widget.is_variable.collection_required", f"$.nodes[{index}].isVariable")
                spec = screen_collections()
                spec["nodes"].append({
                    "id": "static-child", "name": "PanelStaticChild", "role": "container.canvas",
                    "parent": spec["nodes"][index]["id"], "rect": spec["nodes"][index]["rect"],
                    "anchor": "left-top", "properties": {},
                })
                self.assert_error(spec, "tree.parent.not-panel", "$.nodes[8].parent")
                if spec["nodes"][index]["role"] == "collection.lua-tile":
                    spec = screen_collections()
                    spec["nodes"][index]["properties"]["entryHeight"] = 0
                    self.assert_error(spec, "tile.entry_size.required", f"$.nodes[{index}].properties.entryHeight")

    def test_screen_container_still_requires_collection_and_sizing_contract(self) -> None:
        spec = screen_collections()
        spec["nodes"] = spec["nodes"][:1]
        self.assert_error(spec, "list.container.missing")
        spec = screen_collections()
        del spec["profile"]["collectionSizing"]
        self.assert_error(spec, "list.collection_sizing")
        spec = screen_collections()
        spec["profile"]["containsRepeatedElements"] = False
        self.assert_error(spec, "list.container.repeated_elements")


if __name__ == "__main__":
    unittest.main(verbosity=2)
