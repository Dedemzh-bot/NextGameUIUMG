# Existing-layout execution preflight correction

Release: `0.1.0+codex.20261105.existinglayout5`. Layout/Requirement schema
versions are unchanged. This is a capability correction, not execution approval.

## Protected Designer mode

NxUE `describe-tool manage-property` returns metadata, not JSON Schema. The
executor validates that metadata (name, editor requirement, list/get/set actions,
and set-only write action), then reads the exact generated CDO property list.
`DesignSizeMode` must be an EnumProperty on the exact expected CDO/class/package.
The existing documented get/set protocol is recorded explicitly as metadata plus
documented contract; it must not be reported as discovered JSON Schema.

The target remains limited to reviewed FillScreen or Desired. Actual before
enum value, exact CDO/property identity, compare-and-set and immediate after-read
are retained. Structural compile precedes reacquiring the CDO and setting mode;
save and final complete readback follow. Compile does not authorize substituting
a different before value. No generic Python write fallback is introduced.

## Serialized Brush preservation

Actual prior native roundtrips establish that SlateBrush serialization includes
`uVRegion` and `bIsDynamicallyLoaded` although the editable schema omits them.
Only these two fields may be carried through unchanged. The parent schema must
be titled SlateBrush and expose drawAs, imageSize and tintColor. Target values
must equal the actual before values using the existing native binary32 equality
authority. Unsupported names, locations or changed values still fail.

For new controls, preflight resolves and checks the actual class CDO and reads
its values. Initialization repeats the comparison against the newly created
instance. Existing operations compare their full before state as usual. The
setter and full after-read comparison remain unchanged; no serialization fields
are silently removed and no changed unexposed field is accepted.

## ScaleBoxSlot boundary

The observed ScaleBoxSlot schema exposes horizontalAlignment and
verticalAlignment only. New/reparent ScaleBox Slots require exactly these two
fields and reject padding. Other Slot requirements are unchanged. An existing
contract that specifies ScaleBoxSlot padding must receive an explicit source
revision; the tool never drops it from an accepted operation automatically.

These changes preserve formal gates, durable failure receipts and no-blind-replay
policy. Read-only preflight evidence is separate from writes, save/readback and
visual acceptance.
