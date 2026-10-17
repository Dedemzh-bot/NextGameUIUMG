# Material reference catalog

Lightweight discovery only, revision 1. Do not read every detailed reference.
First match the required effect, then verify these exact assets exist and follow
[the discovery and immutable-instance policy](material-instance-rules.md).
All paths below are package paths, not guessed transient object references.

| Effect / family | Root Material | Reference Widget and component | Existing seed / reserved ordinal | Detail after existence check |
| --- | --- | --- | --- | --- |
| Angular progress, sector cooldown, partial full-range fill | `/Game/UI/Materials/Circular_Progress_Bar_mat` | `/Game/UI/UMG/Fight/Widgets/uw_fight_skill` / `ImgCD` | `/Game/UI/Materials/Circular_Progress_Bar_CD_Inst` / `1` | [Circular progress](material-reference-circular.md) |
| Circular transparent opening, outer scope mask, soft edge | `/Game/UI/Materials/HaloMask_mat` | `/Game/UI/UMG/Fight/Widgets/uw_fight_scope` / `GameImageBlack` | `/Game/UI/Materials/HaloMask_Scope1_Inst` / `1` | [Halo mask](material-reference-halo.md) |

These existing seeds are never renamed or modified by reuse. Sequence allocation
must query the complete current root-Material family; this two-row catalog is not
a current instance inventory. Numerical presets below are observations, not
project-wide defaults.

## Evidence boundary

The 2026-09-30 source observations are distributed in
`../../../assets/material-reference-evidence/20260930/` as
`actual-material-readback.json` and `actual-graph-readback.json`.
UMGToolSet.GetWidgets was invoked through the existing NxUE reflected-call
fallback; actual parameter values came from MaterialEditingLibrary and protected
graph inputs from NxUE manage-property list/get. Official MCP tools were absent
from the chat and localhost:8000 was not listening.

The evidence includes both real Widget Brush resources, Parent links, effective
parameters, local overrides, 33 circular and 17 Halo parent expressions, output
connections, dirty-state observations and unchanged saved-asset hashes.
The acquisition scripts and diagnostic trials remain in the project task folder
`Saved/CodexUIStandards/material-instances-20260930`.

The generic draw-to-render-target diagnostic returned blank/black images. It
does not establish clockwise/counterclockwise visual labels or final target-UI
appearance. No persistent variant, reference edit, compile or save was performed.
Current native values and graph semantics are learned; new variants still need
actual UI rendering and normal verification.
