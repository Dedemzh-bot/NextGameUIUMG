---
name: reverse-nextgame-umg
description: Reverse existing NextGame UMG screens into editable, versioned Figma prototypes; audit hidden controls and runtime states, optimize layout with project prototype standards, and retain per-page evidence for batch design. Use for Demo-to-prototype extraction and subsequent prototype revisions. Does not modify Unreal assets or game business code.
---

# Reverse NextGame UMG to prototypes

Use existing Unreal structure and read-only behavior evidence to create an editable design source. Keep source facts, proposed design, rendered results and user acceptance separate. This is the reverse entry from NextGameUIUMG into NextGameUIDesign; it does not replace the existing Art, design-contract or production build workflow.

## Restore and scope

- Read project AGENTS/local instructions. Read the project's NextGame_UI_Spec `AI_ENTRY.md`; resolve its current prototype profile rather than copying dimensions from a screenshot or this skill. Discover that root from project configuration/current task, never another user's fixed drive.
- Restore the page ledger and explicit revision. A screenshot, latest file timestamp or hidden Designer flag is insufficient to choose the current version or business scope.
- UI authorization permits read-only source analysis and authorized Figma work, not Lua/C++ changes, event binding, runtime configuration or Unreal asset writes.
- Prefer official Unreal MCP for asset/WidgetTree readback. Use project fallback only when required capabilities are absent. Read the applicable Blueprint-reading instructions before examining Blueprint logic.

## Workflow

1. **Capture source.** Record asset identity, source hash, WidgetTree, variables, parent slots, default visibility, inherited children, user widgets, dynamic collection EntryClass and dependencies. Preserve source defaults, independent text and resource roles. Mark estimated geometry and unexpanded dependencies explicitly; a normalized source model is not itself a fresh Unreal observation.
2. **Analyze behavior before drawing.** Read associated bindings, open/refresh paths and state-changing functions. Classify hidden controls as conditional, explicitly inactive, template, or unresolved. A name search is discovery, not proof that a function is unused. Follow the checklist in [state coverage](references/state-coverage.md).
3. **Prepare the ledger.** Use `scripts/prototype_workflow.py prepare` with the supported normalized source format. It creates a pending checklist, not inferred decisions or approvals. Classify every source node and record active interactions, conditions, dependent fields, required states and evidence. Unread dependencies stay unresolved. The helper currently imports `nextgame-umg-reverse-prototype` version 1; other readbacks require an explicit, evidence-preserving normalization step.
4. **Project source and optimize separately.** Preserve the source page. Derive an editable prototype revision with stable source IDs, Figma IDs, independent text, collection hosts/entries and state samples. Use the existing Figma skill/tool workflow. Read current nodes before editing, keep state navigation in the current revision, and do not use one raster screenshot as the editable UI.
5. **Review the actual result.** Read Figma state after changes and export current screenshots. Check effective visibility through ancestors, clipping, overlaps, labels/costs and interaction regions. Record actual observation, not intended coordinates. A visual-review flag is a human/agent attestation, not automatic image recognition. Interactions only count as exercised if actually clicked; configuration readback alone is not an interaction test.
6. **Check coverage and archive.** Run `validate`; it checks source/evidence hashes, complete source identity inventory and declared state coverage. It cannot discover runtime behavior, verify screenshots visually or establish user acceptance. After edits, refresh evidence and rerun. Run `batch` over explicit page-ledger paths for a per-page index; a failure on one page remains visible. Do not claim all pages complete from one passing page.
7. **Handoff.** Present the current prototype and remaining gaps. Only after the user accepts the design, pass the versioned layout/state decisions to NextGameUIArt. If artwork changes layout, revise the design source first. Formal UMG intake still uses receive-nextgame-design and the existing production gates.

## Reusable layout decisions

For ordinary system prototypes, the project currently provides `SYS.PrototypeShell@1.0.0` under rule `NG-UI-COM-024`. From the discovered spec root, use `python tools/prototype_profile.py resolve --profile SYS.PrototypeShell@1.0.0 --output <task/prototype-shell.json>`. Bind the exact resolved version to the page; this output is prototype-only, not a production design-contract or UMG build input. Preserve old profile locks unless explicitly migrating the page.

The project spec owns numeric values and profile versions. Reuse the common return-button slot, currency slot, bottom hint bar and ordinary-item metric. Preserve edge anchoring and text growth directions. Hint groups should size to their content; a small nominal group gap does not fix excessive fixed label width. Changing column count must recompute host width, not scale ordinary cells. Page-specific columns, weapon proportions, sample amounts and disabled business modules remain page decisions.

Moving a warning requires checking the released list space, scroll rail, controls and bottom margins. Changing a panel width requires checking its position and neighbors. Keep the role-model space clear through surrounding layout; a prototype mannequin is composition evidence, not an empty UMG node to generate.

## Commands and deliverables

Python 3 and `jsonschema` are required; scripts have no network or Editor access and refuse to overwrite outputs.

```text
python scripts/prototype_workflow.py prepare --source <prototype-source.json> --page-id <stable-page-id> --revision <revision> --out <state-ledger.json>
python scripts/prototype_workflow.py validate <state-ledger.json> --out <coverage-report.json>
python scripts/prototype_workflow.py batch <page-a-ledger.json> <page-b-ledger.json> --out <page-index.json>
```

Keep source files, the ledger, source-to-Figma mapping, current screenshots/readback, profile references, revision history and unresolved items. Outputs record completeness of this declared evidence only, never production acceptance. Do not edit historical evidence to make an older revision appear complete. Do not create or run game tests unless explicitly requested.
