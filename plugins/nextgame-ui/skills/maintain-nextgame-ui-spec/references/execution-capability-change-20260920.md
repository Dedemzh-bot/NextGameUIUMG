# Explicit execution capability migration — 2026-09-20

This change belongs to the build, art evidence and acceptance mapping layers. It does not establish a global screen recipe, fixed screen dimensions, new business behavior, actual Unreal capability or completed visual acceptance. Existing review and source-provenance gates remain mandatory.

## Contracts and owning sources

- `layout-dependency/2` in the Layout schema and validator supports a real root-direct, fixed-width, natural-height SizeBox with exact width propagation through supported explicit Slots. Horizontal Fill is limited to text leaves; visible graphic sources retain the conservative natural-height lower bound. Version 1 remains unchanged.
- `content-driven-child-size/2` in the Bundle schema and capability validator requires exact equality between placement width, native SizeBox width and proof width. The integer local reference width is their ceiling. Versions 1 and 2 cannot be declared together. This is planned dependency evidence, not Slate measurement.
- `bounded-wrap/1` is an explicit closed Layout `textCapacity` declaration for deliberately bounded wrapped Canvas text. It preserves fixed placement and checks exact positive Slot/rectangle/capacity dimensions and wrapping width. It does not add a runtime max-lines property or prove fit.
- `procedural-ui-material/2` in the art schema and material validator supports one TexCoord feeding separate Float3 Emissive and Float1 Opacity Custom nodes. Both complete code strings, topology, native inputs, compile/save, post-save readback and final saved state remain mandatory. Version 1 retains its original constant-RGB graph. A request selects exactly one version.
- `zh-one-test-delegated-review/1` registers one complete explicit original-message sentence under the existing request-scoped one-use result delegation. The corresponding existing art delegation accepts the same complete grant only with its original art-stage context. Generic continuation words do not grant result acceptance. The coordinator remains the actual reviewer; no personal user review is invented.

The authoritative details are [Layout contracts](../../build-nextgame-umg/references/layout-spec.md), [Bundle handoff](../../build-nextgame-umg/references/requirement-build-handoff.md), [art workflow](../../refine-nextgame-ui-art/references/workflow.md), and [delegated acceptance](../../document-nextgame-umg/references/delegated-result-acceptance.md). Rule index and routing version 0.23 route the same mandatory stages and current exact headings. No preliminary screening tool is added.

## Migration and verification boundary

Preserve original source images, packets, nine-role Findings, review drafts and accepted historical artifacts. A task that adopts a new capability must create and review a new design revision when accepted fields change, regenerate its Accepted Build View, layouts and Bundle, then rerun all strict linked checks. Independently bind new derivation and review records; old approvals do not approve changed coordinates.

Historical analysis is revalidated against its explicitly locked original authority and the current complete model using the existing historical-authority helper. This never relabels original packets, filters validator errors or replaces the current complete model validator.

Directed regressions cover compatible version 1 behavior and invalid mixed contracts, unknown widths, unsupported Fill propagation, invalid text capacity, stale or incomplete material evidence, and missing or generic authorization wording. Full art, relevant Layout/Bundle, rule routing and acceptance regressions are required before publication. Store actual command outputs and environment recovery separately from production evidence.

Prepare changes in isolation, compare source hashes against the pre-edit inventory, publish only reviewed files, update the existing manifest cachebuster through the plugin-creator helper and reinstall from the verified local marketplace. Compare source and installed bytes. Any task-local execution fallback must preserve exact native operations, actual ordered receipts and post-save readback; no test fixture or planned value may stand in for Unreal state or rendering.
