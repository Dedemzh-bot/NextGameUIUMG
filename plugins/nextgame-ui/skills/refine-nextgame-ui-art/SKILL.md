---
name: refine-nextgame-ui-art
description: Refine existing NextGame UMG from high-fidelity artwork and cut resources, prepare local art decisions, verify visual results, or collect scoped reference samples. Use as the optional art stage of an existing NextGame UI task or independently for an existing accepted UI. Raw first-time UI requirements still use analyze-nextgame-ui-requirements.
---

# Refine NextGame UI Art

Before local art decisions or application, apply [production fidelity checks](../build-nextgame-umg/references/production-fidelity-checks.md): verify resource identity and complete-frame responsibilities, trace each accepted native property and retain unsupported or unrendered items as outstanding.

Use one optional stage under the original primary coordinator. `developer-only` keeps the existing build workflow; `formal-art` follows a development baseline; `upgrade-art` and `local-art` start from current existing UMG. Keep the same request identity and accepted design. Missing art resources or unavailable verification remain unfinished items when formal art was requested.

Read [workflow.md](references/workflow.md) for commands and artifact ordering. Before any Editor operation, read [runtime-support.md](references/runtime-support.md) and check the current host's capabilities. Shared chain/version rules remain in [on-demand-art-stage.md](../build-nextgame-umg/references/on-demand-art-stage.md).

## Authority and decisions

Read [visual presentation rules](../build-nextgame-umg/references/visual-presentation-rules.md) before preparing local packets. New initialization enables `presentation-review/1` in the existing pipeline. Review every scoped image and TextBlock, including hidden/unchanged nodes; use local recognition and preserve effect-type and parameter uncertainty separately. For remaining ambiguous text, retain the specific direct-user annotation route or explicitly validate `delegated-art-choice/1` for exact coordinator-selected appearance values; delegation does not confirm their source identification or final appearance. Legacy requests require an explicit new revision to adopt a capability.

- Require the current accepted Requirement, verified baseline Bundle, normalized actual readback, and a separate actual art snapshot. For an unfinished formal-art development build, explicitly adopt `development-baseline/1` for pending previews only, or `development-baseline/2` for the narrow accepted Brush resource gaps and explicit open art judgments in [workflow](references/workflow.md#development-baseline-resource-deferrals). Preserve every original check and require a separate actual primary review for version 2; use the strict compiled/saved actual-state contract; this is not final verification. Preserve immutable baseline files; final Bundle and art evidence must not form circular hash references.
- Use `$receive-nextgame-design` for structured design source revisions. Reopen only affected design gaps, accept the revised source, then plan art; do not silently change locked layout/state/collection decisions or rerun nine raw-analysis roles for resource replacement.
- Keep variable names, program references, collection EntryClass and animation bindings protected. Only observed permitted properties and supported static structural changes can enter an executable plan. Unknown Designer mode and incomplete reference evidence are unresolved facts, not values to guess.
- Record existing exact asset authorization truthfully. An already authorized update does not need a second permission question; `productionAuthorized` must not be inferred from a default or from the existence of a baseline.
- Keep native source-image coordinates separate from render coordinates. `mapped-source-reference/1` declares `sourceSize` and per-region `captureBounds`; it compares original and actual pixels without resampling and does not create canonical or geometry evidence.
- A saved procedural UI Material uses an explicit `procedural-ui-material/1` or `procedural-ui-material/2` contract (no automatic migration) and `source.kind: material`, with graph/property/class, compile/save and current saved-file evidence. Its `evaluationSize` is an evaluation domain, not a texture frame. Resource-free procedural brushes and imported textures keep their original contracts.
- Prefer current project import manifests and actual import readback for resource identity. Atlas/icon IDs and shared resources remain owned by the existing resource workflow. Do not recreate them as standalone textures merely to simplify matching.

## Model and cost boundary

Default to one art judgment Agent. Tools index images, shortlist candidates, measure, lower properties, execute and compare. Give the model a local decision packet, its image and at most the included candidates/scoped samples; ask for structured decisions and uncertainty, not UE Python or tool names. Reuse unchanged packets and decisions. Delegate separate regions only when useful and permitted; keep the selected model and reasoning effort, with no automatic model upgrade.

Reserve each logical model call before dispatch, then record its actual provider usage with the existing token telemetry. A reservation executes no model call. Missing actual usage is unmeasured, not zero; a configured actual-token limit cannot be satisfied with character counts or estimates. Default corrections are at most two, with prior verification required. Stop automatic repair on no improvement, unresolved ambiguity or exhausted budget and report the concentrated issues.

## Completion

Plan, apply, collect final actual state, capture the declared viewport/DPI/state/data/font context, and verify local comparisons. Do not pass a generic thumbnail as canonical capture or label a synthesized snapshot as an actual read. The default art adapter currently reports canonical capture unavailable and supplies no measured Widget geometry. A separate host integration must prove those capabilities with actual evidence; runtime diagnostics, a material compile or synthetic tests do not prove a production art result.

After passed art verification, create the stage bindings, finalize Bundle 0.4, acquire fresh normalized Readback 0.4 and run both final validators. Present the final assets, screenshots, tree, key properties and deviations. The default acceptance 0.1 route requires a later direct user message accepting that concrete result. Only the separate explicit [one-request result delegation 0.2](../document-nextgame-umg/references/delegated-result-acceptance.md) route permits the primary coordinator to perform the actual post-result review under the original user grant; record the coordinator as reviewer and `userHasReviewedResult: false`, then bind the one-use consumption to the frozen result before `$document-nextgame-umg`. An art-choice grant or a generic “complete the workflow” request cannot replace result acceptance.

Any art, preview, Bundle or readback change invalidates earlier result acceptance. Static art parameters do not become programmer-facing API requirements.

Write task artifacts under the current request directory outside the plugin and resource input folder. Samples are scoped `reference-only` project data; they do not train model weights or establish global standards. Report completed capabilities and remaining runtime limitations separately.
