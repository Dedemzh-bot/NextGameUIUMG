---
name: maintain-nextgame-ui-spec
description: Add, revise, version or migrate NextGame UI design and UMG production standards, module parameters, design recipes, mapping rules and validation policies. Use for maintaining the reusable specification system or its AI reading workflow, not one-off screen construction.
---

# Maintain NextGame UI Specifications

For the reusable production review policy and its explicitly scoped migration, see [production fidelity checks](../build-nextgame-umg/references/production-fidelity-checks.md) and the [2026-09-18 change record](references/production-review-change-20260918.md). The [2026-09-20 capability migration](references/execution-capability-change-20260920.md) adds explicit size, bounded text, material and authorization-format capabilities without reclassifying old evidence. Keep task-specific dimensions and unfinished visual checks out of global defaults.

Locate the project design specification root supplied by the user or current project. Read its `AGENTS.md`, `AI_ENTRY.md` and `spec/07-spec-maintenance.md` when present. Do not hardcode another developer's drive or an installed plugin cache as authority.

## Choose the owner before editing

| Decision | Authority |
|---|---|
| Fixed geometry, enums, text capacity and parameter expressions | Project `data/` versioned module/parameter files |
| When a module applies, conflict priority and exceptions | Numbered rules under project `spec/` |
| Reusable design intent and required page decisions | Project versioned design recipe catalog |
| Compatible Unreal classes, native Slot lowering, font/color conversion | Build skill mapping rules and scripts |
| Existing reusable Unreal assets | Plugin `assets/shared-widget-registry.json`, with actual asset evidence |
| Acceptance conditions and actual-state validators | Matching analysis/build/document contract and tests |

A single screen correction is not automatically a global rule. Establish its general scope with evidence. Do not put fixed dimensions into both Markdown and JSON, turn preview fixtures into business limits, or modify gameplay/state transitions merely to fix a UI standard.

## Art-stage ownership

The optional sibling `$refine-nextgame-ui-art` stage owns art resource mappings, presentation evidence, and scoped example records; it shares the existing design authority and coordinator. A confirmed example is scoped project data, not automatically a global recipe or parameter default. Keep fixed layout/state/collection decisions in their original versioned design source. Any art change to those decisions requires an explicit source revision and new acceptance before application.

Bundle/normalized Readback 0.4 add an opt-in art completion contract without relaxing 0.1–0.3. Do not relabel old accepted runs or change Requirement schema hashes merely because an art sidecar was added. Update art, Bundle, actual-state, and document gate regression tests together when changing the art handoff. See [on-demand-art-stage.md](../build-nextgame-umg/references/on-demand-art-stage.md).

## Make a compatible, reviewable change

1. Search the light registry and exact rule IDs before creating anything. Reuse a matching rule, or add a distinct version/scope. Record the problem, owning layer, authority, before/after behavior, affected consumers and migration plan.
2. Preserve released IDs and parameter versions. An incompatible shape/meaning needs a new contract version; a changed module gets an explicit new module version. Update exact references deliberately. Keep legacy artifacts readable against their recorded authority; never relabel or rewrite old evidence.
3. Update all relevant registration surfaces. Project numbered rules require the `migration-map.json` entry; module versions require Registry/Invocation updates. Plugin build rules require both `rule-index.json` and `rule-card-routing.json`, with complete routing and exact headings. New fields require closed schemas, semantic checks and dependency/reference projection audit. Do not just bump an accepted-schema hash without auditing its reference shape.
4. Add checks for observable invariants and meaningful rejection cases: conflicting locked values, stale hashes/versions, wrong scope, unsupported mappings and unapproved decisions. Run relevant Registry/Invocation, schema, source-provenance, Accepted Build View and Bundle/Coverage/Layout regressions. Validate shared assets or actual rendering only when the change requires those facts.
5. Record acceptance of the concrete standard separately from production authorization or UI result acceptance. Use existing user delegation truthfully; leave unsolved gaps and missing evidence visible.
6. Prepare in an isolated workspace, compare with the current source to detect concurrent edits, publish only intended files, then use the `plugin-creator` update/reinstall workflow for a local plugin. Verify source and installed-cache bytes. Report exactly which entry points are active and which old artifacts still need explicit migration.

Use the project's `templates/spec-change.md` for substantial changes. Do not invent a new report/checklist for a spelling correction. Generated previews, exports and installed caches are outputs; change their authoritative source first.

Design contract changes flow back to the design source, increment its revision and invalidate affected derived approvals/results. Preserve unchanged module decisions and analyze only new gaps. Both structured and raw inputs continue through the same UMG generation and actual verification path.
