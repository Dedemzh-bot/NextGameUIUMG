# Layout 0.4 native responsive validation

Release: `0.1.0+codex.20261105.existinglayout4`.

The Bundle gate validates every mapped responsive intent for existing-layout
updates against the **effective target Slot**, not the legacy `adaptiveLayout`
field. This branch requires explicit Bundle capability
`existing-asset-layout-update/2`, Layout 0.4, matching SHA from the same bytes used
for JSON parsing, and the complete existing Layout/Requirement local gate.

Existing nodes merge reviewed `nativeSlot` patches into their immutable baseline
Slot. Reparents use their declared complete new Slot and class; additions use
their own complete Slot. Requirement intent does not participate in deriving
this actual target semantics and is compared independently and exactly.

- Canvas: a fixed anchor at 0, 0.5 or 1 means the corresponding edge/center;
  a valid nonzero anchor range means stretch. Other fixed anchors are not guessed.
- Overlay, box, button, size and scale Slots: native horizontal/vertical alignment
  maps explicitly to edge/center/stretch. Missing or unsupported values fail.
- ScaleBoxSlot Fill/Fill describes allocated Slot extent. ScaleBox ScaleToFit
  controls proportional content scaling separately; no Canvas anchors are invented.

Inherited-provider coverage is shared by both Bundle and coverage gates through
`_inherited_provider_coverage.py`. The helper retains the existing full native
validation, source SHA, actual parent class, nonvisual policy element, accepted
full-canvas region and unique asset ownership conditions. Ordinary elements and
regions still need their usual mappings. No fake widget nodes are introduced.

Legacy Layout 0.2/0.3 adaptation rules and Requirement schema hashes are unchanged.
Old erroneous intentions must be corrected in a new reviewed contract revision;
this tool change does not reinterpret them as accepted. Source/target semantics,
planned operations, UE execution, readback and visual acceptance remain separate.
