# Supplemental existing-update review

## Scope and authority

`scripts/review_existing_update.py` is an offline, read-only diagnostic for an
existing `UILayoutSpec 0.4` / `existing-asset-layout-update/2`. It reuses the
canonical Layout validator, plan builder, snapshot/2 evidence validator and
binary32 equality implementation. It does not connect to Unreal, mutate assets,
write ownership into a Widget Blueprint, or execute an operation.

Use it after preparing a local Layout and before executing the accepted Bundle,
or to explain an interrupted run from newly captured actual evidence. The full
Requirement, Accepted Build View, Bundle/Coverage, current asset CAS, native
schema discovery, compile/save and actual readback gates remain required.
`executionAllowed`, `formalGatesValidated` and `visualVerified` are always false.
`review-ready` means that this supplemental diagnostic found no blocking issue;
it is not a production authorization, dependency completeness claim or result
acceptance. This optional capability does not change historical Layouts,
snapshots, or the dedicated executor's existing semantics.

## CLI

```powershell
python -B skills/build-nextgame-umg/scripts/review_existing_update.py `
  --layout TASK/layout.json `
  --current-snapshot TASK/current/snapshot.json `
  --output TASK/update-review.json
```

The installed script resolves its own plugin root. An isolated staged copy can
use `--plugin-root <actual-source-plugin-root>` to reuse that source's canonical
validators and schemas. A different already-imported authority is rejected.
No local machine path is a published default. `--output` creates a new explicit
diagnostic JSON file; it never overwrites an existing file. Omitting it prints
the complete report to stdout. Exit codes: `0` review-ready, `2` blocked, `1`
invalid input or failed evidence validation. All statuses keep execution denied.

The result binds the physical Layout, baseline and current snapshot bytes,
canonical code/schema authority, and the canonical target-plan digest. Evidence
files and authority bytes are checked again before returning. The script lists
baseline/current drift, exact planned values, operation status, observed
WidgetTree order and the planned final sibling order. `target-observed` only
states that one operation's target value is present; it does not make an old
baseline replayable. Any baseline drift remains blocked and requires a new
scoped reviewed plan. No automatic rollback or conflict resolution is provided.

## Ownership records

Without additional provenance, existing non-inherited widgets remain `unknown`.
Variable exposure, a name prefix, appearance or membership in a planned tree
does not prove that a generator owns the widget. Actual inherited UObjects and
null inherited declarations are separately marked; a declaration with no
UObject is never an editable node. Names in `plannedGeneratedWidgets` are future
additions from the canonical plan, not evidence that creation already happened.

`--ownership <ledger.json>` optionally records explicit responsibility
declarations. The closed schema is
`assets/existing-update-review.schema.json#/$defs/ownership`. The document uses
`kind: nextgame-ui-widget-ownership`, `version: "1"`, the exact target
`assetPath`, the exact current snapshot `{path, sha256}` binding, and `records`.
Each record has `widgetName`, `ownerKind` (`generated` or `manual`), a bound
JSON `evidence`, a `jsonPointer` into it, and a nonempty `reason`. Duplicate names,
unknown widgets, stale evidence, a pointer without the widget identity or an
attempt to relabel actual inheritance are rejected.

These records remain `evidence-bound-declaration`, with `ownershipProven=false`.
Hash binding proves which declaration was reviewed; it does not independently
prove historical creation, authorship, user approval or the right to delete or
move. A future generator-receipt verifier can add a separately versioned proof
contract. Do not silently upgrade declarations to verified ownership.

## Dependencies and structural conflicts

The review reports observed variable exposure, the existing protected-name set,
actual NamedSlot host/content identity and conservative graph-text token hits.
A graph-text hit is explicitly `possible-text-hit`, not a resolved binding;
absence of a hit proves nothing about complete program references. Graph text is
tokenized once, and NamedSlot references and per-widget hits are indexed once,
so the review does not repeatedly serialize the entire graph for each widget.

`--dependencies <references.json>` can incorporate scoped programmer or
extractor evidence for `blueprint`, `animation`, `native`, `lua` and `named-slot`
references. The closed `#/$defs/dependencies` contract uses
`kind: nextgame-ui-widget-reference-evidence`, `version: "1"`, exact
`assetPath`/`currentSnapshot` and `records`. Each record has an `id`,
`widgetName`, `referenceKind`, bound JSON `evidence`, `jsonPointer` and `reason`.
The evidence fragment must mention the actual name or object reference. These
are labelled `reported-evidence-bound`; this tool does not claim to verify the
extractor's semantic interpretation or independently scan external Lua/native
code. Negative or complete-coverage declarations are not accepted.

Reference coverage remains incomplete for animation, native and external Lua
enumeration, even when positive examples are supplied. Structural additions or
reparents produce explicit scoped blocking issues for that uncertainty, affected
unproven ownership and any protected/reference hits. Reparents inspect the actual
source subtree, so a referenced descendant is included. Additions inspect their
actual target parent. Property-only plans retain the canonical allowlists and
remain subject to all formal gates; this diagnostic never substitutes for them.

## Borrowed design principles

The reference is [Design2UMG's conflict implementation](https://github.com/DiracSea12/Design2UMG/blob/master/Source/Design2UMGEditor/Private/DesignImportReimportConflict.cpp),
which checks generated-content ownership, developer bindings, animation
bindings, Blueprint variable references and preserves an asset on conflict.
NextGame's Python implementation is independently written around the existing
Layout/snapshot authorities. It adds conservative dependency reporting, not
Design2UMG's deletion, replacement, navigation-generation or Blueprint-writing
capabilities. Unreal animation/native/Lua enumeration is explicitly unfinished.
