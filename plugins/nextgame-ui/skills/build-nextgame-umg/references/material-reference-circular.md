# Circular progress reference

Read only after a relevant catalog match and current asset existence check.
Follow [immutable variants and family numbering](material-instance-rules.md).
Observed 2026-09-30; re-read current actual data before execution.

## Identity and scope

`uw_fight_skill.ImgCD` references
`/Game/UI/Materials/Circular_Progress_Bar_CD_Inst`, whose direct Parent is
`/Game/UI/Materials/Circular_Progress_Bar_mat`.
The parent has UI domain, Translucent blend and `two_sided=false`.
The legacy Widget is `/Script/UMG.Image`; new consumers use project GameImage.
Its Brush is Image/NoTile/NoMirror, black tint with alpha `0.6`, and image size
`32x32`. Those are observed Brush settings, not the actual allocation or universal
cooldown dimensions/color.

## Effective reference parameters

| Type | Exact name | Reference value | Observed responsibility |
| --- | --- | --- | --- |
| Scalar | `Percent` | `1` | Progress input, multiplied by CutPercent when DebugAnimation is false; slider 0..1. |
| Scalar | `CutPercent` | `1` | Full angular range; separate progress-product and maximum-range gates; slider 0..1. |
| Scalar | `Clockwise` | `0` | Lerp between angle and one-minus-angle; parent default is 1. Use endpoint 0 or 1 for opposing directions, not fractional interpolation. |
| Scalar | `CutStartPivot` | `1` | Rotator Time input. Author's node description maps 1=top, 2=left, 3=bottom, 4=right. Rotator speed is approximately 1.57; this is not a 0..1 turn parameter. |
| Scalar | `Opacity` | `1` | Maximum of the cut gate Clamp, then multiplied by texture alpha and the progress gate. |
| Vector | `FillColor` | `(1,1,1,1)` | RGB multiplies Atlas RGB. Its alpha is not connected to the opacity output. |
| Vector | `MoveAndScale` | `(0,0,1,1)` | RG offset and BA scale inputs in the angular-coordinate branch. Read actual masks/output indices before changing. Does not transform Atlas texture sampling UVs. |
| Texture | `Atlas` | `/Engine/EngineResources/WhiteSquareTexture` | Texture RGB/alpha source; texture sample UV is unconnected, using its default coordinates. |
| Static switch | `DebugAnimation` | `false` | False selects Percent*CutPercent; true selects the Time-based debug branch. Do not enable for an ordinary progress preset. |

The local scalar overrides contain Percent, Clockwise, CutPercent and
CutStartPivot. A legacy `RefractionDepthBias=0` override also exists but is not an
exposed parameter of this parent graph; do not invent a UI control for it.
Vector/texture values above are inherited, not local overrides.

## Graph-derived usage

The angular branch transforms TexCoord, rotates around `(1,1)`, subtracts one,
then calls VectorToRadialValue. `Clockwise` interpolates its radial-coordinate
output and the complement. The two Floor gates use the resulting angle plus
`Percent * CutPercent` and angle plus `CutPercent`. RGB is gated Atlas RGB times
FillColor RGB; opacity combines the main gate, Atlas alpha and the clamped
full-range gate.

For a fractional full arc, configure CutPercent on a newly numbered instance
and let Percent express progress relative to that chosen full range. For
example CutPercent=0.5 is a half-range candidate, not a command to modify the
existing CD instance. Starting pivot and direction are separate choices.
Compare increasing and decreasing Percent at partial values before labeling a
render clockwise or counterclockwise. This acquisition did not obtain a valid
render, so no numeric-to-visible-direction claim is certified.

This graph is an angular cutter, not a general ring generator. With the observed
white square texture, it cannot itself supply ring inner/outer radii, round caps,
an independent background ring or a circular silhouette. Choose a compatible
Texture with the required alpha, not a PaperSprite object for Atlas. Confirm any
sprite/atlas conversion and UV mapping separately. Never substitute decorative
fragments or change the shared shader merely to mimic an unsupported contour.

Old task notes are not authoritative over the current readback: in particular,
the current AppendVector reads B and A separately for scale. Preserve actual
mask/output-index evidence rather than copying an old component interpretation.
