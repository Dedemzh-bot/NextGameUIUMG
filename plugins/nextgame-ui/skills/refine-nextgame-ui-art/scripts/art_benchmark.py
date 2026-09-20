#!/usr/bin/env python3
"""Report measured art-workflow runs without executing or selecting any model.

Input contracts are exposed as MANIFEST_SCHEMA and RESULT_SCHEMA. A benchmark
label is supplied by the experiment owner; it is never inferred from price or
model capability. Source quality verdicts are reported, never awarded here.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
from pathlib import Path
import tempfile

from jsonschema import Draft202012Validator

import art_common as common


BINDING = {"type": "object", "additionalProperties": False, "required": ["path", "sha256"],
           "properties": {"path": {"type": "string", "minLength": 1}, "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"}}}
LABEL = {"type": "string", "minLength": 1, "maxLength": 128}
DIGEST = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
SCENARIOS = ("first-production", "local-change", "rerun")
ASSET_KINDS = ("child-widget", "full-screen")


def _object(properties, required=None):
    return {"type": "object", "additionalProperties": False, "properties": properties,
            "required": list(properties) if required is None else required}


CALL_SCHEMA = _object({"stage": LABEL, "agentRole": LABEL, "callIdDigest": DIGEST})
RUN_SCHEMA = _object({"id": LABEL, "sampleId": LABEL, "modelLabel": LABEL, "scenario": {"enum": list(SCENARIOS)},
                     "result": BINDING, "ledger": {"oneOf": [BINDING, {"type": "null"}]},
                     "measurementBoundaryId": LABEL, "runIdDigest": DIGEST,
                     "expectedModelCalls": {"type": "array", "items": CALL_SCHEMA, "maxItems": 10000}})
MANIFEST_SCHEMA = _object({"kind": {"const": "nextgame-ui-art-benchmark-manifest"}, "version": {"const": 1},
    "benchmarkId": LABEL, "synthetic": {"type": "boolean"}, "requireHeldOut": {"type": "boolean"},
    "samples": {"type": "array", "minItems": 1, "items": _object({"id": LABEL,
        "assetKind": {"enum": list(ASSET_KINDS)}, "membership": {"enum": ["reference-library", "held-out"]}, "reference": BINDING})},
    "runs": {"type": "array", "minItems": 1, "items": RUN_SCHEMA}})
RESULT_SCHEMA = _object({"kind": {"const": "nextgame-ui-art-benchmark-result"}, "version": {"const": 1},
    "runId": LABEL, "sampleId": LABEL, "modelLabel": LABEL, "scenario": {"enum": list(SCENARIOS)},
    "synthetic": {"type": "boolean"}, "timingSource": {"const": "measured-run-clock"},
    "startedAt": LABEL, "finishedAt": LABEL, "humanCorrectionSource": {"const": "counted-review-events"},
    "humanCorrections": {"type": "array", "items": _object({"id": LABEL, "timestamp": LABEL})}, "verification": BINDING})


def _validate(value, schema, label):
    errors = sorted(Draft202012Validator(schema).iter_errors(value), key=lambda error: str(list(error.path)))
    if errors:
        raise common.ArtError("benchmark.schema", f"{label} {list(errors[0].path)}: {errors[0].message}")
    common.canonical(value)
    return value


def _bound(record, owner):
    return common.bound_path({key: record[key] for key in ("path", "sha256")}, owner)


def _read(record, owner):
    path = _bound(record, owner)
    return path, common.load_json(path)


def _telemetry():
    path = common.PLUGIN_ROOT / "scripts" / "token_telemetry.py"
    spec = importlib.util.spec_from_file_location("_nextgame_art_benchmark_telemetry", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _time(value):
    return common.aware_time(value)


def _quality(record, owner, *, synthetic, sample):
    path, verification = _read(record, owner)
    common.validate(verification, "verification")
    snapshot_path, snapshot = _read(verification["snapshot"], path)
    common.validate(snapshot, "snapshot")
    fixture = snapshot["acquisition"]["method"] == "fixture"
    if fixture and not synthetic:
        raise common.ArtError("benchmark.fixture", "Fixture verification cannot become a measured production result.")
    plan_path, plan = _read(verification["plan"], path)
    common.validate(plan, "plan")
    execution_path, execution = _read(verification["execution"], path)
    common.validate(execution, "execution")
    if (execution["status"] != "completed" or execution["planSha256"] != common.sha256(plan_path)
            or _bound(execution["readback"], execution_path) != snapshot_path
            or execution["completedIds"] != [operation["id"] for operation in plan["operations"]]
            or execution["currentOperation"] is not None or execution["expectedStateSha256"] != plan["expectedStateSha256"]
            or common.state_hash(snapshot) != plan["expectedStateSha256"]):
        raise common.ArtError("benchmark.execution", "Verification is not backed by a matching completed actual-state execution.")
    request_path, request = _read(plan["request"], plan_path)
    _bound(plan["decisions"], plan_path)
    for source in request.get("baseline", {}).values():
        _bound(source, request_path)
    for source in request.get("target", {}).values():
        _bound(source, request_path)
    if not synthetic:
        common.validate(request, "request")
        source = request.get("target", request["baseline"])
        _, bundle = _read(source["bundle"], request_path)
        asset_kinds = {asset["assetPath"]: asset.get("assetKind") for asset in bundle["assets"]}
        reference_kinds = {asset_kinds.get(reference["assetPath"]) for reference in request["references"]
                           if reference["image"]["sha256"] == sample["reference"]["sha256"]}
        required_kind = "screen" if sample["assetKind"] == "full-screen" else "child-widget"
        if required_kind not in reference_kinds:
            raise common.ArtError("benchmark.asset_kind", "Declared benchmark asset kind must match the bound design Bundle.")
    review_path, review = _read(verification["visualReview"], path)
    common.validate(review, "visualReview")
    if review["snapshotSha256"] != common.sha256(snapshot_path):
        raise common.ArtError("benchmark.review", "Visual review is bound to a different snapshot.")
    if {common.digest(item) for item in review["comparisons"]} != {common.digest(item) for item in verification["comparisons"]}:
        raise common.ArtError("benchmark.review", "Visual review comparison coverage differs from verification.")
    metrics, seen_sample = [], False
    for item in verification["comparisons"]:
        comparison_path, comparison = _read(item, path)
        for name in ("reference", "actual", "overlay", "diff"):
            if comparison.get(name) is not None:
                _bound(comparison[name], comparison_path)
        if comparison.get("capture") is not None:
            capture_path, capture = _read(comparison["capture"], comparison_path)
            _bound(capture["image"], capture_path)
            if capture.get("snapshotSha256") != common.sha256(snapshot_path):
                raise common.ArtError("benchmark.capture", "Compared capture does not bind the actual snapshot.")
        seen_sample |= comparison.get("reference", {}).get("sha256") == sample["reference"]["sha256"]
        value = comparison.get("mae")
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 255):
            raise common.ArtError("benchmark.metric", "Comparison MAE must be measured in the supported 0..255 range.")
        metrics.append({"referenceId": comparison.get("referenceId"), "mae": value, "dimensionAgreement": comparison.get("dimensionAgreement")})
    if not seen_sample:
        raise common.ArtError("benchmark.sample", "Verification does not compare the declared sample reference.")
    # Production 'passed' results must pass the same complete, current source
    # gate as the final Bundle. Synthetic fixtures can exercise reporting only.
    production_validated = False
    if not synthetic and verification["status"] == "passed":
        requirement_path = _bound(request.get("target", request["baseline"])["requirement"], request_path)
        stage = {"goal": request["goal"], "request": common.binding(request_path), "plan": common.binding(plan_path), "verification": common.binding(path)}
        errors = common.validate_art_stage(stage, bundle_path=path, requirement=common.load_json(requirement_path), requirement_path=requirement_path)
        if errors:
            raise common.ArtError("benchmark.quality", str(errors))
        production_validated = True
    return {"sourceStatus": verification["status"], "verifiedAt": verification["verifiedAt"], "productionValidated": production_validated,
            "evidenceType": "synthetic-fixture" if synthetic else "bound-art-verification", "comparisons": metrics,
            "verification": common.binding(path), "acceptance": "not-awarded-by-benchmark"}


def _tokens(run, owner, telemetry, start, finish):
    fields = telemetry.TOKEN_FIELDS
    unavailable = {"status": "unavailable", "modelCallCount": None, "metrics": {field: None for field in fields},
                   "metricStatus": {field: "unavailable" for field in fields}, "providerModels": []}
    if run["ledger"] is None:
        return unavailable
    ledger_path = _bound(run["ledger"], owner)
    ledger = telemetry.load_ledger(ledger_path)
    events = ledger["events"]
    if any(event["eventKind"] == telemetry.LEGACY_UNCLASSIFIED for event in events):
        raise common.ArtError("benchmark.legacy", "Unclassified legacy telemetry cannot substantiate model measurements.")
    selected = [event for event in events if event["eventKind"] == telemetry.MODEL_CALL
                and event["measurementBoundaryId"] == run["measurementBoundaryId"] and event["runIdDigest"] == run["runIdDigest"]]
    if any(event["tokenSource"] != telemetry.PROVIDER_RECEIPT for event in selected):
        raise common.ArtError("benchmark.estimated_tokens", "Tokenizer proxies and estimated tokens are unsupported in measured benchmarks.")
    if any(not start <= _time(event["timestamp"]) <= finish for event in selected):
        raise common.ArtError("benchmark.token_time", "Token receipt timestamp is outside the measured run interval.")
    expected = [(item["stage"], item["agentRole"], item["callIdDigest"]) for item in run["expectedModelCalls"]]
    if not expected:
        if selected:
            raise common.ArtError("benchmark.call_boundary", "A declared zero-call run contains model receipts.")
        return {**unavailable, "status": "no-model-calls-recorded", "modelCallCount": 0,
                "metricStatus": {field: "not-applicable" for field in fields}}
    audit = telemetry.check_measurement_boundary(events, measurement_boundary_id=run["measurementBoundaryId"],
        run_id_digest=run["runIdDigest"], expected_model_calls=expected)
    if audit["unexpectedCallCount"]:
        raise common.ArtError("benchmark.call_boundary", "Ledger contains unaccounted calls within this measurement boundary.")
    if audit["missingCallCount"]:
        return {**unavailable, "reason": "missing-provider-receipts", "observedModelCallCount": len(selected), "expectedModelCallCount": len(expected)}
    summary = telemetry.summarize_events(selected)
    metrics, statuses = {}, {}
    for field in fields:
        coverage = summary["tokenMeasurement"][field]
        if coverage["unmeasuredCallCount"]:
            metrics[field], statuses[field] = None, "unavailable"
        elif coverage["applicableCallCount"] == 0:
            metrics[field], statuses[field] = None, "not-applicable"
        else:
            metrics[field], statuses[field] = summary["totals"][field], "measured"
    return {"status": "measured" if audit["complete"] else "partially-measured", "modelCallCount": len(selected),
            "metrics": metrics, "metricStatus": statuses,
            "providerModels": sorted({event["provider"] + "/" + event["model"] for event in selected})}


def build_report(manifest_path: Path) -> dict:
    """Read current bound evidence and build a deterministic comparison report."""
    manifest_path = Path(manifest_path).resolve()
    manifest = _validate(common.load_json(manifest_path), MANIFEST_SCHEMA, "manifest")
    samples = {}
    for sample in manifest["samples"]:
        if sample["id"] in samples:
            raise common.ArtError("benchmark.duplicate_sample", "Sample IDs must be unique.")
        _bound(sample["reference"], manifest_path)
        samples[sample["id"]] = sample
    reference_hashes = {sample["reference"]["sha256"] for sample in samples.values() if sample["membership"] == "reference-library"}
    if any(sample["reference"]["sha256"] in reference_hashes for sample in samples.values() if sample["membership"] == "held-out"):
        raise common.ArtError("benchmark.held_out_overlap", "A reference-library image cannot also be declared held-out.")
    telemetry, rows, run_ids, boundaries = _telemetry(), [], set(), set()
    for run in manifest["runs"]:
        if run["id"] in run_ids or run["sampleId"] not in samples:
            raise common.ArtError("benchmark.run_identity", "Run IDs must be unique and sample IDs must resolve.")
        run_ids.add(run["id"])
        boundary = (run["measurementBoundaryId"], run["runIdDigest"])
        if boundary in boundaries:
            raise common.ArtError("benchmark.reused_boundary", "Distinct benchmark runs must not reuse a telemetry run boundary.")
        boundaries.add(boundary)
        result_path, result = _read(run["result"], manifest_path)
        _validate(result, RESULT_SCHEMA, "result")
        for field, expected in (("runId", run["id"]), ("sampleId", run["sampleId"]), ("modelLabel", run["modelLabel"]),
                                ("scenario", run["scenario"]), ("synthetic", manifest["synthetic"])):
            if result[field] != expected:
                raise common.ArtError("benchmark.result_identity", f"Bound result {field} disagrees with manifest.")
        start, finish = _time(result["startedAt"]), _time(result["finishedAt"])
        if finish < start:
            raise common.ArtError("benchmark.time", "Measured run finish precedes its start.")
        corrections = result["humanCorrections"]
        if len({event["id"] for event in corrections}) != len(corrections):
            raise common.ArtError("benchmark.corrections", "Human correction event IDs must be unique.")
        if any(not start <= _time(event["timestamp"]) <= finish for event in corrections):
            raise common.ArtError("benchmark.corrections", "Human correction event is outside the measured run.")
        sample = samples[run["sampleId"]]
        quality = _quality(result["verification"], result_path, synthetic=manifest["synthetic"], sample=sample)
        rows.append({"runId": run["id"], "modelLabel": run["modelLabel"], "scenario": run["scenario"], "sampleId": sample["id"],
            "assetKind": sample["assetKind"], "membership": sample["membership"], "synthetic": manifest["synthetic"],
            "elapsedSeconds": round((finish - start).total_seconds(), 6), "humanCorrections": len(corrections),
            "tokens": _tokens(run, manifest_path, telemetry, start, finish), "quality": quality,
            "result": common.binding(result_path), "ledger": run["ledger"]})
    coverage = []
    for label in sorted({row["modelLabel"] for row in rows}):
        model_rows = [row for row in rows if row["modelLabel"] == label]
        held_out = {row["assetKind"] for row in model_rows if row["membership"] == "held-out"}
        missing = sorted(set(ASSET_KINDS) - held_out)
        coverage.append({"modelLabel": label, "heldOutRequired": manifest["requireHeldOut"], "coveredHeldOutKinds": sorted(held_out),
                         "missingHeldOutKinds": missing, "heldOutCoverageComplete": not missing,
                         "observedScenarios": sorted({row["scenario"] for row in model_rows}),
                         "missingScenarios": sorted(set(SCENARIOS) - {row["scenario"] for row in model_rows})})
    return {"kind": "nextgame-ui-art-benchmark-report", "version": 1, "benchmarkId": manifest["benchmarkId"],
            "synthetic": manifest["synthetic"], "manifest": common.binding(manifest_path), "rows": rows, "coverage": coverage,
            "heldOutRequirementSatisfied": not manifest["requireHeldOut"] or all(item["heldOutCoverageComplete"] for item in coverage),
            "qualityAcceptance": "not-awarded-by-benchmark", "ranking": "not-computed",
            "tokenAccounting": "Only complete provider-receipt measurements are summed per metric. Missing and non-applicable values remain null; token subcategories are not added together."}


def render_markdown(report: dict) -> str:
    def label(value):
        return str(value).replace("\\", "\\\\").replace("|", "\\|").replace("\r", " ").replace("\n", " ")
    def metric(row, field):
        value = row["tokens"]["metrics"][field]
        return "unavailable" if value is None else str(value)
    lines = ["# NextGame UI art benchmark", "", "**SYNTHETIC FIXTURES — not production performance.**" if report["synthetic"] else "Measured runs from bound evidence; no automatic quality acceptance or model ranking.", "",
             "| Model label | Scenario | Sample / membership | Seconds | Human corrections | Input tokens | Output tokens | Source quality |",
             "|---|---|---|---:|---:|---:|---:|---|"]
    for row in report["rows"]:
        lines.append("| " + " | ".join((label(row["modelLabel"]), row["scenario"], label(row["sampleId"]) + " / " + row["membership"],
            str(row["elapsedSeconds"]), str(row["humanCorrections"]), metric(row, "inputTokens"), metric(row, "outputTokens"),
            row["quality"]["sourceStatus"] + (" (synthetic)" if row["synthetic"] else ""))) + " |")
    lines += ["", "Held-out requirement satisfied: " + str(report["heldOutRequirementSatisfied"]).lower() + "."]
    for entry in report["coverage"]:
        lines.append("- " + label(entry["modelLabel"]) + ": missing held-out kinds: " + (", ".join(entry["missingHeldOutKinds"]) or "none")
                     + "; missing scenarios: " + (", ".join(entry["missingScenarios"]) or "none") + ".")
    lines += ["", "Unavailable tokens are not measured zero. Compare matching samples and scenarios; input/output and their cached, reasoning or vision subcategories are not added into an invented total.", ""]
    return "\n".join(lines)


def write_report(manifest_path: Path, output_dir: Path) -> dict:
    output_dir = Path(output_dir).resolve()
    if output_dir.is_relative_to(common.PLUGIN_ROOT):
        raise common.ArtError("output.plugin", "Benchmark reports must be outside the plugin package.")
    report = build_report(manifest_path)
    json_path, markdown_path = output_dir / "art-benchmark.json", output_dir / "art-benchmark.md"
    markdown = render_markdown(report)
    if markdown_path.exists() and markdown_path.read_text(encoding="utf-8") != markdown:
        raise common.ArtError("output.immutable", "Choose a new benchmark output revision.")
    common.write_json(json_path, report)
    if not markdown_path.exists():
        fd, temporary = tempfile.mkstemp(prefix=".art-benchmark.", dir=output_dir)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(markdown)
            os.replace(temporary, markdown_path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return {"report": common.binding(json_path), "markdown": common.binding(markdown_path),
            "runCount": len(report["rows"]), "synthetic": report["synthetic"],
            "heldOutRequirementSatisfied": report["heldOutRequirementSatisfied"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(write_report(args.manifest, args.output_dir), ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({"status": "blocked", "code": getattr(error, "code", "benchmark.invalid"), "message": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
