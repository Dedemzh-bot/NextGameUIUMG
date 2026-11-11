# Slot composition, creation naming and proportional-size review

## Change identity and decision

- Change: `nextgame-ui-composition-review/2026-11-04`.
- Owner decision: recognize **and use** Slot structure; keep iteration versions out of component names; inspect descendant structure/sizes and actual compressed results for proportional scaling. Thumbnail freshness is optional and is not an asset retirement request.
- Scope: local UI tool instructions, read-only acquisition, reverse-prototype composition evidence, new component naming and BuildBundle sizing validation. No game-source, Blueprint business-logic or production-asset change is authorized by this release.
- Decision accepted; implementation provided by this package. Runtime rendering and UI acceptance are separate and remain unclaimed. Task-specific screenshots, readbacks and review receipts stay outside the distributed plugin.

## Ownership and changes

| Responsibility | Authority and change |
| --- | --- |
| Slot interpretation/use | Build `references/shared-widget-reuse.md`, section `Slot recognition and composition decisions`; reverse `references/slot-composition.md` supplies the source/ledger v2 projection. |
| Acquisition | Art `composition_evidence()` and reverse `capture_composition.py` preserve raw inherited/NamedSlot/instance evidence independently from unchanged art snapshot/1. Runtime providers still require separate real class-default and source-code evidence. |
| Composition coverage | Reverse `composition_contract.py` and `prototype_workflow.py` validate declared relationships, host contexts and source/review evidence. They do not discover arbitrary runtime behavior or execute arbitrary Slot bindings. |
| Creation naming | Build `widget-component-naming.md` and shared `component_naming.py`, consumed by Layout validation and Art add-widget validation. Existing-only property edits preserve old bindings. |
| Proportional sizing | Build `visual-presentation-rules.md` and `requirement-build-handoff.md`; Bundle `explicit-scalebox` checks the actual declared role, common content ancestry, uniform mode/direction and supported positive unscaled-size basis. Unproved allocation, nested scaling and overflow remain explicit review items. |
| Render review | Existing actual-state and visual-review flow checks reference/compressed sizes, icons, numbers, state overlays, clipping and readability. Static checks do not inspect screenshots or establish rendered acceptance. |
| Preview freshness | `umg-mcp-workflow.md` distinguishes stale thumbnails from current assets. A supported refresh may be used; no refresh capability is fabricated and failure is non-blocking. |

Numeric project parameters, shared Registry activation requirements and business-code boundaries do not change. Existing ItemSlot/SlotTime interfaces are not renamed to SlotDown/SlotUp. Arbitrary Slot production execution remains limited to existing supported contracts; capability gaps cannot be repaired by flattening or duplicating the source.

## Versions, routing and migration

- Package: `0.1.0+codex.20261030.reverse1` → `0.1.0+codex.20261104.composition1`.
- Rule index: `0.27` → `0.28`, with creation-naming, Slot-composition and whole-component-scaling duties routed through planning, execution and verification, including fallback.
- Reverse normalized source and ledger: explicit opt-in version 2. Version 1 remains readable and reports composition coverage as not assessed. New composition work uses version 2; do not relabel a historical source or acceptance record.
- Art snapshot stays version 1. The raw composition sidecar has independent kind `nextgame-umg-composition-evidence`, version 1; it is not an accepted Requirement, BuildBundle or final readback.
- Bundle/Layout shapes remain unchanged. New-version validators tighten creation names and `explicit-scalebox` claims. Archived jobs use their frozen authority. An active job choosing this release must refresh affected rule packs and re-evaluate claims, retaining historical evidence.
- This is a plugin mapping/workflow change, not a new numbered project-design rule or fixed parameter. Project migration-map/module registries and parameter manifests are therefore unchanged.

## Verification and release boundary

Static syntax, closed schema structure, rule index/routing/fallback equality, local documentation targets and package hash comparison are the relevant performed checks recorded by the release task. Independent static reviews cover current diffs and callers. No C++ changed; Editor/Shipping compile configurations are not applicable.

The project requires explicit instructions before adding, changing or running tests. This request did not authorize that work, so no test cases were added/modified/run. Official Unreal MCP acquisition and current Figma/UMG render execution were not exercised by the maintenance release. Claims about current UI geometry, complete runtime provider discovery or visual acceptance would require separate real evidence.

Prepare in an isolated package, compare changed source files against the frozen baseline, publish only those files, install through the supported plugin manager and compare installed/source bytes. Keep release receipts and the prior complete source snapshot in the local task folder. Cache bytes being current does not hot-reload instructions already captured in an open conversation; a newly loaded skill context uses the installed revision.

Rollback restores the prior package/registry/router and installs that prior version through the same manager. New version-2 outputs remain versioned history; rollback must not rewrite them or change assets, game code or unrelated tools.
