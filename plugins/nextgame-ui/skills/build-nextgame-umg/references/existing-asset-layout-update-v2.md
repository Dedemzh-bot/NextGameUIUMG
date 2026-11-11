# Existing Asset Layout Update Version 2

## Explicit scope and compatibility

Opt in with `UILayoutSpec 0.4` and Bundle capability `existing-asset-layout-update/2`. This branch consumes the separately closed `nextgame-ui-existing-asset-snapshot` version `2`. Historical Layout 0.2, existing-property Layout 0.3 and art snapshot/1 retain their original meaning and validators. Do not relabel old evidence.

Use this branch for authorized updates to an existing UI asset when collection footprint/pitch, a local addition or an explicit parent change cannot be expressed by the property-only branch. It does not create/recreate Widget Blueprints, delete nodes, rename existing variables, replace existing classes, edit Blueprint graphs, bind events, or change game source. The declared asset and every accepted native target remain bound to the complete Requirement, Accepted Build View and Bundle/Coverage.

`nodes` covers every actual existing UObject. `additions` describes only explicitly accepted new nodes; `reparents` preserves the existing identity and supplies both old and final native parent/Slot. New image receivers use GameImage and stable semantic names. Reused project Widget classes require exact current asset evidence. Do not manufacture an editable UObject for a null inherited declaration.

## Actual evidence and execution

Capture with `scripts/existing_asset_snapshot_v2.py capture`. Keep the complete GetWidgets order, raw NamedSlots, graphs, actual classes, native slots, current Designer mode, inherited declarations, and immutable saved-file backups. The source backup proves what was read; the executor separately compares the current Content file before writing. Changing a production asset must not invalidate the immutable historical baseline itself.

Use `validate_layout_spec.py`, `prepare_build.py` and the normal complete Requirement/View/Bundle/Coverage gates. The generated plan is not executable by the generic Create executor. Use the dedicated `execute_existing_update_v2.py` after its full preflight. Record intent before each write and actual schema/CAS/readback results. On failure retain recovery evidence and stop; do not delete created objects, discard unrelated edits, or silently replay a partial plan.

Compile and save scoped assets, read the actual result again, verify old protected identities/graph and NamedSlot bindings, reconcile only the declared sibling-order changes, and derive a zero-write repeat from the current state. Property agreement is not visual acceptance.

## Collections and content sizing

Preserve EntryClass. Keep visible content dimensions, native entry pitch, native spacing, host allocation, desired-size providers and runtime capacity as separate facts. The project's LuaTileView spacing contracts are owned by [dynamic-list-widgets.md](dynamic-list-widgets.md); do not redefine native spacing as an external gap. A changed list must bind its provider layout and accepted column/overflow/footprint decisions. A fixed item image must not stretch to consume its pitch's transparent gap.

An adaptive shared shell may declare multiple accepted host sizes only if its content/interaction/NamedSlot/state layers follow the same sizing responsibility. Provide a positive desired-size source, and review the provider content separately. A source size or a numeric declaration alone does not establish measured Desired Size or rendered proportions.

## Designer mode and review boundaries

The v2 snapshot records Custom and other actual legacy modes without changing their value. An explicitly accepted `designSizeModeTarget` can migrate to FillScreen or Desired; retain the exact old mode and validate the positive Desired-size proof. Do not use an intended mode as observed evidence. Every complete umg_* screen still targets FillScreen.

Existing text/visibility changes require explicit content/state acceptance tied to the locked design. This supports authored static states; it does not authorize runtime logic or changing data protocols. Runtime assignments which may override the authored state remain programmer dependencies.

Use `prepare_build.lower_px_font` for canonical compensated even-point font targets. The original new-build path calls the same helper. Preserve unrelated font/transform fields and independently check rendered glyphs.

## Class-specific appearance and inherited coverage

Only this branch captures and writes native ScaleBox `stretch`, `stretchDirection` and `ignoreInheritedScale`, and ProgressBar `fillColorAndOpacity`. Check the actual class and discovered field schema before writing. New ScaleBoxes declare all three fields; color writes use the actual observed prior RGBA. Do not backfill newly supported observations into historical snapshots. Reacquire affected assets and bind their new immutable evidence.

For an inherited-only provider, represent the sizing policy as an asset-owned nonvisual Requirement element. It may cover only that asset's uniquely owned full reference canvas after exact Layout hash, complete parent-chain and v2 Bundle validation. It is not a fabricated root widget and cannot replace mappings for actual visual or interactive nodes. All additions still require individual accepted mappings.

## Completion limits

The v2 snapshot and executor do not provide a canonical renderer. A schema pass, compile/save receipt, Designer screenshot or zero-write repeat cannot close fixed-resolution/DPI/state/data/font and measured-geometry obligations by itself. Preserve any missing preview coverage. This capability is static UMG tooling and does not replace the later independent result-acceptance or program-handoff gates.
