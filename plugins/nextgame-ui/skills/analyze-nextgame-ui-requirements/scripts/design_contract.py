#!/usr/bin/env python3
"""Deterministic design intake, with no Unreal connection or asset mutation.

Design contracts contain already authored Requirement semantics. References are
provenance, not an arbitrary recipe interpreter. Compile copies values exactly;
all normal Requirement semantics continue through validate_requirement_spec.
Accept records an explicitly authorized design review in a new scoped receipt;
it never grants new production authorization or post-build acceptance.
"""
from __future__ import annotations

import argparse
import copy
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from _contract_common import (ASSETS_ROOT, canonical_sha256, compute_approved_content_sha256,
    issue, load_json, result, sha256_file, validate_schema_instance)

CONTRACT_SCHEMA = ASSETS_ROOT / "design-contract.schema.json"
COMPATIBILITY_SCHEMA = ASSETS_ROOT / "design-compatibility-review.schema.json"
REVIEW_SCHEMA = ASSETS_ROOT / "design-review-receipt.schema.json"
REQUIREMENT_SCHEMA = ASSETS_ROOT / "ui-requirement-spec.schema.json"
CONTENT_EXCLUDED = {"version", "normalization", "reviewGate"}
SEMANTIC_POLICIES = (
    "geometryEvidenceRequired", "listPriorityRequired", "assetBoundaryRequired",
    "standardSystemBoundaryRequired", "stateControlInputRequired", "staticVisualCoverageRequired",
    "imageCompositionRequired", "explicitPanelSlotsRequired", "explicitImageOwnerIntentRequired",
    "designSizeModeRequired",
)


class DesignContractError(ValueError):
    pass


def content_of(requirement: dict) -> dict:
    return {key: copy.deepcopy(value) for key, value in requirement.items() if key not in CONTENT_EXCLUDED}


def _equal(left: Any, right: Any) -> bool:
    return canonical_sha256(left) == canonical_sha256(right)


def pointer_value(content: Any, pointer: str) -> Any:
    if pointer == "":
        return content
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise DesignContractError("Content pointer must be an RFC 6901 JSON Pointer.")
    value = content
    for raw in pointer[1:].split("/"):
        # Reject malformed encodings, negative/alternate array indices and '-' append.
        if "~" in raw.replace("~1", "").replace("~0", ""):
            raise DesignContractError("Invalid JSON Pointer escape.")
        key = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(value, list):
            if not key.isdigit() or (key != "0" and key.startswith("0")):
                raise DesignContractError("Invalid JSON Pointer array index.")
            value = value[int(key)]
        elif isinstance(value, dict):
            value = value[key]
        else:
            raise DesignContractError("JSON Pointer traverses a scalar.")
    return value


def _leaf_pointers(value: Any, path: str = "") -> set[str]:
    if isinstance(value, dict) and value:
        return set().union(*(_leaf_pointers(v, path + "/" + k.replace("~", "~0").replace("/", "~1")) for k, v in value.items()))
    if isinstance(value, list) and value:
        return set().union(*(_leaf_pointers(v, path + "/" + str(i)) for i, v in enumerate(value)))
    return {path}


def _absolute_file(raw: str) -> Path:
    path = Path(raw)
    if not path.is_absolute() or ".." in path.parts:
        raise DesignContractError("Source path must be absolute without parent traversal.")
    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise DesignContractError("Source path must name an existing file.")
    return resolved


def _source_bindings(contract: dict, errors: list) -> dict[str, tuple[dict, Path]]:
    bindings = {}
    for index, source in enumerate(contract.get("sourceBindings", [])):
        if not isinstance(source, dict):
            continue
        key = source.get("key")
        where = f"$.sourceBindings[{index}]"
        if key in bindings:
            errors.append(issue("design.source_duplicate", where, "Source keys must be unique."))
        try:
            path = _absolute_file(source["path"])
            if sha256_file(path) != source.get("sha256"):
                raise DesignContractError("Source file changed; create and review a new contract revision.")
            if "version" in source:
                document = load_json(path)
                actual = pointer_value(document, source.get("versionPointer", "/version"))
                if actual != source["version"]:
                    raise DesignContractError("Declared source version differs from its actual JSON value.")
            bindings[key] = (source, path)
        except (OSError, ValueError, TypeError, KeyError, IndexError) as error:
            errors.append(issue("design.source_binding", where, str(error)))
    return bindings


def _pending_review(content: dict) -> dict:
    return {"required": True, "status": "pending",
        "acceptedClaimIds": [c["id"] for c in content.get("claims", []) if c.get("status") == "accepted"],
        "rejectedClaimIds": [c["id"] for c in content.get("claims", []) if c.get("status") == "rejected"]}


def compatibility_authority_sha256(contract: dict) -> str:
    return canonical_sha256([source for source in contract["sourceBindings"]
        if source["role"] not in {"implementation-evidence", "review-evidence"}])


def bound_request_packet(spec: dict) -> tuple[dict, Path]:
    normalization = spec["normalization"]
    path = (Path(normalization["contractRoot"]) / normalization["contractRef"]).resolve(strict=True)
    contract = load_json(path)
    entries = [s for s in contract["sourceBindings"] if s["role"] == "request-packet"]
    packet_path = _absolute_file(entries[0]["path"])
    return load_json(packet_path), packet_path


def _check_compatibility_report(contract: dict, entry: tuple[dict, Path], errors: list) -> bool:
    """Validate an explicit design review; this is never live Editor proof."""
    source, path = entry
    if source["role"] != "implementation-evidence":
        errors.append(issue("design.compatibility_role", "$.compatibility", "Compatibility reports must have role implementation-evidence."))
        return False
    try:
        report = load_json(path)
        checks = validate_schema_instance(report, load_json(COMPATIBILITY_SCHEMA))
        errors.extend(checks)
        if checks:
            return False
        if report["contentSha256"] != canonical_sha256(contract["content"]) or report["moduleBindingsSha256"] != canonical_sha256(contract["moduleRefs"]) or report["authorityBindingsSha256"] != compatibility_authority_sha256(contract):
            raise DesignContractError("Compatibility review is stale for the exact content, modules or authorities.")
        expected = {"contract", *(module["moduleId"] for module in contract["moduleRefs"])}
        targets = [check["target"] for check in report["checks"]]
        if len(targets) != len(set(targets)) or set(targets) != expected:
            raise DesignContractError("Compatibility review must cover the contract and every declared module exactly once.")
        review = report["review"]
        when = datetime.fromisoformat(review["reviewedAt"].replace("Z", "+00:00"))
        message = _absolute_file(review["messagePath"])
        if when.tzinfo is None or sha256_file(message) != review["messageSha256"] or not message.read_text(encoding="utf-8").strip():
            raise DesignContractError("Compatibility review requires a real unchanged review authorization message and timezone-aware timestamp.")
        return all(check["status"] == "passed" for check in report["checks"])
    except (OSError, ValueError, TypeError, KeyError, IndexError) as error:
        errors.append(issue("design.compatibility_report", "$.compatibility", str(error)))
        return False


def _normalize(contract: dict, contract_path: Path) -> dict:
    return {"kind": "design-contract", "version": "1", "contractRoot": str(contract_path.parent.resolve()),
        "contractRef": contract_path.name, "contractFileSha256": sha256_file(contract_path),
        "contractCanonicalSha256": canonical_sha256(contract), "contentSha256": canonical_sha256(contract["content"])}


def _review_scope(spec: dict) -> dict:
    normalization = spec["normalization"]
    return {"requestId": spec["requestId"], "revision": spec["revision"],
        "contractFileSha256": normalization["contractFileSha256"],
        "contractCanonicalSha256": normalization["contractCanonicalSha256"],
        "contentSha256": canonical_sha256(content_of(spec))}


def validate_design_contract(contract: Any, *, contract_path: Path | None = None,
                             check_semantics: bool = True) -> dict:
    errors = validate_schema_instance(contract, load_json(CONTRACT_SCHEMA))
    warnings = []
    if errors or not isinstance(contract, dict):
        return result(errors, warnings)
    content = contract["content"]
    bindings = _source_bindings(contract, errors)
    policy = content.get("analysisPolicy", {})
    for name in SEMANTIC_POLICIES:
        if policy.get(name) is not True:
            errors.append(issue("design.semantic_policy", "$.content.analysisPolicy." + name,
                "New design intake requires every current shared semantic policy; upgrade the design explicitly."))
    if policy.get("noHistoryRolePacketsRequired") is not False:
        errors.append(issue("design.analysis_provenance", "$.content.analysisPolicy.noHistoryRolePacketsRequired",
            "Structured design uses its own provenance, not historical analysis role packets."))
    coverage: dict[str, int] = {p: 0 for p in _leaf_pointers(content)}
    leaf_sources: dict[str, set[str]] = {}
    ready = True
    seen = set()
    for index, decision in enumerate(contract["decisions"]):
        where = f"$.decisions[{index}]"
        pointer = decision["pointer"]
        if pointer in seen:
            errors.append(issue("design.decision_duplicate", where, "A content pointer may have only one decision."))
        seen.add(pointer)
        try:
            value = pointer_value(content, pointer)
            if canonical_sha256(value) != decision["valueSha256"]:
                raise DesignContractError("Decision digest does not match the declared content value.")
            for leaf in _leaf_pointers(value, pointer):
                coverage[leaf] = coverage.get(leaf, 0) + 1
                leaf_sources[leaf] = set(decision["sourceKeys"])
        except (ValueError, TypeError, KeyError, IndexError) as error:
            errors.append(issue("design.decision_binding", where, str(error)))
        if decision["status"] != "locked":
            ready = False
        if any(key not in bindings for key in decision["sourceKeys"]):
            errors.append(issue("design.decision_source", where, "Every adopted decision must cite actual hash-verified source bindings."))
    if any(count != 1 for count in coverage.values()):
        errors.append(issue("design.decision_coverage", "$.decisions", "Every content leaf must have exactly one declared decision; no missing or overlapping scopes."))
    gap_ids = set()
    for index, gap in enumerate(contract["gapDecisions"]):
        if gap["id"] in gap_ids:
            errors.append(issue("design.gap_duplicate", "$.gapDecisions", "Gap IDs must be unique."))
        gap_ids.add(gap["id"])
        try:
            pointer_value(content, gap["pointer"])
        except (ValueError, TypeError, KeyError, IndexError) as error:
            errors.append(issue("design.gap_pointer", f"$.gapDecisions[{index}]", str(error)))
        if gap["status"] == "open":
            ready = False
        elif not gap.get("resolution"):
            errors.append(issue("design.gap_resolution", f"$.gapDecisions[{index}]", "Resolved gaps require their exact resolution."))
    module_ids = set()
    for index, module in enumerate(contract["moduleRefs"]):
        where = f"$.moduleRefs[{index}]"
        if module["moduleId"] in module_ids:
            errors.append(issue("design.module_duplicate", where, "Module IDs must be unique."))
        module_ids.add(module["moduleId"])
        for role in ("spec", "recipe"):
            entry = bindings.get(module[role + "SourceKey"])
            if entry is None:
                errors.append(issue("design.module_source", where, "Module must bind the exact source document."))
                continue
            try:
                document = load_json(entry[1])
                name, version = module[role + "Ref"].rsplit("@", 1)
                if entry[0].get("version") != version or document.get("version") != version:
                    raise DesignContractError("Module @version must match both the source binding and actual document version.")
                if role == "spec":
                    if entry[0]["role"] != "module-spec" or document.get("id") != name or document.get("schema_version") != "2.0.0" or not isinstance(document.get("geometry"), dict) or not isinstance(document.get("layout"), dict) or not {"space", "sizing", "anchor", "alignment", "offset", "size"}.issubset(document["geometry"]) or not {"kind", "padding", "gap", "horizontal_align", "vertical_align", "growth", "overflow"}.issubset(document["layout"]):
                        raise DesignContractError("Spec must bind the actual supported v2 module document with geometry/layout, not a catalog envelope.")
                    if content["target"]["mode"] == "production":
                        approval = document.get("approval")
                        if document.get("status") != "Approved" or not isinstance(approval, dict) or not approval.get("by") or not approval.get("at"):
                            ready = False
                            warnings.append(issue("design.draft_production", where, "Draft/unapproved module parameters cannot become approved production standards through a design lock."))
                else:
                    if entry[0]["role"] != "recipe" or document.get("format") != "nextgame-design-recipes/1":
                        raise DesignContractError("Recipe source format is unsupported.")
                    actual = pointer_value(document, module["recipeRefPointer"])
                    if actual != module["recipeRef"]:
                        raise DesignContractError("Recipe reference differs from actual source JSON identity.")
                    recipe = pointer_value(document, module["recipeRefPointer"].rsplit("/", 1)[0])
                    if recipe.get("specRef") != module["specRef"]:
                        raise DesignContractError("Recipe does not target the bound actual module version.")
            except (OSError, ValueError, TypeError, KeyError, IndexError) as error:
                errors.append(issue("design.module_identity", where, str(error)))
        for pointer in module["contentPointers"]:
            try:
                value = pointer_value(content, pointer)
                needed_sources = {module["specSourceKey"], module["recipeSourceKey"]}
                if any(not needed_sources.issubset(leaf_sources.get(leaf, set())) for leaf in _leaf_pointers(value, pointer)):
                    errors.append(issue("design.module_decision_source", where, "Every module-adopted content leaf must be covered by a decision citing its actual spec and recipe sources."))
            except (ValueError, TypeError, KeyError, IndexError) as error:
                errors.append(issue("design.module_pointer", where, str(error)))
        if module["mappingStatus"] != "explicit-content":
            ready = False
    compatibility = contract["compatibility"]
    if compatibility["status"] != "verified":
        ready = False
    for key in compatibility["evidenceKeys"]:
        if key not in bindings:
            errors.append(issue("design.compatibility_source", "$.compatibility", "Compatibility evidence must name a hash-verified source."))
        elif not _check_compatibility_report(contract, bindings[key], errors):
            ready = False
    if compatibility["status"] == "verified" and not compatibility["evidenceKeys"]:
        errors.append(issue("design.compatibility_evidence", "$.compatibility", "Verified compatibility requires exact evidence sources; intent strength is not capability proof."))
    packet_sources = [value for value in bindings.values() if value[0]["role"] == "request-packet"]
    if len(packet_sources) != 1:
        errors.append(issue("design.request_packet", "$.sourceBindings", "Exactly one actual RequestPacket source is required."))
    else:
        from validate_request_packet import validate_request_packet, DEFAULT_SCHEMA as PACKET_SCHEMA
        packet_path = packet_sources[0][1]
        packet = load_json(packet_path)
        validation = validate_request_packet(packet, load_json(PACKET_SCHEMA), packet_path=packet_path)
        errors.extend(validation["errors"])
        # This is also checked by the shared validator during compile. Keep the
        # binding independently verifiable from an in-memory Bundle/View call.
        if packet.get("requestId") != content.get("requestId") or packet.get("inputDigest") != content.get("inputDigest"):
            errors.append(issue("design.packet_identity", "$.content", "Design identity must match the real bound RequestPacket."))
        expected_sources = []
        for item in content.get("sources", []):
            item = copy.deepcopy(item)
            item.pop("id", None)
            if "dimensions" in item:
                item["imageSize"] = item.pop("dimensions")
            expected_sources.append(item)
        if not _equal(expected_sources, packet.get("sources")):
            errors.append(issue("design.packet_sources", "$.content.sources", "Design sources must exactly preserve the bound RequestPacket sources and order."))
        if content.get("request", {}).get("originalText") != packet.get("userRequest", {}).get("originalText"):
            errors.append(issue("design.packet_user_text", "$.content.request", "Design must preserve the original user message exactly."))
    origin = contract["origin"]
    if origin["kind"] == "frozen-accepted-requirement":
        entry = bindings.get(origin.get("sourceKey"))
        if entry is None or entry[0]["role"] != "legacy-origin":
            errors.append(issue("design.legacy_origin", "$.origin", "Frozen designs must retain their real accepted Requirement source."))
        else:
            from validate_requirement_spec import validate_requirement_spec
            legacy = load_json(entry[1])
            valid = validate_requirement_spec(legacy, load_json(REQUIREMENT_SCHEMA))
            if not valid["valid"] or legacy.get("version") != "0.1" or legacy.get("reviewGate", {}).get("status") != "accepted":
                errors.append(issue("design.legacy_origin", "$.origin", "Legacy origin must remain a valid accepted UIRequirementSpec 0.1."))
            # Freeze may only change the truthful provenance policy. All design
            # meaning, review resolutions and execution authorization are copied.
            expected = content_of(legacy)
            expected.setdefault("analysisPolicy", {})["noHistoryRolePacketsRequired"] = False
            if not _equal(expected, content):
                errors.append(issue("design.legacy_projection", "$.content", "Frozen content differs from its real legacy origin; author a new design revision explicitly."))
    elif content.get("reviewResolutions"):
        errors.append(issue("design.legacy_resolutions", "$.content.reviewResolutions", "Authored designs use gapDecisions; legacy review resolutions may only come from their bound original Requirement."))
    if check_semantics and contract_path is not None and not errors:
        from validate_requirement_spec import validate_requirement_spec
        candidate = {"version": "0.2", **copy.deepcopy(content), "normalization": _normalize(contract, contract_path),
                     "reviewGate": _pending_review(content)}
        # The external packet is rehashed above and semantically compared here.
        packet_path = packet_sources[0][1]
        checked = validate_requirement_spec(candidate, load_json(REQUIREMENT_SCHEMA),
            request_packet=load_json(packet_path), request_packet_path=packet_path,
            spec_path=None)
        errors.extend(checked["errors"])
    for claim in content.get("claims", []):
        if claim.get("status") == "unresolved" and (claim.get("impact") == "high" or claim.get("blocksBuild") is True):
            ready = False
    for question in content.get("questions", []):
        if question.get("status") == "open" and (question.get("impact") == "high" or question.get("blocksBuild") is True):
            ready = False
    output = result(errors, warnings)
    output["buildReady"] = not errors and ready
    output["editorMutationAllowed"] = False
    return output


def validate_design_provenance(spec: dict, *, spec_path: Path | None = None) -> list:
    errors = []
    normalization = spec.get("normalization", {})
    try:
        root = Path(normalization["contractRoot"])
        ref = Path(normalization["contractRef"])
        if not root.is_absolute() or ".." in root.parts or ref.is_absolute() or ".." in ref.parts:
            raise DesignContractError("Design contract reference must stay inside its absolute declared contract root.")
        contract_path = (root / ref).resolve(strict=True)
        if not contract_path.is_relative_to(root.resolve(strict=True)):
            raise DesignContractError("Design contract reference escapes its root, including symlinks.")
        contract = load_json(contract_path)
        if normalization != _normalize(contract, contract_path):
            raise DesignContractError("Design provenance no longer matches the exact bound contract file and content.")
        validation = validate_design_contract(contract, contract_path=contract_path, check_semantics=False)
        errors.extend(validation["errors"])
        if not _equal(content_of(spec), contract["content"]):
            errors.append(issue("design.adoption_mismatch", "$", "Requirement semantics must exactly equal authored contract content; re-normalizing after an edit cannot authorize a changed design."))
        if spec.get("reviewGate", {}).get("status") == "accepted" and not validation.get("buildReady"):
            errors.append(issue("design.not_ready", "$.normalization", "Accepted design cannot retain proposed/pending decisions, open gaps, unsupported module mappings or unverified compatibility."))
        review = spec.get("reviewGate", {})
        if review.get("status") == "accepted":
            record = review.get("designReview")
            if not isinstance(record, dict):
                errors.append(issue("design.review_evidence", "$.reviewGate", "Accepted design requires the actual direct-user or delegated review authorization evidence."))
            else:
                receipt_path = _absolute_file(record["receiptPath"])
                receipt = load_json(receipt_path)
                if sha256_file(receipt_path) != record["receiptSha256"]:
                    raise DesignContractError("The independent review receipt changed.")
                receipt_errors = validate_schema_instance(receipt, load_json(REVIEW_SCHEMA))
                errors.extend(receipt_errors)
                if receipt_errors:
                    return errors
                if receipt["scope"] != _review_scope(spec) or receipt["reviewedBy"] != review.get("reviewedBy") or receipt["reviewedAt"] != review.get("reviewedAt"):
                    raise DesignContractError("The independent review receipt does not approve this contract, revision and reviewer record.")
                message_file = _absolute_file(receipt["messagePath"])
                if sha256_file(message_file) != receipt.get("messageSha256") or not message_file.read_text(encoding="utf-8").strip():
                    raise DesignContractError("Design review message is empty or changed.")
        elif review.get("designReview") is not None:
            errors.append(issue("design.pending_review_evidence", "$.reviewGate", "A pending design cannot claim completed review evidence."))
    except (OSError, ValueError, TypeError, KeyError, IndexError) as error:
        errors.append(issue("design.provenance", "$.normalization", str(error)))
    return errors


def _write_new(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def compile_contract(contract_path: Path, output: Path) -> dict:
    contract_path = contract_path.resolve(strict=True)
    contract = load_json(contract_path)
    validation = validate_design_contract(contract, contract_path=contract_path)
    if not validation["valid"]:
        raise DesignContractError(json.dumps(validation, ensure_ascii=False))
    requirement = {"version": "0.2", **copy.deepcopy(contract["content"]),
        "normalization": _normalize(contract, contract_path), "reviewGate": _pending_review(contract["content"])}
    _write_new(output, requirement)
    return {"valid": True, "requirementPath": str(output.resolve()), "reviewStatus": "pending",
        "contentSha256": canonical_sha256(contract["content"]), "buildAllowed": False}


def freeze_requirement(source: Path, request_packet: Path, review_draft: Path | None, output: Path,
                       authority_lock: Path | None = None, allowed_root: Path | None = None,
                       external_gaps: Path | None = None, external_evidence: list[Path] | None = None) -> dict:
    from validate_requirement_spec import validate_requirement_spec
    source, request_packet = source.resolve(strict=True), request_packet.resolve(strict=True)
    requirement = load_json(source)
    if authority_lock is not None or allowed_root is not None:
        if authority_lock is None or allowed_root is None or review_draft is None:
            raise DesignContractError("Historical freeze requires explicit authority lock, trusted root and review draft together.")
        import importlib.util
        helper_path = Path(__file__).resolve().parents[3] / "scripts/revalidate_historical_authority.py"
        loader = importlib.util.spec_from_file_location("_design_historical_authority", helper_path)
        helper = importlib.util.module_from_spec(loader)
        loader.loader.exec_module(helper)
        checked = helper.revalidate(source, request_packet, review_draft, authority_lock, allowed_root)
    else:
        checked = validate_requirement_spec(requirement, load_json(REQUIREMENT_SCHEMA),
            request_packet=load_json(request_packet), request_packet_path=request_packet, spec_path=source,
            check_findings_files=True, review_draft_path=review_draft.resolve(strict=True) if review_draft else None)
    if not checked["valid"] or requirement.get("version") != "0.1" or requirement.get("reviewGate", {}).get("status") != "accepted":
        raise DesignContractError("Freeze requires a complete strict accepted legacy Requirement: " + json.dumps(checked, ensure_ascii=False))
    content = content_of(requirement)
    content.setdefault("analysisPolicy", {})["noHistoryRolePacketsRequired"] = False
    contract = {"kind": "nextgame-ui-design-contract", "version": "1", "contractId": requirement["requestId"] + ".design",
        "origin": {"kind": "frozen-accepted-requirement", "sourceKey": "legacy-origin"},
        "sourceBindings": [
            {"key": "legacy-origin", "role": "legacy-origin", "path": str(source), "sha256": sha256_file(source), "version": "0.1"},
            {"key": "request-packet", "role": "request-packet", "path": str(request_packet), "sha256": sha256_file(request_packet), "version": "0.1"}],
        "moduleRefs": [], "content": content,
        "decisions": [{"pointer": "", "status": "locked", "valueSha256": canonical_sha256(content), "sourceKeys": ["legacy-origin"],
            "reason": "Exact design semantics imported from the real accepted legacy Requirement; new contract review remains pending."}],
        "gapDecisions": [], "compatibility": {"status": "pending", "evidenceKeys": [],
            "notes": ["Legacy design approval is preserved as provenance; assess current mapping compatibility before accepting this new contract."]}}
    if external_gaps is not None:
        gap_path = external_gaps.resolve(strict=True)
        gaps = load_json(gap_path)
        if not isinstance(gaps, list):
            raise DesignContractError("External gap input must be an explicit gapDecisions JSON array.")
        contract["gapDecisions"] = copy.deepcopy(gaps)
        contract["sourceBindings"].append({"key": "external-gaps", "role": "review-evidence",
            "path": str(gap_path), "sha256": sha256_file(gap_path)})
    for index, evidence_path in enumerate(external_evidence or []):
        evidence_path = evidence_path.resolve(strict=True)
        contract["sourceBindings"].append({"key": f"external-evidence-{index + 1}", "role": "review-evidence",
            "path": str(evidence_path), "sha256": sha256_file(evidence_path)})
    # Fail before writing if the legacy semantics do not satisfy current rules.
    validation = validate_design_contract(contract, check_semantics=False)
    if not validation["valid"]:
        raise DesignContractError(json.dumps(validation, ensure_ascii=False))
    # Keep the full strict AND result as evidence without blessing this new
    # contract. No later validator executes paths from this report.
    proof_path = output.with_name(output.stem + ".freeze-validation.json")
    _write_new(proof_path, checked)
    contract["sourceBindings"].append({"key": "freeze-validation", "role": "review-evidence",
        "path": str(proof_path.resolve()), "sha256": sha256_file(proof_path)})
    _write_new(output, contract)
    return {"valid": True, "contractPath": str(output.resolve()), "contentSha256": canonical_sha256(content),
        "reviewStatus": "pending", "buildAllowed": False, "compatibilityStatus": "pending"}


def accept_requirement(source: Path, output: Path, review_message: Path, reviewed_by: str, reviewed_at: str,
                       review_kind: str = "direct-user-message") -> dict:
    from validate_requirement_spec import validate_requirement_spec
    requirement = load_json(source)
    if requirement.get("version") != "0.2" or requirement.get("reviewGate", {}).get("status") != "pending":
        raise DesignContractError("Accept requires a pending compiled design Requirement 0.2.")
    when = datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
    if when.tzinfo is None or not reviewed_by.strip():
        raise DesignContractError("Review requires identity and a timezone-aware timestamp.")
    message_path = _absolute_file(str(review_message.resolve(strict=True)))
    message = message_path.read_text(encoding="utf-8").strip()
    if not message:
        raise DesignContractError("A real explicit user review message is required.")
    checked = validate_requirement_spec(requirement, load_json(REQUIREMENT_SCHEMA), spec_path=source)
    if not checked["valid"]:
        raise DesignContractError(json.dumps(checked, ensure_ascii=False))
    review = requirement["reviewGate"]
    if review_kind not in {"direct-user-message", "delegated-design-review"}:
        raise DesignContractError("Unsupported review kind.")
    receipt = {"kind": "nextgame-ui-design-review-receipt", "version": "1", "reviewKind": review_kind,
        "messagePath": str(message_path), "messageSha256": sha256_file(message_path),
        "scope": _review_scope(requirement), "reviewedBy": reviewed_by, "reviewedAt": reviewed_at,
        "notice": "Design review only; never post-build user acceptance or new production authorization."}
    receipt_path = output.with_name(output.stem + ".design-review.json")
    if output.exists() or receipt_path.exists():
        raise DesignContractError("Accept writes new artifacts only; choose new output paths for a new review event.")
    # Check readiness before writing a receipt. The receipt is created only for
    # a reviewed complete scope, never a pending or unsupported design.
    contract_path = Path(requirement["normalization"]["contractRoot"]) / requirement["normalization"]["contractRef"]
    readiness = validate_design_contract(load_json(contract_path), contract_path=contract_path)
    if not readiness.get("buildReady"):
        raise DesignContractError("Design is not ready for acceptance: " + json.dumps(readiness, ensure_ascii=False))
    _write_new(receipt_path, receipt)
    review.update({"status": "accepted", "reviewedBy": reviewed_by, "reviewedAt": reviewed_at,
        "designReview": {"receiptPath": str(receipt_path.resolve()), "receiptSha256": sha256_file(receipt_path)},
        "notes": ["Review basis: " + review_kind, message]})
    review["approvedContentSha256"] = compute_approved_content_sha256(requirement)
    checked = validate_requirement_spec(requirement, load_json(REQUIREMENT_SCHEMA), spec_path=source)
    if not checked["valid"]:
        raise DesignContractError(json.dumps(checked, ensure_ascii=False))
    _write_new(output, requirement)
    return {"valid": True, "requirementPath": str(output.resolve()), "reviewStatus": "accepted",
        "approvedContentSha256": review["approvedContentSha256"], "editorMutationAllowed": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    freeze = sub.add_parser("freeze")
    freeze.add_argument("requirement", type=Path)
    freeze.add_argument("--request-packet", type=Path, required=True)
    freeze.add_argument("--review-draft", type=Path)
    freeze.add_argument("--authority-lock", type=Path)
    freeze.add_argument("--allow-authority-root", type=Path)
    freeze.add_argument("--external-gaps", type=Path)
    freeze.add_argument("--external-evidence", type=Path, action="append", default=[])
    freeze.add_argument("--output", type=Path, required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("contract", type=Path)
    compile_parser = sub.add_parser("compile")
    compile_parser.add_argument("contract", type=Path)
    compile_parser.add_argument("--output", type=Path, required=True)
    accept = sub.add_parser("accept")
    accept.add_argument("requirement", type=Path)
    accept.add_argument("--output", type=Path, required=True)
    accept.add_argument("--review-message-file", type=Path, required=True)
    accept.add_argument("--reviewed-by", required=True)
    accept.add_argument("--reviewed-at", required=True)
    accept.add_argument("--review-kind", choices=["direct-user-message", "delegated-design-review"], default="direct-user-message")
    args = parser.parse_args()
    try:
        if args.command == "freeze":
            receipt = freeze_requirement(args.requirement, args.request_packet, args.review_draft, args.output,
                args.authority_lock, args.allow_authority_root, args.external_gaps, args.external_evidence)
        elif args.command == "compile":
            receipt = compile_contract(args.contract, args.output)
        elif args.command == "accept":
            receipt = accept_requirement(args.requirement, args.output, args.review_message_file, args.reviewed_by, args.reviewed_at, args.review_kind)
        else:
            receipt = validate_design_contract(load_json(args.contract), contract_path=args.contract.resolve(strict=True))
        print(json.dumps(receipt, ensure_ascii=False))
        return 0 if receipt.get("valid") else 1
    except (OSError, ValueError, TypeError, KeyError, IndexError) as error:
        print(json.dumps({"valid": False, "buildAllowed": False, "error": str(error)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
