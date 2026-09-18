---
name: receive-nextgame-design
description: Receive or prepare a versioned NextGame design-contract/1 from explicit design decisions and source files, validate locked design content, and compile UIRequirementSpec 0.2 for the existing UMG build workflow. Use for Figma design handoff files, approved structured design packages, or explicit migration of an existing requirement. Raw screenshots without a design contract use analyze-nextgame-ui-requirements.
---

# Receive NextGame Design

Apply [production fidelity checks](../build-nextgame-umg/references/production-fidelity-checks.md) to specific gaps and downstream handoff coverage. Preserve locked values; do not use these checks to reinterpret an accepted structured design.

Design decides intent once; the receiver checks and translates it. Read [the contract workflow](references/design-contract-workflow.md) for commands and provenance. This skill does not connect to Unreal or create assets.

1. Locate the explicitly supplied project design root and its `AI_ENTRY.md`. Restore existing builds through their validated `current-run.json`; never choose a Bundle from its filename or timestamp.
2. Classify the input. A `design-contract/1` (`kind: nextgame-ui-design-contract`, `version: 1`) uses the structured route. A legacy accepted Requirement can be explicitly frozen as a new design source. A screenshot or parameter bundle alone is incomplete design input: use the raw analysis route or finish only the missing design modules before producing a contract.
3. Validate the design contract and all source bindings with the sibling analysis skill's `scripts/design_contract.py`. Module `specRef` and `recipeRef` are exact versions, not suggestions; numeric parameters are resolved by the project registry. A Figma node link is traceability, not proof of a current exported snapshot.
4. Compile deterministically to a new pending `UIRequirementSpec 0.2`. Do not change locked fields, invent Findings, auto-upgrade Draft parameters, copy old approval, or inherit build verification. Record a concrete gap/conflict against the owning module when a decision is incomplete, incompatible or unsupported. Make a new design revision to resolve it; do not patch the compiled output independently.
5. Review that concrete design and record real decision provenance. Apply an existing user delegation only within its scope; identify the reviewer as an AI acting under delegation. Review acceptance is separate from production-asset authorization and post-build acceptance. Then validate the complete Requirement and its current RequestPacket using the shared validator.
6. Build and validate an Accepted Build View. Hand that View to `$build-nextgame-umg`, which retains all existing Bundle, layout, asset, compile/save, readback and visual gates. The receiver's success never means UMG exists or the UI passed visual acceptance.

For a new module, read the project's `spec/07-spec-maintenance.md` or use `$maintain-nextgame-ui-spec`. Update the authoritative design source and exact-version recipe first. Reuse a known recipe only when purpose, state, capacity and adaptation match; naming similarity alone is insufficient.

Keep complete JSON in files and return a compact receipt with route, revision, hashes, unresolved modules and next action. Send only the necessary design content to a gap-analysis agent. Re-run deterministic checks over the complete authority; reduced model context is not reduced validation.
