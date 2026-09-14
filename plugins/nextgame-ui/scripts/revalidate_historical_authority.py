#!/usr/bin/env python3
"""Revalidate unchanged historical analysis provenance and today's full model.

An explicit, trusted frozen plugin directory is a prerequisite, not a directory
discovered from evidence. The lock is an integrity record, not a signature or a
grant of trust. No packet is relabelled, no validator error is filtered, and no
Unreal, build, acceptance or document action is performed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


PLUGIN_ROOT = Path(__file__).resolve().parent.parent
ANALYSIS = Path("skills/analyze-nextgame-ui-requirements")
VALIDATOR = ANALYSIS / "scripts/validate_requirement_spec.py"
MANIFEST = Path(".codex-plugin/plugin.json")
ROLE_CARDS = ANALYSIS / "assets/analysis-role-cards.json"
LOCK_VERSION = "nextgame-analysis-authority-lock/1"
REPORT_VERSION = "nextgame-analysis-authority-revalidation/1"
ROLES = {
    "visual-structure", "text-requirements", "project-pattern", "state-modeling",
    "data-adaptation", "asset-decomposition", "state-visual-review",
    "schema-feasibility-review", "coverage-review",
}


class AuthorityError(ValueError):
    pass


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=lambda value: (
        _ for _ in ()
    ).throw(AuthorityError(f"Non-finite JSON constant: {value}")))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _regular(path: Path) -> None:
    if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
        raise AuthorityError(f"Linked paths are not accepted for authority: {path}")


def inventory(root: Path) -> dict[str, str]:
    root = root.absolute()
    for part in [root, *root.parents]:
        _regular(part)
    if not root.is_dir():
        raise AuthorityError(f"Missing authority directory: {root}")
    records = {}
    for current, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            _regular(Path(current) / name)
        # Cached bytecode can be executed even with -B (which only disables
        # writes), so it is part of the locked authority rather than excluded.
        dirs[:] = sorted(dirs)
        for name in sorted(files):
            path = Path(current) / name
            records[path.relative_to(root).as_posix()] = digest(path)
    return dict(sorted(records.items()))


def _root(path: Path) -> Path:
    if not path.is_absolute():
        raise AuthorityError("The allowed frozen authority root must be an explicit absolute path.")
    for part in [path, *path.parents]:
        _regular(part)
    resolved = path.resolve(strict=True)
    if resolved.name != "nextgame-ui":
        raise AuthorityError("Choose the exact nextgame-ui plugin directory, not a broad parent root.")
    return resolved


def make_lock(authority_root: Path) -> dict[str, Any]:
    root = _root(authority_root)
    files = inventory(root)
    manifest = load(root / MANIFEST)
    if manifest.get("name") != "nextgame-ui" or not isinstance(manifest.get("version"), str):
        raise AuthorityError("Frozen directory is not an identified NextGame UI plugin.")
    for required in [MANIFEST, ROLE_CARDS, VALIDATOR]:
        if required.as_posix() not in files:
            raise AuthorityError(f"Frozen authority is incomplete: {required}")
    return {
        "version": LOCK_VERSION,
        "authorityRoot": str(root),
        "authority": {
            "pluginVersion": manifest["version"],
            "pluginManifestSha256": files[MANIFEST.as_posix()],
            "roleCardsSha256": files[ROLE_CARDS.as_posix()],
        },
        "files": files,
        "treeSha256": canonical_digest(files),
    }


def check_lock(lock: Any, allowed_root: Path) -> Path:
    root = _root(allowed_root)
    if not isinstance(lock, dict) or set(lock) != {
        "version", "authorityRoot", "authority", "files", "treeSha256"
    } or lock.get("version") != LOCK_VERSION:
        raise AuthorityError("Unknown or malformed frozen authority lock.")
    if not isinstance(lock.get("authorityRoot"), str) or Path(lock["authorityRoot"]).resolve() != root:
        raise AuthorityError("Lock root does not equal the explicit allowed authority root.")
    if lock != make_lock(root):
        raise AuthorityError("Frozen authority content differs from its lock (missing, extra or changed files).")
    return root


def _scoped(root: Path, base: Path, ref: Any) -> Path:
    if not isinstance(ref, str) or Path(ref).is_absolute() or ".." in Path(ref).parts:
        raise AuthorityError("Historical evidence refs must be relative and contain no '..'.")
    path = (base / ref).resolve(strict=True)
    if not path.is_relative_to(root):
        raise AuthorityError("Historical evidence escapes the RequestPacket directory.")
    return path


def input_bindings(spec_path: Path, request_path: Path, draft_path: Path,
                   expected_authority: dict[str, Any]) -> dict[str, str]:
    root = request_path.parent.resolve()
    paths = {spec_path.resolve(strict=True), request_path.resolve(strict=True), draft_path.resolve(strict=True)}
    if any(not path.is_relative_to(root) for path in paths):
        raise AuthorityError("Requirement and immutable review Draft must remain in the request directory.")
    spec = load(spec_path)
    normal = spec.get("normalization", {})
    findings = normal.get("findingsInputs", [])
    if (not isinstance(findings, list) or len(findings) != 9
            or any(not isinstance(item, dict) for item in findings)
            or {item.get("agentRole") for item in findings} != ROLES):
        raise AuthorityError("Exactly nine distinctly identified historical analysis roles are required.")
    paths.add(_scoped(root, spec_path.parent, normal.get("baseContextRef")))
    for item in findings:
        for key in ("findingsRef", "rolePacketRef", "contextRef"):
            if key in item:
                paths.add(_scoped(root, spec_path.parent, item[key]))
        role_path = _scoped(root, spec_path.parent, item.get("rolePacketRef"))
        role = load(role_path)
        if role.get("agentRole") != item.get("agentRole") or role.get("authority") != expected_authority:
            raise AuthorityError("Mixed, relabelled or wrong analysis authority/role is not compatible.")
        if role.get("context"):
            paths.add(_scoped(root, root, role["context"].get("ref")))
        for attachment in role.get("additionalInputs", []):
            paths.add(_scoped(root, root, attachment.get("ref")))
    for source in load(request_path).get("sources", []):
        if source.get("locatorKind") == "local-file":
            paths.add(Path(source["path"]).resolve(strict=True))
        elif source.get("locatorKind") == "unreal-object" and source.get("snapshotPath"):
            paths.add(_scoped(root, root, source["snapshotPath"]))
    return {str(path): digest(path) for path in sorted(paths)}


def _run(plugin: Path, spec: Path, packet: Path, draft: Path, strict: bool) -> dict[str, Any]:
    command = [sys.executable, "-E", "-S", "-B", "-X", "utf8", str(plugin / VALIDATOR),
               str(spec), "--request-packet", str(packet), "--review-draft", str(draft)]
    if strict:
        command.append("--check-findings-files")
    completed = subprocess.run(command, cwd=plugin, capture_output=True, text=True,
                               encoding="utf-8", timeout=180, check=False)
    try:
        validation = json.loads(completed.stdout)
    except ValueError:
        validation = {"valid": False, "errors": [{"code": "authority.validator_output",
                       "message": completed.stdout[:2000]}]}
    valid = (completed.returncode == 0 and isinstance(validation, dict)
             and validation.get("valid") is True and validation.get("errors") == [])
    return {"valid": valid, "mode": "strict-historical-provenance" if strict else "current-full-model",
            "command": command, "exitCode": completed.returncode,
            "validation": validation, "stderr": completed.stderr}


def revalidate(spec_path: Path, request_path: Path, draft_path: Path, lock_path: Path,
               allowed_root: Path, *, current_root: Path = PLUGIN_ROOT) -> dict[str, Any]:
    """AND two complete validators; historical provenance is never skipped."""
    report: dict[str, Any] = {"version": REPORT_VERSION, "valid": False, "errors": [], "warnings": []}
    try:
        spec_path, request_path, draft_path, lock_path = (
            path.resolve(strict=True) for path in (spec_path, request_path, draft_path, lock_path)
        )
        lock_hash = digest(lock_path)
        lock = load(lock_path)
        frozen_root = check_lock(lock, allowed_root)
        current_root = current_root.resolve(strict=True)
        if frozen_root == current_root:
            raise AuthorityError("Use normal strict validation for the current plugin, not compatibility mode.")
        before = input_bindings(spec_path, request_path, draft_path, lock["authority"])
        current_files = inventory(current_root)
        report["bindings"] = {"authorityLockPath": str(lock_path), "authorityLockSha256": lock_hash,
                              "historicalAuthority": lock["authority"], "historicalTreeSha256": lock["treeSha256"],
                              "currentPluginRoot": str(current_root),
                              "currentTreeSha256": canonical_digest(current_files), "inputs": before}
        # Historical scripts validate every findings/context/view/source link. The
        # current process independently validates the ENTIRE model, not a View.
        historical = _run(frozen_root, spec_path, request_path, draft_path, True)
        report["historical"] = historical
        if not historical["valid"]:
            raise AuthorityError("Historical strict provenance validation failed; do not re-author labels.")
        current = _run(current_root, spec_path, request_path, draft_path, False)
        report["current"] = current
        if not current["valid"]:
            raise AuthorityError("The complete Requirement fails current schema/approval/semantic validation.")
        check_lock(lock, allowed_root)
        if digest(lock_path) != lock_hash or inventory(current_root) != current_files:
            raise AuthorityError("An authority changed during revalidation.")
        if input_bindings(spec_path, request_path, draft_path, lock["authority"]) != before:
            raise AuthorityError("An input changed during revalidation.")
        report["valid"] = True
    except (OSError, ValueError, TypeError, KeyError, subprocess.TimeoutExpired) as error:
        report["errors"].append({"code": "authority.revalidation", "path": "$", "message": str(error)})
    return report


def write_new(path: Path, value: Any, forbidden: list[Path]) -> None:
    resolved = path.resolve()
    if any(resolved == item.resolve() or (item.is_dir() and resolved.is_relative_to(item.resolve()))
           for item in forbidden):
        raise AuthorityError("Output cannot replace evidence or be placed inside a plugin authority.")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    with resolved.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    lock_parser = commands.add_parser("lock", help="Bind an explicitly trusted frozen plugin; does not establish trust.")
    lock_parser.add_argument("--allow-authority-root", type=Path, required=True)
    lock_parser.add_argument("--output", type=Path, required=True)
    check = commands.add_parser("validate", help="Deep-check original provenance AND current full Requirement.")
    check.add_argument("spec", type=Path)
    check.add_argument("--request-packet", type=Path, required=True)
    check.add_argument("--review-draft", type=Path, required=True)
    check.add_argument("--authority-lock", type=Path, required=True)
    check.add_argument("--allow-authority-root", type=Path, required=True)
    check.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "lock":
            value = make_lock(args.allow_authority_root)
            write_new(args.output, value, [PLUGIN_ROOT, args.allow_authority_root])
            print(json.dumps({"valid": True, "lock": str(args.output.resolve()),
                              "sha256": digest(args.output), "fileCount": len(value["files"])}))
            return 0
        value = revalidate(args.spec, args.request_packet, args.review_draft, args.authority_lock,
                           args.allow_authority_root)
        if args.output:
            write_new(args.output, value, [PLUGIN_ROOT, args.allow_authority_root,
                                           args.spec, args.request_packet, args.review_draft, args.authority_lock])
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return 0 if value["valid"] else 1
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(json.dumps({"valid": False, "errors": [{"code": "authority.arguments", "message": str(error)}]}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
