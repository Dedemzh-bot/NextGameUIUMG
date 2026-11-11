"""Shared strict inherited-provider coverage for Bundle and coverage gates."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from _contract_common import issue, resolve_contract_path


def _inherited_provider_coverage(bundle, requirement, bundle_path, accepted_claims, errors):
    """Map a proven inherited sizing policy, never invent a WidgetTree node.

    Only this explicit capability can cover an asset-local full-canvas region
    through an actual, hash-bound parent provider chain. Ordinary visual and
    interactive elements still require their own node mappings.
    """
    refs, regions = set(), set()
    capability = "existing-asset-layout-update/2"
    if capability not in bundle.get("capabilities", []) or bundle_path is None:
        return refs, regions
    build_scripts = Path(__file__).resolve().parents[2] / "build-nextgame-umg/scripts"
    if str(build_scripts) not in sys.path:
        sys.path.append(str(build_scripts))
    from existing_asset_update_v2 import validate_bundle_layout_v2, _baseline
    elements = {e["id"]: e for e in requirement.get("uiModel", {}).get("elements", [])}
    region_index = {r["id"]: r for r in requirement.get("uiModel", {}).get("regions", [])}
    plans = {p["id"]: p for p in requirement.get("assetPlan", [])}
    for asset in bundle.get("assets", []):
        if not asset.get("layoutSpecPath"):
            continue
        path = resolve_contract_path(bundle_path, asset["layoutSpecPath"])
        try:
            payload = path.read_bytes()
            layout = json.loads(payload.decode("utf-8-sig"))
            if layout.get("version") != "0.4" or layout.get("capability") != capability:
                continue
            sizing = layout.get("profile", {}).get("providerSizing", {})
            if not sizing or sizing.get("rootSizingNodeId") is not None:
                continue
            if hashlib.sha256(payload).hexdigest() != asset.get("layoutSpecSha256"):
                raise ValueError("Inherited provider layout hash differs from Bundle")
            local_errors = validate_bundle_layout_v2(layout, asset, bundle, requirement, spec_path=path, accepted_claim_ids=accepted_claims)
            if local_errors:
                errors.extend(local_errors)
                continue
            _, actual_asset, _ = _baseline(layout, path)
            ref = sizing["acceptedRequirementRef"]
            element = elements[ref]
            properties = element.get("properties", {})
            if element.get("kind") != "other" or properties.get("sourceParentClassPath") != actual_asset["parentClassPath"]:
                raise ValueError("Asset-level provider policy must be nonvisual and bind its actual parent class")
            plan = plans[asset["assetPlanId"]]
            region_id = element.get("regionId")
            region = region_index.get(region_id, {})
            if region_id not in plan.get("coversRegionIds", []) or region.get("bounds") != [0, 0, 1, 1]:
                raise ValueError("Inherited provider policy only covers its own full reference canvas")
            if region.get("inBuildScope") is not True or not set(region.get("claimIds", [])) & accepted_claims:
                raise ValueError("Inherited provider region is not explicitly accepted and in scope")
            if sum(region_id in p.get("coversRegionIds", []) for p in plans.values()) != 1:
                raise ValueError("Inherited provider region must have a unique asset owner")
            refs.update((ref, region_id))
            regions.add(region_id)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append(issue("coverage.inherited_provider", "$.assets", str(exc)))
    return refs, regions

