#!/usr/bin/env python3
"""Validate versioned post-build acceptance without bypassing final source gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
from typing import Any

from _document_contract_common import (
    BUILD_ACCEPTANCE_SCHEMA,
    READBACK_SCHEMA,
    canonical_sha256,
    issue,
    load_json,
    parse_aware_iso8601,
    result,
    resolve_request_path,
    sha256_file,
    validate_schema_instance,
)
from validate_unreal_widget_readback import validate_unreal_widget_readback


def _expected_requirement_binding(requirement: dict[str, Any], requirement_path: Path) -> dict[str, Any]:
    review = requirement.get("reviewGate") if isinstance(requirement.get("reviewGate"), dict) else {}
    return {
        "requestId": requirement.get("requestId"),
        "revision": requirement.get("revision"),
        "approvedContentSha256": review.get("approvedContentSha256"),
        "sha256": sha256_file(requirement_path),
    }


def _expected_bundle_binding(bundle: dict[str, Any], bundle_path: Path) -> dict[str, Any]:
    return {"bundleId": bundle.get("bundleId"), "sha256": sha256_file(bundle_path)}


def _expected_readback_binding(readback: dict[str, Any], readback_path: Path) -> dict[str, Any]:
    return {"readbackId": readback.get("readbackId"), "sha256": sha256_file(readback_path)}


def _asset_pairs_from_bundle(bundle: dict[str, Any]) -> list[tuple[Any, Any]]:
    return [
        (asset.get("id"), asset.get("assetPath"))
        for asset in bundle.get("assets", [])
        if isinstance(asset, dict)
    ]


DIRECT_REVIEWER = {"actorType": "user", "confirmationSource": "direct-user-message"}
DELEGATED_REVIEWER = {
    "actorType": "agent", "role": "primary-coordinator",
    "confirmationSource": "delegated-user-authorization",
}
GRANT_STATEMENTS = {
    "zh-one-test-automation/1": (
        "我授权你这一次测试自动进行下去。", "制作结果确认", "程序说明文档",
    ),
    "zh-one-test-delegated-review/1": (
        "我授权本次测试按插件现有支持的委托审核流程自动推进；委托审核不能替代真实验证或伪造通过。",
        "制作结果确认", "程序说明文档",
    ),
    "en-one-request-result-review/1": (
        "I authorize you to review the final result on my behalf and continue to documentation for this request only.",
        "review the final result", "documentation",
    ),
}


def delegated_result_fingerprint(acceptance: dict[str, Any]) -> str:
    """Bind all acceptance content except its forward consumption-file reference.

    The handoff still binds the final acceptance bytes. Excluding this one reference
    avoids a circular acceptance-hash/consumption-hash dependency, not a result bypass.
    """
    return canonical_sha256({key: value for key, value in acceptance.items() if key != "consumptionBinding"})


def delegated_consumption_path(grant_id: str) -> str:
    token = hashlib.sha256(grant_id.encode("utf-8")).hexdigest()
    return f"acceptance-authority/consumptions/{token}.json"


def _linked_file(binding: Any, root_file: Path, at: str, errors: list[dict[str, str]]) -> Path | None:
    if not isinstance(binding, dict):
        errors.append(issue("delegation.binding", at, "Expected a closed relative file binding."))
        return None
    try:
        raw = binding.get("path")
        if not isinstance(raw, str) or PureWindowsPath(raw).drive:
            raise ValueError("Evidence paths must be request-relative, including on Windows.")
        path = resolve_request_path(root_file, raw)
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError("Evidence must be an existing nonempty file.")
        if sha256_file(path) != binding.get("sha256"):
            raise ValueError("Evidence SHA-256 differs from current file bytes.")
        return path
    except (OSError, ValueError) as error:
        errors.append(issue("delegation.file", at, str(error)))
        return None


def _linked_json(binding: Any, root_file: Path, at: str, errors: list[dict[str, str]]) -> tuple[Any, Path | None]:
    path = _linked_file(binding, root_file, at, errors)
    if path is None:
        return None, None
    try:
        return load_json(path), path
    except (OSError, ValueError) as error:
        errors.append(issue("delegation.json", at, str(error)))
        return None, path


def _sidecar(binding: Any, name: str, root_file: Path, errors: list[dict[str, str]]) -> Any:
    value, _ = _linked_json(binding, root_file, f"$.{name}", errors)
    if value is None:
        return None
    authority = load_json(BUILD_ACCEPTANCE_SCHEMA)
    problems = validate_schema_instance(value, {"$ref": f"#/$defs/{name}", "$defs": authority["$defs"]})
    errors.extend(problems)
    return value if not problems else None


def _review_evidence(binding: Any, acceptance_path: Path, reviewed_at: Any,
                     errors: list[dict[str, str]], *, image: bool = False) -> Path | None:
    path = _linked_file(binding, acceptance_path, "$.resultReview.evidence", errors)
    captured = parse_aware_iso8601(binding.get("capturedAt"), "$.resultReview.evidence.capturedAt", errors)
    if captured is not None and reviewed_at is not None and captured > reviewed_at:
        errors.append(issue("delegation.evidence_after_review", "$.resultReview.evidence", "Evidence must exist before its actual review."))
    if path is not None and image:
        try:
            from PIL import Image
            with Image.open(path) as picture:
                if picture.format != "PNG" or min(picture.size) <= 0:
                    raise ValueError("Render evidence must be an actual nonempty PNG.")
                picture.verify()
        except (ImportError, OSError, ValueError, SyntaxError) as error:
            errors.append(issue("delegation.render_image", "$.resultReview.assetReviews", str(error)))
    return path


def _validate_delegation(acceptance: dict[str, Any], acceptance_path: Path,
                         errors: list[dict[str, str]], current_sources: dict[str, Any] | None) -> None:
    # Always use the installed authoritative shape, including when the CLI receives
    # an alternate --schema. The new authorization capability is not a skip flag.
    shape_errors = validate_schema_instance(acceptance, load_json(BUILD_ACCEPTANCE_SCHEMA))
    errors.extend(shape_errors)
    if shape_errors:
        return
    grant = _sidecar(acceptance["authorizationBinding"], "grant", acceptance_path, errors)
    review = _sidecar(acceptance["resultReviewBinding"], "resultReview", acceptance_path, errors)
    consumption = _sidecar(acceptance["consumptionBinding"], "consumption", acceptance_path, errors)
    if any(value is None for value in (grant, review, consumption)):
        return
    request_id = acceptance["requirementBinding"]["requestId"]
    grant_id = grant["grantId"]
    expected_pairs = list(zip(acceptance["reviewedAssetIds"], acceptance["reviewedAssetPaths"]))
    if grant["status"] != "active" or grant["requestId"] != request_id:
        errors.append(issue("delegation.grant_scope", "$.grant", "Grant must be active and scoped to this original request."))
    if set(grant["assetPaths"]) != {path for _, path in expected_pairs} or any(
        not path.startswith(grant["systemAssetRoot"] + "/") for _, path in expected_pairs
    ):
        errors.append(issue("delegation.asset_scope", "$.grant.assetPaths", "Grant must exactly cover this result within its one system asset root."))

    packet, _ = _linked_json(grant["sourcePacket"], acceptance_path, "$.grant.sourcePacket", errors)
    original, _ = _linked_json(grant["authorizationFile"], acceptance_path, "$.grant.authorizationFile", errors)
    message = None
    if isinstance(packet, dict):
        index = int(grant["messagePointer"].split("/")[2])
        sources = packet.get("sources")
        source = sources[index] if isinstance(sources, list) and index < len(sources) else None
        if (packet.get("requestId") == request_id and isinstance(source, dict)
                and source.get("sourceKey") == grant["sourceKey"]
                and source.get("kind") == "user-text" and source.get("locatorKind") == "inline"):
            message = source.get("content")
        original_text = packet.get("userRequest", {}).get("originalText", []) if isinstance(packet.get("userRequest"), dict) else []
        if not isinstance(message, str) or message not in original_text:
            message = None
    if (not isinstance(message, str)
            or hashlib.sha256(message.encode("utf-8")).hexdigest() != grant["messageSha256"]):
        errors.append(issue("delegation.message", "$.grant.sourcePacket", "Grant must bind the exact original direct-user source and UTF-8 message hash."))
    else:
        statements = GRANT_STATEMENTS[grant["statementFormat"]]
        supplied = (grant["explicitGrantQuote"], grant["resultReviewQuote"], grant["documentationQuote"])
        if supplied != statements or any(quote not in message for quote in statements):
            errors.append(issue("delegation.explicit_grant", "$.grant.explicitGrantQuote", "Ordinary full-workflow requests are not delegation; the declared statement format and exact three quotes must exist in the same original message."))
    if (not isinstance(original, dict) or original.get("kind") != "request-scoped-user-authorization"
            or original.get("sourceMessage") != message
            or original.get("freshEvidenceRequired") is not True
            or original.get("mayFabricatePostResultUserMessage") is not False
            or original.get("mayReuseOldAssetsOrCachedPlans") is not False):
        errors.append(issue("delegation.original_authorization", "$.grant.authorizationFile", "Original authorization file must preserve the same message and fresh-evidence/no-fabrication boundaries."))

    loaded: dict[str, Any] = {}
    for name, binding_key in (("requirement", "requirementBinding"), ("bundle", "bundleBinding"), ("readback", "readbackBinding")):
        document, path = _linked_json(review["sourceFiles"][name], acceptance_path, f"$.resultReview.sourceFiles.{name}", errors)
        if review[binding_key] != acceptance[binding_key] or review["sourceFiles"][name]["sha256"] != acceptance[binding_key]["sha256"]:
            errors.append(issue("delegation.final_binding", f"$.resultReview.{binding_key}", "Review must bind the exact final acceptance sources."))
        if not isinstance(document, dict) or path is None:
            return
        loaded[name], loaded[name + "_path"] = document, path
        if path.parent != acceptance_path.resolve().parent:
            errors.append(issue("delegation.source_root", f"$.resultReview.sourceFiles.{name}", "The acceptance and final three sources must share their request root."))
        if current_sources is not None and (document != current_sources[name] or path != current_sources[name + "_path"].resolve()):
            errors.append(issue("delegation.current_source", f"$.resultReview.sourceFiles.{name}", "Review source differs from the actual current validator input."))
    if current_sources is None:
        # The handoff-only entry point must re-enter the SAME strict source gate.
        report = validate_unreal_widget_readback(
            loaded["readback"], load_json(READBACK_SCHEMA), readback_path=loaded["readback_path"],
            requirement=loaded["requirement"], requirement_path=loaded["requirement_path"],
            bundle=loaded["bundle"], bundle_path=loaded["bundle_path"],
        )
        if not report["valid"]:
            errors.append(issue("sources.invalid", "$", "Delegated handoff requires valid current final sources, including formal art."))
            errors.extend(report["errors"])
    real_bindings = (
        _expected_requirement_binding(loaded["requirement"], loaded["requirement_path"]),
        _expected_bundle_binding(loaded["bundle"], loaded["bundle_path"]),
        _expected_readback_binding(loaded["readback"], loaded["readback_path"]),
    )
    if tuple(acceptance[key] for key in ("requirementBinding", "bundleBinding", "readbackBinding")) != real_bindings:
        errors.append(issue("delegation.final_identity", "$.resultReview.sourceFiles", "Final file identities must match their acceptance bindings."))
    actual_pairs = _asset_pairs_from_bundle(loaded["bundle"])
    review_pairs = [(row["assetId"], row["assetPath"]) for row in review["assetReviews"]]
    if (len(expected_pairs) != len(actual_pairs) or set(expected_pairs) != set(actual_pairs)
            or len(review_pairs) != len(actual_pairs) or set(review_pairs) != set(actual_pairs)):
        errors.append(issue("delegation.review_coverage", "$.resultReview.assetReviews", "Coordinator review must exactly cover every final asset pair once."))
    if any(review[key] != value for key, value in (
        ("grantId", grant_id), ("acceptanceId", acceptance["acceptanceId"]), ("requestId", request_id),
        ("reviewer", DELEGATED_REVIEWER), ("reviewedAt", acceptance["reviewedAt"]),
    )):
        errors.append(issue("delegation.review_identity", "$.resultReview", "Review identity, actor and actual time must match this acceptance and grant."))

    reviewed_at = parse_aware_iso8601(review["reviewedAt"], "$.resultReview.reviewedAt", errors)
    recorded_at = parse_aware_iso8601(grant["recordedAt"], "$.grant.recordedAt", errors)
    captured_at = parse_aware_iso8601(loaded["readback"].get("capturedAt"), "$.readback.capturedAt", errors)
    completed_at = parse_aware_iso8601(loaded["bundle"].get("execution", {}).get("completedAt"), "$.bundle.execution.completedAt", errors)
    presented_at = parse_aware_iso8601(review["presentation"]["presentedAt"], "$.resultReview.presentation.presentedAt", errors)
    checked_at = parse_aware_iso8601(review["conversationAuthorityCheck"]["checkedAt"], "$.resultReview.conversationAuthorityCheck.checkedAt", errors)
    consumed_at = parse_aware_iso8601(consumption["consumedAt"], "$.consumption.consumedAt", errors)
    now = datetime.now(timezone.utc)
    if reviewed_at is not None and (reviewed_at > now or any(
        stamp is not None and stamp > reviewed_at for stamp in (recorded_at, captured_at, completed_at, presented_at)
    ) or checked_at != reviewed_at):
        errors.append(issue("delegation.review_time", "$.resultReview.reviewedAt", "Actual review and conversation-authority check must follow the grant, final sources and presentation, and cannot be future dated."))
    if presented_at is not None and captured_at is not None and presented_at < captured_at:
        errors.append(issue("delegation.presentation_time", "$.resultReview.presentation", "Present the bound final result after its actual readback."))
    if consumed_at is not None and (consumed_at > now or (reviewed_at is not None and consumed_at < reviewed_at)):
        errors.append(issue("delegation.consumption_time", "$.consumption.consumedAt", "Consumption must follow actual final review and cannot be future dated."))
    _linked_file(review["presentation"], acceptance_path, "$.resultReview.presentation", errors)
    for row in review["assetReviews"]:
        for binding in row["renderImages"]:
            _review_evidence(binding, acceptance_path, reviewed_at, errors, image=True)
        for key in ("geometryEvidence", "stateMatrixEvidence"):
            _review_evidence(row[key], acceptance_path, reviewed_at, errors)
    checks = loaded["bundle"].get("verification", {}).get("checks", [])
    check_ids = [check.get("id") for check in checks]
    reviewed_ids = [row["checkId"] for row in review["checkReviews"]]
    if len(reviewed_ids) != len(check_ids) or set(reviewed_ids) != set(check_ids):
        errors.append(issue("delegation.check_coverage", "$.resultReview.checkReviews", "Coordinator must review all original final Bundle checks exactly once, without omissions or waivers."))
    checks_by_id = {check.get("id"): check for check in checks}
    for row in review["checkReviews"]:
        paths = {_review_evidence(binding, acceptance_path, reviewed_at, errors) for binding in row["evidence"]}
        check = checks_by_id.get(row["checkId"], {})
        if check.get("artifactPath"):
            try:
                artifact = resolve_request_path(loaded["bundle_path"], check["artifactPath"])
                if artifact not in paths:
                    errors.append(issue("delegation.check_artifact", "$.resultReview.checkReviews", "Review evidence must include the original check artifact, not a substitute."))
            except ValueError as error:
                errors.append(issue("delegation.check_artifact", "$.resultReview.checkReviews", str(error)))

    expected_consumption = {
        "kind": "request-authorization-consumption", "version": 1, "grantId": grant_id,
        "grantSha256": acceptance["authorizationBinding"]["sha256"], "requestId": request_id,
        "acceptanceId": acceptance["acceptanceId"], "resultFingerprint": delegated_result_fingerprint(acceptance),
        "consumedAt": consumption["consumedAt"], "useNumber": 1,
    }
    if (consumption != expected_consumption
            or acceptance["consumptionBinding"]["path"] != delegated_consumption_path(grant_id)):
        errors.append(issue("delegation.consumption", "$.consumptionBinding", "One grant has one deterministic request-local consumption record bound to one frozen result. Revalidation is not a second grant."))


def _validate_review_authority(acceptance: dict[str, Any], acceptance_path: Path,
                               errors: list[dict[str, str]], current_sources: dict[str, Any] | None = None) -> None:
    if acceptance.get("version") == "0.1":
        if acceptance.get("reviewer") != DIRECT_REVIEWER:
            errors.append(issue("acceptance.not_direct_user", "$.reviewer", "Acceptance 0.1 requires a direct user message after final build review."))
    elif acceptance.get("version") == "0.2":
        _validate_delegation(acceptance, acceptance_path, errors, current_sources)
    else:
        errors.append(issue("acceptance.version", "$.version", "Unsupported acceptance authorization version."))


def validate_build_acceptance(
    acceptance: Any,
    schema: dict[str, Any],
    *,
    acceptance_path: Path,
    requirement: Any,
    requirement_path: Path,
    bundle: Any,
    bundle_path: Path,
    readback: Any,
    readback_path: Path,
) -> dict[str, Any]:
    """Validate acceptance against the exact current files and their complete asset set.

    The repository can verify the declared actor/source fields, timestamps, identities,
    hashes, and coverage. It cannot cryptographically authenticate the originating chat
    message. Version 0.1 requires post-result direct user review; 0.2 requires a separately
    evidenced one-request grant and truthful coordinator review after final readback.
    """

    errors = validate_schema_instance(acceptance, schema)
    warnings: list[dict[str, str]] = []

    readback_report = validate_unreal_widget_readback(
        readback,
        load_json(READBACK_SCHEMA),
        readback_path=readback_path,
        requirement=requirement,
        requirement_path=requirement_path,
        bundle=bundle,
        bundle_path=bundle_path,
    )
    if not readback_report["valid"]:
        errors.append(issue("sources.invalid", "$", "Build acceptance requires a valid current Requirement, Bundle, and Unreal readback."))
        errors.extend(readback_report["errors"])

    if not all(isinstance(value, dict) for value in (acceptance, requirement, bundle, readback)):
        return result(errors, warnings)

    if acceptance.get("status") != "accepted":
        errors.append(issue("acceptance.not_accepted", "$.status", "Documentation requires explicit post-build status 'accepted'."))
    _validate_review_authority(acceptance, acceptance_path, errors, {
        "requirement": requirement, "requirement_path": requirement_path,
        "bundle": bundle, "bundle_path": bundle_path,
        "readback": readback, "readback_path": readback_path,
    })

    reviewed_at = parse_aware_iso8601(acceptance.get("reviewedAt"), "$.reviewedAt", errors)
    captured_at = parse_aware_iso8601(readback.get("capturedAt"), "$.readback.capturedAt", errors)
    if reviewed_at is not None and captured_at is not None and reviewed_at < captured_at:
        errors.append(issue("time.acceptance_before_readback", "$.reviewedAt", "Build acceptance must not precede the bound Unreal readback."))

    expected_requirement = _expected_requirement_binding(requirement, requirement_path)
    if acceptance.get("requirementBinding") != expected_requirement:
        errors.append(issue("binding.requirement", "$.requirementBinding", "Acceptance Requirement binding does not match the actual current Requirement file."))
    expected_bundle = _expected_bundle_binding(bundle, bundle_path)
    if acceptance.get("bundleBinding") != expected_bundle:
        errors.append(issue("binding.bundle", "$.bundleBinding", "Acceptance Bundle binding does not match the actual current Bundle file."))
    expected_readback = _expected_readback_binding(readback, readback_path)
    if acceptance.get("readbackBinding") != expected_readback:
        errors.append(issue("binding.readback", "$.readbackBinding", "Acceptance readback binding does not match the actual current Unreal readback file."))

    expected_pairs = _asset_pairs_from_bundle(bundle)
    reviewed_ids = acceptance.get("reviewedAssetIds") if isinstance(acceptance.get("reviewedAssetIds"), list) else []
    reviewed_paths = acceptance.get("reviewedAssetPaths") if isinstance(acceptance.get("reviewedAssetPaths"), list) else []
    reviewed_pairs = list(zip(reviewed_ids, reviewed_paths)) if len(reviewed_ids) == len(reviewed_paths) else []
    if len(reviewed_ids) != len(reviewed_paths) or set(reviewed_pairs) != set(expected_pairs) or len(reviewed_pairs) != len(expected_pairs):
        errors.append(issue("coverage.assets", "$.reviewedAssetIds", "Reviewed asset IDs and paths must pairwise and exactly cover every Bundle asset, with no extras."))

    return result(errors, warnings)


def validate_acceptance_handoff_binding(
    acceptance: Any,
    acceptance_path: Path,
    handoff: Any,
) -> dict[str, Any]:
    """Prevent document-content generation from bypassing the acceptance artifact."""

    errors = validate_schema_instance(acceptance, load_json(BUILD_ACCEPTANCE_SCHEMA))
    if not isinstance(acceptance, dict) or not isinstance(handoff, dict):
        return result(errors)
    if acceptance.get("status") != "accepted":
        errors.append(issue("acceptance.not_accepted", "$.status", "Document content requires accepted post-build user review."))
    _validate_review_authority(acceptance, acceptance_path, errors)

    sources = handoff.get("sources") if isinstance(handoff.get("sources"), dict) else {}
    expected_acceptance_source = {
        "acceptanceId": acceptance.get("acceptanceId"),
        "sha256": sha256_file(acceptance_path),
    }
    if sources.get("buildAcceptance") != expected_acceptance_source:
        errors.append(issue("binding.acceptance", "$.sources.buildAcceptance", "Handoff is not bound to this exact build-acceptance file."))
    if acceptance.get("requirementBinding") != sources.get("requirement"):
        errors.append(issue("binding.requirement", "$.requirementBinding", "Acceptance Requirement binding differs from the handoff source."))
    if acceptance.get("bundleBinding") != sources.get("bundle"):
        errors.append(issue("binding.bundle", "$.bundleBinding", "Acceptance Bundle binding differs from the handoff source."))
    if acceptance.get("readbackBinding") != sources.get("unrealReadback"):
        errors.append(issue("binding.readback", "$.readbackBinding", "Acceptance readback binding differs from the handoff source."))

    asset_pairs = [
        (asset.get("assetId"), asset.get("assetPath"))
        for asset in handoff.get("assets", [])
        if isinstance(asset, dict)
    ]
    ids = acceptance.get("reviewedAssetIds") if isinstance(acceptance.get("reviewedAssetIds"), list) else []
    paths = acceptance.get("reviewedAssetPaths") if isinstance(acceptance.get("reviewedAssetPaths"), list) else []
    reviewed_pairs = list(zip(ids, paths)) if len(ids) == len(paths) else []
    if len(ids) != len(paths) or set(reviewed_pairs) != set(asset_pairs) or len(reviewed_pairs) != len(asset_pairs):
        errors.append(issue("coverage.assets", "$.reviewedAssetIds", "Acceptance must exactly cover the handoff asset identities and paths."))

    reviewed_at = parse_aware_iso8601(acceptance.get("reviewedAt"), "$.reviewedAt", errors)
    generated_at = parse_aware_iso8601(handoff.get("generatedAt"), "$.handoff.generatedAt", errors)
    if reviewed_at is not None and generated_at is not None and generated_at < reviewed_at:
        errors.append(issue("time.handoff_before_acceptance", "$.handoff.generatedAt", "Program handoff must be generated after post-build acceptance."))
    return result(errors)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("acceptance", type=Path)
    parser.add_argument("--requirement", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--readback", type=Path, required=True)
    parser.add_argument("--schema", type=Path, default=BUILD_ACCEPTANCE_SCHEMA)
    args = parser.parse_args()
    try:
        output = validate_build_acceptance(
            load_json(args.acceptance),
            load_json(args.schema),
            acceptance_path=args.acceptance.resolve(),
            requirement=load_json(args.requirement),
            requirement_path=args.requirement.resolve(),
            bundle=load_json(args.bundle),
            bundle_path=args.bundle.resolve(),
            readback=load_json(args.readback),
            readback_path=args.readback.resolve(),
        )
    except (OSError, json.JSONDecodeError, ValueError) as error:
        output = result([issue("io.read", "$", str(error))])
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if output["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
