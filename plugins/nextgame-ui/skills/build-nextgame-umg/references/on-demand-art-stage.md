# On-demand NextGame UI art stage

## Routing and task ownership

`refine-nextgame-ui-art` is independently callable and also a continuation of the existing build chain. The same primary coordinator owns request identity, source decisions, restoration, final integration and result acceptance. A separate conversation and repeated full analysis are not required.

| Goal | Route |
|---|---|
| `developer-only` | Existing development build and delivery, with no art-stage bindings |
| `formal-art` | Accepted design → development build → art stage → final verification/readback |
| `upgrade-art` | Current accepted design and existing actual UMG baseline → art stage |
| `local-art` | Same route, limited to explicitly affected resources, widgets and regions |

Art inputs are existing UMG, reference artwork, cut resources, and current accepted design/build records when available. Missing resources, unknown fonts or unreferenced states remain explicit gaps. A formal-art request cannot complete at its development baseline. Prototype and legacy standalone input cannot acquire production documentation by attaching an art sidecar; first establish the ordinary accepted production design and build authority.

## Source changes and small decisions

Keep layout, responsive intent, states, runtime collections, variable names, program references and animation bindings under their original accepted authority. Art decisions add resource correspondence and presentation parameters; they do not redefine design decisions. New static nodes or layout/structure changes must update the owning design revision and derived mappings/layouts before execution. For `design-contract/1`, revise that source and compile/accept the next Requirement. For raw-analysis Requirements, revise only the affected decisions truthfully under the existing source/provenance rules; do not fabricate another nine-role run or reuse old approvals.

Read actual Unreal state before planning/resuming a patch. Restore current task bindings, never select a historical Bundle only because it has the latest filename or modification time. Compile/save and recapture all affected evidence after each applied change.

One art judgment Agent is the default. Tools index resources, shortlist candidates, measure, compute patches, execute in batches and compare renders. Send only a local reference crop, candidate IDs/images, and relevant widget evidence to the model. Reuse unchanged decisions and scoped examples by content hash. Independent regions may be delegated only when useful; every Agent inherits the selected model and effort. Never silently switch models. Default automatic repair stops after two rounds, on no improvement, unresolved ambiguity, or budget exhaustion. Existing token telemetry records actual reported usage separately from estimates.

## Bundle and actual-state version contract

Use `UIBuildBundle 0.4` for art completion. It has every required 0.3 top-level field and the same closed asset and reuse relation shapes, plus this required field:

```json
{
  "artStage": {
    "goal": "formal-art",
    "request": {"path": "art/ui-art-request.json", "sha256": "<sha256>"},
    "plan": {"path": "art/ui-art-plan.json", "sha256": "<sha256>"},
    "verification": {"path": "art/ui-art-verification.json", "sha256": "<sha256>"}
  }
}
```

The goal is `formal-art`, `upgrade-art`, or `local-art`. All three paths are relative to the Bundle. Unlike 0.3, 0.4 permits an empty `reuseRelations` for ordinary art-only layouts; each layout asset still declares `representationKind: layout-spec`. Existing reuse, placement, coverage, registry, source hash, schema and semantic checks continue unchanged. Existing 0.1–0.3 schemas remain closed and reject the new field.

A planned/running Bundle may name pending art outputs but must not be reported as finished. At either `execution.status: completed` or `verification.status: passed`, the Bundle validator calls the art completion validator and requires current valid request/plan/passed verification. `--skip-linked-files` cannot bypass art completion. Missing, pending, stale or unavailable art evidence fails closed. Planned placeholder bindings must be replaced with actual file hashes before completion.

Use normalized `UnrealWidgetReadback 0.4` with Bundle 0.4. It retains the 0.3 identity/reuse shape and permits empty `reuseRelations`; no visual property fields are added. The separate art acquisition snapshot records Brush, font, Slot and other visual evidence. Both are actual reads, never inferred from a plan.

The cross-skill integration function is:

```python
validate_art_stage(stage, *, bundle_path: Path, requirement: dict,
                   requirement_path: Path, readback: dict | None = None,
                   final_bundle: dict | None = None) -> list[dict]
```

It resides in `refine-nextgame-ui-art/scripts/art_common.py`; each issue has string `code`, `path`, and `message`. `validate_build_bundle.py` loads it lazily through `validate_bundle_art_stage`. It must not recursively invoke the full Bundle validator. Completion validation checks sidecars and their current evidence; the document readback gate calls it again with the **current normalized actual readback** to compare identity and freshness against the verified art snapshot. Missing helper capability is an error for art completion and does not affect developer-only validation.

## Development baseline capability

An explicitly declared art request capability `development-baseline/1` permits only formal-art to start from an unfinished development Bundle 0.1–0.3. Its closed `developmentBaseline` version 1 contract binds structural completion time, the exact original pending preview IDs, and each actual compile/save plan and checkpoint. See the [art workflow](../../refine-nextgame-ui-art/references/workflow.md#explicit-development-baseline) for the exact request/job shape. No Requirement, Bundle or normalized Readback version is relabeled.

The baseline remains running/pending with built assets; completed compile/save and normalized actual-state checks are mandatory for every asset. Only visual preview obligations may stay pending. The common source and actual-state validation cores are shared with the final document validator; no error filtering or arbitrary skip flag selects this path. The normal final readback entry point always adds its original final lifecycle and art completion gates.

At final Bundle 0.4 completion, `validate_bundle_art_stage` supplies `final_bundle` to the art helper. Every original baseline check, including all pending hidden/render obligations, must survive with identical ID/type/asset/requirement/claim identity and pass. Art-side verification alone cannot prove Bundle completion. Final readback and user acceptance remain separate mandatory gates.

## Result acceptance and documentation

Render the requested states with fixed viewport, DPI, fonts and test data. Full screens use `2560 × 1440` and additional wider/taller viewport checks. Check local appearance, resource identity, input regions, long text, adaptive layout and program relationships; a whole-image similarity score alone is insufficient.

Finish applying art, compile/save, pass art verification, finalize the Bundle, obtain fresh normalized actual readback and validate the final sources. Present paths, screenshots, tree, key properties and deviations. The ordinary acceptance 0.1 route requires a later direct user message accepting that result. The explicitly opted-in [acceptance 0.2](../../document-nextgame-umg/references/delegated-result-acceptance.md) route requires a registered request-scoped original grant and an actual post-result primary-coordinator review, with all evidence gates unchanged; it never claims personal user review. Updating art, preview, Bundle or either readback invalidates previous acceptance. Re-read all current sources at document-content generation and final DOCX verification. Existing document tables derive solely from normalized actual identity and accepted program intent; static art settings are not added to program-facing documentation.
