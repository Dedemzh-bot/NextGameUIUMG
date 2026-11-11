# State coverage for reverse prototypes

Empty source dependencies produce an `@unexpanded` audit marker with `sourceUnread=true`. It is not a WidgetTree node. Refresh the source with actual inherited/content evidence before completing coverage; changing the classification alone cannot clear this gap.

For Slot-aware version 2 work, also follow [Slot composition](slot-composition.md). Read and review the actual relationships between host, inherited slot and content; ordinary node coverage does not prove that the design used the correct composition. An explicitly read-back inheritance-only asset may use `ownTreeEmptyConfirmed` with its resolved inheritance relation; its parent content still requires coverage. Version 1 coverage remains historical and does not certify composition.

## Why source-node preservation is insufficient

The umg_bag pilot preserved BtnQuick but copied Designer Collapsed into ordinary screens. Static Lua analysis already showed positive-cost visibility; only the insufficient-funds combination was illustrated. The missing deliverable was the normal visible state, not a missing source node. Preserve this distinction in future reviews.

For each source widget, use an asset-qualified identity. Include child-widget and inherited scopes so identical names in different assets do not collide. The source snapshot is immutable; changing source or design revision invalidates dependent coverage evidence.

## Classifications

| Classification | Meaning and required evidence |
|---|---|
| static | No independent runtime-state obligation after reviewing its context; structural/decorative nodes may map many-to-one into the prototype. |
| active | A live function; an interactive control needs a visible normal case. |
| conditional | Visibility depends on runtime conditions; requires hidden and visible normal cases, plus applicable adverse states. |
| inactive | Explicitly removed from current business scope; needs user-decision or source-code evidence. Designer Hidden/Collapsed alone is insufficient. |
| template | Generated or inherited reusable entry, represented through its host; evidence and an explicit explanation of host coverage are required. |
| unknown | Unresolved; coverage cannot be declared complete. |

An interactive node must not be classified static. A hidden source node needs conditional/inactive/template resolution, including hidden ancestors. Even if currently visible, read bindings and state updates before deciding whether it is conditional. Nodes not expanded in the source remain unknown until a new source snapshot supplies them.

## Cases and linked content

For BtnQuick, require:
- hidden: total supply cost is zero;
- normal: cost is positive and silver is sufficient;
- insufficient-funds: cost is positive and silver is insufficient; cost warning and click feedback apply, button is not disabled.

`normal` and `hidden` are reserved case names. Use descriptive names for additional cases and place them in `requiredCases`. Code/user evidence justifies the required set; the checker cannot infer missed branches from a source-code file. Cases can share a screen if compatible; no exhaustive Cartesian product is required.

Record dependent field IDs in `relatedIds` and case `representedIds`. For a visible button case, its own ID and its dependent labels/cost/icon IDs must all be represented. If an associated field is legitimately absent in one case, split the semantic obligation or explain the scope in the analysis; do not mark an invisible field visible to satisfy the checker.

Each case references current Figma readback and screenshot evidence, file key, screen ID and control node ID. `visible` means effectively visible, on-canvas and not unintentionally clipped/occluded, based on the actual visual review. `visualReviewed` is an attestation; hashes establish file identity, not correctness of that attestation. Non-Figma source evidence explains conditions. File evidence records its exact path and SHA-256; evidence IDs may not be reused for changed bytes.

PanelAugment differs from BtnQuick: the user explicitly retired the former while the latter has a live conditional action. Capture that evidence rather than generalizing hidden=unused.

## Iteration obligations

Before applying a revision, compare functional IDs, node visibility, independent fields, host/entry relationships, required cases and exclusions with the previous ledger. Investigate missing/renamed/reclassified controls and lost state cases. Keep the previous ledger and report; do not backfill it with later approval.

The checker handles declared coverage and source identity, not automatic semantic discovery, screenshot analysis, navigation execution or approval. The coordinator remains responsible for inspecting these gaps. Passing `coverage-complete` is not `user-accepted` or `production-ready`.
