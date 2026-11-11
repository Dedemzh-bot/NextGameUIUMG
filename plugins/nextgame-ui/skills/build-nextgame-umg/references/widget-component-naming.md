# Widget-tree component instance naming

These rules were explicitly supplied by the project owner on 2026-07-23. Treat them as authoritative.

## Scope and creation stage

This file governs component instance names inside a Widget Blueprint's WidgetTree. It does not govern Widget Blueprint asset names.

Apply the two naming stages independently:

1. Create and name the Widget Blueprint asset using `project-ui-rules.md`.
2. Build its WidgetTree and name each component instance using this file.

Keep future Widget Blueprint asset-name rules in `project-ui-rules.md`. Keep future component instance-name rules in this file. If a future rule set concerns another creation stage or grows into a separate concern, place it in another directly linked reference instead of merging unrelated rules.

## Prefix rule

- Start every mapped component instance name with the exact case-sensitive prefix assigned to its concrete component type.
- Append a concise semantic name after the prefix, for example `PanelRoot`, `ImgMap`, `TxtTitle`, `BarStamina`, `ListQuest`, and `SizeMagazineWidth`.
- When a component's purpose is clear, replace Unreal-generated defaults such as `CanvasPanel_0` with a concise semantic mapped name.
- A generated/default name or prefix mismatch is a review warning, not a build-blocking error. If purpose is not yet clear, report it without failing or inventing a misleading functional name.
- Do not infer a prefix for an unmapped type. Record the missing rule and ask the project owner to supply it.
- The prefix rule does not prescribe mandatory suffix segments; also apply the owner-confirmed creation rule below.
- For data-driven collections, use a semantic `List` or `Tile` instance name such as `ListTask`; keep the entry Widget Blueprint asset naming separate according to `dynamic-list-widgets.md`.

## Revision-free creation names

Owner-confirmed on 2026-11-04; policy `component-creation-naming/2026-11-04`.

- New WidgetTree components use stable semantic names. Do not insert task iterations, revisions or batch versions such as `R14` into the name. For example, create `ImgShieldLocked`, not `ImgR14ShieldLocked`; record the revision in the task artifacts.
- Apply this to new-build Layout nodes in both prototype and production mode, and to Art `add-widget` operations in existing assets. A reserved iteration token is a blocking error, independent of the existing prefix warning.
- The shared creation check recognizes `R<number>`, `V<number>`, `Rev<number>`, `Revision<number>` and `Version<number>` at PascalCase or underscore boundaries, including lower-case underscore-delimited forms. It does not reject digits alone: `TxtPlayer2`, `ImgSlot01` and embedded identifiers such as `ImgR2D2Icon` are not revision tokens. A lexical check does not establish the purpose of every number; review ambiguous or differently spelled batch names semantically.
- Preserve unchanged observed names, program variables, Lua accesses, Blueprint and animation bindings. Existing-only Layout 0.3 takes its independent baseline-preserving route and cannot add or rename nodes. Art property/Slot edits do not apply creation naming checks to their existing target names. Do not force a legacy component rename to make it pass a new-build gate.
- Historical accepted layouts, snapshots and operations retain their original names and evidence. Review/replay them with their recorded frozen authority; selecting this newer creation gate for new work is an explicit policy migration, not retroactive evidence that older artifacts were invalid. A requested rename requires its own binding/reference audit and authorized migration.
- Build and Art share `scripts/component_naming.py` from the Build skill; do not duplicate a different token recognizer in another entry point.

## Type-to-prefix mapping

| Component type | Unreal class path | Required prefix |
|---|---|---|
| GameImage | `/Script/UIFramework.GameImage` | `Img` |
| TextBlock | `/Script/UMG.TextBlock` | `Txt` |
| ProgressBar (project term: Progress) | `/Script/UMG.ProgressBar` | `Bar` |
| Button | `/Script/UMG.Button` | `Btn` |
| Slider | `/Script/UMG.Slider` | `Sli` |
| RadialSlider | `/Script/AdvancedWidgets.RadialSlider` | `Rad` |
| CanvasPanel | `/Script/UMG.CanvasPanel` | `Panel` |
| Overlay | `/Script/UMG.Overlay` | `Over` |
| VerticalBox | `/Script/UMG.VerticalBox` | `Ver` |
| HorizontalBox | `/Script/UMG.HorizontalBox` | `Hor` |
| WrapBox | `/Script/UMG.WrapBox` | `Wrap` |
| LuaListView | `/Script/UIFramework.LuaListView` | `List` |
| LuaTileView | `/Script/UIFramework.LuaTileView` | `Tile` |
| Game Scroll Box (`UGameScrollBox`) | `/Script/UIFramework.GameScrollBox` | `Scr` |
| ScaleBox | `/Script/UMG.ScaleBox` | `Sca` |
| SizeBox | `/Script/UMG.SizeBox` | `Size` |

## Verified custom-component identities

The custom mappings above were verified against the running NextGame Unreal Editor 5.8 reflection data:

- `LuaListView` resolves to `/Script/UIFramework.LuaListView` and derives from `ListViewBase`; treat it as a leaf in the static WidgetTree.
- `LuaTileView` resolves to `/Script/UIFramework.LuaTileView` and derives from `LuaListView` then `ListViewBase`; treat it as a leaf in the static WidgetTree.
- `GameImage` resolves to `/Script/UIFramework.GameImage`; use it for every new image-like visual while retaining the `Img` instance prefix. Do not create native `/Script/UMG.Image` components in new assembly work.
- `GameScrollBox` resolves to `/Script/UIFramework.GameScrollBox` and derives from `CommonHierarchicalScrollBox`, `ScrollBox`, then `PanelWidget`; it may own WidgetTree children.
- `Overlay` resolves to `/Script/UMG.Overlay`; use `Over` for layered or shared-rectangle content as described in `component-knowledge.md`.
- `SizeBox` resolves to `/Script/UMG.SizeBox`; use `Size` for its one-child size-constraint purpose and follow `component-knowledge.md` for when the constraint is appropriate.

## Currently unmapped types

No project-owner prefix has yet been supplied for other catalog types such as Border or Spacer. Keep them usable without a prefix check, but do not derive a naming standard from their current example names.
