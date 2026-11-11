# Toolchain retest corrections · 2026-11-10

Scope: maintenance of the existing local UI toolchain, following the user's
request to repair the recorded retest findings. This does not change design
parameters, historical contracts, result-acceptance rules or game code.

| Finding | Owning correction | Compatibility |
| --- | --- | --- |
| Fallback tests hardcoded an obsolete rule count | Compare current complete indexed IDs, multiplicity, count and cards; retain ordering and full-document assertions | Runtime routing and index unchanged |
| Art resource validator missed local transitive imports | Load exact selected-root dependencies in private module identities; hash loaded bytes and restore invocation state | Existing catalog/1 three-root provenance remains readable; no old artifact rewritten |
| Native PNG export contained data after IEND | Optional native RGBA8 stream extraction to a separate new output, preserving native stream bytes and the source export | No image re-encoding, renderer claim or capture schema change |
| Fresh-profile MCP did not start from a port flag alone | Document the official explicit startup flag plus requested port and actual instance verification | Persistent Editor settings unchanged |

The Design standalone documentation correction belongs to that separate
package. Its checker boundary and consumer lock remain unchanged.

Publish as a new local plugin revision after review and the relevant existing
regressions. Keep the prior revision recoverable. Verify the authoritative
source and CLI-installed cache file trees. Actual command receipts and test
results stay in the project's private Saved task output, not this package.

No rule IDs, schemas, geometric parameters or library production flags change.
The old consumer lock's exact release identity and the whole public library's
production readiness remain independently pending until their real evidence
exists. Successful tool regressions do not clear those production states.
