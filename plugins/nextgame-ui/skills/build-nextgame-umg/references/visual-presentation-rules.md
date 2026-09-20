# Visual presentation rules

These production rules generalize reviewed layout and art corrections. They apply to new analysis, build planning, art refinement and final verification. Exact resources, dimensions, slice cuts and text effects remain task decisions. They do not authorize a design change or establish acceptance of a finished Widget.

## Stage ownership

| Existing stage | Required decision or evidence |
| --- | --- |
| Requirement analysis / design reception | Semantic owners, independent headings and inputs, state scope, shared child boundaries, growth direction, image responsibilities and known design evidence. Preserve locked design decisions. |
| Requirement confirmation | Resolve material ambiguity; retain accepted relationships and explicit exceptions. A general review-method preference is not approval of every visual parameter. |
| Build planning / construction | Preserve accepted parents; declare actual direct-parent Slots; lower text geometry jointly; preserve local states and shared widgets. |
| Art packets / decisions | Inspect source frames and local reference pixels, choose exact imported resources, review every text effect, compare declared families and record uncertainty. |
| Plan / apply / verification | Check the simulated final state and actual saved state separately; compare local visuals and representative content/viewport/state cases; repeat unchanged execution. |
| Result confirmation / documentation | Present remaining uncertainty honestly. Obtain the separate post-build acceptance; only program-controlled behavior enters the program document. |

Use the existing entry points and review artifacts. Do not add a preliminary screening tool or substitute a new checklist for existing validation. The machine checks cover declared, measurable relationships; they do not infer semantic ownership, font appearance or source slice cuts from widget names.

## Local state ownership

- Put an item's selection marker and other item-specific state visuals under that item's accepted local owner or state branch. Do not put one screen-level marker outside all items merely because only one is visible in the reference. A deliberately shared moving indicator requires an explicit accepted design responsibility.
- Preserve each family's supported combinations. Separate selection from availability only when evidence supports independent variation; locked/unlocked may be values of the availability axis rather than another independent axis. Do not invent combinations from visual differences alone. Include hidden branches in art and readback coverage; a default screenshot is not coverage of those branches.
- Expose the actual runtime-controlled marker/branch as a variable. Inactive branches use `Collapsed` unless preserving their layout allocation is intentional; passive active visuals retain descendant input.
- State whether a selection group is exclusive only when supported by the requirement. Per-item selected/unselected branches alone do not prove cross-item exclusivity. Record the high-level group relationship for program handoff without implementing business switching logic.
- When several help triggers show the same functional popup with configured title/body, preserve one shared child asset and the accepted instance relationship. Do not duplicate the popup's internals per trigger. The popup's selected data is distinct from each trigger's local visual state.

## Image aspect and source identity

- Identify a resource by its actual use, imported asset identity, source bytes and supported state. A filename, thumbnail similarity or source canvas size alone does not establish correspondence. Search generic resources by function and confirm their visible content before reuse.
- Keep source frame dimensions, alpha-visible bounds and deliberately chosen visual core bounds distinct. For sprites, use the real frame, not the whole atlas. Transparent RGB pixels are not opaque borders; alpha bounds are not automatic slice cuts or design edges.
- Classify each image as preserving aspect, intentionally stretching, or using evidence-backed nine-slice behavior. Use full-frame aspect by default; document a different accepted basis or intentional deformation instead of silently cropping transparent margins.
- A square icon must remain square through the complete rendering chain: source frame, Brush `ImageSize`, parent Slot allocation, alignment, ancestor constraints, ScaleBox behavior and effective transforms. A square Brush inside a rectangular stretched Slot does not prove correctness.
- Inspect source/frame, Brush and allocation separately. Missing runtime geometry or unsupported ancestor reads remain unverified; never fill them from the planned rectangle. A calculated prediction may guide repair but cannot be labelled actual geometry.

## Nine-slice evidence

- Decide whether the artwork permits stretching before choosing Draw As. Complete ornaments or logos may require a fixed aspect image; a plate and a separate fixed glyph have different responsibilities.
- Measure cuts in the actual source frame. Identify the protected corners, border thickness, shadows, footer marks, glyphs and other art before selecting the stretch bands. Protect each region on the axes where it must not stretch: a straight top border may extend along X while preserving its Y thickness. Keep non-stretchable art outside the corresponding enabled stretch bands; a cut chosen only around the central icon can still damage the border.
- Record permitted stretch axes, source-frame size, pixel cuts, Brush basis/scale and protected regions. Convert cuts consistently to native margins; do not copy a convenient margin or use the same cut for unrelated textures.
- Check the target against the scaled protected caps on both axes. Too-small targets, overlapping cuts, empty stretch centers or a changed Brush basis with stale cuts require correction or a declared alternative rendering method.
- Transparent padding participates in the source frame but does not automatically define the visible seam. Verify visible edges after scaling at the actual DPI; do not guess a seam's cause from alpha or RGB alone.

## Text effects and annotations

- Review every TextBlock in scope, including static, unchanged and inactive-state text. Record an explicit effect judgment: none, outline, shadow, both, or unresolved. `None` needs positive visual evidence/reasoning; absence of a recognized edge is not enough on a low-contrast reference.
- Start with automatic local inspection of the original pixels and nearby background. Preserve the reference identity, original pixel crop coordinates, observation and uncertainty. Upscaling a crop helps inspection but does not add source detail.
- Distinguish effect-type confidence from parameter confidence. Clearly visible outlining does not prove its exact size/color; a candidate-similarity score is neither confidence value. Do not apply a global outline size to all labels.
- Before diagnosing a mismatch, check actual font object, typeface, fallback font, size, shadow/outline properties, DPI and preview context. Similar dark edges can come from a shadow, antialiasing, compression or background contrast. Readback proves properties exist; local comparison assesses their appearance.
- Use **automatic recognition plus annotations for remaining ambiguity**. Batch only the unresolved crops with the competing interpretations and a proposed correction. Preserve the user's precise annotation as design evidence. Agreement to this workflow does not confirm any specific effect or numeric parameter.
- A low-confidence or ambiguous judgment must remain unresolved until supported by stronger evidence or a specific confirmation. Do not manufacture a confirmation from a method preference, a previous asset's approval or a generic instruction to continue.
- Recheck effects against native post-save properties and local rendered text; record property match, visual result and remaining uncertainty separately. Do not reclassify unknown as `none` to satisfy coverage.

## Shared surfaces and visible seams

- A joined header/body or other continuous surface needs one explicit width authority and an intentional common visible boundary. Compute positions from the same owner and account for each resource's transparent insets; matching outer Slot rectangles alone does not ensure visible edges align.
- Choose a shared adaptive container only when its layout responsibility requires it. Keep content-driven Canvas, flow containers, Overlay and SizeBox within their existing selection rules; this rule does not mandate an Overlay for every popup.
- Keep desired-size producers independent from the stretched surface that follows them. Prevent cycles where the background drives desired width/height and then feeds its own stretch or text wrapping width. A stable wrap width and content-driven height must survive all ancestor Slots.
- Test short and long title/body combinations, including a long title with a short body. Verify wrapping, joined corners, top/bottom overlap or gaps and visible left/right edges. Do not repair a seam with an arbitrary offset before separating resource inset, padding, allocation, transform and rendering causes.
- Treat semantic parent and drawing order as separate decisions. A region heading near a Button belongs to the region when it describes that region; a label or decoration belonging to the Button stays in its content tree. Inspect parentage and effective draw order independently before reparenting.

## Family consistency

- Explicitly declare a visual family from shared function, resource family and layout responsibility. Matching file dimensions or nearby colors alone do not establish a family.
- Compare the relevant axes, frame-to-Brush scale, Slot allocation, margins and visible core across members, including unavailable or unselected states. Compare like contexts at the same reference scale.
- A different dimension is permitted when backed by an intended function/content difference. Record the exact member, property/axis and reason; do not normalize every plate or allow an unexplained outlier.
- Keep resource-color/state differences distinct from geometry differences. A family review supplements the per-image review and must not omit a member silently.

## Actual verification and unchanged replay

- Before editing an existing asset, capture current actual tree/properties and preserve user changes. Reconcile that state with accepted intent; do not overwrite it from an old plan.
- Verify saved node identity, class, parent, relevant direct-parent Slot, variable status, resource identity and visual properties. Verify inactive states and shared child assets, not only visible screen nodes.
- Verify the intended design canvas separately from screenshot pixel dimensions, editor zoom and DPI. Wider/taller screenshots must show the complete required viewport; a clipped editor capture cannot prove the off-screen edge passed or failed.
- Repeat the same accepted execution against the completed state. It must create no extra nodes and perform no redundant mutations or saves; compare stable identities, parent relationships and counts. When there was no legitimate asset write, compare asset bytes too. Counts alone cannot detect one node replacing another.
- Keep ordinary readback, measured geometry, render-context proof and human visual inspection distinct. Unknown geometry, unavailable canonical capture and residual seams remain pending even if property assertions and idempotence pass.
- A correction invalidates affected downstream evidence and prior result acceptance. Reacquire the final evidence and present it before opening the separate document gate. Promoting these standards is not approval of any task's current UI result.

## Compatibility and migration

Rule index `0.18` introduces these reusable policies and updates rule routing. Rebuild selected rule packs when their source version/hash changes. Historical requirement role-card identities and archived trial evidence are not rewritten.

The art workflow's explicit `presentation-review/1` capability opts into its closed presentation contract within existing requests, decisions and validation commands. New initialization enables it. Legacy requests without it keep their original interpretation and do not become compliant by being readable. To migrate an active task, create a new bound request/decision revision, cover the full declared scope, rebuild the plan and rerun the affected actual verification; preserve the baseline and previous artifacts. Do not copy old verification or user acceptance onto that revision.

See [art workflow](../../refine-nextgame-ui-art/references/workflow.md) for the executable contract and current supported measurements. Rules requiring semantic or visual judgment remain review duties when the native data cannot establish them; a machine pass must never be described as complete visual acceptance.
