# Material reference policy - 2026-09-30

## Authority and scope

The user's direct request authorizes learning the ImgCD and GameImageBlack
material references and establishing a reusable selection/variant/numbering
standard for future similar designs. It does not authorize altering these
assets, production UI results or historical approvals.

Owner: plugin resource selection and Unreal lowering guidance. No current
project design-spec root was supplied or registered in the inspected project
entry files; archived copies under Saved are not promoted to design authority.
No design dimensions, design-contract schema or numbered external design rule
was changed. The shared-widget registry remains Widget-Blueprint-only.

## Change

Before: no cataloged circular/Halo material learning rule in the source index;
an older task-local circular study existed, without a reusable discovery entry.
After: rule index 0.25 adds `material.reference-discovery` and
`material.instance-variants`, with matching exact-heading routing and count 58.
The build and maintenance skill entry points link the lightweight catalog.
Detailed observations are loaded only for a matching, existing candidate.

The normative order is applicability/rule lookup, asset existence, targeted
actual readback, compatibility comparison, then read-only reuse or new instance
creation. Changed authored presets never mutate existing Materials/instances.
One sequence spans all instances of the same resolved root Material. Existing
legacy seeds reserve ordinal 1 without renaming; future allocation reads live
inventory and current reservations and chooses max+1.

UMGToolSet.GetWidgets and material/property reads were performed through NxUE
because the official MCP endpoint was unavailable. Six saved assets were
hash-checked; reference properties/graph targets reported non-dirty. No existing
asset was modified, compiled or saved. Diagnostic rendering used new transient
MIDs only; the blank output is failed visual evidence, not an accepted preview.
Current input/output wiring corrects an old task note about MoveAndScale:
its AppendVector takes separate B/A scale components.

## Verification and migration

Routing regressions cover both rules at all build stages, complete fallback
coverage and stale-pack rejection when the material policy changes. Evidence
tests check live-read provenance, exact resource/Parent/parameter identities and
unchanged asset hashes. These are not automated visual acceptance or a new
material write executor.

The policy does not expand `procedural-ui-material/1|2` to accept MIC graphs,
change closed production schemas or bypass result review. New runs use the new
entry points. Active runs regenerate rule packs and inspect affected resource
decisions; changed accepted designs require their normal revision/review.
Archived requirements, bundles, previews and approvals remain untouched.

Prepare and test in the isolated task copy, compare each changed source file
with its initial SHA before publishing, then use the plugin-creator cachebuster
and reinstall workflow and compare source/cache bytes.
