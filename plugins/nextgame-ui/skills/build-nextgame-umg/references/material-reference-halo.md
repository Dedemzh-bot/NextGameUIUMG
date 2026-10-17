# Halo mask reference

Read only after a relevant catalog match and current asset existence check.
Follow [immutable variants and family numbering](material-instance-rules.md).
Observed 2026-09-30; re-read current actual data before execution.

## Identity and scope

`uw_fight_scope.GameImageBlack` references
`/Game/UI/Materials/HaloMask_Scope1_Inst`, whose direct Parent is
`/Game/UI/Materials/HaloMask_mat`.
The parent has UI domain, Translucent blend and `two_sided=false`.
The Widget is `/Script/UIFramework.GameImage`. Its observed Brush is
Image/NoTile/NoMirror with black tint and alpha `0.9`, image size `32x32`.
Brush image size is not its actual display allocation. New component instances
use the standard Img prefix; do not rename this legacy source during learning.

## Effective reference parameters

| Type | Exact name | Reference value | Parent default | Observed responsibility |
| --- | --- | --- | --- | --- |
| Scalar | `Size` | approximately `0.45` | approximately `0.3` | Radius-like threshold in corrected UV space, not a diameter in pixels. |
| Scalar | `SmoothValue` | approximately `0.01` | approximately `0.1` | Width of the SmoothStep transition. Positive values are required for a non-degenerate feather. |
| Vector | `Param` | `(2560,1440,0,1)` | `(0,0,0,1)` | R/G ratio corrects horizontal UV. Use positive actual width/height for the intended allocation; B/A are not connected. |

Both scalars and Param are overridden in the instance. There are no exposed
texture or static-switch parameters. The parent's zero R/G defaults must not be
blindly used when creating a new instance, because the ratio would be undefined.

## Graph-derived usage

The current graph computes:

```text
aspect = Param.R / Param.G
d = length(((U - 0.5) * aspect, V - 0.5))
mask = 1 - smoothstep(d, d + SmoothValue, Size)
EmissiveColor = mask
Opacity = mask
```

This follows the actual SmoothStep inputs: Min=distance, Max=distance+SmoothValue,
Value=Size. Do not incorrectly document the inputs as smoothstep(Size,
Size+SmoothValue, distance). With positive SmoothValue, the opening is
transparent inside `d <= Size-SmoothValue`; the mask is opaque for `d >= Size`,
with the transition between them. Widget/Brush black tint provides the black
appearance; the material output alone is not inherently black.

Larger Size enlarges the transparent opening; SmoothValue controls its inner
feather band. New opening sizes, feather widths and allocation/aspect presets
require a new sequential instance. Match Param R/G to the intended rendered
rectangle, not always the 2560x1440 full-screen design canvas or 32x32 Brush size.
If the allocation changes dynamically, record the required per-widget MID
aspect update as runtime intent; do not mutate the saved shared instance or
implement gameplay here.

The observed graph has a fixed center and no angular progress/direction switch.
Do not invent Clockwise, center-offset, invert or color parameters for Halo.
For angular fill choose the circular family when applicable; unsupported mask
behavior requires a separate accepted capability decision.
