# Repository agent rules

This repository publishes contracts and adapters, not project-generated UI assets.

- Keep `plugins/nextgame-ui` as the canonical schema, validator, and Skill implementation.
- Keep `orchestration` vendor-neutral. Runtime-specific APIs belong only in `adapters/<runtime>`.
- Classify input before dispatch. Raw image/text analysis produces UIRequirementSpec 0.1 and preserves the exact nine AgentFindings roles, their isolated output files, and the three dependency barriers. Structured design-contract/1 uses the plugin's receive-nextgame-design skill and deterministic compiler to produce UIRequirementSpec 0.2; never fabricate nine Findings for that route.
- Both routes retain the full source, schema, review, geometry, state, layout, coverage, Bundle, and actual-readback gates. The portable DAG and bundled runtime adapters currently schedule the raw 0.1 route only; do not claim they implement structured intake scheduling.
- Keep direct user review as the repository default. A project's already explicit design-review delegation may be recorded truthfully with the plugin's scoped delegated-design-review receipt; it is not a default permission for other users or projects. Never invent delegation or impersonate a user. Post-build acceptance still requires a later direct user message accepting the presented result.
- Treat validated JSON artifacts as authoritative. Agent messages and task status are receipts only.
- Never commit Unreal assets, `Saved` request runs, screenshots from a user task, credentials, local caches, or machine-specific absolute paths. The only exception is an explicitly documented synthetic/hash-bound fixture already shipped under plugin `assets`; changing its placeholder paths requires rebuilding every linked digest.
- Requirement analysis and structured intake are read-only with respect to Unreal. Build mutation begins only after valid design review and separately authorized asset scope; the default first review is direct user approval.
- Keep the design-contract, compatibility-review, review-receipt, and Requirement schemas authoritative only in plugins/nextgame-ui. A separate design repository owns project parameters and recipes and consumes these contracts; it must not create a competing validator authority.
- Preserve the authoritative plugin's physical bytes. Its schemas and fixtures use file hashes, so do not normalize plugin newlines or rewrite versioned files while packaging. Update the source first if a validator fix is needed.
- Documentation begins only after the verified saved build and normalized readback are presented and accepted in a later direct user message.
- Run the repository, adapter, orchestration, Skill, and plugin checks documented in `README.md` before committing.
