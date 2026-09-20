# Art-stage workflow

Commands below run from this skill's directory. Replace quoted `<...>` paths with current task files; outputs belong outside the plugin. Complete JSON stays on disk. Return compact receipts, new decisions and unresolved issues to the coordinator.

## 1. Route, collect and initialize

```powershell
python scripts/art_pipeline.py route --goal formal-art --has-baseline --has-resources
python scripts/art_pipeline.py collect --asset /Game/UI/UMG/Example/Widgets/uw_example_card --output "<request-dir>/art/baseline-snapshot.json"
```

The asset above is illustrative, not a real task target. `collect` reads the current Editor and accepts repeated `--asset`. A successful command can still contain diagnostic `designSizeMode: null` or `referencesComplete: false`; inspect these before planning. See [runtime support](runtime-support.md). Do not fill unknown values from the expected layout.

`init` takes compact file paths, computes bindings, derives `requestId` from the accepted Requirement and runs the baseline authority validators. Optional `target` is a new accepted Requirement and corresponding Bundle, not an edited copy of compiled fields. Paths in the job resolve relative to the job file. Default budget is two correction rounds, 16 model calls and no numeric token limit; set the user's actual budget explicitly when provided.

Illustrative `job.json` shape for one child widget, **not executable evidence**: the asset/path names and all-zero font digest below must be replaced with verified task inputs. Empty authorization intentionally grants no production mutation.

```json
{
  "goal": "upgrade-art",
  "originalText": "Replace this example with the user's actual requested art change.",
  "scope": [{"assetPath": "/Game/UI/UMG/Example/Widgets/uw_example_card"}],
  "baseline": {
    "requirement": "baseline/ui-requirement.json",
    "bundle": "baseline/ui-build-bundle.json",
    "readback": "baseline/unreal-widget-readback.json",
    "snapshot": "art/baseline-snapshot.json"
  },
  "references": [{
    "id": "card-default",
    "assetPath": "/Game/UI/UMG/Example/Widgets/uw_example_card",
    "image": "reference/card.png",
    "context": {
      "size": [256, 128], "dpiScale": 1, "locale": "zh-CN",
      "dataId": "card-preview-data", "stateId": "default",
      "fontSetDigest": "0000000000000000000000000000000000000000000000000000000000000000",
      "background": [0, 0, 0, 1]
    },
    "regions": [{"id": "icon", "bounds": [0, 0, 64, 64], "widgetNames": ["ImgIcon"]}]
  }],
  "resourceDir": "cuts",
  "authorizedAssetPaths": [],
  "budget": {"maxCorrectionRounds": 2, "maxModelCalls": 4, "tokenLimits": {}}
}
```

Use actual local dimensions for child widgets. Full-screen render contexts require `2560 × 1440` plus the required wider/taller contexts; every state/view must be declared. Under the legacy equal-pixel contract the source image has that same size. `mapped-source-reference/1` below may instead retain the original source image at its native dimensions. Region `bounds` always use source-image pixels. The renderer must later prove the exact capture size, DPI, locale, data, state, font set and background actually used.

For existing import batches, link their verified identities first:

```powershell
python scripts/art_resources.py --manifest "<import-manifest.json>" --readback "<import-readback.json>" --project-root "<project-root>" --output "<request-dir>/art/import-bindings.json"
```

This bridge consumes the existing import contract; it does not create a second atlas, icon-ID allocator or import pipeline. For already imported project sprites with no compatible batch manifest, the existing `art_resources` module exposes `collect_existing_resources`, `load_existing_resources`, and `merge_existing_resources`. The explicit `ExistingProjectResourceCatalog/1` provider binds the exact official read-only call ledger, actual SpriteSheet membership, untrimmed/unrotated source frame, source identity and saved-file hashes, then retains all original batch records on merge. It does not invent an import history or reimport assets. The same `validate_catalog` entry point revalidates either provider; this is not a preliminary screening command. Keep existing IDs, source hashes and resource settings. Atlas entries point to their actual PaperSprite, not the whole atlas texture. Add the resulting path as the job's optional `resourceCatalog` before initialization; the request binds it and local packets include the validated `importedAssets` candidates. Use the catalog's saved `brushResourceObject` for the selected source, not a guessed filename. A new import still follows the project's established resource workflow. The direct art importer is restricted to standalone PNGs and requires independent actual source-identity verification.

```powershell
python scripts/art_pipeline.py init "<job.json>" --output "<request-dir>/art/request.v1.json"
```

New initialization declares `capabilities: ["presentation-review/1"]`. This opts into the closed presentation review below without adding a new screening command or changing operation types. An old v1 request without this capability retains its original interpretation; it cannot claim the new checks passed. Adopt the capability through a new bound request/decision revision and rerun affected planning and verification, preserving old artifacts. Unknown capabilities and a review attached to a request that did not declare the capability are rejected.

## Explicit capability adoption

The request's closed `capabilities` enum is the authority; adding a field or passing schema validation alone does not grant permission or provide runtime evidence. `init` enables `presentation-review/1` by default. Its supported job options additionally enable `development-baseline/1` through `developmentBaseline`, and `mapped-source-reference/1` through `referenceMode`.

`procedural-ui-material/1`, `procedural-ui-material/2` and `delegated-art-choice/1` require an explicit new request revision alongside `presentation-review/1`; they are not accepted job options or automatic defaults. A request selects exactly one material capability version, and its material evidence must use that same version. Bind their actual evidence, validate the new request, rebind decisions to its SHA and run the existing plan/apply/verify gates. Preserve old requests, source packets and results. These changes do not upgrade historical contracts or alter an accepted Requirement by themselves.

### Original artwork and actual capture coordinates

For different native-source and capture dimensions, set the job's `referenceMode` to `mapped-source-reference/1`. Every reference then requires `sourceSize` matching its decoded source bytes, while `context.size` continues to specify the actual viewport. Every region supplies both `bounds` in source pixels and `captureBounds` in capture pixels, each as integer x/y/width/height inside its own image. Presentation reference crops stay in source coordinates.

The existing [art_reference.py](../scripts/art_reference.py) helper produces labelled native-pixel full views and region pairs. It does not resize the original artwork, synthesize a new reference or invent a cross-resolution error score: comparison records have `metric: null`, `resampling: none`, and `acceptance: requires-visual-review`. The final validator recomputes those exact comparison pixels and bindings. A `captureBounds` declaration is a comparison region, not measured Widget geometry or proof of canonical capture. Accepted layout geometry and all actual render-context checks remain independent.

## Explicit development baseline

Only `formal-art` may opt into `development-baseline/1`. Existing requests without it still require a fully verified baseline. Do not change historical requests or mark unfinished visual checks passed. This capability changes neither Requirement nor Bundle/Readback schemas.

Add this closed object to the art job (illustrative paths, not execution evidence):

```json
"developmentBaseline": {
  "version": 1,
  "structureCompletedAt": "<actual timezone-aware structural completion time>",
  "pendingCheckIds": ["<every original pending preview check ID>"],
  "buildEvidence": [
    {"checkId": "<compile check ID>", "stepId": "compile", "plan": "<actual executed plan.json>", "checkpoint": "<actual completed checkpoint.json>"},
    {"checkId": "<save check ID>", "stepId": "save", "plan": "<actual executed plan.json>", "checkpoint": "<actual completed checkpoint.json>"}
  ]
}
```

Repeat build evidence for every compile/save check and every asset. `init` replaces plan/checkpoint paths with immutable path/SHA-256 bindings and adds the capability alongside `presentation-review/1`; a hand-authored request must declare the capability and those bindings explicitly. No additional screening command is needed.

Freeze the development Bundle 0.1–0.3 with all original checks, `execution.status: running`, a real `startedAt`, no final `completedAt`, `verification.status: pending`, and every asset `built`. Each asset must have passed compile/save/widget-tree/key-properties checks. Only `preview` may remain pending; pending IDs must match exactly, and failed checks are rejected. Hidden-state and render obligations keep their original preview IDs and accepted requirement/claim references.

Compile/save check `artifactPath` resolves relative to the frozen Bundle and must point to its bound programmatic executor checkpoint v2. The validator checks the exact asset, plan hash, complete ordered event prefix, official `CompileWidgetBlueprint`/`AssetTools.save_assets` arguments and actual boolean success. Each asset's save follows its last compile, all within `startedAt` through `structureCompletedAt`. Unsupported receipt formats require an explicit future capability; do not normalize a failed or unavailable result into success.

The normalized actual readback binds this frozen Bundle and must follow structural completion. Widget-tree/key-properties checks name that exact readback. The separate art snapshot also follows completion and agrees on assets, tree, parent class, Designer mode and observed state/EntryClass. All accepted production, linked layout, source hash, actual identity, runtime variable, state, collection and reuse checks remain active. A fixture, missing mode or plan-derived state is not actual evidence.

Art-side verification/stage creation is followed by final Bundle 0.4 validation. The final Bundle must preserve every baseline check's ID, type, asset, requirement refs and claim refs, and every original check must pass. Removing or relabeling an unresolved baseline obligation cannot complete art. Final normalized readback, result acceptance and document gates still require the fully completed and verified final Bundle.

## 2. Prepare local decisions and reserve model calls

```powershell
python scripts/art_pipeline.py packets "<request.json>" --output-dir "<request-dir>/art/packets"
python scripts/art_pipeline.py reserve-call "<request.json>" --packet "<packet.json>" --journal "<request-dir>/art/model-calls.json" --call-key "region-icon-pass-1" --ledger "<token-ledger.json>"
```

`packets` indexes resources, retains transparent bounds, creates local comparison sheets and at most three candidates per region, and returns `packet-receipt.json`. It executes zero model calls. At most two matching scoped sample cards are included. With the same request, source bytes, baseline and implementation, verified packet/cache outputs are reused. Changed inputs invalidate their dependent packet identities; preserve unchanged reference/sample data and avoid sending full readbacks to the model.

Dispatch only when `reserve-call` returns `dispatchAllowed: true`. Reusing the same logical call key returns `already-reserved`; do not dispatch it twice. Record actual provider usage using plugin-level `scripts/token_telemetry.py append-model-call` or its importable API, with the returned `measurementBoundaryId`, `runIdDigest`, `callIdDigest`, stage `art`, role `art-judgment`, actual provider/model, and provider receipt hash. Read its `--help` for receipt counters. `tokenLimits` supports nonnegative `inputTokens`, `cachedInputTokens`, `outputTokens`, `reasoningTokens`, and `visionTokens`. Any configured zero limit blocks dispatch; reaching a measured limit blocks the next call. A numeric token budget requires complete receipts before further calls; local estimates cannot stand in for receipts. The reservation checks measured consumption before the next call and cannot predict the cost of an unfinished call. A single call may exceed the remaining allowance; use a provider output cap separately when available.

The model returns the closed `decisions` definition in [art-contract.schema.json](../assets/art-contract.schema.json). The coordinator merges local decisions without duplicate operation IDs. Each decision has an allowed `operation`, its evidence, and `resolution: unambiguous|confirmed|unresolved`; `confirmed` needs the actual confirmation text. Each operation names the exact asset, observed widget and accepted `sourceElementId`. Copy `before` from actual readback. Never generate arbitrary property paths, code or MCP calls. Set unresolved items explicitly and collect them into one review.

### Presentation review in existing decisions

Use [visual presentation rules](../../build-nextgame-umg/references/visual-presentation-rules.md) for the semantic and visual judgments. With `presentation-review/1`, the same decisions document must contain `presentationReview: {version: 1, images: [...], texts: [...], families: [...]}`. This is independent from the mutation array: an unchanged text still needs a judgment, not a fabricated no-op write. Exact `assetPath + widgetName` coverage is checked against the final simulated scope, including added nodes and hidden states.

| Record | Required evidence and current machine boundary |
| --- | --- |
| Image | Exact widget, reference region/bounds, reason/resolution, `source`, `aspectMode` and explicit `familyId` or null. A resource source binds `catalogResourceId`, local `image` hash, complete `frameSize` and measured `alphaBounds` to the existing request resource catalog and native Brush. Resource-free procedural brushes need an explicit reason and no resource. A saved Material uses the separate explicit capability below; neither branch can disguise a texture or invent an import history. |
| Aspect / slices | `preserve`, `stretch`, `nine-slice` or `no-draw` is explicit. Nine-slice adds `cutPixels` in left/top/right/bottom source-frame pixels, `stretchAxes`, positive `basisScale` and `protectedRegions`. Each region has `id`, pixel `bounds` (x/y/width/height), `purpose` and `preserveAxes`; only the intersection of protected and stretched axes must remain outside the stretch band. Alpha bounds alone do not define cuts. |
| Text | Every scoped TextBlock records its reference crop, reason, `effect`, separate `effectTypeConfidence` and `parameterConfidence`, actual numeric outline/shadow decisions, resolution and scoped confirmations. `unknown` remains unresolved. A `none` judgment needs evidence and must agree with native disabled effects. Explicit delegated text choices use their own resolution/authority branch below, without changing the recorded source confidence. |
| Family | Explicit members and chosen `comparisons`: Brush/Slot sizes, selected width/height, source scale (pair or selected axis), or aspect mode. Declare `exceptions` even when empty. An exception names a non-baseline member, one declared comparison, its exact `expectedValue` and reason. Unsupported, duplicate, unused or blanket exceptions do not waive comparison. |

The full closed field types live in the schema, not a second permissive sidecar. The planner validates resource bytes and import identity, reference bounds/ownership, coverage, native effect values, slice invariants and the selected family comparisons. Known configuration distortions are errors. Narrow static allocation arithmetic is labelled as such; it is not measured geometry. Semantic heading ownership, joined visible seams and valid cross-item state relationships still require the local human/model review because names and rectangles cannot establish them.

For low-contrast text, first inspect the original local pixels and actual font/typeface/fallback, DPI and native effect properties. Separate certainty that an effect exists from certainty about its numeric parameters. Only unresolved interpretations go into a consolidated annotation request. Confirmations must quote the specific direct user decision with `effect-type` or `appearance-parameters` scope. Agreement to “automatic recognition plus annotations” is a method preference, never confirmation of every outline size/color. Preserve unresolved judgments instead of forcing them to `none` or blanket outline values.

### Saved procedural UI Material sources

With explicit `procedural-ui-material/1` or `/2`, an image may declare the closed source `{kind: "material", materialPath: "<package path>", evaluationSize: [width, height], evidence: {path, sha256}}`. The package path has no object suffix; the observed native Brush must resolve to that exact Material. Only `aspectMode: preserve` is supported. Do not add `image`, `frameSize`, `alphaBounds`, `catalogResourceId` or pixel-cut `nineSlice` fields. The imported-resource catalog and its existing validators remain unchanged.

[art_materials.py](../scripts/art_materials.py) validates `proceduralMaterialReadback` from the [art schema](../assets/art-contract.schema.json). The version 1 evidence binds the explicit project file, exact nonempty Content `.uasset` bytes and the completed original `task-native-material-execution/1` receipt. Compile and exact-asset save rows must match that receipt; later official calls read the loaded material class, UI domain, Translucent blend, two-sided flag, no customized UVs, all three expressions, their classes/properties/input/output wiring, and finally non-dirty state. Sidecar calls have real sequential timezone-aware times and a later capture time. Recheck all bound files on each use; do not rewrite failed or unavailable calls as success.

Version 1 supports one TextureCoordinate → Custom opacity path and one Constant3Vector → Emissive path. It reads the Custom code and rejects unbound includes, defines, extra outputs, extra expressions and unsupported material-instance/external-dependency graphs. Code is bound for actual review; this helper is not a proof of arbitrary HLSL semantics. `validate_material_source` is importable by the existing presentation validator; there is no additional screening CLI or new importer.

Version 2 uses the separately closed `proceduralMaterialReadbackV2` definition with `version: 2`. It has exactly three owned native expressions: one unmodified TextureCoordinate0, one Custom with `CMOT_Float3` feeding `MP_EmissiveColor`, and one Custom with `CMOT_Float1` feeding `MP_Opacity`. Both Customs have exactly one input named `UV` wired directly to the same TextureCoordinate's default output; the native `inputs` fields and the official graph edges must agree, with no input masks. Each expression has one default output. Constant colors, ComponentMask nodes, extra expressions, external input edges, extra outputs/defines/include paths and inline `#` preprocessor directives are outside /2. Each complete Custom code string is read from the actual node and participates in the bound evidence and graph SHA; changing either code requires fresh actual compile/save/readback evidence. The request capability selects the evidence schema: /1 cannot consume /2, /2 cannot consume /1, and requests cannot declare both.

Version 2 retains the same 21 official calls and compile/save receipt contract as /1: exact original execution rows first, independent post-save material and per-node class/property/wiring reads next, and `is_dirty: false` last. No material creation API or new signatures are assumed; discover the host's actual MaterialTools/ObjectTools/AssetTools schemas before creating or collecting anything. This capability proves the supported saved source graph only. It does not prove either HLSL program's semantics, correspondence between RGB and alpha, absence of implicit shader-global behavior, shader visual correctness, actual geometry, rendering or final acceptance; inspect the complete bound code and verify the actual render separately.

The full evaluation domain must have finite positive dimensions. Brush must be untiled Image, NoMirror, zero margin and observed invalid atlas UV override. Brush and known allocation/transform scales preserve its aspect. `evaluationSize` is not source-image pixels, alpha bounds or measured Widget size. Material compile/save can establish a saved source but cannot establish rendered art, geometry, appearance confirmation or runtime progress semantics. Create/modify a material only under separately established exact asset authorization, then use its actual evidence; an art `set-property` operation only binds an already verified Brush resource.

### Explicit coordinator text choices

Follow [delegated-art-choice.md](delegated-art-choice.md) for the registered `delegated-art-choice/1` contract. The request binds `delegatedArtChoice: {path, sha256}` alongside the capability. The closed `request-scoped-art-choice/1` sidecar names `reviewer: primary-coordinator`, `scope: appearance-choices-only`, exact current scoped assets, the original inline direct-user RequestPacket source and message hash, the preserved authorization file and individually selected text records. The accepted Requirement must preserve that request, input digest and original message. Use the schema's registered exact grant wording; ordinary continuation and method preference do not qualify.

Only a presentation TextBlock may use `resolution: delegated`. Its identity, reference, reason, effect, separate source confidences, outline and shadow must exactly equal its bound coordinator choice; `confirmations` stays empty. Keep medium/low identification confidence when that is the evidence. A chosen reconstruction value does not prove the original artwork used that value. Unknown effect/confidence or an unmade choice cannot be hidden by delegation. The main mutation-decision array retains its existing resolution contract.

The `sourceConfidencePreserved` and `actualVisualAcceptanceRequired` true fields describe the boundary; they are not visual pass receipts. Native-property agreement, exact local reference ownership, scoped coverage, real canonical captures and region inspection, actual geometry, hidden/wider/taller states and final validation remain required. Without the capability, the existing annotation/uncertainty rules above are unchanged. This sidecar neither accepts a final result nor consumes the separate one-use documentation grant.

## 3. Plan and apply

```powershell
python scripts/art_pipeline.py validate "<decisions.json>" --type decisions
python scripts/art_pipeline.py plan "<request.json>" --decisions "<decisions.json>" --output "<request-dir>/art/plan.v1.json"
python scripts/art_pipeline.py apply "<plan.json>" --checkpoint "<request-dir>/art/execution.v1.json"
```

The closed plan binds the request and decisions, baseline and expected state hashes, operations, round and issues. `ready` is necessary but still subject to current Editor preflight. The planner lowers the current accepted layouts and rejects changes conflicting with locked values or unmapped source elements. Structural changes require the accepted target source to already describe the new structure. Use the allowlisted `set-property`, `set-slot`, supported static `add-widget`, and narrowly supported resource operations; a schema-recognized operation is not proof that the current Editor supports it.

`apply` revalidates source bindings and the exact deterministic plan, compares current actual state, preflights capabilities, then records durable intent and checks each observed result. It compiles/saves changed assets and writes final actual readback. Keep the same checkpoint when recovering an interrupted run. A changed source, conflicting actual state or incomplete operation provenance needs a new baseline/review or explicit recovery; deleting the checkpoint is not a repair. An unchanged completed rerun reports `changed: false`.

For structural changes, repeat with the same completed checkpoint and verify stable widget identities, parents and counts, plus no additional save. Compare unchanged asset bytes where available. The baseline must preserve current user edits; an old accepted plan does not authorize overwriting a changed actual state.

## 4. Capture, inspect and verify

```powershell
python scripts/art_pipeline.py capture "<plan.json>" --execution "<execution.json>" --reference "card-default" --output "<request-dir>/art/capture-card-default.json"
python scripts/art_pipeline.py verify "<plan.json>" --execution "<execution.json>" --captures "<captures.json>" --output "<request-dir>/art/verification.pending.json"
python scripts/art_pipeline.py verify "<plan.json>" --execution "<execution.json>" --captures "<captures.json>" --visual-review "<reviewed-visual-review.json>" --output "<request-dir>/art/verification.passed.json"
```

`capture` returns `{referenceId, capture: {path, sha256}}`; collect one such returned record per required reference into the `captures.json` array. It verifies the actual state before and after rendering. The default adapter reports canonical capture unavailable rather than creating a false receipt; a reviewed host renderer integration must independently supply the full required context and actual evidence. Do not substitute editor thumbnails or manually set `canonical: true`.

The first `verify` writes comparison images and a `needs-review` template. Inspect every declared region and all required viewport/state references, record the actual reviewer and inspection time, resolve issues, and save a separate reviewed file. Whole-image similarity alone cannot pass the visual review. The second invocation checks current image bytes, dimensions, fixed context, expected actual state, comparison coverage and chronology. Numeric matches and a review template alone are not acceptance.

Presentation checks are recomputed from the actual saved snapshot during `verify`, and recomputed again by final stage validation. Exact text properties can pass independently from their appearance. The current adapter does not supply measured Widget geometry: preserve/nine-slice image geometry and Slot-family measurements stay pending even if all static arithmetic agrees. A plan may apply supported corrections while this render evidence is pending, but final art cannot pass by relabelling the configuration proof or copying a receipt. Canonical-capture checks remain mandatory and unchanged.

Inspect shared header/body visible boundaries after transparent insets and DPI scaling, short/long content combinations, local selection and unavailable branches, and the entire required wider/taller viewport. A clipped editor screenshot is not evidence about an unseen edge. Retain residual seams and uncertain text parameters explicitly; property agreement does not resolve them.

For a correction, use the failed/pending verification as its baseline:

```powershell
python scripts/art_pipeline.py plan "<request.json>" --decisions "<correction-decisions.json>" --previous-verification "<previous-verification.json>" --output "<request-dir>/art/plan.correction1.json"
```

The previous chain determines the round; do not invent a counter with `--round`. At most two corrections are allowed. Stop on no improvement, unresolved ambiguity or budget exhaustion. A passed result requires a new requested revision for subsequent changes.

## 5. Join the final Bundle and deliver

```powershell
python scripts/art_pipeline.py stage "<passed-verification.json>" --bundle-path "<final-bundle.json>" --output "<request-dir>/art/stage.json"
```

The stage fragment contains `goal`, `request`, `plan`, and `verification`, with bindings relative to the **final Bundle**, not to the fragment. Merge its value into final Bundle 0.4 `artStage`, retaining every existing asset mapping, layout and verification check. Preserve frozen baseline files to avoid a request → final Bundle → request hash cycle.

Finalize and validate the Bundle, acquire fresh normalized Unreal Readback 0.4, and run the existing readback validator. The art snapshot carries visual evidence; normalized readback carries actual identity for downstream program documentation. The final gate compares both, not merely old sidecar hashes. Use the existing [shared coordinator handoff](../../build-nextgame-umg/references/on-demand-art-stage.md) to present the completed result. Acceptance 0.1 still requires the later direct user confirmation. The separate explicit [delegated result acceptance 0.2](../../document-nextgame-umg/references/delegated-result-acceptance.md) contract can instead use a real original one-request grant and the primary coordinator's actual post-result review; it does not claim a later user message or that the user inspected the result. `stage` creates neither form of acceptance.

For 0.2, preserve the original user message/source packet/authorization hashes and exact asset scope. Only after the strict final Requirement, Bundle, formal art and normalized Readback gates pass may the coordinator review the current presentation, every asset and every original check with real render/geometry/state evidence, record the actual review time, and exclusively bind the single-use consumption to that frozen result. Keep `userHasReviewedResult: false` and the actual agent reviewer. Recheck current conversation authority for narrowing or revocation before review and document entry. An art-choice authority, earlier Requirement approval or generic full-workflow request is insufficient. Changes to saved assets, art/capture/layout, final files or evidence invalidate old acceptance; do not relabel historical 0.1 records, recycle consumption or let the document agent manufacture authorization.

## Scoped samples

```powershell
python scripts/art_pipeline.py sample --reference "<approved-reference.png>" --snapshot "<actual-art-snapshot.json>" --inventory "<resource-index.json>" --mappings "<sample-mappings.json>" --scope "Navigation tabs using this resource family" --output-dir "<request-dir>/samples/navigation-tabs"
```

Mappings are an array of exact `assetPath`, `widgetName` and inventory `resourceId`, with optional reference pixel `bounds`. Include only the confirmed correspondences and scope. Export copies the reference, snapshot and selected resources with hashes; its status is `reference-only`, `globalStandard: false`, and approval is not established by export. Include the resulting sample paths in a later job's optional `samples` list. The model receives matching scoped cards and must still check current design compatibility.

## Measured model comparison

Run `python scripts/art_benchmark.py <benchmark-manifest.json> --output-dir <request-dir>/benchmark` to report recorded runs; it does not call or select a model. The strict `MANIFEST_SCHEMA` and `RESULT_SCHEMA` are exposed by that script. Record `first-production`, `local-change`, and `rerun` separately, with supplied model labels, measured start/end times and counted human correction events. Bind each result to current verification and each usage ledger to the exact call/run boundary. Missing usage stays null; tokenizer proxies cannot become measured tokens.

Declare sample membership as `reference-library` or `held-out`, and kind as `child-widget` or `full-screen`. The report checks held-out coverage and reference leakage per model, preserves the actual source quality verdict, and outputs immutable JSON/Markdown. Synthetic demonstrations remain explicitly synthetic and cannot establish real model quality or cost. No K3 or other model benchmark has been performed by merely installing this tool.
