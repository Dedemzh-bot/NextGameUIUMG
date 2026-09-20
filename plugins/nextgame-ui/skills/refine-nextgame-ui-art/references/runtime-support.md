# Runtime support and current limits

## Python and Editor entrypoints

Use a Python runtime with the packages in [requirements.txt](../requirements.txt). `jsonschema` validates closed contracts; Pillow and numpy index/match/compare images; requests is required by the reused build MCP HTTP client. PyYAML is not a runtime dependency of this art stage. Keep dependency environments and outputs outside the plugin; never assume another developer's absolute runtime path.

```powershell
python -c "import jsonschema, PIL, numpy, requests; print('art dependencies available')"
python scripts/art_pipeline.py --help
```

The adapter defaults to `http://127.0.0.1:8000/mcp`; `collect`, `apply` and `capture` support `--url` and `--timeout`. Official Unreal MCP is the primary Editor entry. The adapter discovers actual registered tool input/output schemas before calling them, obtains the ProgrammaticToolset execution environment before batching, and never executes model-written UE Python. Read-only NxUE fallback is used only for concrete missing source-identity or protected generated-CDO Designer-mode capabilities. It reads the exact returned object and property identity; it never supplies expected values. The existing project import workflow remains authoritative for atlas/icon resources.

For a current capability snapshot, the importable `art_editor.create_editor(...).capabilities()` returns compact supported operations and limitations. This reads registry metadata and is not evidence that a particular asset operation passed.

## Observed host capability boundary

| Capability | Current implementation and consequence |
|---|---|
| Actual widget/visual/Slot collection | Uses registered UMG, Object and Blueprint toolsets. Widget classes come from actual `ObjectTools.get_class`, including Blueprint child instances. If the official generated-CDO schema omits `designSizeMode`, an available project NxUE `manage-property get` may read the exact returned CDO `DesignSizeMode`; acquisition is labelled mixed. Failed or unavailable reads remain null with uncertainty and block planning. |
| Program and animation reference completeness | The collector does not prove all native/Lua/animation references. `referencesComplete: false` remains explicit; removal/reparenting is not supported by the current Editor adapter. Do not set completeness to true from a partial list. |
| Property and Slot updates | Allowlisted observed fields only, after deterministic source checks and actual-schema preflight. No runtime behavior creation. |
| Static addition | Supported only for permitted static classes under compatible actual multi-child parents, with accepted design mapping and explicit Slot properties. |
| Resource import | Reuse existing import batches by default. The direct fallback is standalone PNG under `/Game/UI/Textures/`, with actual import identity/settings verification; atlas/icon imports use the project workflow. |
| Compile/save | Registered compile/save tools; the executor compares final observed state. |
| Presentation configuration | `presentation-review/1` validates exact resource/frame identity, native text effects, declared slice protection and family invariants in expected and actual snapshots. It covers unchanged and hidden scoped nodes too. |
| Native-source comparison | `mapped-source-reference/1` independently validates decoded `sourceSize` and actual `context.size`, plus source `bounds` and `captureBounds`. Native-pixel comparison pairs have no resampling or numeric cross-resolution metric; they do not supply a renderer or actual geometry. |
| Saved procedural UI Material | Explicit `procedural-ui-material/1` keeps the native TextureCoordinate → scalar Custom opacity / Constant3Vector emissive graph. Opt-in `/2` instead requires one shared TextureCoordinate → two Custom nodes, `CMOT_Float3` to Emissive and `CMOT_Float1` to Opacity. Request and readback versions must match exactly and cannot be mixed. Both require UI/Translucent/two-sided properties, original compile/save receipt, complete post-save official readback, final non-dirty state and current saved-file SHA. Actual Brush identity and uniform `evaluationSize` aspect are checked without pretending the material is a texture. Neither creates materials nor adds general graph execution to the art adapter. |
| Delegated appearance choice | `delegated-art-choice/1` permits exactly bound coordinator text choices under the original explicit art-stage grant, preserving source confidence and empty direct-user confirmations. It is decision authority, not source certainty, visual acceptance or permission to change locked design. |
| Measured Widget geometry | Not supplied by the current art snapshot/adapter. Static Slot/transform arithmetic can reject known distortion but cannot pass actual image geometry or Slot-family measurements. Those checks stay pending; the new capability does not add a renderer or a geometry tool. |
| Canonical render | The default adapter currently reports unavailable: `CaptureAssetImage` accepts asset identity without controllable resolution, DPI, state or test data. The adapter raises `RendererUnavailable` and writes no canonical evidence. |

A diagnostic collection is useful even when it cannot enter planning. Never replace null Designer mode with the Requirement's intended value, infer hidden state from a screenshot, or attach an expected context to a generic thumbnail. A host renderer integration must actually set and report the isolated viewport, DPI, locale, data/state, font set and background, and verify that previewing did not alter saved production defaults.

The tooling's synthetic tests validate contracts, recovery, comparisons and gates. Installation, a capability probe or a passing synthetic test does not establish that any real UMG art has been applied or visually accepted. Evaluate a separate host renderer against actual current evidence; do not turn the default adapter's limitation into either a permanent host-wide claim or an invented successful capture. Until required actual fields, geometry and canonical rendering are available, report the relevant production stage as incomplete and retain verified intermediate artifacts.

## Contracts and recovery

[art-contract.schema.json](../assets/art-contract.schema.json) is the format authority for request, snapshot, decisions, plan, execution, capture, visual review, verification and stage. SHA-256 binds physical input files; stable state hashes omit acquisition timestamps but retain actual structure and properties. Do not edit immutable evidence in place to satisfy a stale binding. Build a new revision, refresh affected outputs and obtain fresh result acceptance where required.

Material evidence acquisition uses existing official MaterialTools/ObjectTools/AssetTools with discovered input/output schemas. The importable material validator itself never calls Editor tools. `AssetTools.is_dirty` takes `asset_path`; save uses the exact nonempty asset-path list. Preserve actual returned refs and responses, and keep a failed/unknown native call visible. No capability permits fabricated import metadata, material graph history or saved hashes.

Material /2 binds both complete Custom code strings and rejects external graph inputs, native input masks, extra nodes/outputs/defines/include paths and inline `#` preprocessor directives. Its two-Custom topology uses the existing /1 official read-call shapes; it assumes no unverified node creation signature. Graph/file validation is not HLSL analysis and cannot certify shader-global behavior, matching RGB/alpha programs, compile diagnostics, appearance or rendered geometry. Actual code review, host schema discovery, authorized creation, truthful execution/readback and visual verification remain separate production work. /1 evidence is unchanged and is never silently migrated.

For document entry, acceptance 0.1 keeps its direct-user post-result semantics. Explicit [delegated result acceptance 0.2](../../document-nextgame-umg/references/delegated-result-acceptance.md) records the actual primary-coordinator review after all final gates and binds one original grant to one frozen result through its deterministic consumption record. It does not create a capture/geometry capability or authorize the document agent to invent a user response. File hashes do not authenticate conversation authorship or reveal an unrecorded revocation; the coordinator must check the current conversation truthfully.

Schema acceptance does not establish current Editor capability or user authorization. Preserve missing capability errors and expected-versus-actual mismatches as diagnostics. The coordinator may continue independent resource indexing, local review or sample work while production mutation/capture is unavailable, but must not mark the user's requested formal-art outcome complete.
