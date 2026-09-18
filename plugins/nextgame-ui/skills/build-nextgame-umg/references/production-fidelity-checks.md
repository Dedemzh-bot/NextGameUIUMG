# Production fidelity checks

Policy revision 1, approved for reusable production practice on 2026-09-18. These checks supplement existing text, image, adaptation and actual-readback rules. They do not define project dimensions, grant design-change permission, or accept a finished UI. Apply them inside the existing analysis, design reception, build, optional art and verification stages; do not add a preliminary screening tool.

## Accepted property coverage

- For every accepted decision that affects a Widget or its direct-parent Slot, trace its source value through the layout, generated operation and saved actual property. Identify the exact asset, widget, property and responsible stage in the existing planning/verification records; a node-count match is insufficient.
- Distinguish an emitted supported operation, a value already equal in current actual readback, an explicitly assigned later-stage operation, and an unsupported/unresolved mapping. An emitted operation establishes planned coverage only; execution coverage requires its successful completion evidence and saved actual readback. An already-equal value requires current actual evidence. A later-stage item remains outstanding until its execution and readback are linked.
- An executor allowlist is a capability boundary. A filtered property must remain an explicit gap; it must not disappear from the coverage review or be replaced by an inferred default. A plan marked ready proves only that plan's scope. Do not describe it as application of all accepted properties.
- Resolve an unsupported field through an existing capable build stage or a separately supported mapping, preserving accepted values. For example, an art path supporting Wrap Text At but not Auto Wrap or collection spacing cannot claim to apply those other fields. Do not bypass the tool's limits or silently expand its authority.
- After another stage changes the asset, reacquire the affected baseline and plans against the new actual state. Preserve already bound source bytes, including encoding and line endings; revisions get new bindings. Never rewrite source observations to make an incorrect plan pass.

## Text capacity and stable placement

- Decide semantic wrapping, native Auto Wrap, Wrap Text At (positive when wrapping is intended, zero when explicitly disabled), Slot width, Size To Content, justification and the stable growth edge/center separately, then lower them together. A semantic wrap flag must not overwrite an accepted Size To Content decision. An explicit positive wrap limit can provide wrapping without native Auto Wrap.
- Separate observed text bounds, the allotted layout area and the capacity reserved for longer text. Increasing a wrap limit or localization allowance does not move the approved center/right/left reference point. A larger capacity rectangle is not new positional evidence.
- For a bounded centered/right-aligned text area, keep its real width and Size To Content disabled. For content-driven text, preserve the approved point anchor, offset and matching alignment so growth maintains its center or right edge. Justification alone cannot position an auto-sized component.
- A width constraint and content-driven height must survive all ancestor Slots. Test short and representative long content, including a long popup title with a short body and the converse. Font compensation and preliminary text measurement do not prove wrapping or Desired Size in the final widget.

## Resource identity and explicit appearance

- Confirm each resource against its semantic role, supported state, visible content and actual imported asset identity. Filename suffix order, thumbnail similarity and equal texture sizes are discovery hints, not a state/color mapping. Review each family member, including hidden ones; do not copy the first member's result.
- Resolve descriptions such as dark, gray or mirrored into the exact accepted resource and/or supported native properties. Record uncertainty when the value is not established; an instruction to continue does not prove a particular source identification.
- Separate color baked into the source, alpha, the Brush/widget color multiplier and render opacity. Declare the color space at each conversion boundary and apply a tint once at its intended layer. Values inferred by reversing a composite image remain hypotheses until the source/alpha assumptions and rendered appearance are checked.
- Read back the exact resource and relevant color/transform fields after save. A written mirror/tint decision that never reaches a native property is an uncovered decision under the property-coverage rule.

## Geometry responsibilities and related surfaces

- Distinguish the resource's complete frame, alpha-visible bounds, chosen visual core, reference display bounds, Brush dimensions and actual parent allocation. A transparent inset is not automatically a crop, a slice cut or a layout edge; source-frame dimensions do not by themselves specify on-screen size. Check aspect through the parent and effective transform, not just the Brush.
- Determine reference framing, semantic edge attachment and device safe insets separately. Extra background on a wide reference is not evidence of a device safe area. Decide each axis from the accepted owner and protected content; do not derive safe insets from an aspect-ratio difference. At wider/taller viewports verify the declared edge margin, movement and stretch, not merely the anchor enum.
- Include every supported hidden-state member in the geometry review. Derive a repeated marker's position from its own semantic owner and approved family relation; an unseen state has no directly observed reference position. A copied screen coordinate or unrelated member's parent transform is not evidence. Inspect supported states individually without inventing business combinations.
- For related plates, entries and joined header/body surfaces, compare complete-frame scale, allocated boundaries, protected art and visible insets together. Use one accepted width authority for a continuous seam. Keep deliberate member exceptions explicit; neither equalizing all sizes nor accepting unexplained outliers is valid.
- Check list viewport, entry footprint and pitch together. Do not shrink a correctly proportioned graphic merely to fit an incorrectly derived container; first establish which source/constraint is authoritative. Preserve the collection's accepted behavior and shared-child boundaries.

## Independent verification and unchanged replay

- Report these results separately: accepted-source-to-plan correctness; plan-to-saved-property agreement; actual Desired Size/allocation; rendered geometry and visual comparison. Deriving the plan and the expected values with the same calculation is not an independent check of design intent.
- Preserve render context: asset/state/content, complete viewport, DPI and editor zoom where relevant. A Designer screenshot with selection overlays or displayed inactive branches is diagnostic evidence, not proof of runtime state visibility. Estimated font size or Slot arithmetic must not be relabelled measured geometry.
- Missing rendering, unavailable actual geometry, contradictory measurements and uninspected hidden/long-content/viewport cases remain pending. An unrelated property pass or high whole-image similarity cannot close them. Use supported versioned verification artifacts; do not invent pass fields or weaken the final acceptance gate.
- Repeat unchanged execution after completion and verify stable node identities, parents, classes and relevant properties, not counts alone. It must create no extra nodes. Where the executor supports a no-op path, verify no redundant writes/compile/save; otherwise report that limitation rather than claim byte-stable replay. Compare asset bytes when no legitimate write occurred.
- A design, layout or asset correction invalidates affected evidence and result acceptance. Rebuild affected plans, read back again and present the final result before the separate result-confirmation/documentation gate. Approval of these rules is not approval of any current UI.

## Integration and migration

| Existing stage | Apply these sections | Required outcome |
| --- | --- | --- |
| Raw analysis / design reception | Text capacity; resource identity; geometry responsibilities | Preserve explicit decisions and uncertainties; do not reinterpret locked design content. |
| Build planning | Property coverage plus all relevant text/image/layout sections | Every accepted field has an executable mapping, actual equality or an explicit outstanding gap. |
| Execution / optional art | Property coverage; resource identity; related surfaces | Apply only supported accepted changes, retain pending work and refresh affected baselines. |
| Verification / result presentation | Independent verification and unchanged replay | Separate native agreement from visual evidence; preserve pending cases and the result gate. |

This revision adds review duties and routes them through existing rule packs. It does not add a Schema capability or claim new automatic detection of semantic/resource/visual errors. Existing validators still enforce their supported properties and bindings. Routing regression tests prove that these duties reach the proper stages, survive fallback and invalidate stale packs; they do not prove a screenshot is correct.

New runs read this revision. Active runs regenerate affected rule packs and review the affected mappings; change an accepted Requirement only through its normal revision/review process. Archived inputs, source measurements, trial observations and acceptance receipts remain untouched. Concrete dimensions, crop values, color estimates and screen-specific fixtures remain task decisions. No new resolution-conversion rule or default is introduced here.
