# Layout 0.4 reference registry correction

Plugin release: `0.1.0+codex.20261105.existinglayout3`.

Requirement 0.2 review and accepted-build projection share the reference registry
in `review_view.py`. This release recognizes only these element properties from
an exact, source-SHA-bound Layout 0.4 with capability
`existing-asset-layout-update/2`, matching its assetPlan ownership and payload:

- `providerSizing.acceptedRequirementRef`
- `providerSizing.consumers[].acceptedRequirementRef`
- `desiredSizeProof.acceptedRequirementRef`
- `collectionCoordination.acceptedRequirementRef`

These are canonical **element** references. The existing dangling/type checks
and dependency closure apply; source and owning asset are also retained in the
projection. No wildcard exemption of properties is introduced.

`providerSizing.rootSizingNodeId`, `desiredSizeProof.nodeId`, and
`collectionCoordination.nodeId` resolve only in the same bound Layout's nodes
and additions. The first two may be null as permitted by the Layout schema;
collection nodeId may not. Local IDs are never global canonical dependencies.

Missing/stale/ambiguous Layout evidence does not enable these rules. Full Layout,
Requirement provenance, acceptance, Bundle and execution checks still apply.
This correction neither approves design nor mutates Unreal assets. Requirement
schema hashes, Layout 0.2/0.3 and Art snapshot 1 behavior remain unchanged.
Existing normalized-first-round agent contexts retain their own strict registry;
the new fields belong to authored Requirement 0.2, not that earlier context format.

Migration: retain old artifacts and rebuild review/accepted-build views from the
new accepted Requirement revision using the new plugin. Never relabel an old view
or reuse an execution/acceptance result. Tool publication is separate from UE
execution and visual verification.
