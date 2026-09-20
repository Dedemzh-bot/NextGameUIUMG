---
name: document-nextgame-umg
description: Validate the accepted NextGame UIRequirementSpec, completed and verified UIBuildBundle, post-save Unreal Widget readback, and independent versioned post-build acceptance; derive a program-facing UIProgramHandoff; then coordinate DOCX creation and page-by-page verification. Use after NextGame UMG construction has been presented and accepted through direct user confirmation or the explicit one-request delegated result-review contract when Codex must produce or verify the programmer handoff document without exposing static Designer configuration or inventing runtime API details.
---

# Document NextGame UMG

Treat documentation as a gated stage after requirement acceptance, verified UMG construction, concrete build-result presentation, and independent post-result acceptance. The default acceptance 0.1 route requires a later direct user confirmation. Only the separately validated [one-request delegated result acceptance 0.2](references/delegated-result-acceptance.md) route permits the primary coordinator's actual post-result review under the original explicit user grant. Neither route lets the documentation Agent create or repair authorization. Read [program-handoff.md](references/program-handoff.md) before preparing artifacts, and read [program-document-template.md](references/program-document-template.md) before creating the DOCX.

The packaged `artifact-template-nextgame-umg` is the canonical presentation template aligned with `program-document-content.json` 0.4. It does not supply business facts or authorize this stage: validated handoff/content contracts remain content authority, while the template contract and neutral DOCX control structure and visual presentation.

## Final-art source guard

When art was requested, require the final Bundle 0.4 and normalized Unreal Readback 0.4. Its required `artStage` binds the art request, plan, and passed verification using relative paths and SHA-256. The readback validator revalidates those current files and compares current actual identity with the separate art snapshot; stale hashes or an old development readback cannot authorize documentation. A pending art stage cannot be skipped because an earlier development build passed. See [on-demand-art-stage.md](../build-nextgame-umg/references/on-demand-art-stage.md).

Re-saving, applying an art patch, replacing a preview, changing the Bundle, or recapturing either readback invalidates prior post-build acceptance. Present the new final result and obtain current acceptance through the applicable versioned contract, then run the existing four-input gate. A consumed 0.2 grant cannot transfer to a changed result; obtain new specific direct-user authority or ordinary post-result confirmation. Art parameters remain static evidence and do not become programmer-facing content. Legacy Bundles and developer-only tasks retain their existing strict contracts.

## Workflow

1. Require the current accepted `UIRequirementSpec`, the completed and passed `UIBuildBundle`, an actual post-save Unreal readback, and `ui-build-acceptance.json`. The first three are authoritative data sources; acceptance is independent authorization evidence. Version 0.1 requires a later direct user message after presentation. Explicit version 0.2 instead binds the original one-request user grant, the primary coordinator's actual review of the final result, and its single-use consumption. Never generate, infer, repair, consume, or pre-authorize acceptance in this skill, and never infer readback fields from the Bundle or UILayoutSpec.
2. Validate the readback:

   ```powershell
   python scripts/validate_unreal_widget_readback.py <readback.json> --requirement <requirement.json> --bundle <bundle.json>
   ```

   Apply the project naming contract first: every Bundle asset whose Blueprint basename is `umg_*`, including `umg_ai_*`, must report actual post-save generated-class CDO `DesignSizeMode: FillScreen`; `assetKind`, Bundle representation, and legacy policy cannot authorize `Desired`. Archived Requirements with the policy absent or false may still omit this newly recorded field, but a present `umg_*` value must be `FillScreen`. When `analysisPolicy.designSizeModeRequired` is enabled, require every Bundle asset, including `reuse-only`, to report the field and match the accepted Requirement asset plan's `designSizeModeDecision.mode`; this binding remains mandatory for `umg_*`, so an inconsistent accepted decision also fails. Only `uw_*` mode selection is analysis-driven, and `assetKind` never substitutes for that decision. If a legacy non-`umg_*` Requirement provides the optional field, accept only `FillScreen` or `Desired` and compare it with a valid bound Requirement decision when one exists. For NxUE-only reads, record an exact `acquisition.fieldFallbacks[].jsonPath` for every reported DesignSizeMode. For mixed reads, treat `fieldFallbacks` as the exhaustive list of NxUE-acquired fields and use only concrete `$.assets[i].designSizeMode` paths, never wildcard or aggregate evidence. Treat this as static verification evidence only; do not expose it as a programmer-facing runtime interface.

3. Validate the post-build acceptance against those exact files:

   ```powershell
   python scripts/validate_build_acceptance.py <ui-build-acceptance.json> --requirement <requirement.json> --bundle <bundle.json> --readback <readback.json>
   ```

   Both versions require phase `post-build-ui-review`, status `accepted`, current Requirement/Bundle/Readback bindings, and exact reviewed asset ID/path coverage. Version 0.1 retains reviewer actor type `user` and confirmation source `direct-user-message`. Version 0.2 requires `authorizationMode: delegated-user-authorization`, the actual `agent` / `primary-coordinator` reviewer, `userHasReviewedResult: false` in the bound result review, and the exact grant, post-result review and frozen-result consumption bindings. Revalidate every dependency, every final asset/check review and the current conversation authority; the coordinator must have completed the real review after all final gates. Do not fabricate a later user message or treat a generic full-workflow request, art-choice delegation or the Requirement review gate as result acceptance.
4. Prepare and validate `UIProgramHandoff 0.3`:

   ```powershell
   python scripts/prepare_program_handoff.py --requirement <requirement.json> --bundle <bundle.json> --readback <readback.json> --build-acceptance <ui-build-acceptance.json> --output <ui-program-handoff.json>
   python scripts/validate_program_handoff.py <ui-program-handoff.json> --requirement <requirement.json> --bundle <bundle.json> --readback <readback.json> --build-acceptance <ui-build-acceptance.json>
   ```

5. Generate the deterministic, safe DOCX content contract 0.4:

   ```powershell
   python scripts/prepare_program_document_contract.py --handoff <ui-program-handoff.json> --requirement <requirement.json> --bundle <bundle.json> --readback <readback.json> --build-acceptance <ui-build-acceptance.json> --output <program-document-content.json>
   ```

   Its `requiredSemanticRelationshipStatements` are machine-generated audit rows, not prose for the Agent to paraphrase or render. Retain and validate every row in the machine-side content contract and verification artifacts, but do not copy them into the programmer-facing DOCX and do not create Appendix A or a semantic-trace appendix.
6. Build the DOCX with the deterministic production builder after the content contract passes. The builder revalidates the current Requirement, Bundle, Unreal Readback, post-build acceptance, Handoff, and content projection before creating any output. It resolves only the environment-variable name and filename authorized by the Handoff, fixes the retained reference internally, consumes only the verified Handoff/content fields as document business data, writes a canonical OPC package, and atomically replaces the output only when bytes changed:

   ```powershell
   python scripts/build_program_docx.py --handoff <ui-program-handoff.json> --document-content <program-document-content.json> --requirement <requirement.json> --bundle <bundle.json> --readback <readback.json> --build-acceptance <ui-build-acceptance.json>
   ```

   Do not add arbitrary template, output-path, or free-copy inputs. `umg_*` uses the fixed Chinese suffix `系统主界面`, verified list-entry assets use `集合条目控件`, and other `uw_*` assets use `功能子控件`; all summaries and relationships are deterministic projections of verified counts, Widget names, purposes, collections, and state controls. The builder preserves the 0.4 four-column table contract, excludes saved Designer Visibility and machine-only semantic statements, rejects unknown package parts and external relationships, fixes ZIP order/metadata without DEFLATE variability, and returns only filename/hash/byte count/change status. A byte-identical repeat reports `changed: false` and preserves the existing file mtime. If `NEXTGAME_UI_PROGRAM_DOCS_ROOT` is unavailable, stop after the verified JSON artifacts. The available `$documents` skill is still required for the following render-and-inspect workflow, but it is no longer an unconstrained production authoring step.
7. Create the authoritative render evidence through fresh rendering. The validator itself performs a fresh headless DOCX-to-PDF conversion and uses `pdftoppm` to create the final `page-<N>.png` files in the fresh directory; those exact pages are the pages to review:

   ```powershell
   python scripts/validate_program_docx.py --docx <document.docx> --render-dir <fresh-pages> --render-evidence-output <render-evidence.json> [--soffice-path <soffice>] [--pdftoppm-path <pdftoppm>]
   ```

8. Visually inspect every authoritative page in that evidence. Record every reviewed PNG filename explicitly; never infer page review from the existence of files.
9. Record and validate final document evidence. Repeat `--reviewed-page` once for every reviewed page. Final validation reconverts the current DOCX and rerenders it, then compares every page hash, size, and dimension with the reviewed pages:

   ```powershell
   python scripts/validate_program_docx.py --handoff <ui-program-handoff.json> --requirement <requirement.json> --bundle <bundle.json> --readback <readback.json> --build-acceptance <ui-build-acceptance.json> --document-content <program-document-content.json> --docx <document.docx> --render-dir <fresh-pages> --render-evidence <render-evidence.json> --reviewed-by <agent> --reviewed-at <iso-8601> --reviewed-page <page-1.png> --output <document-verification.json> [--soffice-path <soffice>] [--pdftoppm-path <pdftoppm>]
   python scripts/validate_program_docx.py --handoff <ui-program-handoff.json> --requirement <requirement.json> --bundle <bundle.json> --readback <readback.json> --build-acceptance <ui-build-acceptance.json> --document-content <program-document-content.json> --docx <document.docx> --render-dir <fresh-pages> --render-evidence <render-evidence.json> --verification <document-verification.json> [--soffice-path <soffice>] [--pdftoppm-path <pdftoppm>]
   ```

## Hard boundaries

- Accept only `target.mode: production` and one `/Game/UI/UMG/<SystemFolder>/...` system folder.
- Require a schema-valid, currently bound `ui-build-acceptance.json` with accepted post-build status: direct-user-message provenance under 0.1, or the explicit independently validated delegation/review/consumption contract under 0.2. Never substitute the Requirement review, an earlier blanket request, or Agent inference. The documentation Agent must never create, repair, consume or broaden authorization.
- Treat any asset mutation or re-save, Requirement or Bundle change, preview replacement or re-verification, or Readback change as invalidating the acceptance. Re-read and fully validate all three current source files at document-content generation and again at final DOCX verification; comparing only an old handoff with an old acceptance is insufficient. Return to final build-result presentation and the applicable acceptance gate. A consumed delegation cannot authorize a different result; obtain new specific direct-user authority or ordinary post-result confirmation.
- Derive program variables only from the intersection of accepted in-scope runtime intent, a mapped layout node with `isVariable: true`, and actual Unreal `isVariable: true`. Accepted state branch Panels obey the same layout-and-actual variable gate.
- Keep post-save `actualSavedVisibilityBindings` as trace evidence only; never project their saved Visibility values into the programmer-facing DOCX. Emit `runtimeVisibilityOutcomes` only from accepted explicit `implementation.stateOverrides[].changes[]` whose property is `Visibility`, after the same accepted-element, layout-variable, and actual-variable gates.
- Preserve each state model's accepted `implementationStrategy`. Emit `State branch` document rows only for `exclusive-panel-branches`, and emit `State outcome` rows only for `shared-tree-properties`; exclusive states cannot carry runtime Visibility outcomes.
- Treat a missing, ambiguous, non-variable, or Visibility-less mapping for an accepted state target as a projection failure. Never silently omit it or downgrade it to a handoff gap.
- Include runtime collections, state controls, accepted build deviations, and explicit state-control gaps with source identifiers.
- Place collection, state, and support-dependency documentation according to owning/hosting-asset membership: inside a first-module asset block when matched, otherwise only inside the conditional `其他资产程序说明` module grouped by asset. Record asset identity and path once per unmatched group, and do not duplicate them inside each item.
- Keep embedded collection and state identifiers in ordinary body or inline-label styling; never promote `collection.*` or `state-model.*` identifiers to Heading, `Tool Asset`, or another section-title style.
- Require every Bundle asset to have passed `widget-tree` and `key-properties` checks whose `artifactPath` resolves to this exact Readback. Require Readback time to follow the timezone-aware Bundle completion time.
- Exclude static Designer layout, anchors, dimensions, fonts, colors, draw settings, fixed text, backgrounds, decoration, and default visibility from program interface requirements.
- Do not document generated-content data source/owner/refresh strategy, runtime parameter type/default/update timing, event or callback name/payload, or list item data structure. These exclusions are policy, never handoff gaps.
- Project program purposes and state-control descriptions only from the fixed high-level enums in the contract. Never copy arbitrary runtime reasons, control descriptions, or deviation prose into the handoff.
- Retain and bind every generated semantic relationship statement in `program-document-content.json` and machine-side verification artifacts for deterministic relationship auditing. Do not require those statements to appear in the DOCX, and do not generate Appendix A or a semantic-trace appendix.
- Keep Readback acquisition, snapshot timing, source bindings, and provenance boundaries in machine contracts and evidence only; do not emit a developer-facing `只读快照边界` section.
- Reject the narrow bilingual policy phrases that would introduce any of the four excluded contract categories into the final DOCX.
- Reject saved/default Designer Visibility evidence, including branch-root Widget/value pairs and any `State branch:` row containing `visibility=`. Allow only accepted shared-tree target Visibility represented by `State outcome` semantics.
- Store only `NEXTGAME_UI_PROGRAM_DOCS_ROOT` and the DOCX filename for the output destination. Never store its resolved absolute directory or output path.
