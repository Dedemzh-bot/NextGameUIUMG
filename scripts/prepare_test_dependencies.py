#!/usr/bin/env python3
"""Fetch and verify the separately versioned resource-tool test dependency."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
LOCK = Path(__file__).with_name("test-dependencies.json")


def git(directory: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(directory), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def verify() -> None:
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    target = ROOT / "Tools/UIResourceImport"
    if not (target / ".git").exists():
        raise RuntimeError("Run python scripts/prepare_test_dependencies.py before release validation")
    if git(target, "rev-parse", "HEAD") != lock["commit"]:
        raise RuntimeError("Resource-tool checkout does not match scripts/test-dependencies.json")
    if git(target, "status", "--porcelain", "--untracked-files=no"):
        raise RuntimeError("Resource-tool dependency has modified tracked files")
    for name, expected in lock["files"].items():
        if Path(name).name != name:
            raise RuntimeError("Dependency lock must use direct module names")
        if hashlib.sha256((target / name).read_bytes()).hexdigest() != expected:
            raise RuntimeError("Resource-tool module hash mismatch: " + name)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local-source", type=Path,
                        help="Clone an existing checkout instead of downloading; the same commit and hashes are required")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    target = ROOT / "Tools/UIResourceImport"
    if not args.verify_only and not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        clone_source = str(args.local_source.resolve()) if args.local_source else lock["repository"]
        subprocess.run(["git", "clone", "--no-hardlinks", "--no-checkout", clone_source, str(target)], check=True)
        if not args.local_source:
            subprocess.run(["git", "-C", str(target), "fetch", "origin", lock["commit"]], check=True)
        subprocess.run(["git", "-C", str(target), "checkout", "--detach", lock["commit"]], check=True)
    verify()
    print("Verified pinned NextGameUIResource test dependency: " + lock["commit"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
