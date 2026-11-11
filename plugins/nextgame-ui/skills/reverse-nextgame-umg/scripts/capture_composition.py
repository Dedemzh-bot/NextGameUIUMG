"""Capture raw UMG/NamedSlot composition evidence without modifying Editor assets."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset", action="append", required=True)
    parser.add_argument("--url", required=True, help="Configured official Unreal MCP endpoint")
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Evidence output already exists; choose a new acquisition path")
    adapter_path = Path(__file__).resolve().parents[2] / "refine-nextgame-ui-art/scripts/art_editor.py"
    spec = importlib.util.spec_from_file_location("_nextgame_composition_editor", adapter_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Bundled read-only composition adapter unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    evidence = module.ArtEditor(module.HttpTransport(args.url, args.timeout)).composition_evidence(args.asset)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(evidence, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": "captured-pending-normalization", "assets": len(evidence["assets"]), "output": str(args.out)}))


if __name__ == "__main__":
    main()
