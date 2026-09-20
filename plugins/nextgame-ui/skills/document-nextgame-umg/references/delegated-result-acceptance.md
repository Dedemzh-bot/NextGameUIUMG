# One-request delegated result acceptance 0.2

This opt-in authorization contract extends the existing `post-build-ui-review` phase. It does not change the meaning of acceptance 0.1, Requirement approval, final Bundle verification, formal art verification, actual Unreal readback, or programmer-document content. Ordinary requests to complete the whole workflow do not opt in.

## Authority and scope

Use acceptance 0.1 for the existing post-result direct-user confirmation. Its closed shape and exact `user` / `direct-user-message` reviewer remain unchanged.

Acceptance 0.2 supports only `authorizationMode: delegated-user-authorization`. Its actual reviewer is `actorType: agent`, `role: primary-coordinator`, `confirmationSource: delegated-user-authorization`. It never claims that the user saw or personally accepted the finished result. The independent grant records the user as authorizer; the result review records the coordinator as reviewer.

All three closed sidecar schemas are registered in `assets/ui-build-acceptance.schema.json` under `$defs/grant`, `$defs/resultReview`, and `$defs/consumption`. Both existing acceptance entry points revalidate these dependencies. Handoff 0.3 and document-content 0.4 keep their existing shapes. There is no new CLI or skip flag.

The primary coordinator must verify the actual current conversation, including later narrowing, cancellation, withdrawal, or a request for personal review, before recording the review and before each document-stage entry. A file hash binds bytes; it does not authenticate a chat author, prove an image was visually inspected, discover an unrecorded revocation, or provide a global transactional lock. The documentation agent must not invent, repair, consume, or broaden authorization.

## Grant: request-scoped-user-authorization/1

The `authorizationBinding` points to an immutable, request-relative grant file and its SHA-256. Its fields bind:

- `grantId`, `requestId`, `status: active`, one `systemAssetRoot`, and exactly all authorized `assetPaths`;
- `capability: final-result-review-and-document-handoff`, `useLimit: 1`, and the truthful direct-user `authorizedBy` declaration;
- `recordedAt`, which is the grant record creation time, **not** an invented user-message timestamp;
- the original `sourcePacket` path/hash, `sourceKey`, exact `/sources/<index>/content` pointer, and SHA-256 of the unchanged UTF-8 message;
- `authorizationFile` path/hash for the preserved original authorization evidence, whose `sourceMessage` must be identical and whose fresh-evidence/no-fabrication/no-old-assets boundaries remain true;
- `statementFormat` and exact original `explicitGrantQuote`, `resultReviewQuote`, and `documentationQuote`.

Version 1 deliberately recognizes only explicit, narrow statement formats. `zh-one-test-automation/1` requires the exact quote `我授权你这一次测试自动进行下去。` plus `制作结果确认` and `程序说明文档` in the same original user message. `en-one-request-result-review/1` requires `I authorize you to review the final result on my behalf and continue to documentation for this request only.`, plus `review the final result` and `documentation`. The source must be an inline `user-text` entry also present in the packet's original user-request text, for the same request ID.

These formats do not infer delegation from keywords, copied historical design answers, a Requirement review gate, or a bare “full workflow” request. Other wording needs a separately reviewed explicit format or the ordinary direct-user 0.1 route. A coordinator must still read the surrounding message truthfully; quoted, hypothetical, contradicted, or revoked statements are not grants.

The separately registered `zh-one-test-delegated-review/1` format recognizes the complete exact sentence `我授权本次测试按插件现有支持的委托审核流程自动推进；委托审核不能替代真实验证或伪造通过。`, together with `制作结果确认` and `程序说明文档` in the same original message. This is an explicit one-test delegation with an express evidence boundary, not a match for a generic continuation such as `执行`. It preserves the existing one-use scope, original-message binding, actual coordinator review and all final gates. Existing formats and evidence remain valid without relabelling or rewriting original user text.

## Actual result review: delegated-result-review/1

Write this record only after the final Requirement, Bundle, formal art, compilation/save, actual readback, state verification, and result presentation are complete. All existing strict source gates run unchanged before acceptance can pass.

`resultReviewBinding` binds a closed review with the same grant ID, acceptance ID, request ID, exact three source identities/hashes, reviewer, and timezone-aware `reviewedAt`. `sourceFiles` names the exact three current files. Acceptance and these final files share one request directory; every dependency path stays inside it after resolution, including symlink and Windows-drive checks.

The review must contain:

- `status: passed`, `userHasReviewedResult: false`, and an empty `unresolvedIssues` array;
- a nonempty, hash-bound presentation record with `presentedAt` after final readback and no later than the actual review;
- a current-conversation authority check at the review time with no revoked or narrowed delegation;
- exactly one `assetReviews` entry for each final asset ID/path pair, actual PNG render files, geometry evidence, state-matrix evidence, and concrete coordinator observations;
- exactly one passed `checkReviews` entry for **every** original final Bundle check, with observations and hash-bound evidence. When a check has an `artifactPath`, the evidence must include that exact artifact, not a replacement report.

Every evidence entry has a relative path, current byte SHA-256, and real `capturedAt` no later than review. A JSON file renamed to PNG is rejected. The coordinator must actually inspect all referenced results; the validator checks dependency identity, coverage and timing, while the existing formal art/readback validators retain their own full semantics. Neither fixture PNGs nor an automated “passed” flag can substitute for production visual inspection. Missing/failed/pending hidden states remain incomplete.

Do not invent exact message IDs, author timestamps, capture times, screenshot contents, or observed results. If a final condition is unmet, retain pending state and do not create an accepted record.

## One consumption, one frozen result

The consumption file is `acceptance-authority/consumptions/<sha256(grantId UTF-8)>.json`, relative to the request root. Producers must create it once using exclusive creation and refuse an existing different record. Validators are read-only and never consume authorization themselves.

The record binds `grantId`, the grant file SHA, request ID, acceptance ID, `useNumber: 1`, actual `consumedAt`, and `resultFingerprint`. Use the existing validator module's `delegated_result_fingerprint(acceptance)` to compute the canonical SHA-256 of **all acceptance fields except `consumptionBinding`**. That field alone is excluded to avoid a circular file-hash dependency; the final acceptance still binds the consumption-file SHA, and Handoff binds the entire final acceptance file SHA.

Prepare the grant and truthful review first, bind their final bytes, assemble the acceptance content, calculate its fingerprint, exclusively create the consumption record, and then add its path/hash as `consumptionBinding`. This describes the required production order; it is not permission to create acceptance before the final result exists.

Repeated document validation may read the same record for the same frozen result. A second acceptance ID, changed review, changed result bindings, replacement evidence, asset mutation/re-save, or changed formal art cannot inherit that consumption. Do not overwrite or move the consumed record to authorize a different result. Obtain a new specific direct-user authorization or ordinary post-result confirmation when a changed result needs acceptance.

The request-local deterministic record and hashes detect stale or mismatched records. They do not claim protection from deliberate copying or coordinated rewriting of every file by a trusted filesystem writer. The primary coordinator retains responsibility for exclusive consumption, actual user authority and truthful review.

## Compatibility and migration

Existing 0.1 acceptance artifacts and their direct-user semantics are unchanged. Do not relabel historical acceptance or rewrite historical Findings/source packets to fit 0.2. Preserve original authorization evidence and add a new versioned grant only for a request with a real explicit delegation.

The shared validator preserves Requirement/Bundle/Readback validation, all asset pairing, final checks and art gates. The handoff-binding entry point also reloads and validates the current final sources for 0.2, so a pre-generated Handoff cannot bypass dependency changes. The existing `--build-acceptance` path is sufficient throughout the document chain.
