# Unreal MCP workflow

## Server

Connect through the plugin dependency named `unreal-editor` at `http://127.0.0.1:8000/mcp`. The server exposes registry wrappers. Use `call_tool` with `toolset_name`, `tool_name`, and `arguments`.

For an explicitly authorized new Editor session with a fresh user profile, pass
both `-ModelContextProtocolStartServer` and `-ModelContextProtocolPort=<port>`.
The port flag alone does not request startup when Auto Start Server is disabled.
Resolve the Editor executable from the current project's EngineAssociation or
an explicitly supplied engine root; do not publish a developer's engine path.
For an already running session, the native console command
`ModelContextProtocol.StartServer <port>` starts the existing official server.
Do not change persistent user settings merely to start a task's own session.

Before using a nondefault endpoint, inspect its actual MCP initialization and
OS listener ownership. Bind the actual process/project and URL; a requested
port or same project path cannot establish the running instance's identity.
If a separate NxUE fallback is required, verify that its explicit endpoint
belongs to the same process. Never silently substitute a different listener.

These startup controls are documented in Epic's
[Unreal MCP command-line flags](https://dev.epicgames.com/documentation/unreal-engine/unreal-mcp-in-unreal-editor?application_version=5.8).

## Toolsets

- `UMGToolSet.UMGToolSet`: create, inspect, modify, compile, and organize Widget Blueprints.
- `editor_toolset.toolsets.object.ObjectTools`: list, read, and write UObject and Slot properties.
- `editor_toolset.toolsets.asset.AssetTools`: save generated assets.
- `EditorToolset.EditorAppToolset` or `SlateInspectorToolset.SlateInspectorToolset`: capture a preview when available.

## Required sequence

1. Use `ListWidgetBlueprints` or asset tools to check the destination.
2. Use `CreateWidgetBlueprint` with `/Script/UMG.UserWidget` as the parent.
3. Use `AddWidget` in parent-before-child order and preserve returned `widget` and `slot` `refPath` values.
4. When a node declares `isVariable`, call `ToggleWidgetAsVariable` with the Widget Blueprint, returned Widget reference, and the intended boolean value. Do not write protected `bIsVariable` through ObjectTools.
5. Before every ordinary property write, call `ObjectTools.list_properties`, `ObjectTools.get_properties`, then `ObjectTools.set_properties` with exact discovered names.
6. Use `CompileWidgetBlueprint` after all structural and WidgetTree property changes.
7. After that final compile, use `BlueprintTools.get_default_object` on the WidgetBlueprint, then ObjectTools `list_properties -> get_properties -> set_properties` on the returned generated `UUserWidget` CDO. Resolve the basename from `asset.name` in prototype mode, or preferentially from `profile.targetAsset.name` in production/formal lowering. Set only `designSizeMode`: `FillScreen` for every resolved `umg_*` basename; the explicit analyzed `FillScreen|Desired` decision for `uw_*`; and the recorded `FillScreen` fallback for missing/unclear or unknown/legacy values. Never let prototype future-target metadata, `assetKind`, directory, or a conflicting Requirement decision bypass the `umg_*` guard.
8. Use `AssetTools.save_assets` with the package path, without the `.AssetName` suffix, only after compile and the CDO write succeed.
9. Reacquire the generated CDO after save and verify actual `designSizeMode`; also use `GetWidgets` and property reads to verify the saved result, including each returned `bIsVariable` flag. Read collection `EntryWidgetClass` and every accepted state-branch Visibility from the saved assets rather than copying their planned values.
10. For a requirement-driven production build, normalize these actual reads into `Saved/CodexUIRequirements/<request-id>/unreal-widget-readback.json` using [unreal-widget-readback.schema.json](../../document-nextgame-umg/assets/unreal-widget-readback.schema.json). Run `python ../document-nextgame-umg/scripts/validate_unreal_widget_readback.py <readback.json> --requirement <requirement.json> --bundle <bundle.json>` from the build skill directory. Cover every built asset, actual generated-CDO `designSizeMode`, actual Widget, Bundle node mapping, variable flag, collection entry class, and accepted state branch. Point the Bundle's passed `widget-tree` and `key-properties` checks to this artifact through `artifactPath` without changing the Bundle top-level shape.
11. For a complete screen, preview or capture it at `2560 × 1440`; verify that the root and global layers fill the full canvas and that the main regions do not remain inside a smaller legacy source-size frame.

## Actual readback boundary

Apply [Actual verification and unchanged replay](visual-presentation-rules.md#actual-verification-and-unchanged-replay) to saved parent/Slot/resource/state coverage, representative views and unchanged execution. Preserve user edits in the initial actual baseline. Numeric property checks do not replace measured geometry or complete visual capture.

- Use the official Unreal MCP as the authoritative acquisition route and record `acquisition.method: official-unreal-mcp`. If it is unavailable or does not expose the exact required read, NxUEAgent may fill only that missing read; use `nxue-agent` with a nonempty `fallbackReason`, or `mixed` with a reason and JSONPath for every field-level fallback.
- Treat `UILayoutSpec`, build plans, Bundle mappings, and mutation inputs as expected state only. Never serialize them as actual Widget values or use them to fill a missing Unreal read.
- `DesignSizeMode` is editor-only data on the generated `UUserWidget` CDO, not a WidgetTree node and not a property of the WidgetBlueprint asset object. Read it from the CDO after save and serialize only `FillScreen|Desired` as `assets[].designSizeMode`.
- When official ObjectTools does not expose the protected CDO field, the permitted fallback is NxUE `manage-property` with object path `/Game/.../<Asset>.Default__<Asset>_C` and property path `DesignSizeMode`. Record the fallback reason in acquisition evidence; for mixed acquisition, identify the exact `$.assets[i].designSizeMode` field path. Save the WidgetBlueprint package and use a second `manage-property` get as post-save readback. `UWidgetBlueprint.ThumbnailSizeMode` is unrelated and must not be changed.
- Preserve the actual asset and Widget identities returned by Unreal, then relate them to Bundle assets and node mappings explicitly. A matching planned name is not proof that the Widget exists or is exposed as a variable.
- Do not pass `widget-tree` or `key-properties` verification until the normalized artifact is schema-valid and covers the affected asset.

## Preview and thumbnail freshness

Content Browser thumbnails and open Designer previews can be stale. Confirm actual asset identity, saved structure and a fresh relevant view before diagnosing an obsolete asset or visual regression; an old thumbnail alone is not evidence that a replacement or deletion is needed.

After the authorized compile/save/readback sequence, use an existing supported preview-refresh or thumbnail-refresh operation if the connected tool exposes one, then observe whether the display actually changed. Record an unavailable or unsuccessful refresh without blocking otherwise verified production. Do not create a replacement asset, delete a referenced asset, change ThumbnailSizeMode, clear broad caches, or force unrelated asset saves to repair a preview.

Unreal exposes Content Browser **Settings → Real-Time Thumbnails** and the native `FAssetThumbnail::RefreshThumbnail` API. These are discovery options, not a claim that a Widget Blueprint thumbnail will refresh through the current MCP/Python adapter. Do not fabricate a reflected callable for a native API or leave global realtime rendering enabled as a hidden workflow change. If no supported scoped refresh is available, report the preview limitation and use the current Designer/render evidence for the actual result.

References: [Content Browser settings](https://dev.epicgames.com/documentation/unreal-engine/content-browser-settings-in-unreal-engine?lang=en-US), [FAssetThumbnail](https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Editor/UnrealEd/FAssetThumbnail).

## References and failures

- Never guess WidgetTree or Slot references.
- A Widget Blueprint asset reference and its generated class reference differ. `AddWidget` may require `<asset>.<asset>_C` for a user-widget class.
- A CanvasPanel child layout belongs to its returned CanvasPanelSlot, not to the child Widget.
- Create only at the destination validated for the selected UILayoutSpec mode.
- In production mode, require the destination to exactly match the formal `profile.targetAsset`.
- If creation succeeds but later calls fail, keep the UILayoutSpec and report the partial asset path.
- Do not delete or overwrite an existing asset without explicit authorization.
