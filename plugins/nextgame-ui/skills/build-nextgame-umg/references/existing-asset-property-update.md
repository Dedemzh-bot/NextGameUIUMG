# Existing Asset Property Updates

`existing-asset-property-update/1` is an explicit existing-only route for a
reviewed design revision. Its independently closed `UILayoutSpec 0.3` binds
the current actual art snapshot and complete raw `GetWidgets` tree. It is not
a relaxed interpretation of new-build `UILayoutSpec 0.2`.

Use this branch when a legacy asset must retain its tree, native names,
classes, variable flags, EntryClass, states and program references, but its
visual properties or immediate-parent Slot need a supported update.
Do not rename a legacy widget, insert a first Panel, or reconstruct an Entry
to satisfy new-build rules.

The layout covers every observed node. Each nonempty `nativeProperties`
and `nativeSlot` target is copied exactly into its own accepted Requirement
element and bound through the normal Accepted Build View and Bundle.
Declare the capability in the Bundle explicitly. Missing baseline nodes,
unknown native fields, structural differences, changed content/state/input/
EntryClass and foreign or unaccepted targets fail closed. Empty targets
mean preserve, not an implicit canonical default.

Optional `adaptiveLayout` and `flowSlot` declarations retain the normal
Bundle's semantic alignment and direct-parent allocation checks. They describe
the effective observed native Slot plus its accepted deltas and must agree
with it. They do not trigger a second lowering pass or authorize new writes.
Keep explicit native targets and semantic declarations consistent rather
than deleting required analysis intent to bypass a Bundle check.

Run the normal Requirement, Accepted Build View, Bundle and coverage gates.
The existing layout validator and `prepare_build.py` dispatch version 0.3 to
`scripts/existing_asset_update.py`; they do not emit Create/Add/replace calls.
Use the original build lowering before authoring native font/color targets,
not a second conversion formula. A generated update plan is never suitable
for a generic Create executor.

Before applying, revalidate the physical sources and current actual baseline,
including clean assets, saved-file hashes, ordered raw trees, NamedSlots and
the scoped protected-reference records. Execute only the resulting supported
property/Slot deltas through the existing ArtEditor adapter and preserve
durable intent, checkpoint and recovery evidence. Compile, save and read back
the changed assets, compare the protected state and repeat unchanged to prove
no additional writes. A changed source or actual state requires a new reviewed
revision or explicit recovery; it is not permission to overwrite user edits.

## Main And Child Responsibility

When updating a shared child, trace the complete visible chain:
screen instance Slot, child root/Desired Size provider, child content Slot
and, for a collection, EntryClass, entry footprint and pitch. A correct child
resource does not establish its screen instance allocation. A centered child
with a fixed Slot does not prove its parent's Desired Size. A source text
baseline does not establish its text box top or native glyph baseline.

Keep complete texture frame, visible bounds, host allocation and effective
transform separate. Use one source coordinate mapping, then derive each local
frame relative to its actual semantic owner. If a source lacks an allocation
or variant, record an explicit reviewed reconstruction choice rather than
calling it measured original geometry.

Property agreement and stable trees are intermediate execution evidence.
Do not close actual Desired Size, rendered geometry, wider/taller states,
font-family or final visual checks without their own current evidence.
