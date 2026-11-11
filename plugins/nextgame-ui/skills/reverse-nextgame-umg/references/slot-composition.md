# Slot recognition and use in reverse prototypes

The owner confirmed on 2026-11-04 that Slot support means recognizing existing composition and using it correctly in design and construction. Capturing an extra property alone is insufficient. Apply the shared [Slot recognition and composition decisions](../../build-nextgame-umg/references/shared-widget-reuse.md#slot-recognition-and-composition-decisions) rules; this reverse route does not introduce another Unreal execution contract.

## Acquire before normalizing

Use the official Unreal MCP where available. The read-only helper preserves raw WidgetTree records, ordinary parent references, NamedSlot host references, full `GetNamedSlots` records, parent-class information and graph evidence in a separate `nextgame-umg-composition-evidence/1` file:

```text
python scripts/capture_composition.py --url <configured-unreal-mcp-url> --asset /Game/UI/Host --asset /Game/UI/Shared --out <new-composition-evidence.json>
```

The command discovers schemas and the permitted programmatic environment through the existing Art adapter. It performs no compile, save, reparent or runtime-code change. It does not alter closed `nextgame-ui-art-snapshot/1`; that format remains valid for existing Art comparison/apply consumers and its flattened `parentWidgetName` must not be used as proof of NamedSlot placement.

Expand relevant inherited and nested assets explicitly. A null ordinary parent is not proof of a root: inherited NamedSlot content may be stored in WidgetTree `NamedSlotBindings`. If the official tools are absent or omit needed fields, use the project-approved read-only fallback and preserve its raw receipt. Runtime insertion also requires class-default/property evidence plus the actual code path that loads and fills the slot. A class reference alone proves neither inheritance nor a binding.

## Normalized source version 2

`nextgame-umg-reverse-prototype/2` retains the version 1 `screen`, `dependencies`, `nodes`, `limits` shape and adds required `compositionRelations`. Every asset block declares its observed `parentClass` string (null only for unread dependencies); an observed Blueprint parent must have a matching inheritance relation. Each relation uses the closed shape enforced by `scripts/composition_contract.py`:

| Field | Meaning |
| --- | --- |
| `id` | Stable relation identity, distinct across host instances. |
| `kind` | `inheritance`, `widget-instance`, `named-slot-content`, `named-slot-empty`, or `runtime-slot-content`. |
| `hostAsset`, `hostWidget` | Owning asset and its nested instance node; use null hostWidget for the asset itself/inherited slot. |
| `slotOwnerAsset`, `slotName` | Asset declaring the observed NamedSlot and its exact name; null for non-Slot relations. |
| `contentAsset`, `contentRoot` | Actual referenced asset and inserted root; inheritance has no contentRoot; empty slots have neither. |
| `classProperty` | Exact observed runtime class-path property when present, otherwise null. Never infer it from naming. |
| `status`, `unresolvedReason` | `resolved` with empty reason, or `unresolved` with a concrete gap. |
| `evidenceIds` | IDs of actual acquisition/code evidence entered into the ledger's existing hashed evidence list. |

All fields are required; use null only where its meaning is specified. Include unknown content assets as unread dependencies instead of omitting them. A runtime relation with unknown content uses null content fields and unresolved status. A NamedSlot must have an explicit content, empty, or unresolved relation; an observed empty Designer slot is not `named-slot-empty` when code injects content. Empty-slot classification needs source-code or explicit scope-decision evidence in addition to readback. Declaring both empty and runtime content for the same host/slot is rejected. A custom `/Game/` Widget node needs a widget-instance relation. Multiple conditional alternatives for a single host/slot are currently unsupported in one normalized source: retain separate explicit source revisions/cases and report this limitation, never choose a convenient alternative or call it resolved.

Inherited slot ownership must be connected through explicit inheritance relations. A slot on a nested Widget instance must also cite a recorded widget-instance relation. Identities remain asset-qualified; the same slot used by two different host nodes has separate relation IDs and reviews. Every declared slot needs its effective binding for the owning asset, each inheriting asset and each actual nested instance. The coverage key is `(hostAsset, hostWidget, slotOwnerAsset, slotName)`, not just owner/slot. Reusing a source/default binding means explicitly recording the same observed content or empty state in the consumer's own relation, with evidence that it is retained; no automatic default-copy assumption is made. One instance's filled slot cannot cover another instance or its source asset. Missing contexts are rejected rather than silently treated as empty. The validator checks endpoint existence, slot class, duplicate bindings, omitted NamedSlots/custom instances, conflicting native parents, inheritance ownership and composition cycles. It does not infer missing runtime relations from source code or establish visual correctness.

Version 2 adds an `asset#@asset` context marker for every asset. This is an audit identity for the asset in a composition case, not a fabricated WidgetTree control or proof of effective visibility. An inheritance-only asset with no own nodes can declare `ownTreeEmptyConfirmed: true` after actual readback and a resolved inheritance relation; its separate `@unexpanded` audit marker is then no longer unread. The ancestor's controls must still be expanded and reviewed. Without that explicit evidence, the legacy `@unexpanded` marker remains unread. Neither marker is an actual WidgetTree control.

## Review how the structure is used

Preparing a version 2 source creates a version 2 ledger with a `compositionReviews` record for every relation. Each record declares the relationship's semantic `role`, one `decision` (`preserve-composition`, `reuse-slot`, `propose-redesign`, or initially `unresolved`), a rationale, evidence IDs and actual rendered cases in the existing CASE format. Preservation and reuse must reference current Figma readback. A redesign proposal additionally needs an explicit user design decision; a proposal does not authorize execution.

Review the composed result at every relevant host instance: public frame, inserted content, state overlays, inherited extension, clipping and sizing. Version 2 inventory labels `sourceVisibilityScope` explicitly as asset-local; `sourceHidden=false` does not assert composed visibility through a reused/inherited host. Every relationship needs a visible composed case. Its represented IDs must include the host's `asset#@asset` context marker and the content asset's marker when present, as well as the host instance, slot owner's marker/slot node and content root where applicable. Inheritance therefore cannot pass with an empty represented set or only a parent-asset picture without the consuming asset context. These markers map to the actual composed screen/case context; they are not extra visible controls. Hash-verified readback and screenshots are required; `visualReviewed` remains an honest reviewer attestation, never automatic screenshot analysis. Runtime injection needs both source-code and source-readback evidence. Unresolved relations, missing reviews/evidence or incomplete visual cases block coverage completion. Slot-cycle checks are scoped to each insertion rather than merging all host instances into a fictitious asset-level tree.

Source and ledger versions must match. Version 1 continues to validate under its historical shape and reports `compositionCoverage: not-assessed-legacy-v1`; do not relabel old acceptance as version 2. Migrate only by fresh evidence and a new source/ledger revision. These offline facts and design-use reviews are not BuildBundle operations: lower accepted choices through existing supported reuse relations, and expose any unsupported arbitrary Slot binding as a production capability gap instead of flattening it or inventing an operation.
