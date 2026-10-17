# Reusable UI material instances

Policy revision 1, user-authorized on 2026-09-30. Applies to similar designs in
all systems, not only Fight. This is resource selection and Editor execution
policy, not a new Layout, Requirement, Bundle or procedural-art capability.

## Discover before learning

1. First identify whether the design needs angular progress/cooldown, a circular
   opening with an outer mask, or another material-backed effect. Search the
   existing rule IDs and the lightweight [material reference catalog](material-reference-catalog.md).
   Search before adding a duplicate rule, family or material.
2. Check the catalog's exact Widget, Brush resource, reference instance and root
   Material for existence using lightweight asset lookup. Inventory other
   instances of that root Material, including indirect descendants. A familiar
   filename is not proof of Parent identity or compatible behavior.
3. Only after finding a relevant existing candidate, load that family's detailed
   reference and read its current actual data: Widget Brush, full Parent chain,
   effective scalar/vector/texture/static-switch parameters, explicit overrides
   versus inherited values, and the parent expressions needed to understand the
   requested difference. Prefer official Unreal MCP and the existing UMG tools;
   record the exact reason for any NxUE fallback. Do not load all material graphs
   at startup, infer values from filenames, or treat archived notes as live state.
4. Compare requested direction, start, full range, shape/texture, mask size,
   feathering, aspect and tint against actual data. Reuse an exact compatible
   instance read-only. If any required authored parameter differs, follow the
   new-instance rule below. If lookup fails, distinguish missing from unavailable
   inspection and report the gap; do not invent a reference or silently replace
   the effect with fragmented GameImages or a new custom shader.
5. Maintain standards the same way: find the owning existing rule first, then
   inspect relevant assets, update that rule and its evidence, register routing,
   test and publish the source. Do not put task-specific values into global
   defaults or use the shared Widget Blueprint registry for Material assets.

## New instances only for authored variants

- Existing root Materials and saved material instances are read-only. Never
  change or resave a reference/shared instance to implement a new direction,
  start position, full range, mask coverage, feather width or other preset.
  Do not "temporarily change then restore" it for experiments.
- Create a new MaterialInstanceConstant at a non-existing authorized path.
  Prefer the same root Material as direct Parent, copying the relevant effective
  reference values before changing only the requested parameters. Do not copy
  only local overrides and accidentally lose inherited values. Do not edit the
  root shader or create a deep instance-parent chain to express a parameter
  variant. An unsupported capability requires a separate design/asset decision.
- Resolve the requested clockwise/counterclockwise behavior jointly with
  progress increasing/decreasing, start pivot and Brush/widget mirroring.
  Full-range changes are distinct from the current progress value. Do not infer
  either solely from a parameter name or a full/empty preview.
- Bind the resulting instance to one complete-graphic GameImage, retaining
  accepted ownership, layout and runtime-variable decisions. The legacy ImgCD
  is a native Image; learning its material does not authorize copying that
  legacy class into new assembly work.
- Per-widget runtime animation may use a newly created transient MID and
  change its runtime parameters; that must not write back to a saved instance.
  This exception does not replace creation of a persistent MIC for a new
  authored preset. Do not add Blueprint/Lua/C++ business logic in this stage.
- Before any write, preserve reference Parent/parameter/Brush evidence, package
  dirty state and saved-file hashes. Save only the newly created authorized
  instance and the authorized consumer, never Save All. Re-read the new Parent,
  effective parameters and consumer Brush after save. Confirm every pre-existing
  reference asset remains unchanged, including unsaved user state.

## One sequence per root Material

- The numbering key is the resolved root Material package, not the consuming
  Widget, system, direction, immediate instance Parent or destination directory.
  All new instances of the same root share one increasing sequence.
- In `/Game/UI/Materials`, use `<root basename without _mat>_Inst_<NNN>`,
  starting at `001`, minimum three digits. Continue naturally past `999`.
  Keep legacy names and references unchanged. The two legacy seeds and their
  reserved ordinal `1` are recorded once in the catalog; embedded business
  digits such as `Scope1` are not generic suffix parsers.
- Before allocating, enumerate the complete family across asset directories,
  resolve Parent chains, combine existing canonical ordinals, cataloged legacy
  reservations and current in-flight reservations, then select `max + 1`.
  Do not use asset count, fill deleted gaps, or restart numbering per variant.
  Unexpected legacy naming/ambiguous family membership must be resolved before
  allocation rather than guessed.
- Recheck both family inventory and destination existence immediately before
  creation. A collision requires a fresh inventory and a new reservation;
  never overwrite, auto-rename by an uncontrolled suffix, or reuse a number
  assigned by another task. When merely reusing an identical instance, allocate
  nothing. Record root, ordinal and final path in the existing task evidence.
- With only the recorded seeds present, examples of the next names are
  `Circular_Progress_Bar_Inst_002` and `HaloMask_Inst_002`. These are examples,
  not reserved assets or hardcoded future next numbers.

## Verify effects separately

- Verify empty, partial and full progress, both requested directions, start
  position and reduced full ranges in the actual target UI context. For Halo,
  verify the opening, outer coverage and feather at target, wider and taller
  allocations. Keep widget/Brush tint separate from material color and opacity.
- Use new transient instances for disposable parameter experiments, never the
  saved reference. A black/blank capture is failed visual evidence. Parameter
  reads, mathematical deductions, thumbnails and compile success do not prove
  final rendered appearance. Keep unverified direction/appearance explicit.
- Do not feed these MaterialInstanceConstant graphs to `procedural-ui-material/1`
  or `/2`, whose closed contracts do not support them. Use a supported,
  authorized binding/readback path or report the missing capability; do not
  weaken art validators or fabricate graph/compile evidence.
- Reusing these references grants no production write authorization and no
  requirement/result acceptance. Preserve normal design review and final
  result gates. Existing approved runs require explicit migration if changed.
