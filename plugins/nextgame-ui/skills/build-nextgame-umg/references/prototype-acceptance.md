# Prototype acceptance protocol

## Scope and evidence boundaries

- Initial support is requirement-driven, all-`prototype`, Bundle `0.1`, with real assets under `/Game/UI/AIPrototype`. Keep the accepted Requirement, View, business topology, asset names, paths, and the existing seven-stage workflow intact. Do not use this contract for mixed-mode or reuse-only bundles.
- A prototype readback is diagnostic build evidence, not `ui-build-acceptance.json`, a formal document readback, or authorization for DOCX. User approval to run tests is not acceptance of their eventual result.
- Separate four results: compilation/save; actual tree and properties; transient visual fixtures; visual/layout acceptance. Passing one does not pass the others.

## Actual structure and property capture

1. Bind the current Requirement and executed Bundle SHA-256. Confirm no PIE, acquire exact asset identities, and record package dirty state and saved package hashes before testing. Never save unrelated user assets.
2. Use fresh official GetWidgets, class/property enumeration and get calls on Blueprint templates and generated CDOs. Capture every actual Widget and Slot, not a sample of recently edited nodes. Do not use Designer transient objects as saved-asset evidence.
3. Preserve original receipts. The normalized actual sidecar may join those actual reads, but retain the deterministic join script and raw hashes. Its widgets include actual identity/class/parent, variable flag, visibility, entry class, full required Widget properties, and Slot identity/class/properties. Plans only select expected comparisons and mapping IDs; missing actual values stay missing.
4. If official reflection resolves the Blueprint to its CDO instead of exposing the true asset class, or does not expose protected `DesignSizeMode`, use narrow read-only NxUE fallback and record the concrete field-level reason. Never guess the expected class or mode.
5. Validate `prototype-widget-readback.json` with `scripts/validate_prototype_widget_readback.py <readback> --requirement <requirement> --bundle <bundle>`. Evidence timestamps must be timezone-aware and no earlier than Bundle completion. Each actual asset source binding must match the hashed raw object. Passed Bundle tree/property checks point to this report. Rebind and revalidate after any Bundle change.

## Transient preview fixtures

- Baseline list preview count is not baseline data: repeated entry defaults must not pass as correct navigation, party, resource, metric, task or chat samples.
- Rediscover exact `/Engine/Transient` owner, class, membership and actual children before setting fixtures. A rebuilt owner invalidates every old mapping and receipt. Use official class/list/get/set/get, preserve original nested values and journal rollback before each batch. Never change templates/CDOs, author static sample children, save fixtures, invoke Lua, call business population/refresh, or invent runtime APIs.
- Bind fixture values to the current accepted View. An unchanged historical recipe may be reused only with explicit current reconciliation; its old hash/owner is not current evidence.
- Determine visual order by uniquely marked actual Slate coordinates or reviewed raw screenshots. Array order, object suffixes and zero cached geometry are not order evidence. Remove all markers and confirm absence before acceptance.
- Restore test probes to baseline and verify readback, list membership, asset dirty state and package hashes. Intentional baseline fixtures may remain transient for viewing, explicitly labeled volatile and cleared by Designer reconstruction.

## Visual and layout test matrix

Create a machine-readable task-side matrix. Every row identifies `id`, `assetIds`, `criterionRefs`, `scenario`, `expected`, `observed`, `status`, `evidence`, `limitation`, and `restoration`. Diagnostic status is exactly `passed`, `failed`, `blocked`, or `not-tested`; do not insert these extra states into an older closed Bundle schema. Blocked/untested rows stay non-passed in the Bundle and aggregate report.

- Resolution: the accepted screen baseline (this project: 2560×1440), plus a genuinely wider and taller viewport. Record actual raw PNG dimensions and measured on-screen scale. Editor `DPI Scale 1.0` and a logical resolution label alone do not prove native one-to-one pixels. Do not resample screenshots and relabel them as native 1440P. Never change asset `DesignSizeMode` to Custom merely to vary a preview viewport.
- Scope: each owned asset needs its own clean preview, including every accepted state branch. Parent list screenshots can provide integration evidence but do not silently replace child-asset coverage.
- Collections: test actual 0, 1, 2, capacity and over-capacity counts where required. Hiding existing entries is not a zero-count test. Verify native desired size, preserved anchors, independent background, correct growth direction and unchanged business order. Unsupported refresh/lifecycle paths are blocked, not simulated passes; do not implement pagination/business guards under visual testing authority.
- Text: exercise exact approved Chinese-character maximum samples, longer numeric values and independent semantic fields. Check width, wrapping/ellipsis, clipping, alignment and neighbor displacement visually. Restore baseline values with actual confirmation. A successful setter is not visual proof.
- Composition: review every in-scope graphic in three passes (surfaces, frames/tracks, accents), tied to its owning asset and actual screenshot. Verify passive/interactive layering, navigation selection, populated/empty party states, root fill, edge margins and protected center. Record missing or merged graphics individually; only accepted deviations can excuse omissions.
- Capability: a whole Editor screenshot, zero UObject geometry, a calculated expected rectangle, unsupported list refresh, or unreviewed render lifecycle does not satisfy clean render/adaptation acceptance. Record the exact missing safe tool path and retain partial evidence without adding C++/Lua/Blueprint business code.

## Result and reusable regression checks

- Publish a concise report with counts for all four statuses, concrete failed items, blocked capabilities, exact asset/report paths, and whether persistent assets changed. Do not describe a partial readback or restored fixture as complete acceptance.
- Validator changes must include positive tests and negative tests for wrong mode/path, forged or missing raw evidence, stale hashes/times, missing/extra Widgets, wrong class/parent/variable/state/entry class, incorrect Widget/Slot properties, and wrong verification artifact links. Keep production readback and documentation rejection tests.
- Re-run current Requirement/View/Layout/Bundle/coverage gates and regenerate the verification rule-card pack after any rule/validator change. Publish source/cache only after regression checks; preserve existing authority and historical receipts.
