# Design contract workflow

The project design package owns module selection, field granularity, collection/state intent, adaptation, capacities, graphics and declared asset boundaries. Versioned JSON owns fixed parameters. NextGame UI owns compatible Unreal class/Slot mappings and execution. Preserve accepted intent when selecting implementation details; a mapping conflict is an explicit design change request.

## Inputs and commands

Use `../analyze-nextgame-ui-requirements/scripts/design_contract.py` relative to this skill. Read its `--help` and command help for current arguments. The supported operations are `freeze`, `validate`, `compile`, and `accept`.

- `freeze` is an explicit migration of a fully validated legacy accepted Requirement. Pass the original RequestPacket and immutable review draft, and explicit historical authority parameters if needed. It produces a new design source; it must not change the original Requirement, revision index, Bundle or result acceptance.
- `validate` verifies the closed design contract, exact source bindings and decision consistency. Missing or conflicted modules remain declared gaps; validation of document shape is not readiness for a build.
- `compile` performs exact-value projection to a new pending Requirement 0.2. It does not perform another nine-role interpretation and does not imply acceptance.
- `accept` records review of that current result from a real supplied review message, reviewer identity and time. It requires a new `--output` and writes an independent `<output-stem>.design-review.json` receipt binding the reviewed contract, content and revision. Existing delegation can authorize a concrete AI review with `--review-kind delegated-design-review`, but the record must not impersonate the user. Any later change invalidates this approval; updating the contract and its internal hashes cannot reuse the old receipt. Retain the receipt as an immutable source alongside the accepted Requirement.

Do not import the old three-module `bridge_poc` as a production contract. Its 0.1 schema remains a historical offline experiment. Project `data/design-recipes.v1.0.0.json` is a separate intent catalog; use `tools/design_module_catalog.py catalog`, then `resolve --recipe <exact-id@version>`. It defines only its registered families. Required page decisions still need design work. Current parameter Draft status survives this process.

## Completion and gaps

Apply [visual presentation rules](../../build-nextgame-umg/references/visual-presentation-rules.md) as compatibility and evidence requirements during reception. Report a precise gap when semantic ownership, joint text geometry, local/shared state scope or art evidence cannot be established. Existing locked fields remain authoritative; resolve a conflict in a new design-source revision rather than reconstructing the page from its reference image or patching compiled values. The new art presentation capability is adopted explicitly downstream and does not rewrite historical design contracts.

An authored design contract contains normalized design content, not merely a frame image or a list of recipe names. Complete its evidence and canonical model once at design time. All schema, ID/reference, state, collection, geometry, image ownership, asset-boundary and review checks apply to Requirement 0.2 just as to legacy 0.1. Only source provenance differs.

The existing raw analysis remains available for new or incompletely described screens. Once those decisions have been accepted and frozen, subsequent compatible builds read them directly. A gap-only revision retains every unaffected locked decision; it never silently broadens scope or turns placeholder samples into business limits.

Expected image resources and multiplication colors must be bound to the same design revision as layout. A changed texture binding invalidates old color expectations; it does not justify ignoring color differences globally. Currency abbreviation, maximum business values and supported viewport ranges require their own declared intent; stress-test samples are not automatically new business rules.

## Shared downstream validation

Run the complete `validate_requirement_spec.py` with the matching RequestPacket. For 0.1 retain original nine-role Findings, context and review-draft validation (or explicit locked historical authority). For 0.2 validate the actual design source and exact compiled content. Never use `--skip-linked-files`, a custom Schema or a fake Findings set to turn a failure into success.

Generate and validate `accepted-build-view.json`, then retain normal Bundle/Coverage/Layout checks. The View can be used only when it is a validated projected view with `buildAllowed: true`; an unknown schema or incomplete dependency closure is a non-buildable fallback.

Post-save Unreal readback and visual checks remain independent. A new design contract or successful compile cannot carry forward a previous build's passed result. Keep the existing prototype/production split and the independent result-acceptance gate for formal documentation.
